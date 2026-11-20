const element = (id) => document.getElementById(id);
const status = element("status");
const timer = element("timer");
const start = element("start");
const extend = element("extend");
const stop = element("stop");
const videos = [element("view-0"), element("view-1")];
const feedback = [element("feedback-0"), element("feedback-1")];
const key = document.querySelector('meta[name="cococam-key"]').content;
const layout = document.body.dataset.layout;
const embedded = layout !== "panel";
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
let players = [];
let activeDocument = true;
let panelVisible = !("IntersectionObserver" in window);
let startPending = false;

function startRequested() {
  if (startPending && !document.hidden && socket?.readyState === WebSocket.OPEN) {
    startPending = false;
    send("start");
  }
}

function unloadVideo() {
  for (const player of players) player.destroy();
  players = [];
  videos.forEach((video, lane) => {
    if (video.hasAttribute("src") || video.hasAttribute("data-playing")) {
      video.pause();
      video.onerror = null;
      video.removeAttribute("src");
      video.removeAttribute("data-playing");
      video.load();
    }
    feedback[lane].textContent = "";
  });
  generation = undefined;
}

function play(next) {
  if (generation === next) return;
  unloadVideo();
  generation = next;
  videos.forEach((video, lane) => {
    if (embedded && layout !== "both" && layout !== String(lane + 1)) return;
    const source = `./media/${next}/${lane}/index.m3u8`;
    const display = () => {
      if (generation !== next) return;
      video.setAttribute("data-playing", "");
      video.play().catch(() => {
        if (generation === next) feedback[lane].textContent = "Appuyez sur lecture.";
      });
    };
    const incompatible = () => {
      if (generation === next) feedback[lane].textContent = "Lecture HEVC indisponible dans ce navigateur.";
    };
    if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.onerror = incompatible;
      video.src = source;
      display();
    } else if (window.Hls?.isSupported()) {
      const player = new window.Hls({lowLatencyMode: false});
      players.push(player);
      player.on(window.Hls.Events.ERROR, (_event, details) => {
        if (details.fatal) incompatible();
      });
      player.on(window.Hls.Events.MANIFEST_PARSED, display);
      player.attachMedia(video);
      player.loadSource(source);
    } else {
      incompatible();
    }
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
