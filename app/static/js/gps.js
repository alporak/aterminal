/* ================================================================
   GPS Server Plugin – Enhanced
   Full IO display, raw data annotations, record export,
   AVL IDs management, IMEI-aware commands.
   ================================================================ */
import { h, $, $$, api, toast, registerPlugin, createTabs, createTable, renderHex, icons, makeColumnsResizable } from "./core.js";

registerPlugin({
  id: "gps", name: "GPS Server", order: 1,
  svgIcon: icons.satellite,

  _ws: null,
  _data: {
    running: false, protocol: "", port: 0,
    devices: {}, records_count: 0, raw_count: 0, log_count: 0, cmd_count: 0,
    last_records: [], last_logs: [], last_raw: [],
  },
  _ioNames: {},

  // Records column preferences (persisted in localStorage)
  _recCols: null,       // { base: {Time:true, IMEI:true, ...}, ios: {239:true, ...} }
  _recData: null,       // cached records from last load
  _recContainer: null,  // DOM ref for re-rendering without refetch

  _loadRecCols() {
    if (this._recCols) return this._recCols;
    try {
      const raw = localStorage.getItem("gps_rec_cols");
      if (raw) { this._recCols = JSON.parse(raw); return this._recCols; }
    } catch {}
    this._recCols = {
      base: { Time: true, IMEI: true, Lat: true, Lng: true, Alt: false, Speed: true,
              Angle: false, Sats: true, Prio: false, IOs: true, EventIO: false },
      ios: {},
    };
    return this._recCols;
  },

  _saveRecCols() {
    try { localStorage.setItem("gps_rec_cols", JSON.stringify(this._recCols)); } catch {}
  },

  init(container) {
    this._loadIoNames();
    createTabs(container, [
      { id: "dash", label: "Dashboard", render: c => this._renderDash(c) },
      { id: "rec",  label: "Records",   render: c => this._renderRecords(c) },
      { id: "raw",  label: "Raw Data",  render: c => this._renderRaw(c) },
      { id: "cmd",  label: "Commands",  render: c => this._renderCommands(c) },
      { id: "log",  label: "Logs",      render: c => this._renderLogs(c) },
      { id: "cfg",  label: "Settings",  render: c => this._renderSettings(c) },
    ]);
    this._connectWs();
  },

  destroy() {
    if (this._ws) { this._ws.close(); this._ws = null; }
  },

  async _loadIoNames() {
    try {
      this._ioNames = await api("/api/gps/io_names");
      console.log(`[GPS] Loaded ${Object.keys(this._ioNames).length} IO names`);
    } catch (e) { console.warn("[GPS] Failed to load IO names:", e.message); }
  },

  _connectWs() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    this._ws = new WebSocket(`${proto}://${location.host}/ws/gps`);
    this._ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === "status") {
          Object.assign(this._data, msg);
          this._updateDash();
        }
      } catch (err) { console.warn("[GPS] WS parse error:", err.message); }
    };
    this._ws.onclose = () => {
      this._ws = null;
      setTimeout(() => { if (!this._destroyed) this._connectWs(); }, 3000);
    };
    this._ws.onerror = () => {};
  },

  _ioName(id) {
    const s = String(id);
    return this._ioNames[s] || `IO_${id}`;
  },

  /* ── Dashboard ────────────────────────────────────────── */
  _renderDash(c) {
    this._dashEl = c;
    c.innerHTML = "";

    const metrics = h("div", { className: "metrics" });
    this._mStatus  = this._metric(metrics, "STATUS", "...");
    this._mProto   = this._metric(metrics, "PROTOCOL", "—");
    this._mPort    = this._metric(metrics, "PORT", "—");
    this._mDevices = this._metric(metrics, "DEVICES", "0");
    this._mRecords = this._metric(metrics, "RECORDS", "0");
    this._mRaw     = this._metric(metrics, "RAW MSGS", "0");
    c.appendChild(metrics);

    c.appendChild(h("div", { className: "btn-group" },
      h("button", { className: "btn btn-primary", onclick: () => this._ctl("start") },
        h("span", { className: "btn-icon", html: icons.play }), "Start"),
      h("button", { className: "btn btn-danger", onclick: () => this._ctl("stop") },
        h("span", { className: "btn-icon", html: icons.stop }), "Stop"),
      h("button", { className: "btn", onclick: () => this._ctl("restart") },
        h("span", { className: "btn-icon", html: icons.refresh }), "Restart"),
      h("button", { className: "btn", onclick: () => this._clearAll() },
        h("span", { className: "btn-icon", html: icons.trash }), "Clear All"),
    ));

    this._devicesCard = h("div", { className: "card" },
      h("h3", null, "Connected Devices"),
      h("div", { id: "gps-devices-list" }, h("span", { className: "text-muted" }, "No devices")));
    c.appendChild(this._devicesCard);

    this._dashLast = h("div", { className: "card" },
      h("h3", null, "Recent Records"),
      h("div", { id: "gps-last-records" }, h("span", { className: "text-muted" }, "Waiting for data…")));
    c.appendChild(this._dashLast);

    this._loadStatus();
  },

  _metric(parent, label, value) {
    const valEl = h("div", { className: "metric-value" }, value);
    parent.appendChild(h("div", { className: "metric" },
      h("div", { className: "metric-label" }, label), valEl));
    return valEl;
  },

  async _loadStatus() {
    try {
      const s = await api("/api/gps/status");
      Object.assign(this._data, s);
      this._updateDash();
    } catch (e) { console.error("[GPS] Load status failed:", e.message); }
  },

  _updateDash() {
    const d = this._data;
    if (this._mStatus) {
      this._mStatus.textContent = d.running ? "Running" : "Stopped";
      this._mStatus.className = "metric-value " + (d.running ? "text-green" : "text-red");
    }
    if (this._mProto) this._mProto.textContent = d.protocol || "—";
    if (this._mPort) this._mPort.textContent = d.port || "—";
    if (this._mDevices) this._mDevices.textContent = Object.keys(d.devices || {}).length;
    if (this._mRecords) this._mRecords.textContent = d.records_count || 0;
    if (this._mRaw) this._mRaw.textContent = d.raw_count || 0;

    // Update devices list
    const dl = $("#gps-devices-list");
    if (dl) {
      const devs = d.devices || {};
      const keys = Object.keys(devs);
      if (keys.length === 0) {
        dl.innerHTML = '<span class="text-muted">No devices connected</span>';
      } else {
        dl.innerHTML = "";
        for (const imei of keys) {
          const dev = devs[imei];
          dl.appendChild(h("div", {
            style: "display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid var(--tk-border)"
          },
            h("div", null,
              h("strong", { style: "font-family:var(--font-mono);font-size:13px" }, imei),
              h("span", { className: "text-muted", style: "margin-left:10px;font-size:12px" }, dev.ip || "")),
            h("div", { style: "display:flex;gap:4px" },
              h("span", { className: "badge badge-primary" }, dev.protocol || ""),
              h("span", { className: "badge badge-green" }, dev.status || ""))
          ));
        }
      }
    }

    // Update last records
    const lr = $("#gps-last-records");
    if (lr && d.last_records?.length) {
      lr.innerHTML = "";
      const tbl = h("table", { style: "font-size:12px" });
      tbl.appendChild(h("thead", null, h("tr", null,
        ...["Time", "IMEI", "Lat", "Lng", "Spd", "Sats", "IOs"].map(t => h("th", null, t))
      )));
      const tbody = h("tbody");
      for (const r of d.last_records.slice(0, 8)) {
        tbody.appendChild(h("tr", null,
          h("td", null, r.Timestamp || "—"),
          h("td", null, h("code", { style: "font-size:11px" }, r.IMEI || "—")),
          h("td", null, (r.Latitude || 0).toFixed(6)),
          h("td", null, (r.Longitude || 0).toFixed(6)),
          h("td", null, String(r.Speed ?? 0)),
          h("td", null, String(r.Satellites ?? 0)),
          h("td", null, h("span", { className: "badge badge-primary" }, String(r.Total_IO ?? 0))),
        ));
      }
      tbl.appendChild(tbody);
      lr.appendChild(h("div", { className: "table-wrap", style: "max-height:250px" }, tbl));
    }
  },

  async _ctl(action) {
    try {
      const r = await api(`/api/gps/${action}`, { method: "POST" });
      toast(`Server ${action}: ${r.msg || "OK"}`, r.ok !== false ? "success" : "error");
      this._loadStatus();
    } catch (e) { toast(`${action} failed: ${e.message}`, "error"); }
  },

  async _clearAll() {
    if (!confirm("Clear ALL data (records, raw, logs, history)?")) return;
    try {
      await api("/api/gps/clear", { method: "POST" });
      toast("All data cleared", "success");
      this._loadStatus();
    } catch (e) { toast("Clear failed: " + e.message, "error"); }
  },

  /* ── Records ──────────────────────────────────────────── */
  async _renderRecords(c) {
    c.innerHTML = "";
    this._recContainer = c;

    // Toolbar row 1: action buttons
    const toolbar = h("div", { className: "btn-group", style: "margin-bottom:6px;flex-wrap:wrap" },
      h("button", { className: "btn", onclick: () => this._fetchAndRenderRecords(c) },
        h("span", { className: "btn-icon", html: icons.refresh }), "Refresh"),
      h("button", { className: "btn", onclick: () => this._showColumnPicker() },
        h("span", { className: "btn-icon", html: icons.settings }), "Columns"),
      h("button", { className: "btn", onclick: () => this._showIoPicker() },
        h("span", { className: "btn-icon", html: icons.plug }), "Pin IOs"),
      h("button", { className: "btn", onclick: () => this._exportRecords("json") },
        h("span", { className: "btn-icon", html: icons.file }), "Export JSON"),
      h("button", { className: "btn", onclick: () => this._exportRecords("csv") },
        h("span", { className: "btn-icon", html: icons.file }), "Export CSV"),
      h("button", { className: "btn btn-danger", onclick: () => this._clearRecords(c) },
        h("span", { className: "btn-icon", html: icons.trash }), "Clear"),
    );
    c.appendChild(toolbar);

    // Active IO pills bar
    this._recIoPills = h("div", { id: "gps-io-pills", style: "display:flex;gap:4px;flex-wrap:wrap;margin-bottom:8px" });
    c.appendChild(this._recIoPills);
    this._renderIoPills();

    // Table area
    this._recTableArea = h("div");
    c.appendChild(this._recTableArea);

    await this._fetchAndRenderRecords(c);
  },

  async _fetchAndRenderRecords(c) {
    const area = this._recTableArea;
    if (!area) return;
    area.innerHTML = '<div class="spinner"></div>';

    try {
      const recs = await api("/api/gps/records?limit=1000");
      this._recData = recs;
      this._rebuildRecordsTable();
    } catch (e) {
      console.error("[GPS] Load records failed:", e);
      area.innerHTML = "";
      area.appendChild(h("div", { className: "card card-error" },
        h("div", { className: "card-alert" },
          h("div", { className: "card-alert-icon", html: icons.alert }),
          h("div", null,
            h("strong", null, "Failed to load records"),
            h("p", { className: "text-muted", style: "margin-top:4px" }, e.message || String(e))))));
    }
  },

  /** Rebuild table from cached _recData using current column prefs */
  _rebuildRecordsTable() {
    const area = this._recTableArea;
    const recs = this._recData;
    if (!area) return;
    area.innerHTML = "";

    if (!recs || recs.length === 0) {
      area.appendChild(h("div", { className: "empty" },
        h("div", { className: "empty-icon" }, "\u2014"),
        h("p", null, "No records yet. Connect a device to start receiving data.")));
      return;
    }

    const cols = this._loadRecCols();

    // Define base column specs
    const baseSpecs = [
      { key: "Time",    pref: "Time",    render: r => r.Timestamp || "\u2014" },
      { key: "IMEI",    pref: "IMEI",    render: r => h("code", { style: "font-size:11px" }, r.IMEI || "\u2014") },
      { key: "Lat",     pref: "Lat",     render: r => (r.Latitude || 0).toFixed(6) },
      { key: "Lng",     pref: "Lng",     render: r => (r.Longitude || 0).toFixed(6) },
      { key: "Alt",     pref: "Alt",     render: r => String(r.Altitude ?? "\u2014") },
      { key: "Speed",   pref: "Speed",   render: r => String(r.Speed ?? 0) },
      { key: "Angle",   pref: "Angle",   render: r => String(r.Angle ?? 0) + "\u00B0" },
      { key: "Sats",    pref: "Sats",    render: r => String(r.Satellites ?? 0) },
      { key: "Prio",    pref: "Prio",    render: r => String(r.Priority ?? 0) },
      { key: "IOs",     pref: "IOs",     render: r => h("span", { className: "badge badge-primary" },
                                            String(r.Total_IO ?? Object.keys(r.IO_Data || {}).length)) },
      { key: "Event IO", pref: "EventIO", render: r => {
        const eid = r.Event_IO;
        return eid != null ? `${this._ioName(eid)} (${eid})` : "\u2014";
      }},
    ];

    // Visible base columns
    const visCols = baseSpecs.filter(s => cols.base[s.pref] !== false);

    // Pinned IO columns
    const pinnedIos = Object.entries(cols.ios)
      .filter(([, v]) => v)
      .map(([id]) => id)
      .sort((a, b) => parseInt(a) - parseInt(b));

    // Build header
    const headerCells = visCols.map(s => h("th", null, s.key));
    for (const ioId of pinnedIos) {
      const name = this._ioName(parseInt(ioId));
      headerCells.push(h("th", {
        title: `IO ${ioId}: ${name}`,
        style: "color:var(--tk-blue);font-size:10px;max-width:100px;overflow:hidden;text-overflow:ellipsis"
      }, `${name}`));
    }
    headerCells.push(h("th", { style: "width:50px" }, ""));

    const tblWrap = h("div", { className: "table-wrap", style: "max-height:calc(100vh - 290px)" });
    const tbl = h("table");
    tbl.appendChild(h("thead", null, h("tr", null, ...headerCells)));

    const tbody = h("tbody");
    for (const r of recs) {
      const cells = visCols.map(s => {
        const val = s.render(r);
        const td = h("td");
        if (val instanceof HTMLElement) td.appendChild(val);
        else td.textContent = String(val);
        return td;
      });

      // Pinned IO values
      for (const ioId of pinnedIos) {
        const ioData = r.IO_Data || {};
        const v = ioData[ioId] ?? ioData[parseInt(ioId)] ?? ioData[String(ioId)] ?? "\u2014";
        const displayVal = typeof v === "string" && v.length > 16
          ? v.substring(0, 16) + "\u2026" : String(v);
        cells.push(h("td", {
          style: "font-family:var(--font-mono);font-size:11px;color:var(--tk-blue)",
          title: `IO ${ioId} = ${v}`
        }, displayVal));
      }

      // Details button
      cells.push(h("td", null, h("button", {
        className: "btn btn-sm",
        onclick: (e) => { e.stopPropagation(); this._showRecordModal(r); }
      }, "\u2026")));

      tbody.appendChild(h("tr", { style: "cursor:pointer", onclick: () => this._showRecordModal(r) }, ...cells));
    }

    tbl.appendChild(tbody);
    tblWrap.appendChild(tbl);

    area.appendChild(h("div", { className: "text-muted", style: "margin-bottom:6px;font-size:12px" },
      `${recs.length} records \u2022 ${visCols.length} columns \u2022 ${pinnedIos.length} pinned IOs`));
    area.appendChild(tblWrap);
    makeColumnsResizable(tbl, "gps_rec_col_widths");
  },

  /** Show IO pills above the table for quick toggling */
  _renderIoPills() {
    const el = this._recIoPills;
    if (!el) return;
    el.innerHTML = "";
    const cols = this._loadRecCols();
    const pinnedIos = Object.entries(cols.ios).filter(([, v]) => v);
    if (pinnedIos.length === 0) {
      el.appendChild(h("span", { className: "text-muted", style: "font-size:11px" },
        'No pinned IOs \u2014 click "Pin IOs" to add IO columns'));
      return;
    }
    for (const [id] of pinnedIos.sort((a, b) => parseInt(a[0]) - parseInt(b[0]))) {
      const name = this._ioName(parseInt(id));
      el.appendChild(h("span", {
        className: "badge badge-blue",
        style: "cursor:pointer;padding:3px 8px;display:inline-flex;align-items:center;gap:4px",
        title: `Click to unpin IO ${id}`,
        onclick: () => {
          cols.ios[id] = false;
          this._saveRecCols();
          this._renderIoPills();
          this._rebuildRecordsTable();
        }
      },
        `[${id}] ${name}`,
        h("span", { style: "font-size:9px;opacity:0.7" }, "\u2715")));
    }
  },

  /** Column picker modal – toggle base columns */
  _showColumnPicker() {
    const cols = this._loadRecCols();
    const allBase = ["Time", "IMEI", "Lat", "Lng", "Alt", "Speed", "Angle", "Sats", "Prio", "IOs", "EventIO"];

    const modal = h("div", { className: "modal-overlay", onclick: (e) => {
      if (e.target === modal) modal.remove();
    }});
    const content = h("div", { className: "modal-content", style: "max-width:420px" });
    content.appendChild(h("div", {
      style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:12px"
    },
      h("h3", { style: "margin:0" }, "Toggle Columns"),
      h("button", { className: "btn btn-sm", onclick: () => modal.remove() }, "\u2715")));

    const list = h("div", { style: "display:flex;flex-direction:column;gap:4px" });
    for (const key of allBase) {
      const on = cols.base[key] !== false;
      const label = h("label", {
        style: "display:flex;align-items:center;gap:8px;padding:6px 8px;cursor:pointer;" +
               "border-radius:4px;background:rgba(0,0,0,0.15);font-size:13px"
      },
        h("input", {
          type: "checkbox", checked: on ? "checked" : undefined,
          onchange: (e) => {
            cols.base[key] = e.target.checked;
            this._saveRecCols();
          }
        }),
        key);
      list.appendChild(label);
    }
    content.appendChild(list);

    content.appendChild(h("div", { style: "margin-top:14px;display:flex;gap:8px" },
      h("button", { className: "btn", onclick: () => {
        for (const k of allBase) cols.base[k] = true;
        this._saveRecCols();
        modal.remove();
        this._rebuildRecordsTable();
      }}, "Show All"),
      h("button", { className: "btn btn-primary", onclick: () => {
        modal.remove();
        this._rebuildRecordsTable();
      }}, "Apply")));

    modal.appendChild(content);
    document.body.appendChild(modal);
  },

  /** IO picker modal – pin IO columns to the table */
  _showIoPicker() {
    const cols = this._loadRecCols();

    // Discover all IO IDs across loaded records
    const allIoIds = new Set();
    for (const r of (this._recData || [])) {
      for (const k of Object.keys(r.IO_Data || {})) allIoIds.add(String(k));
    }
    // Also include any from io names
    for (const k of Object.keys(this._ioNames)) allIoIds.add(k);
    const sorted = [...allIoIds].sort((a, b) => parseInt(a) - parseInt(b));

    const modal = h("div", { className: "modal-overlay", onclick: (e) => {
      if (e.target === modal) modal.remove();
    }});
    const content = h("div", { className: "modal-content", style: "max-width:600px" });
    content.appendChild(h("div", {
      style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"
    },
      h("h3", { style: "margin:0" }, "Pin IO Columns"),
      h("button", { className: "btn btn-sm", onclick: () => modal.remove() }, "\u2715")));

    content.appendChild(h("p", { className: "text-muted", style: "font-size:12px;margin-bottom:8px" },
      "Select IOs to show as columns in the records table. " +
      "IOs found in current records are shown first."));

    // Quick add by ID
    const quickRow = h("div", { style: "display:flex;gap:6px;margin-bottom:12px" });
    const quickInput = h("input", {
      className: "form-control", type: "text",
      placeholder: "Add IO by ID (e.g. 239, 240, 21)...", style: "flex:1"
    });
    quickRow.appendChild(quickInput);
    quickRow.appendChild(h("button", { className: "btn btn-primary", onclick: () => {
      const ids = quickInput.value.split(/[,\s]+/).map(s => s.trim()).filter(Boolean);
      for (const id of ids) {
        if (/^\d+$/.test(id)) cols.ios[id] = true;
      }
      this._saveRecCols();
      quickInput.value = "";
      renderList();
    }}, "Add"));
    content.appendChild(quickRow);

    // Search filter
    const searchInput = h("input", {
      className: "form-control", placeholder: "Filter IOs by ID or name...",
      style: "width:100%;margin-bottom:8px",
      oninput: () => renderList(searchInput.value)
    });
    content.appendChild(searchInput);

    // Scrollable list
    const listEl = h("div", { style: "max-height:400px;overflow-y:auto" });
    content.appendChild(listEl);

    // Count IOs that appear in data
    const ioFreq = {};
    for (const r of (this._recData || [])) {
      for (const k of Object.keys(r.IO_Data || {})) {
        ioFreq[k] = (ioFreq[k] || 0) + 1;
      }
    }

    const renderList = (filter = "") => {
      listEl.innerHTML = "";
      const f = filter.toLowerCase();
      let items = sorted.filter(id => {
        if (!f) return true;
        const name = this._ioName(parseInt(id));
        return id.includes(f) || name.toLowerCase().includes(f);
      });

      // Sort: pinned first, then those in data, then by ID
      items.sort((a, b) => {
        const pa = cols.ios[a] ? 1 : 0, pb = cols.ios[b] ? 1 : 0;
        if (pa !== pb) return pb - pa;
        const fa = ioFreq[a] || 0, fb = ioFreq[b] || 0;
        if (fa !== fb) return fb - fa;
        return parseInt(a) - parseInt(b);
      });

      for (const id of items) {
        const name = this._ioName(parseInt(id));
        const pinned = !!cols.ios[id];
        const freq = ioFreq[id] || 0;
        const row = h("label", {
          style: "display:flex;align-items:center;gap:8px;padding:5px 8px;cursor:pointer;" +
                 "border-radius:4px;font-size:12px;" +
                 (pinned ? "background:rgba(59,130,246,0.12);border:1px solid rgba(59,130,246,0.3)" :
                           "background:rgba(0,0,0,0.12);border:1px solid transparent") +
                 ";margin-bottom:3px"
        },
          h("input", {
            type: "checkbox", checked: pinned ? "checked" : undefined,
            onchange: (e) => {
              cols.ios[id] = e.target.checked;
              this._saveRecCols();
              renderList(searchInput.value);
            }
          }),
          h("span", { style: "font-family:var(--font-mono);min-width:40px;color:var(--tk-fg-dim)" }, `[${id}]`),
          h("span", { style: "flex:1" }, name),
          freq > 0
            ? h("span", { className: "badge badge-green", style: "font-size:10px" }, `${freq}x`)
            : h("span", { className: "text-muted", style: "font-size:10px" }, "no data")
        );
        listEl.appendChild(row);
      }
      if (!items.length) {
        listEl.appendChild(h("span", { className: "text-muted" }, "No matching IOs"));
      }
    };
    renderList();

    // Common IOs quick buttons
    const commonIos = [
      ["Ignition", "239"], ["Movement", "240"], ["GSM Signal", "21"],
      ["GNSS Status", "69"], ["Ext Voltage", "66"], ["Battery V", "67"],
      ["Odometer", "16"], ["Speed", "24"], ["DIN1", "1"], ["ICCID", "11"],
    ];
    const quickBtns = h("div", { style: "display:flex;flex-wrap:wrap;gap:4px;margin-top:10px" },
      h("span", { className: "text-muted", style: "font-size:11px;margin-right:4px;line-height:26px" }, "Quick:"),
      ...commonIos.map(([label, id]) =>
        h("button", {
          className: "btn btn-sm" + (cols.ios[id] ? " btn-primary" : ""),
          style: "font-size:11px",
          onclick: () => {
            cols.ios[id] = !cols.ios[id];
            this._saveRecCols();
            renderList(searchInput.value);
          }
        }, `${label} (${id})`))
    );
    content.appendChild(quickBtns);

    content.appendChild(h("div", { style: "margin-top:14px;display:flex;gap:8px" },
      h("button", { className: "btn btn-danger", onclick: () => {
        for (const k of Object.keys(cols.ios)) cols.ios[k] = false;
        this._saveRecCols();
        renderList();
      }}, "Clear All"),
      h("button", { className: "btn btn-primary", onclick: () => {
        modal.remove();
        this._renderIoPills();
        this._rebuildRecordsTable();
      }}, "Apply")));

    modal.appendChild(content);
    document.body.appendChild(modal);
  },

  _showRecordModal(r) {
    const modal = h("div", { className: "modal-overlay", onclick: (e) => {
      if (e.target === modal) modal.remove();
    }});
    const content = h("div", { className: "modal-content", style: "max-width:950px" });

    // Header
    content.appendChild(h("div", { style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:14px" },
      h("h3", { style: "margin:0" }, `Record: ${r.Timestamp || "Unknown"}`),
      h("button", { className: "btn btn-sm", onclick: () => modal.remove() }, "\u2715")
    ));

    // GPS Data section
    const gpsGrid = h("div", { className: "io-grid" });
    const gpsFields = [
      ["IMEI", r.IMEI], ["Protocol", r.Protocol],
      ["Timestamp", r.Timestamp], ["Timestamp (ms)", r.Timestamp_ms],
      ["Priority", r.Priority],
      ["Latitude", (r.Latitude || 0).toFixed(7)], ["Longitude", (r.Longitude || 0).toFixed(7)],
      ["Altitude", `${r.Altitude ?? 0}m`], ["Speed", r.Speed ?? 0],
      ["Angle", `${r.Angle ?? 0}\u00B0`], ["Satellites", r.Satellites ?? 0],
      ["Event IO", r.Event_IO != null ? `${this._ioName(r.Event_IO)} (${r.Event_IO})` : "—"],
      ["Total IOs", r.Total_IO ?? 0],
    ];
    for (const [k, v] of gpsFields) {
      gpsGrid.appendChild(h("div", { className: "io-item" },
        h("span", { className: "io-key" }, k),
        h("span", { className: "io-val" }, String(v ?? "—"))));
    }
    content.appendChild(h("div", { style: "margin-bottom:16px" },
      h("h4", { style: "margin-bottom:8px;color:var(--tk-green);font-size:13px" }, "\uD83D\uDCCD GPS Data"),
      gpsGrid));

    // IO Data section – ALL IOs with names
    const ioData = r.IO_Data || {};
    const ioEntries = Object.entries(ioData);
    if (ioEntries.length > 0) {
      // Sort by ID numerically
      ioEntries.sort((a, b) => {
        try { return parseInt(a[0]) - parseInt(b[0]); } catch { return 0; }
      });

      const ioGrid = h("div", { className: "io-grid" });
      for (const [id, val] of ioEntries) {
        let name;
        try { name = this._ioName(parseInt(id)); } catch { name = `IO_${id}`; }

        const displayVal = typeof val === "string" && val.length > 20
          ? val.substring(0, 20) + "\u2026" : String(val);

        const item = h("div", {
          className: "io-item",
          title: `AVL ID: ${id}\nName: ${name}\nValue: ${val}\nType: ${typeof val}`
        },
          h("span", { className: "io-key" }, `[${id}] ${name}`),
          h("span", { className: "io-val" }, displayVal));
        ioGrid.appendChild(item);
      }

      content.appendChild(h("div", { style: "margin-bottom:16px" },
        h("h4", { style: "margin-bottom:8px;color:var(--tk-blue,#3b82f6);font-size:13px" },
          `\uD83D\uDD27 IO Elements (${ioEntries.length})`),
        ioGrid));
    }

    // Raw JSON (collapsible)
    const rawPre = h("pre", { style: "max-height:200px;overflow:auto;display:none" },
      JSON.stringify(r, null, 2));
    const toggleBtn = h("button", { className: "btn btn-sm", onclick: () => {
      const show = rawPre.style.display === "none";
      rawPre.style.display = show ? "block" : "none";
      toggleBtn.textContent = show ? "Hide Raw JSON" : "Show Raw JSON";
    }}, "Show Raw JSON");

    content.appendChild(h("div", { style: "margin-top:12px" }, toggleBtn, rawPre));

    // Action buttons
    content.appendChild(h("div", { style: "margin-top:14px;display:flex;gap:8px" },
      h("button", { className: "btn", onclick: () => {
        navigator.clipboard.writeText(JSON.stringify(r, null, 2));
        toast("Copied to clipboard", "success");
      }}, "Copy JSON"),
      h("button", { className: "btn btn-primary", onclick: () => modal.remove() }, "Close")
    ));

    modal.appendChild(content);
    document.body.appendChild(modal);
  },

  async _exportRecords(fmt) {
    try {
      if (fmt === "json") {
        const link = document.createElement("a");
        link.href = "/api/gps/records/export";
        link.download = "gps_records.json";
        document.body.appendChild(link);
        link.click();
        link.remove();
        toast("Downloading records as JSON", "success");
        return;
      }
      // CSV: fetch data, convert client-side
      const recs = await api("/api/gps/records?limit=10000");
      if (!recs?.length) { toast("No records to export", "info"); return; }

      // Collect all IO keys across records
      const ioKeys = new Set();
      for (const r of recs) {
        for (const k of Object.keys(r.IO_Data || {})) ioKeys.add(k);
      }
      const sortedIoKeys = [...ioKeys].sort((a, b) => parseInt(a) - parseInt(b));

      // CSV header
      const baseCols = ["Timestamp", "IMEI", "Protocol", "Priority", "Latitude", "Longitude",
        "Altitude", "Speed", "Angle", "Satellites", "Event_IO", "Total_IO"];
      const ioCols = sortedIoKeys.map(k => {
        const name = this._ioName(parseInt(k));
        return `IO_${k}_${name}`;
      });
      const allCols = [...baseCols, ...ioCols];

      let csv = allCols.join(",") + "\n";
      for (const r of recs) {
        const baseVals = baseCols.map(c => {
          const v = r[c] ?? "";
          const s = String(v);
          return s.includes(",") || s.includes('"') ? `"${s.replace(/"/g, '""')}"` : s;
        });
        const ioVals = sortedIoKeys.map(k => {
          const v = (r.IO_Data || {})[k] ?? (r.IO_Data || {})[parseInt(k)] ?? "";
          const s = String(v);
          return s.includes(",") || s.includes('"') ? `"${s.replace(/"/g, '""')}"` : s;
        });
        csv += [...baseVals, ...ioVals].join(",") + "\n";
      }

      const blob = new Blob([csv], { type: "text/csv" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = "gps_records.csv";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(link.href);
      toast(`Exported ${recs.length} records as CSV`, "success");
    } catch (e) { toast("Export failed: " + e.message, "error"); }
  },

  async _clearRecords(c) {
    if (!confirm("Clear all GPS records? This cannot be undone.")) return;
    try {
      const r = await api("/api/gps/records/clear", { method: "POST" });
      toast(r.msg || "Records cleared", "success");
      if (c) this._renderRecords(c);
    } catch (e) { toast("Clear failed: " + e.message, "error"); }
  },

  /* ── Raw data ─────────────────────────────────────────── */
  async _renderRaw(c) {
    c.innerHTML = "";
    const container = h("div");

    const dirFilter = h("select", {
      className: "form-control", style: "width:110px",
      onchange: () => this._loadRaw(container)
    },
      h("option", { value: "" }, "All"),
      h("option", { value: "RX" }, "\u2B07 RX (In)"),
      h("option", { value: "TX" }, "\u2B06 TX (Out)")
    );
    this._rawDirFilter = dirFilter;

    const searchInput = h("input", {
      className: "form-control", type: "text",
      placeholder: "Search hex...", style: "width:200px",
      onkeydown: (e) => { if (e.key === "Enter") this._loadRaw(container); }
    });
    this._rawSearchInput = searchInput;

    c.appendChild(h("div", { className: "btn-group", style: "margin-bottom:12px;flex-wrap:wrap;align-items:center" },
      dirFilter, searchInput,
      h("button", { className: "btn", onclick: () => this._loadRaw(container) },
        h("span", { className: "btn-icon", html: icons.refresh }), "Refresh"),
      h("button", { className: "btn btn-primary", onclick: () => this._loadRaw(container, true) },
        h("span", { className: "btn-icon", html: icons.search }), "Annotate All"),
    ));
    c.appendChild(container);
    this._loadRaw(container);
  },

  async _loadRaw(container, annotate = false) {
    container.innerHTML = '<div class="spinner"></div>';
    const dir = this._rawDirFilter?.value || "";
    const search = this._rawSearchInput?.value || "";

    try {
      let url = `/api/gps/raw?limit=100`;
      if (dir) url += `&direction=${dir}`;
      if (search) url += `&search=${encodeURIComponent(search)}`;
      if (annotate) url += `&annotate=true`;

      const raw = await api(url);
      container.innerHTML = "";

      if (!raw?.length) {
        container.appendChild(h("div", { className: "empty" },
          h("div", { className: "empty-icon" }, "\u2014"),
          h("p", null, "No raw data yet")));
        return;
      }

      container.appendChild(h("div", { className: "text-muted", style: "margin-bottom:8px;font-size:12px" },
        `${raw.length} packets shown`));

      for (let i = 0; i < raw.length; i++) {
        const pkt = raw[i];
        const card = h("div", { className: "card", style: "margin-bottom:8px;padding:12px" });

        // Direction badge
        const isRx = pkt.direction === "RX";
        const dirBadge = h("span", { className: isRx ? "badge badge-blue" : "badge badge-yellow" },
          isRx ? "\u2B07 RX" : "\u2B06 TX");

        // Header
        card.appendChild(h("div", {
          style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"
        },
          h("div", { style: "display:flex;gap:6px;align-items:center" },
            dirBadge,
            h("span", { className: "badge badge-primary" }, pkt.protocol || "TCP"),
            h("span", { className: "text-muted", style: "font-size:12px" }, `${pkt.length || 0} bytes`)),
          h("div", { style: "display:flex;gap:6px;align-items:center" },
            h("span", { className: "text-muted", style: "font-size:12px" }, pkt.timestamp || ""),
            h("button", { className: "btn btn-sm", "data-idx": i, onclick: async (e) => {
              e.stopPropagation();
              await this._annotatePacket(i, card, pkt);
            }}, "Annotate"),
            h("button", { className: "btn btn-sm", onclick: () => {
              navigator.clipboard.writeText(pkt.hex || "");
              toast("Hex copied", "success");
            }}, "Copy")
          )
        ));

        // Hex content
        if (pkt.annotations?.length) {
          this._renderAnnotatedHex(card, pkt);
        } else {
          const hexDiv = h("div", { className: "hex-viewer", style: "word-break:break-all;font-size:12px" });
          const hex = (pkt.hex || "").replace(/(.{2})/g, "$1 ").trim();
          hexDiv.textContent = hex;
          card.appendChild(hexDiv);
        }

        container.appendChild(card);
      }
    } catch (e) {
      console.error("[GPS] Load raw failed:", e);
      container.innerHTML = `<div class="card card-error"><p>Failed to load raw data: ${e.message}</p></div>`;
    }
  },

  _renderAnnotatedHex(card, pkt) {
    // Remove old hex/legend
    const oldHex = card.querySelector(".hex-viewer");
    if (oldHex) oldHex.remove();
    const oldLeg = card.querySelector(".hex-legend");
    if (oldLeg) oldLeg.remove();

    // Map backend {s,e} to {start,end} for renderHex
    const mapped = (pkt.annotations || []).map(a => ({ ...a, start: a.s, end: a.e }));
    renderHex(card, pkt.hex || "", mapped);

    // Legend
    const legend = h("div", { className: "hex-legend", style: "margin-top:6px" });
    for (const ann of pkt.annotations) {
      legend.appendChild(h("span", {
        style: `background:${ann.color || "#666"};font-size:10px;padding:1px 5px`
      }, ann.label));
    }
    card.appendChild(legend);
  },

  async _annotatePacket(index, card, pkt) {
    try {
      const res = await api(`/api/gps/raw/${index}/annotate`);
      if (res.annotations?.length) {
        pkt.annotations = res.annotations;
        this._renderAnnotatedHex(card, pkt);
        toast("Packet annotated", "success");
      } else {
        toast("No annotations available", "info");
      }
    } catch (e) { toast("Annotate failed: " + e.message, "error"); }
  },

  /* ── Commands ─────────────────────────────────────────── */
  _renderCommands(c) {
    c.innerHTML = "";

    // IMEI selector
    const imeiSelect = h("select", { id: "gps-cmd-imei", className: "form-control", style: "width:200px" },
      h("option", { value: "" }, "Select device..."));
    this._cmdImeiSelect = imeiSelect;

    // Populate from connected devices
    const devs = this._data.devices || {};
    for (const imei of Object.keys(devs)) {
      imeiSelect.appendChild(h("option", { value: imei }, imei));
    }
    // If only one device, auto-select it
    const devKeys = Object.keys(devs);
    if (devKeys.length === 1) imeiSelect.value = devKeys[0];

    // Command input
    const cmdInput = h("input", {
      id: "gps-cmd", className: "form-control",
      placeholder: "AT command (e.g. getinfo)...",
      style: "flex:1;min-width:200px",
      onkeydown: e => { if (e.key === "Enter") this._sendCmd(); }
    });

    c.appendChild(h("div", { className: "card" },
      h("h3", null, "Send AT Command"),
      h("div", { style: "display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap" },
        imeiSelect, cmdInput,
        h("button", { className: "btn btn-primary", onclick: () => this._sendCmd() },
          h("span", { className: "btn-icon", html: icons.send }), "Send")),
      // Quick commands
      h("div", { style: "margin-top:4px" },
        h("span", { className: "text-muted", style: "font-size:11px;margin-right:8px" }, "Quick:"),
        ...["getinfo", "getver", "getparam 2001", "readio 239", "readio 240", "getgps",
            "readio 21", "readio 66", "readio 67", "readio 16"]
          .map(cmd => h("button", {
            className: "btn btn-sm", style: "margin:2px",
            onclick: () => { cmdInput.value = cmd; this._sendCmd(); }
          }, cmd))
      )
    ));

    // Command history
    c.appendChild(h("div", { className: "card" },
      h("div", { style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:8px" },
        h("h3", { style: "margin:0" }, "Command History"),
        h("button", { className: "btn btn-sm", onclick: () => this._loadCmdHistory() },
          h("span", { className: "btn-icon", html: icons.refresh }), "Refresh")),
      h("div", { id: "gps-cmd-history" })
    ));
    this._loadCmdHistory();
  },

  async _sendCmd() {
    const inp = $("#gps-cmd");
    const sel = this._cmdImeiSelect;
    if (!inp?.value) { toast("Enter a command", "error"); return; }
    if (!sel?.value) { toast("Select a device first", "error"); return; }

    const cmd = inp.value;
    const imei = sel.value;
    inp.value = "";

    console.log(`[GPS] Sending command to ${imei}: ${cmd}`);
    try {
      const r = await api("/api/gps/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ imei, command: cmd }),
      });
      toast(r.ok ? `Command queued for ${imei}` : "Send failed", r.ok ? "success" : "error");
      setTimeout(() => this._loadCmdHistory(), 2000);
    } catch (e) { toast("Command failed: " + e.message, "error"); }
  },

  async _loadCmdHistory() {
    const container = $("#gps-cmd-history");
    if (!container) return;
    try {
      const hist = await api("/api/gps/history?limit=50");
      container.innerHTML = "";
      if (!hist?.length) {
        container.innerHTML = '<span class="text-muted">No command history yet</span>';
        return;
      }
      const tbl = h("table", { style: "font-size:12px" });
      tbl.appendChild(h("thead", null, h("tr", null,
        ...["Time", "IMEI", "Command", "Response", "Proto", "Duration"].map(t => h("th", null, t))
      )));
      const tbody = h("tbody");
      for (const e of hist) {
        const dur = e.duration_ms >= 0 ? `${e.duration_ms}ms` : "\u2014";
        const respCls = (e.response || "").includes("TIMEOUT") ? "text-red" : "";
        tbody.appendChild(h("tr", null,
          h("td", { style: "white-space:nowrap" }, e.timestamp || ""),
          h("td", null, h("code", { style: "font-size:11px" }, e.imei || "")),
          h("td", null, h("code", { style: "font-size:11px;color:var(--tk-green)" }, e.command || "")),
          h("td", { className: respCls, style: "max-width:350px;overflow:hidden;text-overflow:ellipsis" },
            e.response || "\u2014"),
          h("td", null, h("span", { className: "badge badge-primary" }, e.protocol || "")),
          h("td", { style: "font-family:var(--font-mono);font-size:11px" }, dur),
        ));
      }
      tbl.appendChild(tbody);
      container.appendChild(h("div", { className: "table-wrap", style: "max-height:400px" }, tbl));
      makeColumnsResizable(tbl, "gps_cmd_col_widths");
    } catch (e) {
      console.error("[GPS] Load history failed:", e);
      container.innerHTML = '<p class="text-muted">Failed to load command history</p>';
    }
  },

  /* ── Logs ─────────────────────────────────────────────── */
  async _renderLogs(c) {
    c.innerHTML = "";

    const searchInput = h("input", {
      className: "form-control", type: "text",
      placeholder: "Search logs...", style: "width:250px",
      onkeydown: (e) => { if (e.key === "Enter") loadLogs(); }
    });

    c.appendChild(h("div", { className: "btn-group", style: "margin-bottom:12px" },
      searchInput,
      h("button", { className: "btn", onclick: () => loadLogs() },
        h("span", { className: "btn-icon", html: icons.refresh }), "Refresh"),
    ));

    const logContainer = h("div", { className: "log-container", style: "max-height:calc(100vh - 220px)" });
    c.appendChild(logContainer);

    const loadLogs = async () => {
      logContainer.innerHTML = '<div class="spinner"></div>';
      try {
        const search = searchInput.value;
        let url = "/api/gps/logs?limit=500";
        if (search) url += `&search=${encodeURIComponent(search)}`;
        const logs = await api(url);
        logContainer.innerHTML = "";
        if (!logs?.length) {
          logContainer.innerHTML = '<span class="text-muted" style="padding:8px">No logs</span>';
          return;
        }
        for (const e of logs) {
          const tp = (e.type || "").toUpperCase();
          let badge = "primary";
          if (tp.includes("ERR")) badge = "danger";
          else if (tp.includes("WARN")) badge = "warning";
          else if (tp === "STOP" || tp === "DISC") badge = "red";
          else if (tp === "START" || tp === "CONN" || tp === "ACK") badge = "green";
          else if (tp === "DATA" || tp === "IMEI") badge = "blue";
          else if (tp === "CMD" || tp === "RESP") badge = "yellow";
          logContainer.appendChild(h("div", { className: "log-line" },
            h("span", { className: "text-muted", style: "margin-right:8px;font-size:11px;min-width:70px;display:inline-block" },
              e.timestamp || ""),
            h("span", {
              className: `badge badge-${badge}`,
              style: "margin-right:8px;min-width:55px;text-align:center;font-size:10px"
            }, tp),
            e.message || ""));
        }
      } catch (e) {
        logContainer.innerHTML = `<p class="text-muted">Failed to load logs: ${e.message}</p>`;
      }
    };

    loadLogs();
  },

  /* ── Settings ─────────────────────────────────────────── */
  async _renderSettings(c) {
    c.innerHTML = '<div class="spinner"></div>';
    try {
      const cfg = await api("/api/gps/settings");
      c.innerHTML = "";

      // ─── Server Configuration Card ───
      const serverCard = h("div", { className: "card" });
      serverCard.appendChild(h("h3", null, "Server Configuration"));

      const form = h("form", { onsubmit: (e) => e.preventDefault() });

      form.appendChild(h("div", { className: "form-row" },
        h("div", { className: "form-group", style: "flex:1" },
          h("label", null, "Server Port"),
          h("input", {
            id: "gps-port", className: "form-control", type: "number",
            value: String(cfg.port || 7580), style: "width:100%"
          })),
        h("div", { className: "form-group", style: "flex:1" },
          h("label", null, "Protocol (TCP or UDP, single port)"),
          h("select", { id: "gps-proto", className: "form-control", style: "width:100%" },
            ["TCP", "UDP"].map(p =>
              h("option", { value: p, selected: (cfg.protocol || "TCP") === p }, p))
          ))
      ));

      form.appendChild(h("button", {
        className: "btn btn-primary", style: "margin-top:8px",
        onclick: async () => {
          try {
            const port = Number($("#gps-port").value);
            const protocol = $("#gps-proto").value;
            if (!port || port < 1 || port > 65535) {
              toast("Invalid port number (1-65535)", "error"); return;
            }
            const payload = { port, protocol };
            console.log("[GPS] Saving settings:", payload);
            const res = await api("/api/gps/settings", {
              method: "PUT",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(payload),
            });
            toast(res.ok ? (res.msg || "Settings saved") : ("Error: " + (res.msg || "Unknown")),
                  res.ok ? "success" : "error");
            this._loadStatus();
          } catch (e) { toast("Save failed: " + e.message, "error"); }
        }
      }, "Save & Restart Server"));

      serverCard.appendChild(form);
      c.appendChild(serverCard);

      // ─── AVL IO Names Card ───
      const avlCard = h("div", { className: "card" });
      avlCard.appendChild(h("h3", null, "AVL IO Element Names"));
      avlCard.appendChild(h("p", { className: "text-muted", style: "font-size:12px;margin-bottom:10px" },
        "Load IO element names from FMB_AVL_IDS.xlsx to display human-readable names " +
        "(e.g. IO 239 \u2192 \"Ignition\", IO 240 \u2192 \"Movement\"). " +
        "Uses the 'MainTable' sheet or active sheet."));

      avlCard.appendChild(h("div", { className: "form-group" },
        h("label", null, "AVL IDs Excel Path (.xlsx)"),
        h("input", {
          id: "gps-avl-path", className: "form-control", type: "text",
          value: cfg.avl_ids_path || "",
          placeholder: "C:\\path\\to\\FMB_AVL_IDS.xlsx",
          style: "width:100%"
        }),
        h("small", { className: "text-muted" },
          "Full path to the .xlsx file containing AVL IO definitions")
      ));

      const ioStatusEl = h("div", {
        style: "font-size:12px;margin-top:6px;padding:4px 8px;border-radius:4px;background:rgba(0,0,0,0.15)"
      },
        `Currently loaded: ${Object.keys(this._ioNames).length} IO names`);

      avlCard.appendChild(h("div", { className: "btn-group", style: "margin-top:10px" },
        h("button", {
          className: "btn btn-primary",
          onclick: async () => {
            const path = $("#gps-avl-path")?.value;
            if (!path) { toast("Enter AVL IDs file path first", "error"); return; }

            // Save path to config
            try {
              await api("/api/gps/settings", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ avl_ids_path: path }),
              });
            } catch (e) {
              toast("Failed to save path: " + e.message, "error"); return;
            }

            // Refresh IO names
            try {
              const r = await api("/api/gps/avl/refresh", { method: "POST" });
              if (r.ok) {
                toast(r.msg || "IO names updated", "success");
                await this._loadIoNames();
                ioStatusEl.textContent = `\u2705 Loaded: ${Object.keys(this._ioNames).length} IO names`;
                ioStatusEl.style.color = "var(--tk-green)";
              } else {
                toast(r.msg || "Failed to load AVL IDs", "error");
                ioStatusEl.textContent = `\u274C Error: ${r.msg}`;
                ioStatusEl.style.color = "var(--tk-red)";
              }
            } catch (e) {
              toast("Refresh failed: " + e.message, "error");
              ioStatusEl.textContent = `\u274C Error: ${e.message}`;
              ioStatusEl.style.color = "var(--tk-red)";
            }
          }
        }, "Update IO Names"),
        h("button", { className: "btn", onclick: () => this._showIoNamesModal() },
          "View All IO Names"),
      ));

      avlCard.appendChild(ioStatusEl);
      c.appendChild(avlCard);

    } catch (e) {
      console.error("[GPS] Load settings failed:", e);
      c.innerHTML = `<div class="card card-error"><p>Failed to load settings: ${e.message}</p></div>`;
    }
  },

  _showIoNamesModal() {
    const modal = h("div", { className: "modal-overlay", onclick: (e) => {
      if (e.target === modal) modal.remove();
    }});
    const content = h("div", { className: "modal-content", style: "max-width:750px" });

    content.appendChild(h("div", {
      style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:12px"
    },
      h("h3", { style: "margin:0" }, `IO Element Names (${Object.keys(this._ioNames).length})`),
      h("button", { className: "btn btn-sm", onclick: () => modal.remove() }, "\u2715")
    ));

    // Search
    const grid = h("div", { className: "io-grid", style: "max-height:500px;overflow-y:auto" });
    const searchInput = h("input", {
      className: "form-control",
      placeholder: "Search by ID or name...",
      style: "margin-bottom:12px;width:100%"
    });

    const render = (filter = "") => {
      grid.innerHTML = "";
      const f = filter.toLowerCase();
      const entries = Object.entries(this._ioNames)
        .filter(([id, name]) => !f || id.includes(f) || name.toLowerCase().includes(f))
        .sort((a, b) => parseInt(a[0]) - parseInt(b[0]));

      for (const [id, name] of entries) {
        grid.appendChild(h("div", { className: "io-item" },
          h("span", { className: "io-key" }, `[${id}]`),
          h("span", { className: "io-val" }, name)));
      }
      if (!entries.length) {
        grid.appendChild(h("span", { className: "text-muted" }, "No matches"));
      }
    };

    searchInput.addEventListener("input", () => render(searchInput.value));
    render();

    content.append(searchInput, grid,
      h("button", {
        className: "btn btn-primary", style: "margin-top:12px",
        onclick: () => modal.remove()
      }, "Close"));

    modal.appendChild(content);
    document.body.appendChild(modal);
  },
});
