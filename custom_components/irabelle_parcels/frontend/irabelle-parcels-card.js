/*
 * Irabelle Parcels cards, served and loaded by the integration itself.
 *
 *   type: custom:irabelle-parcels-card        Active / Archive tabs, add form
 *   type: custom:irabelle-parcels-chips-card  one chip per active parcel,
 *                                             renders nothing when empty
 *
 * Both read the parcel list from the `irabelle_parcels/subscribe` websocket
 * command (archived parcels have no sensor) and act through the
 * irabelle_parcels.* actions.
 */

const DOMAIN = "irabelle_parcels";
const VERSION = "1.0.0";

const STATUS = {
  pending: { label: "Checking…", icon: "mdi:timer-sand", color: "var(--disabled-text-color, #9e9e9e)" },
  transit: { label: "In transit", icon: "mdi:truck-delivery", color: "var(--orange-color, #ff9800)" },
  arrived: { label: "Arrived", icon: "mdi:airplane-landing", color: "var(--blue-color, #2196f3)" },
  pickup: { label: "Ready for pickup", icon: "mdi:store-marker", color: "var(--purple-color, #9c27b0)" },
  delivered: { label: "Delivered", icon: "mdi:package-variant-closed-check", color: "var(--green-color, #4caf50)" },
  cancelled: { label: "Cancelled", icon: "mdi:cancel", color: "var(--grey-color, #9e9e9e)" },
  returned: { label: "Returned", icon: "mdi:package-variant-closed-remove", color: "var(--grey-color, #9e9e9e)" },
  no_data: { label: "No information yet", icon: "mdi:help-circle", color: "var(--grey-color, #9e9e9e)" },
  error: { label: "Error", icon: "mdi:alert-circle", color: "var(--red-color, #f44336)" },
  unknown: { label: "Unknown", icon: "mdi:help-circle", color: "var(--grey-color, #9e9e9e)" },
};
const status = (p) => STATUS[p.state] || STATUS.unknown;

const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

// -- shared subscription ------------------------------------------------------
// One websocket subscription per connection, shared by every card on the page.

const parcelsStore = {
  conn: null,
  unsub: null,
  data: null,
  listeners: new Set(),

  subscribe(hass, listener) {
    this.listeners.add(listener);
    if (this.conn !== hass.connection) {
      this._close();
      this.conn = hass.connection;
      this.unsub = hass.connection
        .subscribeMessage((msg) => {
          this.data = msg;
          this.listeners.forEach((l) => l(msg));
        }, { type: `${DOMAIN}/subscribe` })
        .catch((err) => {
          console.error("irabelle-parcels: subscribe failed", err);
          this.conn = null;
          return null;
        });
    } else if (this.data) {
      listener(this.data);
    }
    return () => {
      this.listeners.delete(listener);
      if (!this.listeners.size) this._close();
    };
  },

  _close() {
    if (this.unsub) this.unsub.then((unsub) => unsub && unsub()).catch(() => {});
    this.unsub = null;
    this.conn = null;
    this.data = null;
  },
};

// -- formatting ---------------------------------------------------------------

// Event dates are the destination's wall-clock time mislabelled as UTC ("Z"),
// so read the digits and don't convert.
function wallClock(value) {
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/.exec(value || "");
  if (!m) return null;
  return new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0));
}

function lang(hass) {
  return hass?.locale?.language || hass?.language || navigator.language;
}

function formatEventTime(hass, value) {
  const date = wallClock(value);
  if (!date) return "";
  return date.toLocaleString(lang(hass), { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function formatDay(hass, date) {
  return date.toLocaleDateString(lang(hass), { weekday: "short", day: "numeric", month: "short" });
}

function relative(hass, date) {
  if (!date) return "";
  const seconds = (date.getTime() - Date.now()) / 1000;
  const rtf = new Intl.RelativeTimeFormat(lang(hass), { numeric: "auto" });
  for (const [unit, size] of [["year", 31536000], ["month", 2592000], ["week", 604800], ["day", 86400], ["hour", 3600], ["minute", 60]]) {
    if (Math.abs(seconds) >= size) return rtf.format(Math.round(seconds / size), unit);
  }
  return rtf.format(0, "minute");
}

function eta(hass, parcel) {
  if (!parcel.expected_delivery || parcel.state === "delivered") return "";
  const date = new Date(parcel.expected_delivery);
  return isNaN(date) ? "" : formatDay(hass, date);
}

function sortActive(a, b) {
  // Ready for pickup first, then the most recent tracking event.
  const rank = (p) => (p.state === "pickup" ? 0 : p.state === "pending" ? 1 : 2);
  return rank(a) - rank(b) || String(b.last_update || b.added_at || "").localeCompare(String(a.last_update || a.added_at || ""));
}

function sortArchived(a, b) {
  return String(b.archived_at || "").localeCompare(String(a.archived_at || ""));
}

function toast(message) {
  const ha = document.querySelector("home-assistant");
  (ha || window).dispatchEvent(new CustomEvent("hass-notification", { detail: { message }, bubbles: true, composed: true }));
}

async function callAction(hass, service, data = {}) {
  try {
    await hass.callService(DOMAIN, service, data);
    return true;
  } catch (err) {
    toast(err?.message || String(err));
    return false;
  }
}

// -- shared styles and parcel detail ------------------------------------------

const STYLES = `
  :host { display: block; }
  .icon-badge {
    --mdc-icon-size: 22px;
    flex: none; width: 40px; height: 40px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    color: var(--parcel-color);
    background: color-mix(in srgb, var(--parcel-color) 18%, transparent);
  }
  button { font: inherit; color: inherit; }
  .btn {
    display: inline-flex; align-items: center; gap: 6px;
    border: 1px solid var(--divider-color); background: none; cursor: pointer;
    border-radius: 18px; padding: 6px 12px; font-size: 13px;
    color: var(--primary-text-color); --mdc-icon-size: 18px;
  }
  .btn:hover { background: var(--secondary-background-color); }
  .btn.primary { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
  .btn.danger { color: var(--error-color, #db4437); border-color: color-mix(in srgb, var(--error-color, #db4437) 50%, transparent); }
  .btn[disabled] { opacity: 0.5; cursor: default; }
  .icon-btn {
    border: none; background: none; cursor: pointer; padding: 6px; border-radius: 50%;
    color: var(--secondary-text-color); display: inline-flex; --mdc-icon-size: 20px;
  }
  .icon-btn:hover { background: var(--secondary-background-color); color: var(--primary-text-color); }
  input {
    font: inherit; font-size: 14px; color: var(--primary-text-color);
    background: var(--secondary-background-color); border: 1px solid var(--divider-color);
    border-radius: 8px; padding: 8px 10px; min-width: 0; width: 100%; box-sizing: border-box;
  }
  input:focus { outline: 2px solid var(--primary-color); outline-offset: -1px; }
  .detail { display: flex; flex-direction: column; gap: 12px; font-size: 14px; }
  .facts { display: flex; flex-wrap: wrap; gap: 6px 16px; color: var(--secondary-text-color); font-size: 13px; }
  .facts b { color: var(--primary-text-color); font-weight: 500; }
  .facts a { color: var(--primary-color); text-decoration: none; }
  .mono { font-family: var(--code-font-family, monospace); cursor: pointer; }
  .timeline { list-style: none; margin: 0; padding: 0 0 0 4px; }
  .timeline li { position: relative; padding: 0 0 12px 20px; border-left: 2px solid var(--divider-color); }
  .timeline li:last-child { border-left-color: transparent; padding-bottom: 0; }
  .timeline li::before {
    content: ""; position: absolute; left: -6px; top: 3px; width: 10px; height: 10px;
    border-radius: 50%; background: var(--divider-color);
  }
  .timeline li:first-child::before { background: var(--parcel-color); }
  .timeline .when { font-size: 12px; color: var(--secondary-text-color); }
  .timeline .what { color: var(--primary-text-color); }
  .timeline .where { color: var(--secondary-text-color); }
  .link { background: none; border: none; color: var(--primary-color); cursor: pointer; padding: 0; font-size: 13px; }
  .actions { display: flex; flex-wrap: wrap; gap: 8px; }
  .confirm { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; color: var(--error-color, #db4437); }
  .muted { color: var(--secondary-text-color); }
`;

/** HTML of a parcel's details, timeline and actions. `ui` holds view state. */
function renderDetail(hass, parcel, ui, maxEvents) {
  const s = status(parcel);
  const events = parcel.statuses || [];
  const showAll = ui.allEvents.has(parcel.tracking_number);
  const shown = showAll ? events : events.slice(0, maxEvents);
  const carrier = parcel.carrier
    ? parcel.tracking_url
      ? `<a href="${esc(parcel.tracking_url)}" target="_blank" rel="noreferrer">${esc(parcel.carrier)}</a>`
      : esc(parcel.carrier)
    : "";
  const route = [parcel.origin, parcel.destination].filter(Boolean).map(esc).join(" → ");
  const facts = [
    `<span><b>Tracking</b> <span class="mono" data-action="copy" data-tracking="${esc(parcel.tracking_number)}" title="Copy">${esc(parcel.tracking_number)}</span></span>`,
    carrier && `<span><b>Carrier</b> ${carrier}</span>`,
    route && `<span><b>Route</b> ${route}</span>`,
    eta(hass, parcel) && `<span><b>Expected</b> ${eta(hass, parcel)}</span>`,
    parcel.days_in_transit != null && `<span><b>In transit</b> ${esc(parcel.days_in_transit)} days</span>`,
    parcel.archived && parcel.archived_at && `<span><b>Archived</b> ${formatDay(hass, new Date(parcel.archived_at))}</span>`,
  ].filter(Boolean).join("");

  const timeline = events.length
    ? `<ul class="timeline" style="--parcel-color:${s.color}">${shown
        .map(
          (ev) => `<li><div class="when">${esc(formatEventTime(hass, ev.date))}</div>
            <div><span class="what">${esc(ev.status)}</span>${ev.location ? ` <span class="where">· ${esc(ev.location)}</span>` : ""}</div></li>`
        )
        .join("")}</ul>
      ${events.length > maxEvents ? `<button class="link" data-action="all-events" data-tracking="${esc(parcel.tracking_number)}">${showAll ? "Show less" : `Show all ${events.length} events`}</button>` : ""}`
    : `<div class="muted">${esc(parcel.status_text || "No tracking events yet.")}</div>`;

  const t = esc(parcel.tracking_number);
  const actions =
    ui.confirmDelete === parcel.tracking_number
      ? `<div class="confirm">Delete “${esc(parcel.name)}” for good?
          <button class="btn danger" data-action="delete" data-tracking="${t}">Delete</button>
          <button class="btn" data-action="cancel-delete">Cancel</button></div>`
      : `<div class="actions">
          ${parcel.archived
            ? `<button class="btn" data-action="unarchive" data-tracking="${t}"><ha-icon icon="mdi:package-variant-closed-plus"></ha-icon>Track again</button>`
            : `<button class="btn" data-action="archive" data-tracking="${t}"><ha-icon icon="mdi:archive-arrow-down-outline"></ha-icon>Archive</button>`}
          <button class="btn" data-action="rename" data-tracking="${t}"><ha-icon icon="mdi:pencil-outline"></ha-icon>Rename</button>
          ${parcel.entity_id ? `<button class="btn" data-action="more-info" data-entity="${esc(parcel.entity_id)}"><ha-icon icon="mdi:chart-timeline-variant"></ha-icon>History</button>` : ""}
          <button class="btn danger" data-action="ask-delete" data-tracking="${t}"><ha-icon icon="mdi:delete-outline"></ha-icon>Delete</button>
        </div>`;

  return `<div class="detail"><div class="facts">${facts}</div>${timeline}${actions}</div>`;
}

/** Handles the actions shared by the card and the dialog. Returns true if handled. */
async function handleCommonAction(host, hass, ui, el) {
  const tracking = el.dataset.tracking;
  switch (el.dataset.action) {
    case "copy":
      try {
        await navigator.clipboard.writeText(tracking);
        toast(`Copied ${tracking}`);
      } catch (_) {
        /* clipboard needs https */
      }
      return true;
    case "all-events":
      ui.allEvents.has(tracking) ? ui.allEvents.delete(tracking) : ui.allEvents.add(tracking);
      host._render();
      return true;
    case "archive":
      await callAction(hass, "archive_parcel", { tracking_number: tracking });
      return true;
    case "unarchive":
      await callAction(hass, "unarchive_parcel", { tracking_number: tracking });
      return true;
    case "rename": {
      const parcel = host._parcels().find((p) => p.tracking_number === tracking);
      const name = window.prompt("Parcel name", parcel?.name || "");
      if (name && name.trim()) await callAction(hass, "update_parcel", { tracking_number: tracking, name: name.trim() });
      return true;
    }
    case "ask-delete":
      ui.confirmDelete = tracking;
      host._render();
      return true;
    case "cancel-delete":
      ui.confirmDelete = null;
      host._render();
      return true;
    case "delete":
      ui.confirmDelete = null;
      await callAction(hass, "remove_parcel", { tracking_number: tracking });
      return true;
    case "more-info":
      host.dispatchEvent(new CustomEvent("hass-more-info", { detail: { entityId: el.dataset.entity }, bubbles: true, composed: true }));
      return true;
  }
  return false;
}

function newUiState() {
  return { allEvents: new Set(), confirmDelete: null };
}

function setHidden(card, hidden) {
  // Same mechanism as Home Assistant's own entity-filter card: the section /
  // stack holding the card collapses instead of showing an empty box.
  if (card.hasAttribute("hidden") === hidden) return;
  card.style.display = hidden ? "none" : "";
  card.toggleAttribute("hidden", hidden);
  card.dispatchEvent(new CustomEvent("card-visibility-changed", { detail: { value: !hidden }, bubbles: true, composed: true }));
}

// -- base class ---------------------------------------------------------------

class ParcelsElement extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null;
    this._ui = newUiState();
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
  }

  set hass(hass) {
    this._hass = hass;
    if (this.isConnected) this._subscribe();
  }

  // Set by Home Assistant while the dashboard is being edited: empty cards
  // must stay visible there so they can be selected.
  set preview(value) {
    this._preview = value;
    this._render();
  }

  set editMode(value) {
    this._editing = value;
    this._render();
  }

  _editMode() {
    return Boolean(this._preview || this._editing);
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    if (this._hass && !this._unsub) this._subscribe();
  }

  disconnectedCallback() {
    if (this._unsub) this._unsub();
    this._unsub = null;
  }

  _subscribe() {
    if (!this._hass || this._unsub) return;
    this._unsub = parcelsStore.subscribe(this._hass, (data) => {
      this._data = data;
      this._render();
    });
  }

  _parcels() {
    return this._data?.parcels || [];
  }

  async _onClick(ev) {
    const el = ev.composedPath().find((n) => n.dataset && n.dataset.action);
    if (!el) return;
    ev.stopPropagation();
    if (!(await handleCommonAction(this, this._hass, this._ui, el))) this._onAction(el, ev);
  }

  _onAction() {}
}

// -- full card ----------------------------------------------------------------

class IrabelleParcelsCard extends ParcelsElement {
  static getStubConfig() {
    return { title: "Parcels" };
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "title", selector: { text: {} } },
        {
          type: "grid",
          name: "",
          schema: [
            { name: "show_add", default: true, selector: { boolean: {} } },
            { name: "show_archive", default: true, selector: { boolean: {} } },
            { name: "hide_if_empty", default: false, selector: { boolean: {} } },
            { name: "max_events", default: 3, selector: { number: { min: 1, max: 50, mode: "box" } } },
          ],
        },
      ],
      computeLabel: (s) =>
        ({
          title: "Title",
          show_add: "Show the add form",
          show_archive: "Show the archive tab",
          hide_if_empty: "Hide when nothing is on the way",
          max_events: "Events shown before “Show all”",
        })[s.name],
    };
  }

  setConfig(config) {
    this._config = { title: "Parcels", show_add: true, show_archive: true, hide_if_empty: false, max_events: 3, ...config };
    this._tab = this._tab || "active";
    this._expanded = this._expanded || new Set();
    this._form = this._form || { open: false, tracking: "", name: "", busy: false };
    this._filter = this._filter || "";
    this._render();
  }

  getCardSize() {
    return 2 + this._parcels().filter((p) => !p.archived).length;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6 };
  }

  _render() {
    if (!this._config) return;
    const hass = this._hass;
    const all = this._parcels();
    const active = all.filter((p) => !p.archived).sort(sortActive);
    const archived = all.filter((p) => p.archived).sort(sortArchived);
    const loaded = this._data != null;

    setHidden(this, Boolean(this._config.hide_if_empty && loaded && !active.length && !this._form.open && !this._editMode()));

    const tab = this._config.show_archive ? this._tab : "active";
    let list = tab === "active" ? active : archived;
    const q = this._filter.trim().toLowerCase();
    if (tab === "archive" && q) {
      list = list.filter((p) => `${p.name} ${p.tracking_number} ${p.carrier || ""}`.toLowerCase().includes(q));
    }

    const focused = this.shadowRoot.activeElement;
    const focusName = focused && focused.name;
    const caret = focused && focused.selectionStart;

    this.shadowRoot.innerHTML = `
      <style>${STYLES}${CARD_STYLES}</style>
      <ha-card>
        <div class="header">
          <div class="title">${esc(this._config.title)}</div>
          ${this._config.show_add
            ? `<button class="icon-btn add-toggle ${this._form.open ? "open" : ""}" data-action="toggle-form" title="Add parcel">
                <ha-icon icon="mdi:plus"></ha-icon></button>`
            : ""}
        </div>
        ${this._form.open ? this._renderForm() : ""}
        ${this._config.show_archive
          ? `<div class="tabs">
              <button class="tab ${tab === "active" ? "selected" : ""}" data-action="tab" data-tab="active">Active <span class="count">${active.length}</span></button>
              <button class="tab ${tab === "archive" ? "selected" : ""}" data-action="tab" data-tab="archive">Archive <span class="count">${archived.length}</span></button>
            </div>`
          : ""}
        ${tab === "archive" && archived.length > 6
          ? `<div class="filter"><input name="filter" placeholder="Search the archive" value="${esc(this._filter)}"></div>`
          : ""}
        <div class="list">
          ${!loaded
            ? `<div class="empty">Loading…</div>`
            : this._data.loaded === false
              ? `<div class="empty">Irabelle Parcels is not set up.</div>`
              : list.length
                ? list.map((p) => this._renderRow(hass, p)).join("")
                : this._renderEmpty(tab, q)}
        </div>
        ${tab === "archive" && archived.length
          ? `<div class="footer">${this._confirmClear
              ? `<div class="confirm">Delete all ${archived.length} archived parcels?
                  <button class="btn danger" data-action="clear-archive">Delete all</button>
                  <button class="btn" data-action="cancel-clear">Cancel</button></div>`
              : `<button class="btn" data-action="ask-clear"><ha-icon icon="mdi:archive-remove-outline"></ha-icon>Clear archive</button>`}</div>`
          : ""}
      </ha-card>`;

    if (focusName) {
      const input = this.shadowRoot.querySelector(`input[name="${focusName}"]`);
      if (input) {
        input.focus();
        if (caret != null) input.setSelectionRange(caret, caret);
      }
    }
    this.shadowRoot.querySelectorAll("input").forEach((input) => {
      input.addEventListener("input", (ev) => this._onInput(ev));
      input.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" && input.name !== "filter") this._submit();
        if (ev.key === "Escape") {
          this._form.open = false;
          this._render();
        }
      });
    });
  }

  _renderForm() {
    const f = this._form;
    const paste = (field) =>
      navigator.clipboard?.readText
        ? `<button class="icon-btn" data-action="paste" data-field="${field}" title="Paste"><ha-icon icon="mdi:clipboard-arrow-down-outline"></ha-icon></button>`
        : "";
    return `
      <div class="form">
        <div class="field"><input name="tracking" placeholder="Tracking number" autocomplete="off" autocapitalize="characters" spellcheck="false" value="${esc(f.tracking)}">${paste("tracking")}</div>
        <div class="field"><input name="name" placeholder="What is it? (optional)" autocomplete="off" value="${esc(f.name)}">${paste("name")}</div>
        <div class="form-actions">
          <button class="btn" data-action="toggle-form">Cancel</button>
          <button class="btn primary" data-action="submit" ${f.busy || !f.tracking.trim() ? "disabled" : ""}>
            <ha-icon icon="mdi:package-variant-closed-plus"></ha-icon>${f.busy ? "Adding…" : "Track"}</button>
        </div>
      </div>`;
  }

  _renderEmpty(tab, query) {
    if (tab === "archive") {
      return `<div class="empty"><ha-icon icon="mdi:archive-outline"></ha-icon>${query ? "No archived parcel matches." : "Delivered parcels end up here."}</div>`;
    }
    return `<div class="empty"><ha-icon icon="mdi:package-variant"></ha-icon>Nothing on the way.${this._config.show_add && !this._form.open ? ` <button class="link" data-action="toggle-form">Track a parcel</button>` : ""}</div>`;
  }

  _renderRow(hass, p) {
    const s = status(p);
    const open = this._expanded.has(p.tracking_number);
    const lastDate = wallClock(p.last_update);
    const when = eta(hass, p);
    const subtitle = [p.status_text && p.status_text !== p.state ? p.status_text : s.label, relative(hass, lastDate)].filter(Boolean).join(" · ");
    return `
      <div class="parcel ${open ? "open" : ""}" style="--parcel-color:${s.color}">
        <div class="row" data-action="expand" data-tracking="${esc(p.tracking_number)}">
          <div class="icon-badge"><ha-icon icon="${s.icon}"></ha-icon></div>
          <div class="info">
            <div class="name">${esc(p.name)}</div>
            <div class="sub">${esc(subtitle)}</div>
          </div>
          <div class="side">
            <span class="pill">${esc(s.label)}</span>
            ${when ? `<span class="eta"><ha-icon icon="mdi:calendar-clock"></ha-icon>${esc(when)}</span>` : ""}
          </div>
        </div>
        ${open ? `<div class="expanded">${renderDetail(hass, p, this._ui, this._config.max_events)}</div>` : ""}
      </div>`;
  }

  _onInput(ev) {
    const input = ev.target;
    if (input.name === "filter") {
      this._filter = input.value;
      this._render();
      return;
    }
    this._form[input.name] = input.value;
    const submit = this.shadowRoot.querySelector('[data-action="submit"]');
    if (submit) submit.disabled = this._form.busy || !this._form.tracking.trim();
  }

  async _onAction(el) {
    switch (el.dataset.action) {
      case "expand": {
        const t = el.dataset.tracking;
        this._expanded.has(t) ? this._expanded.delete(t) : this._expanded.add(t);
        break;
      }
      case "tab":
        this._tab = el.dataset.tab;
        this._confirmClear = false;
        break;
      case "toggle-form":
        this._form.open = !this._form.open;
        this._render();
        if (this._form.open) this.shadowRoot.querySelector('input[name="tracking"]')?.focus();
        return;
      case "paste":
        try {
          this._form[el.dataset.field] = (await navigator.clipboard.readText()).trim();
        } catch (_) {
          toast("Clipboard access was denied");
        }
        break;
      case "submit":
        await this._submit();
        return;
      case "ask-clear":
        this._confirmClear = true;
        break;
      case "cancel-clear":
        this._confirmClear = false;
        break;
      case "clear-archive":
        this._confirmClear = false;
        await callAction(this._hass, "clear_archive");
        break;
      default:
        return;
    }
    this._render();
  }

  async _submit() {
    const f = this._form;
    if (f.busy || !f.tracking.trim()) return;
    f.busy = true;
    this._render();
    const data = { tracking_number: f.tracking.trim() };
    if (f.name.trim()) data.name = f.name.trim();
    const ok = await callAction(this._hass, "add_parcel", data);
    f.busy = false;
    if (ok) {
      Object.assign(f, { open: false, tracking: "", name: "" });
      this._tab = "active";
      toast(`Tracking ${data.name || data.tracking_number}`);
    }
    this._render();
  }
}

const CARD_STYLES = `
  ha-card { overflow: hidden; }
  .header { display: flex; align-items: center; justify-content: space-between; padding: 12px 12px 4px 16px; }
  .title { font-size: 20px; font-weight: 500; color: var(--ha-card-header-color, var(--primary-text-color)); }
  .add-toggle ha-icon { transition: transform 0.2s; }
  .add-toggle.open ha-icon { transform: rotate(45deg); }
  .form { display: flex; flex-direction: column; gap: 8px; padding: 4px 16px 12px; }
  .field { display: flex; align-items: center; gap: 4px; }
  .form-actions { display: flex; justify-content: flex-end; gap: 8px; }
  .tabs { display: flex; gap: 4px; padding: 0 12px; border-bottom: 1px solid var(--divider-color); }
  .tab {
    border: none; background: none; cursor: pointer; padding: 10px 12px; font-size: 14px;
    color: var(--secondary-text-color); border-bottom: 2px solid transparent; margin-bottom: -1px;
  }
  .tab.selected { color: var(--primary-color); border-bottom-color: var(--primary-color); font-weight: 500; }
  .count {
    display: inline-block; min-width: 18px; padding: 0 5px; margin-left: 4px; border-radius: 9px;
    font-size: 12px; line-height: 18px; text-align: center; background: var(--secondary-background-color);
  }
  .filter { padding: 8px 16px 0; }
  .list { padding: 4px 0 8px; }
  .parcel { border-bottom: 1px solid var(--divider-color); }
  .parcel:last-child { border-bottom: none; }
  .row { display: flex; align-items: center; gap: 12px; padding: 10px 16px; cursor: pointer; }
  .row:hover { background: var(--secondary-background-color); }
  .info { flex: 1; min-width: 0; }
  .name { font-weight: 500; color: var(--primary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .sub { font-size: 13px; color: var(--secondary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .side { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; flex: none; }
  .pill {
    font-size: 12px; padding: 2px 8px; border-radius: 10px; white-space: nowrap;
    color: var(--parcel-color); background: color-mix(in srgb, var(--parcel-color) 15%, transparent);
  }
  .eta { display: inline-flex; align-items: center; gap: 3px; font-size: 12px; color: var(--secondary-text-color); --mdc-icon-size: 14px; white-space: nowrap; }
  .expanded { padding: 0 16px 14px 68px; }
  .empty {
    display: flex; align-items: center; justify-content: center; gap: 8px; flex-wrap: wrap;
    padding: 20px 16px; color: var(--secondary-text-color);
  }
  .footer { padding: 4px 16px 14px; display: flex; justify-content: flex-end; }
  @media (max-width: 450px) { .expanded { padding-left: 16px; } }
`;

// -- chips card ---------------------------------------------------------------

class IrabelleParcelsChipsCard extends ParcelsElement {
  static getStubConfig() {
    return {};
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "show_eta", default: true, selector: { boolean: {} } },
        { name: "max_events", default: 5, selector: { number: { min: 1, max: 50, mode: "box" } } },
      ],
      computeLabel: (s) => ({ show_eta: "Show the expected delivery day", max_events: "Events shown in the popup" })[s.name],
    };
  }

  setConfig(config) {
    this._config = { show_eta: true, max_events: 5, ...config };
    this._render();
  }

  getCardSize() {
    return 1;
  }

  getGridOptions() {
    return { columns: "full" };
  }

  _render() {
    if (!this._config) return;
    const active = this._parcels().filter((p) => !p.archived).sort(sortActive);
    setHidden(this, this._data != null && !active.length && !this._editMode());
    this.shadowRoot.innerHTML = `
      <style>${STYLES}
        .chips { display: flex; flex-wrap: wrap; gap: 8px; }
        .chip {
          display: inline-flex; align-items: center; gap: 6px; cursor: pointer;
          height: 36px; padding: 0 12px 0 8px; border-radius: 18px; box-sizing: border-box;
          background: var(--ha-card-background, var(--card-background-color));
          border: var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, var(--divider-color));
          box-shadow: var(--ha-card-box-shadow, none);
          color: var(--primary-text-color); font-size: 14px; font-weight: 500;
          --mdc-icon-size: 20px;
        }
        .chip ha-icon { color: var(--parcel-color); }
        .chip .eta { font-weight: 400; color: var(--secondary-text-color); font-size: 12px; }
        .placeholder { color: var(--secondary-text-color); font-size: 14px; padding: 8px; }
      </style>
      <div class="chips">
        ${active.length
          ? active
              .map((p) => {
                const s = status(p);
                const when = this._config.show_eta ? eta(this._hass, p) : "";
                return `<button class="chip" style="--parcel-color:${s.color}" data-action="open" data-tracking="${esc(p.tracking_number)}" title="${esc(s.label)}">
                  <ha-icon icon="${s.icon}"></ha-icon>${esc(p.name)}${when ? `<span class="eta">${esc(when)}</span>` : ""}</button>`;
              })
              .join("")
          : `<div class="placeholder">No parcels on the way (this card is hidden on the dashboard)</div>`}
      </div>`;
  }

  _onAction(el) {
    if (el.dataset.action === "open") ParcelDialog.open(this._hass, el.dataset.tracking, this._config.max_events);
  }
}

// -- popup --------------------------------------------------------------------

class ParcelDialog extends ParcelsElement {
  static open(hass, tracking, maxEvents) {
    const dialog = document.createElement("irabelle-parcels-dialog");
    dialog._tracking = tracking;
    dialog._maxEvents = maxEvents;
    document.body.appendChild(dialog);
    dialog.hass = hass;
  }

  connectedCallback() {
    super.connectedCallback();
    this._onKey = (ev) => ev.key === "Escape" && this.remove();
    window.addEventListener("keydown", this._onKey);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    window.removeEventListener("keydown", this._onKey);
  }

  _render() {
    const parcel = this._parcels().find((p) => p.tracking_number === this._tracking);
    if (this._data && !parcel) {
      this.remove(); // deleted
      return;
    }
    if (!parcel) return;
    const s = status(parcel);
    this.shadowRoot.innerHTML = `
      <style>${STYLES}
        .scrim { position: fixed; inset: 0; z-index: 10; background: rgba(0, 0, 0, 0.45); display: flex; align-items: center; justify-content: center; padding: 16px; }
        .panel {
          width: min(520px, 100%); max-height: calc(100vh - 32px); overflow: auto; box-sizing: border-box;
          background: var(--ha-card-background, var(--card-background-color, #fff)); color: var(--primary-text-color);
          border-radius: var(--ha-dialog-border-radius, 24px); padding: 20px; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
          font-family: var(--paper-font-body1_-_font-family, var(--ha-font-family-body, Roboto, sans-serif));
        }
        .head { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
        .head .t { flex: 1; min-width: 0; }
        .head .n { font-size: 20px; font-weight: 500; }
        .head .s { color: var(--parcel-color); font-size: 14px; }
      </style>
      <div class="scrim" data-action="close">
        <div class="panel" data-action="noop" style="--parcel-color:${s.color}">
          <div class="head">
            <div class="icon-badge"><ha-icon icon="${s.icon}"></ha-icon></div>
            <div class="t"><div class="n">${esc(parcel.name)}</div><div class="s">${esc(s.label)}</div></div>
            <button class="icon-btn" data-action="close" title="Close"><ha-icon icon="mdi:close"></ha-icon></button>
          </div>
          ${renderDetail(this._hass, parcel, this._ui, this._maxEvents || 5)}
        </div>
      </div>`;
  }

  async _onClick(ev) {
    const el = ev.composedPath().find((n) => n.dataset && n.dataset.action);
    if (!el || el.dataset.action === "noop") return;
    if (el.dataset.action === "close") {
      this.remove();
      return;
    }
    if (el.dataset.action === "more-info") {
      // The dialog lives outside Home Assistant's tree: fire on the app.
      document.querySelector("home-assistant")?.dispatchEvent(
        new CustomEvent("hass-more-info", { detail: { entityId: el.dataset.entity }, bubbles: true, composed: true })
      );
      this.remove();
      return;
    }
    await handleCommonAction(this, this._hass, this._ui, el);
    if (el.dataset.action === "archive") this.remove();
  }
}

if (!customElements.get("irabelle-parcels-card")) {
  customElements.define("irabelle-parcels-card", IrabelleParcelsCard);
  customElements.define("irabelle-parcels-chips-card", IrabelleParcelsChipsCard);
  customElements.define("irabelle-parcels-dialog", ParcelDialog);
  window.customCards = window.customCards || [];
  window.customCards.push(
    { type: "irabelle-parcels-card", name: "Irabelle Parcels", description: "Active and archived parcels, with an add form.", preview: true, documentationURL: "https://github.com/notf0und/irabelle-parcels" },
    { type: "irabelle-parcels-chips-card", name: "Irabelle Parcels chips", description: "One chip per parcel on the way; hidden when there are none.", preview: true, documentationURL: "https://github.com/notf0und/irabelle-parcels" }
  );
  console.info(`%c IRABELLE-PARCELS %c ${VERSION} `, "color:#fff;background:#d4762c;font-weight:700", "color:#d4762c;background:#fff");
}
