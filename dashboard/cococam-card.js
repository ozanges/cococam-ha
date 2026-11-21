const VIEWS = [
  ["1", "Vue 1"],
  ["2", "Vue 2"],
  ["both", "Les deux vues"],
];
const DEFAULT_CONFIG = {type: "custom:cococam-card", slug: "ae189e14_cococam", view: "1"};

function setIngressCookie(session) {
  if (!/^[A-Za-z0-9_-]+$/.test(session ?? "")) throw new Error("Session Ingress invalide");
  const secure = location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `ingress_session=${session}; Path=/api/hassio_ingress/; SameSite=Strict${secure}`;
}

function ingressUrl(path) {
  const url = new URL(path, location.origin);
  if (url.origin !== location.origin || !/^\/api\/hassio_ingress\/[A-Za-z0-9_-]+\/?$/.test(url.pathname)) {
    throw new Error("URL Ingress invalide");
  }
  if (!url.pathname.endsWith("/")) url.pathname += "/";
  return url;
}

class CococamCard extends HTMLElement {
  constructor() {
    super();
    const root = this.attachShadow({mode: "open"});
    root.innerHTML = `
      <style>
        .launcher { display: flex; align-items: center; justify-content: space-between;
                    flex-wrap: wrap; gap: 8px; padding: 0 16px 16px; }
        .launcher[hidden] { display: none; }
        .hint { color: var(--secondary-text-color); margin: 0; }
        .battery { color: var(--secondary-text-color); margin: 4px 0 0; font-size: .85em; }
        button { cursor: pointer; font: inherit; font-weight: 600; min-height: 40px;
                 padding: 6px 14px; border: 0; border-radius: 20px;
                 background: var(--primary-color); color: var(--text-primary-color, white); }
        button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 3px; }
        button:disabled { opacity: .55; cursor: default; }
        iframe { display: block; width: 100%; border: 0; }
      </style>
      <ha-card header="COCOCAM">
        <div class="launcher">
          <div><p class="hint" role="status"></p><p class="battery" hidden></p></div>
          <button type="button">Voir le direct</button>
        </div>
      </ha-card>`;
    this.launcher = root.querySelector(".launcher");
    this.hint = root.querySelector(".hint");
    this.battery = root.querySelector(".battery");
    this.button = root.querySelector("button");
    this.button.addEventListener("click", () => this.open());
    this.onMessage = this.onMessage.bind(this);
  }

  static getStubConfig() { return {...DEFAULT_CONFIG}; }

  static getConfigElement() { return document.createElement("cococam-card-editor"); }

  getCardSize() { return 3; }

  getGridOptions() { return {columns: 12, min_columns: 6}; }

  setConfig(config) {
    const next = {...DEFAULT_CONFIG, ...config};
    if (typeof next.slug !== "string" || !/^[a-z0-9][a-z0-9_-]*$/.test(next.slug)) {
      throw new Error("Identifiant de l’application COCOCAM invalide");
    }
    const view = VIEWS.find(([value]) => value === next.view);
    if (!view) throw new Error("Choisis la vue 1, la vue 2 ou les deux vues");
    if (this.config?.slug === next.slug && this.config.view === next.view) return;
    this.config = next;
    this.viewLabel = view[1];
    this.close();
    this.battery.hidden = true;
    this.refreshBattery();
  }

  set hass(value) {
    const first = !this._hass;
    this._hass = value;
    if (first) this.refreshBattery();
  }

  get hass() { return this._hass; }

  connectedCallback() {
    window.addEventListener("message", this.onMessage);
    this.refreshBattery();
    this.batteryRefresh = setInterval(() => this.refreshBattery(), 60000);
  }

  disconnectedCallback() {
    window.removeEventListener("message", this.onMessage);
    clearInterval(this.batteryRefresh);
    this.close();
  }

  close(message = this.viewLabel ?? "") {
    clearTimeout(this.openingTimeout);
    clearInterval(this.sessionRefresh);
    this.frame?.remove();
    this.frame = undefined;
    this.opening = undefined;
    this.launcher.hidden = false;
    this.button.disabled = false;
    this.hint.textContent = message;
  }

  async createSession(slug) {
    const result = await this.hass.callWS({type: "supervisor/ingress/session", slug});
    return result.session;
  }

  async refreshBattery() {
    if (!this.isConnected || !this.hass || !this.config || this.batteryPending ||
        this.frame || this.opening || document.hidden) return;
    const {slug} = this.config;
    const active = () => this.isConnected && this.config?.slug === slug;
    this.batteryPending = true;
    try {
      const info = await this.hass.callWS({type: "supervisor/ingress/info", slug});
      if (!active() || info.state !== "started" || !info.ingress_url) return;
      const url = new URL("./api/battery", ingressUrl(info.ingress_url));
      let response = await fetch(url);
      if ([401, 403].includes(response.status) && active() && !this.frame && !this.opening) {
        const session = await this.createSession(slug);
        if (!active() || this.frame || this.opening) return;
        setIngressCookie(session);
        response = await fetch(url);
      }
      if (!response.ok) return;
      const data = await response.json();
      if (!active() || data === null) return;
      this.battery.textContent = `Batterie · ${data.percent} %${data.charging ? " · En charge" : ""}`;
      this.battery.title = `Dernière lecture · ${new Date(data.observed_at).toLocaleString("fr-FR")}`;
      this.battery.hidden = false;
    } catch {
      // Battery telemetry is optional and independent of the live player.
    } finally {
      this.batteryPending = false;
    }
  }

  async open() {
    if (!this.hass || !this.config || this.frame || this.opening) return;
    const {slug, view} = this.config;
    const attempt = {};
    this.opening = attempt;
    this.hint.textContent = "Ouverture du lecteur…";
    this.button.disabled = true;
    this.openingTimeout = setTimeout(() => {
      this.close("Lecteur COCOCAM indisponible. Vérifie la version de l’application.");
    }, 15000);
    try {
      const info = await this.hass.callWS({type: "supervisor/ingress/info", slug});
      if (this.opening !== attempt) return;
      if (info.state !== "started" || !info.ingress_url) {
        this.close("Démarre l’application COCOCAM pour accéder au direct.");
        return;
      }
      const url = ingressUrl(info.ingress_url);
      let session = await this.createSession(slug);
      if (this.opening !== attempt) return;
      setIngressCookie(session);
      url.searchParams.set("embed", view);

      const frame = document.createElement("iframe");
      frame.title = `COCOCAM — ${this.viewLabel}`;
      frame.allow = "autoplay; fullscreen";
      frame.height = "260";
      frame.src = url.href;
      this.frame = frame;
      this.shadowRoot.querySelector("ha-card").append(frame);

      this.sessionRefresh = setInterval(async () => {
        try {
          await this.hass.callWS({type: "supervisor/ingress/validate_session", session});
        } catch {
          try {
            session = await this.createSession(slug);
            if (this.frame === frame) setIngressCookie(session);
          } catch {
            if (this.frame === frame) this.close("Session Home Assistant indisponible. Réessaie.");
          }
        }
      }, 60000);
    } catch {
      if (this.opening === attempt) this.close("Impossible d’ouvrir COCOCAM avec ce compte Home Assistant.");
    }
  }

  onMessage(event) {
    const frame = this.frame;
    if (!frame || event.origin !== location.origin || event.source !== frame.contentWindow) return;
    if (event.data?.type === "cococam/ready" && this.opening) {
      clearTimeout(this.openingTimeout);
      this.opening = undefined;
      this.launcher.hidden = true;
      frame.contentWindow.postMessage({type: "cococam/start"}, location.origin);
      frame.focus({preventScroll: true});
    } else if (event.data?.type === "cococam/resize" && Number.isFinite(event.data.height)) {
      frame.height = String(Math.min(1600, Math.max(100, Math.ceil(event.data.height))));
    }
  }
}

class CococamCardEditor extends HTMLElement {
  setConfig(config) {
    if (!this.shadowRoot) {
      const root = this.attachShadow({mode: "open"});
      root.innerHTML = `
        <style>
          label { display: grid; gap: 4px; margin: 12px 0; }
          input, select { padding: 8px; font: inherit; color: var(--primary-text-color);
                          background: var(--card-background-color); }
        </style>
        <label>Objectif<select name="view"></select></label>
        <label>Identifiant de l’application (slug)<input name="slug" spellcheck="false"></label>`;
      for (const [value, label] of VIEWS) {
        root.querySelector("select").append(new Option(label, value));
      }
      root.addEventListener("change", (event) => {
        const {name, value} = event.target;
        this.config = {...this.config, [name]: value.trim()};
        this.dispatchEvent(new CustomEvent("config-changed", {
          detail: {config: this.config}, bubbles: true, composed: true,
        }));
      });
    }
    this.config = {...DEFAULT_CONFIG, ...config};
    this.shadowRoot.querySelector("select").value = this.config.view;
    this.shadowRoot.querySelector("input").value = this.config.slug;
  }
}

if (!customElements.get("cococam-card")) {
  customElements.define("cococam-card-editor", CococamCardEditor);
  customElements.define("cococam-card", CococamCard);
  window.customCards ??= [];
  window.customCards.push({
    type: "cococam-card", name: "COCOCAM en direct",
    description: "Affiche une ou deux vues COCOCAM à la demande.",
  });
}
