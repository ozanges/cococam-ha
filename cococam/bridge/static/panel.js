const element = (id) => document.getElementById(id);
const status = element("status");
const battery = element("battery");
const timer = element("timer");
const start = element("start");
const extend = element("extend");
const stop = element("stop");
const videos = [element("view-0"), element("view-1")];
const feedback = [element("feedback-0"), element("feedback-1")];
const key = document.querySelector('meta[name="cococam-key"]').content;
const layout = document.body.dataset.layout;
const embedded = layout !== "panel";
const VIDEO_RETRY_DELAYS = [750, 1500, 3000];
const CODEC_ERRORS = new Set(["manifestIncompatibleCodecsError", "bufferIncompatibleCodecsError"]);
const errors = {
  credentials: "Renseignez le compte CloudEdge dans la configuration de l’application.",
  login: "Connexion CloudEdge refusée ou indisponible.",
  camera_selection: "Indiquez le nom exact de la COCOCAM dans la configuration.",
  stream: "La caméra n’a pas fourni les deux vues.",
  worker: "Le module vidéo a rencontré une erreur.",
  disconnected: "La caméra a fermé la session.",
};
let socket;
let reconnect;
let generation;
let videoCleanups = [];
let activeDocument = true;
let panelVisible = !("IntersectionObserver" in window);
let startPending = false;

async function refreshBattery() {
  if (document.hidden) return;
  try {
    const response = await fetch("./api/battery");
    if (!response.ok) return;
    const data = await response.json();
    if (data === null) return;
    const time = new Date(data.observed_at).toLocaleString("fr-FR");
    battery.textContent = `Batterie · ${data.percent} %${data.charging ? " · En charge" : ""} · ${time}`;
    battery.hidden = false;
  } catch {
    // Keep the last reading during short Ingress outages.
  }
}

function startRequested() {
  if (startPending && !document.hidden && socket?.readyState === WebSocket.OPEN) {
    startPending = false;
    send("start");
  }
}

function unloadVideo() {
  for (const cleanup of videoCleanups) cleanup();
  videoCleanups = [];
  generation = undefined;
}

function playLane(video, lane, next) {
  const message = feedback[lane];
  const source = `./media/${next}/${lane}/index.m3u8`;
  const native = video.canPlayType("application/vnd.apple.mpegurl");
  const Hls = window.Hls;
  let player;
  let retry;
  let attempts = 0;
  let closed = false;

  function resetPlayer() {
    video.onerror = null;
    const previous = player;
    player = undefined;
    previous?.destroy();
    if (video.hasAttribute("src") || video.hasAttribute("data-playing")) {
      video.pause();
      video.removeAttribute("src");
      video.removeAttribute("data-playing");
      video.load();
    }
  }

  function playing() {
    if (!closed && retry === undefined) message.textContent = "";
  }

  function display() {
    video.setAttribute("data-playing", "");
    video.play().catch((error) => {
      if (!closed && retry === undefined && error.name === "NotAllowedError") {
        message.textContent = "Appuyez sur lecture.";
      }
    });
  }

  function loadFailed(details) {
    if (closed || retry !== undefined) return;
    if (CODEC_ERRORS.has(details?.details)) {
      message.textContent = "Lecture HEVC indisponible dans ce navigateur.";
      return;
    }
    if ([401, 403].includes(details?.response?.code)) {
      message.textContent = "Accès à la vidéo refusé. Rechargez la page.";
      return;
    }
    if (attempts >= VIDEO_RETRY_DELAYS.length) {
      message.textContent = "Le flux vidéo n’a pas pu être chargé.";
      return;
    }
    message.textContent = "Nouvelle tentative de lecture…";
    retry = setTimeout(() => {
      retry = undefined;
      resetPlayer();
      load();
    }, VIDEO_RETRY_DELAYS[attempts++]);
  }

  function load() {
    if (native) {
      video.onerror = () => loadFailed();
      video.src = source;
      display();
    } else if (Hls?.isSupported()) {
      const current = new Hls({lowLatencyMode: false});
      player = current;
      current.on(Hls.Events.ERROR, (_event, details) => {
        if (current === player && details.fatal) loadFailed(details);
      });
      current.on(Hls.Events.MANIFEST_PARSED, () => {
        if (current === player && retry === undefined) display();
      });
      current.attachMedia(video);
      current.loadSource(source);
    } else {
      message.textContent = Hls ? "Lecture HEVC indisponible dans ce navigateur." : "Le lecteur vidéo n’a pas chargé.";
    }
  }

  message.textContent = "Préparation de la vidéo…";
  video.addEventListener("playing", playing);
  load();
  return () => {
    closed = true;
    clearTimeout(retry);
    video.removeEventListener("playing", playing);
    resetPlayer();
    message.textContent = "";
  };
}

function play(next) {
  if (generation === next) return;
  unloadVideo();
  generation = next;
  videos.forEach((video, lane) => {
    if (embedded && layout !== "both" && layout !== String(lane + 1)) return;
    videoCleanups.push(playLane(video, lane, next));
  });
}

function render(state) {
  const live = state.phase === "live";
  start.hidden = !state.configured || live || state.phase === "opening";
  start.disabled = state.stopping;
  start.textContent = state.phase === "idle" ? "Ouvrir le direct" : "Rouvrir le direct";
  extend.hidden = timer.hidden = !live;
  stop.hidden = !live && state.phase !== "opening";
  if (!state.configured) status.textContent = errors.credentials;
  else if (state.stopping) status.textContent = "Arrêt de la caméra…";
  else if (state.phase === "opening") status.textContent = "Réveil de la caméra…";
  else if (state.phase === "live") status.textContent = "En direct";
  else if (state.phase === "paused" && state.reason === "startup_timeout") status.textContent = "Le réveil de la caméra a expiré.";
  else if (state.phase === "paused") status.textContent = state.reason === "timeout" ? "Temps écoulé." : "Direct coupé.";
  else if (state.phase === "failed") status.textContent = errors[state.reason] ?? errors.worker;
  else status.textContent = "Caméra au repos.";
  if (live) {
    timer.value = `${state.remaining} s`;
    extend.textContent = `Prolonger (${state.live_seconds} s)`;
    play(state.generation);
  } else {
    unloadVideo();
  }
}

function send(command) {
  if (socket?.readyState === WebSocket.OPEN) socket.send(command);
}

function connect() {
  if (!activeDocument || !panelVisible || document.hidden || socket) return;
  const url = new URL("./api/events", location.href);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("key", key);
  const current = new WebSocket(url);
  socket = current;
  current.onmessage = (event) => {
    if (socket === current) render(JSON.parse(event.data));
  };
  current.onopen = () => {
    if (socket !== current) return;
    if (embedded) startRequested();
    else send("open");
  };
  current.onclose = () => {
    if (socket !== current) return;
    close();
    status.textContent = "Connexion à la passerelle…";
    if (activeDocument && !document.hidden) reconnect = setTimeout(connect, 2500);
  };
}

function close() {
  clearTimeout(reconnect);
  const current = socket;
  socket = undefined;
  current?.close();
  unloadVideo();
  for (const control of [start, stop, extend, timer]) control.hidden = true;
}

start.addEventListener("click", () => send("start"));
extend.addEventListener("click", () => send("extend"));
stop.addEventListener("click", () => send("stop"));
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    startPending = false;
    close();
  } else {
    connect();
  }
});
window.addEventListener("pagehide", () => {
  activeDocument = false;
  startPending = false;
  close();
});
window.addEventListener("pageshow", () => { activeDocument = true; connect(); });
if ("IntersectionObserver" in window) {
  const observer = new IntersectionObserver(([entry]) => {
    panelVisible = entry.isIntersecting && entry.intersectionRatio > 0;
    if (panelVisible) connect();
    else close();
  });
  observer.observe(document.querySelector("main"));
}
if (embedded && window.parent !== window) {
  window.addEventListener("message", (event) => {
    if (event.source !== window.parent || event.origin !== location.origin) return;
    if (event.data?.type === "cococam/start") {
      startPending = true;
      startRequested();
    }
  });
  const observer = new ResizeObserver(([entry]) => {
    window.parent.postMessage({
      type: "cococam/resize", height: Math.ceil(entry.target.getBoundingClientRect().height),
    }, location.origin);
  });
  observer.observe(document.querySelector("main"));
  window.parent.postMessage({type: "cococam/ready"}, location.origin);
}
connect();
refreshBattery();
setInterval(refreshBattery, 60000);
