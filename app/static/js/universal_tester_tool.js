/* ================================================================
   Universal Tester Tool Plugin – Drag/Drop Test Case Builder (FMB)
   ================================================================ */
import { h, $, $$, api, toast, registerPlugin, icons } from "./core.js";

const PLUGIN_ID = "universal_tester_tool";
let _catalog = [];
let _cases = [];
let _currentCase = null;
let _ws = null;
let _logEl = null;

// ── Background WebSocket for global notifications ──────────
let _bgWs = null;
let _bgWsTimer = null;
let _lastBgStatus = "";    // track status transitions
let _lastBgStep = -1;      // track step transitions
let _lastBgStepStatus = "";

function _connectBackgroundWS() {
  if (_bgWs && _bgWs.readyState <= 1) return;
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  _bgWs = new WebSocket(`${proto}//${location.host}/ws/universal-tester-tool`);
  _bgWs.onmessage = (evt) => {
    try {
      const data = JSON.parse(evt.data);
      _notifyFromStatus(data);
    } catch {}
  };
  _bgWs.onclose = () => { _bgWs = null; };
  _bgWs.onerror = () => { try { _bgWs.close(); } catch {} _bgWs = null; };
}

function _notifyFromStatus(data) {
  const st = data.status;
  const steps = data.steps || [];
  const curIdx = data.current_step;

  // Status transition notifications
  if (st !== _lastBgStatus) {
    if (st === "completed") toast("Universal Tester Tool test completed!", "success", 5000);
    else if (st === "failed") {
      const reason = data.fail_reason === "com_port"
        ? "Universal Tester Tool test failed: COM port busy — close the port & STOP & KILL"
        : "Universal Tester Tool test failed";
      toast(reason, "error", 8000);
    } else if (st === "stopped") toast("Universal Tester Tool test stopped", "warn", 4000);
    else if (st === "running" && _lastBgStatus && _lastBgStatus !== "running")
      toast("Universal Tester Tool test started", "info", 3000);
    _lastBgStatus = st;
  }

  // Step transition notifications (only while running)
  if (st === "running" && curIdx >= 0 && curIdx < steps.length) {
    const step = steps[curIdx];
    if (curIdx !== _lastBgStep || step.status !== _lastBgStepStatus) {
      if (step.status === "running") {
        toast(`Step ${curIdx + 1}: ${step.label}${step.detail ? " — " + step.detail : ""}`, "info", 3000);
      } else if (step.status === "failed") {
        toast(`Step ${curIdx + 1} FAILED: ${step.label}`, "error", 5000);
      }
      _lastBgStep = curIdx;
      _lastBgStepStatus = step.status;
    }
  }

  // Reset tracking when idle
  if (st === "idle") {
    _lastBgStep = -1;
    _lastBgStepStatus = "";
  }
}

// Start background WS on page load, auto-reconnect every 3s
_connectBackgroundWS();
_bgWsTimer = setInterval(_connectBackgroundWS, 3000);

// ── Helpers ────────────────────────────────────────────────────────

function uid() { return Math.random().toString(36).slice(2, 9); }

function blankCase() {
  return {
    name: "New Test Case",
    device_name: "FMB_Device",
    firmware: "03.29.00",
    run_time: "0s",
    iterations: 1,
    interfaces: { terminal_port: "COM7", baudrate: 115200, catcher_port: "", use_otii: false },
    steps: [],
  };
}

// ── Drag/Drop state ────────────────────────────────────────────────

let _dragData = null;

// ── Main render ────────────────────────────────────────────────────

registerPlugin({
  id: PLUGIN_ID, name: "Universal Tester Tool", order: 15,
  svgIcon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 2v6m6-6v6M9 16v6m6-6v6M2 9h6m8 0h6M2 15h6m8 0h6"/><rect x="7" y="7" width="10" height="10" rx="1"/></svg>`,

  init(container) {
    this._c = container;
    this._boot();
  },

  destroy() {
    if (_ws) { try { _ws.close(); } catch {} _ws = null; }
  },

  async _boot() {
    try {
      _catalog = await api(`/api/${PLUGIN_ID}/catalog`);
      _cases = await api(`/api/${PLUGIN_ID}/cases`);
    } catch (e) {
      this._c.innerHTML = "";
      this._c.appendChild(h("div", { className: "card" },
        h("p", { className: "text-muted" }, "Universal Tester Tool unavailable: " + e.message)));
      return;
    }
    _currentCase = null;
    this._renderMain();
  },

  _renderMain() {
    const c = this._c; c.innerHTML = "";

    // Top bar: case list + controls
    const topBar = h("div", { className: "utt-topbar" },
      h("h2", null, "Universal Tester Tool"),
      h("div", { className: "utt-topbar-actions" },
        h("button", { className: "btn btn-primary", onclick: () => this._newCase() },
          "+ New Test Case"),
      ),
    );
    c.appendChild(topBar);

    if (!_currentCase) {
      // Show case list
      this._renderCaseList(c);
    } else {
      // Show editor
      this._renderEditor(c);
    }
  },

  _renderCaseList(c) {
    // Settings card (Universal Tester Tool path + log directory)
    this._renderSettingsCard(c);

    if (!_cases.length) {
      c.appendChild(h("div", { className: "utt-empty card" },
        h("div", { style: { textAlign: "center", padding: "2rem" } },
          h("p", { style: { fontSize: "3rem" } }, "🧪"),
          h("p", null, "No test cases yet. Create one to get started!"),
        )));
      return;
    }
    const grid = h("div", { className: "utt-cases-grid" });
    for (const cs of _cases) {
      const card = h("div", { className: "card utt-case-card", onclick: () => this._loadCase(cs.id) },
        h("div", { className: "utt-case-header" },
          h("strong", null, cs.name),
          h("button", { className: "btn btn-danger btn-sm", onclick: async (e) => {
            e.stopPropagation();
            if (!confirm(`Delete "${cs.name}"?`)) return;
            await api(`/api/${PLUGIN_ID}/cases/${cs.id}`, { method: "DELETE" });
            _cases = await api(`/api/${PLUGIN_ID}/cases`);
            this._renderMain();
          }}, "✕"),
        ),
        h("div", { className: "utt-case-meta text-muted" },
          h("span", null, `Device: ${cs.device_name}`),
          h("span", null, `Steps: ${cs.steps_count}`),
          h("span", null, `Iterations: ${cs.iterations}`),
        ),
      );
      grid.appendChild(card);
    }
    c.appendChild(grid);

    // Run status section
    this._renderStatusSection(c);
  },

  _newCase() {
    _currentCase = blankCase();
    this._renderMain();
  },

  async _loadCase(id) {
    try {
      _currentCase = await api(`/api/${PLUGIN_ID}/cases/${id}`);
      this._renderMain();
    } catch (e) { toast("Failed to load case: " + e.message, "error"); }
  },

  _renderEditor(c) {
    const cs = _currentCase;

    // Back button
    c.appendChild(h("button", { className: "btn", style: { marginBottom: "1rem" },
      onclick: () => { _currentCase = null; this._boot(); } },
      "← Back to Cases"));

    const editorWrap = h("div", { className: "utt-editor" });

    // ── Left panel: Step palette ───────────────────────────────
    const palette = h("div", { className: "utt-palette" });
    palette.appendChild(h("h3", null, "Available Steps"));
    palette.appendChild(h("p", { className: "text-muted", style: { fontSize: "0.8rem" } },
      "Drag steps to the sequence area →"));

    const categories = {};
    for (const s of _catalog) {
      if (!categories[s.category]) categories[s.category] = [];
      categories[s.category].push(s);
    }
    for (const [cat, items] of Object.entries(categories)) {
      palette.appendChild(h("div", { className: "utt-cat-label" }, cat));
      for (const item of items) {
        const el = h("div", {
          className: "utt-palette-item",
          draggable: "true",
        },
          h("span", { className: "utt-step-icon" }, item.icon),
          h("div", null,
            h("strong", null, item.label),
            h("div", { className: "text-muted", style: { fontSize: "0.75rem" } }, item.description),
          ),
        );
        el.addEventListener("dragstart", (e) => {
          _dragData = { source: "palette", type: item.type };
          e.dataTransfer.effectAllowed = "copy";
          e.dataTransfer.setData("text/plain", item.type);
          el.classList.add("dragging");
        });
        el.addEventListener("dragend", () => {
          el.classList.remove("dragging");
          _dragData = null;
        });
        palette.appendChild(el);
      }
    }

    // ── Center: Config header + Sequence ───────────────────────
    const center = h("div", { className: "utt-center" });

    // Case config
    const configCard = h("div", { className: "card utt-config-card" });
    configCard.appendChild(h("h3", null, "Test Case Configuration"));
    const configGrid = h("div", { className: "utt-config-grid" });

    const mkInput = (label, key, val, type = "text", opts = {}) => {
      const inp = h("input", {
        type, value: val, placeholder: label,
        className: "utt-input",
        ...opts,
      });
      inp.addEventListener("change", () => {
        if (type === "number") cs[key] = parseInt(inp.value) || 0;
        else cs[key] = inp.value;
      });
      return h("label", { className: "utt-field" }, h("span", null, label), inp);
    };

    const mkIfaceInput = (label, key, val, type = "text") => {
      const inp = h("input", {
        type, value: val, placeholder: label,
        className: "utt-input",
      });
      inp.addEventListener("change", () => {
        if (!cs.interfaces) cs.interfaces = {};
        if (type === "number") cs.interfaces[key] = parseInt(inp.value) || 0;
        else cs.interfaces[key] = inp.value;
      });
      return h("label", { className: "utt-field" }, h("span", null, label), inp);
    };

    configGrid.appendChild(mkInput("Test Name", "name", cs.name));
    configGrid.appendChild(mkInput("Device Name", "device_name", cs.device_name));
    configGrid.appendChild(mkInput("Firmware", "firmware", cs.firmware));
    configGrid.appendChild(mkInput("Iterations", "iterations", cs.iterations, "number", { min: "1" }));
    configGrid.appendChild(mkInput("Run Time", "run_time", cs.run_time));
    configGrid.appendChild(mkIfaceInput("Terminal Port", "terminal_port", cs.interfaces?.terminal_port || "COM7"));
    configGrid.appendChild(mkIfaceInput("Baudrate", "baudrate", cs.interfaces?.baudrate || 115200, "number"));
    configGrid.appendChild(mkIfaceInput("Catcher Port (optional)", "catcher_port", cs.interfaces?.catcher_port || ""));

    const otiiCheck = h("input", {
      type: "checkbox",
      ...(cs.interfaces?.use_otii ? { checked: true } : {}),
    });
    otiiCheck.addEventListener("change", () => {
      if (!cs.interfaces) cs.interfaces = {};
      cs.interfaces.use_otii = otiiCheck.checked;
    });
    configGrid.appendChild(h("label", { className: "utt-field utt-field-checkbox" },
      otiiCheck, h("span", null, "Use OTII Power Supply")));

    configCard.appendChild(configGrid);
    center.appendChild(configCard);

    // Sequence area
    center.appendChild(h("h3", null, "Test Sequence"));
    center.appendChild(h("p", { className: "text-muted", style: { fontSize: "0.8rem" } },
      "Drop steps here. They execute top to bottom. Drag to reorder."));

    const seqArea = h("div", { className: "utt-sequence" });
    this._renderSequence(seqArea, cs);

    // Drop zone for new items
    seqArea.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = _dragData?.source === "palette" ? "copy" : "move";
      seqArea.classList.add("drag-over");
    });
    seqArea.addEventListener("dragleave", () => seqArea.classList.remove("drag-over"));
    seqArea.addEventListener("drop", (e) => {
      e.preventDefault();
      seqArea.classList.remove("drag-over");
      if (_dragData?.source === "palette") {
        const catItem = _catalog.find(c => c.type === _dragData.type);
        if (catItem) {
          cs.steps.push({
            _id: uid(),
            type: catItem.type,
            ...JSON.parse(JSON.stringify(catItem.defaults)),
          });
          this._renderSequence(seqArea, cs);
        }
      }
    });
    center.appendChild(seqArea);

    // Action buttons
    const actions = h("div", { className: "utt-actions" },
      h("button", { className: "btn btn-primary", onclick: () => this._saveCase() }, "💾 Save"),
      h("button", { className: "btn", onclick: () => this._previewYaml() }, "📄 Preview YAML"),
      h("button", { className: "btn btn-success", onclick: () => this._runCase() }, "▶ Run Test"),
    );
    center.appendChild(actions);

    // Status section
    this._renderStatusSection(center);

    editorWrap.appendChild(palette);
    editorWrap.appendChild(center);
    c.appendChild(editorWrap);
  },

  _renderSequence(seqArea, cs) {
    seqArea.innerHTML = "";
    if (!cs.steps.length) {
      seqArea.appendChild(h("div", { className: "utt-seq-empty" },
        h("p", null, "Drop steps here to build your test sequence")));
      return;
    }

    cs.steps.forEach((step, idx) => {
      const catItem = _catalog.find(c => c.type === step.type) || {};
      const stepEl = h("div", {
        className: "utt-step-item",
        draggable: "true",
      });

      // Drag to reorder
      stepEl.addEventListener("dragstart", (e) => {
        _dragData = { source: "sequence", index: idx };
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", String(idx));
        stepEl.classList.add("dragging");
      });
      stepEl.addEventListener("dragend", () => {
        stepEl.classList.remove("dragging");
        _dragData = null;
      });
      stepEl.addEventListener("dragover", (e) => {
        e.preventDefault();
        if (_dragData?.source === "sequence") {
          e.dataTransfer.dropEffect = "move";
          stepEl.classList.add("drag-target");
        }
      });
      stepEl.addEventListener("dragleave", () => stepEl.classList.remove("drag-target"));
      stepEl.addEventListener("drop", (e) => {
        e.preventDefault();
        e.stopPropagation();
        stepEl.classList.remove("drag-target");
        if (_dragData?.source === "sequence" && _dragData.index !== idx) {
          const [moved] = cs.steps.splice(_dragData.index, 1);
          cs.steps.splice(idx, 0, moved);
          this._renderSequence(seqArea, cs);
        } else if (_dragData?.source === "palette") {
          const catInsert = _catalog.find(c => c.type === _dragData.type);
          if (catInsert) {
            cs.steps.splice(idx, 0, {
              _id: uid(),
              type: catInsert.type,
              ...JSON.parse(JSON.stringify(catInsert.defaults)),
            });
            this._renderSequence(seqArea, cs);
          }
        }
      });

      // Step number + icon
      const header = h("div", { className: "utt-step-header" },
        h("span", { className: "utt-step-num" }, `${idx + 1}`),
        h("span", { className: "utt-step-icon" }, catItem.icon || "?"),
        h("strong", null, catItem.label || step.type),
        h("div", { className: "utt-step-actions" },
          h("button", { className: "btn btn-sm", onclick: () => {
            if (idx > 0) { [cs.steps[idx - 1], cs.steps[idx]] = [cs.steps[idx], cs.steps[idx - 1]]; this._renderSequence(seqArea, cs); }
          }}, "↑"),
          h("button", { className: "btn btn-sm", onclick: () => {
            if (idx < cs.steps.length - 1) { [cs.steps[idx], cs.steps[idx + 1]] = [cs.steps[idx + 1], cs.steps[idx]]; this._renderSequence(seqArea, cs); }
          }}, "↓"),
          h("button", { className: "btn btn-sm", onclick: () => {
            cs.steps.splice(idx, 0, JSON.parse(JSON.stringify(step)));
            cs.steps[idx]._id = uid();
            this._renderSequence(seqArea, cs);
          }}, "📋"),
          h("button", { className: "btn btn-danger btn-sm", onclick: () => {
            cs.steps.splice(idx, 1);
            this._renderSequence(seqArea, cs);
          }}, "✕"),
        ),
      );
      stepEl.appendChild(header);

      // Step-specific fields
      const fields = h("div", { className: "utt-step-fields" });
      this._renderStepFields(fields, step, () => this._renderSequence(seqArea, cs));
      stepEl.appendChild(fields);

      seqArea.appendChild(stepEl);
    });
  },

  _renderStepFields(container, step, refresh) {
    const t = step.type;

    const mkF = (label, key, val, type = "text", opts = {}) => {
      const inp = h("input", {
        type, value: val ?? "", placeholder: label,
        className: "utt-input utt-input-sm",
        ...opts,
      });
      inp.addEventListener("change", () => {
        if (type === "number") step[key] = parseFloat(inp.value) || 0;
        else step[key] = inp.value;
      });
      return h("label", { className: "utt-field-inline" }, h("span", null, label + ":"), inp);
    };

    const mkSelect = (label, key, val, options) => {
      const sel = h("select", { className: "utt-input utt-input-sm" });
      for (const opt of options) {
        const optEl = h("option", { value: opt }, opt);
        if (opt === val) optEl.selected = true;
        sel.appendChild(optEl);
      }
      sel.addEventListener("change", () => { step[key] = sel.value; });
      return h("label", { className: "utt-field-inline" }, h("span", null, label + ":"), sel);
    };

    if (t === "power_off" || t === "power_on") {
      container.appendChild(mkF("Timeout (s)", "timeout", step.timeout, "number"));
      container.appendChild(mkF("Retry", "retry", step.retry, "number"));
      container.appendChild(mkSelect("Error Level", "error_level", step.error_level || "Warning", ["Warning", "Error"]));
    } else if (t === "send_command") {
      container.appendChild(mkF("Command", "input", step.input));
      container.appendChild(mkF("Timeout (s)", "timeout", step.timeout, "number"));
      container.appendChild(mkF("Retry", "retry", step.retry, "number"));
      container.appendChild(mkSelect("Error Level", "error_level", step.error_level || "Warning", ["Warning", "Error"]));
    } else if (t === "read_response") {
      container.appendChild(mkF("Expected Output", "output", step.output));
      container.appendChild(this._renderArgsField(step));
      container.appendChild(mkF("Timeout (s)", "timeout", step.timeout, "number"));
      container.appendChild(mkF("Retry", "retry", step.retry, "number"));
      container.appendChild(mkSelect("Error Level", "error_level", step.error_level || "Warning", ["Warning", "Error"]));
    } else if (t === "send_and_verify") {
      container.appendChild(mkF("Command", "input", step.input));
      container.appendChild(mkF("Expected Output", "output", step.output));
      container.appendChild(this._renderArgsField(step));
      container.appendChild(mkF("Timeout (s)", "timeout", step.timeout, "number"));
      container.appendChild(mkF("Retry", "retry", step.retry, "number"));
      container.appendChild(mkSelect("Error Level", "error_level", step.error_level || "Warning", ["Warning", "Error"]));
    } else if (t === "delay") {
      container.appendChild(mkF("Delay (seconds)", "delay", step.delay, "number"));
    } else if (t === "read_catcher") {
      container.appendChild(mkF("Source", "source", step.source));
      container.appendChild(mkF("Destination", "destination", step.destination));
      container.appendChild(mkF("SAP", "SAP", step.SAP));
      container.appendChild(mkF("Message ID", "msg_id", step.msg_id));
      container.appendChild(this._renderArgsField(step));
      container.appendChild(mkF("Timeout (s)", "timeout", step.timeout, "number"));
      container.appendChild(mkF("Retry", "retry", step.retry, "number"));
      container.appendChild(mkSelect("Error Level", "error_level", step.error_level || "Warning", ["Warning", "Error"]));
    }
  },

  _renderArgsField(step) {
    const wrap = h("div", { className: "utt-args-field" });
    const label = h("span", null, "Args (comma-separated):");
    const inp = h("input", {
      type: "text",
      className: "utt-input utt-input-sm",
      value: (step.args || []).join(", "),
      placeholder: 'e.g. 0, 0, NaN, NaN',
    });
    inp.addEventListener("change", () => {
      step.args = inp.value.split(",").map(s => s.trim()).filter(Boolean);
    });
    wrap.appendChild(h("label", { className: "utt-field-inline" }, label, inp));
    return wrap;
  },

  async _saveCase() {
    const cs = _currentCase;
    if (!cs) return;
    try {
      const saved = await api(`/api/${PLUGIN_ID}/cases`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cs),
      });
      // Sync the returned id back so Run works without reload
      _currentCase.id = saved.id;
      toast(`Saved: ${saved.id}`, "success");
      _cases = await api(`/api/${PLUGIN_ID}/cases`);
    } catch (e) { toast("Save failed: " + e.message, "error"); }
  },

  async _previewYaml() {
    const cs = _currentCase;
    if (!cs) return;
    try {
      const preview = await api(`/api/${PLUGIN_ID}/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cs),
      });
      // Show in a modal-like overlay
      const overlay = h("div", { className: "utt-overlay" });
      const modal = h("div", { className: "utt-modal" });
      modal.appendChild(h("div", { className: "utt-modal-header" },
        h("h3", null, "Generated YAML Preview"),
        h("button", { className: "btn btn-sm", onclick: () => overlay.remove() }, "✕"),
      ));

      for (const [name, content] of Object.entries(preview)) {
        modal.appendChild(h("h4", null, name));
        modal.appendChild(h("pre", { className: "utt-yaml-preview" }, content));
      }

      overlay.appendChild(modal);
      overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });
      document.body.appendChild(overlay);
    } catch (e) { toast("Preview failed: " + e.message, "error"); }
  },

  async _runCase() {
    const cs = _currentCase;
    if (!cs?.id) {
      toast("Save the test case first", "warn");
      return;
    }
    try {
      await api(`/api/${PLUGIN_ID}/run/${cs.id}`, { method: "POST" });
      toast("Test started!", "success");
      this._connectWS();
      // Just refresh the status section, don't rebuild the whole page
      this._refreshStatus();
    } catch (e) { toast("Run failed: " + e.message, "error"); }
  },

  async _renderSettingsCard(container) {
    let cfg;
    try { cfg = await api(`/api/${PLUGIN_ID}/config`); }
    catch { cfg = { universal_tester_tool_path: "", universal_tester_tool_log_dir: "" }; }

    const card = h("div", { className: "card utt-settings-card" });
    card.appendChild(h("h3", null, "⚙ Universal Tester Tool Settings"));

    const grid = h("div", { className: "utt-config-grid" });

    const mkCfgInput = (label, key, val, placeholder) => {
      const inp = h("input", {
        type: "text", value: val || "", placeholder,
        className: "utt-input",
      });
      inp.dataset.cfgKey = key;
      return h("label", { className: "utt-field" }, h("span", null, label), inp);
    };

    grid.appendChild(mkCfgInput("Universal Tester Tool Path", "universal_tester_tool_path",
      cfg.universal_tester_tool_path, "C:\\path\\to\\universal-tester-tool"));
    grid.appendChild(mkCfgInput("Log Directory", "universal_tester_tool_log_dir",
      cfg.universal_tester_tool_log_dir, "C:\\path\\to\\logs"));

    card.appendChild(grid);

    const saveBtn = h("button", { className: "btn btn-primary", style: { marginTop: "0.5rem" },
      onclick: async () => {
        const inputs = card.querySelectorAll("input[data-cfg-key]");
        const body = {};
        inputs.forEach(inp => { body[inp.dataset.cfgKey] = inp.value; });
        try {
          const updated = await api(`/api/${PLUGIN_ID}/config`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          });
          toast("Universal Tester Tool settings saved", "success");
        } catch (e) { toast("Save failed: " + e.message, "error"); }
      }
    }, "Save Settings");
    card.appendChild(saveBtn);

    container.appendChild(card);
  },

  _renderStatusSection(container) {
    const statusCard = h("div", { className: "card utt-status-card" });
    statusCard.appendChild(h("h3", null, "Run Status"));

    const statusBody = h("div", { className: "utt-status-body", id: "utt-status-body" });
    statusBody.appendChild(h("p", { className: "text-muted" }, "Loading status..."));
    statusCard.appendChild(statusBody);

    // Step progress list
    const stepsBox = h("div", { className: "utt-steps-progress", id: "utt-steps-progress" });
    statusCard.appendChild(stepsBox);

    const logBox = h("pre", { className: "utt-log-box", id: "utt-log-box" });
    statusCard.appendChild(logBox);

    container.appendChild(statusCard);

    // Load initial status
    this._refreshStatus();
    this._connectWS();
  },

  async _refreshStatus() {
    try {
      const status = await api(`/api/${PLUGIN_ID}/status`);
      this._updateStatusUI(status);
    } catch {}
  },

  _updateStatusUI(status) {
    const body = document.getElementById("utt-status-body");
    const logBox = document.getElementById("utt-log-box");
    const stepsBox = document.getElementById("utt-steps-progress");
    if (!body) return;
    body.innerHTML = "";

    const badge = (text, cls) => h("span", { className: `utt-badge utt-badge-${cls}` }, text);

    const statusBadge = {
      idle: badge("Idle", "idle"),
      running: badge("Running", "running"),
      completed: badge("Completed", "success"),
      failed: badge("Failed", "error"),
      stopped: badge("Stopped", "warn"),
    }[status.status] || badge(status.status, "idle");

    const info = h("div", { className: "utt-status-info" },
      h("div", null, h("strong", null, "Status: "), statusBadge),
    );

    if (status.case_name) {
      info.appendChild(h("div", null, h("strong", null, "Case: "), status.case_name));
    }
    if (status.running || status.status === "completed" || status.status === "failed" || status.status === "stopped") {
      info.appendChild(h("div", null,
        h("strong", null, "Iteration: "),
        `${status.current_iteration} / ${status.total_iterations}`));
    }
    if (status.started_at) {
      info.appendChild(h("div", null, h("strong", null, "Started: "), status.started_at));
    }
    if (status.log_file && !status.running) {
      info.appendChild(h("div", null,
        h("strong", null, "Log: "),
        h("span", { className: "text-muted", style: { fontFamily: "var(--font-mono)", fontSize: "0.78rem" } },
          status.log_file)));
    }

    const btnRow = h("div", { style: { marginTop: "0.5rem", display: "flex", gap: "0.5rem", alignItems: "center" } });

    const nukeBtn = h("button", {
      className: "btn utt-nuke-btn",
      onclick: async () => {
        try {
          await api(`/api/${PLUGIN_ID}/reset`, { method: "POST" });
          toast("STOP & KILL complete — all Universal Tester Tool processes killed", "success", 3000);
        } catch (e) { toast("Reset failed: " + e.message, "error"); }
        this._refreshStatus();
      },
    }, "☢ STOP & KILL");
    btnRow.appendChild(nukeBtn);

    info.appendChild(btnRow);

    // COM port guidance banner
    if (status.fail_reason === "com_port") {
      const guidance = h("div", { className: "utt-com-guidance" },
        h("strong", null, "⚠ COM port is busy or locked"),
        h("p", null, "Another program (PuTTY, Catcher, Device Manager, etc.) is holding the COM port open."),
        h("ol", null,
          h("li", null, "Close the program using the COM port"),
          h("li", null, "Hit STOP & KILL to clean up orphaned processes"),
          h("li", null, "Run the test again"),
        ),
      );
      info.appendChild(guidance);
    }

    body.appendChild(info);

    // Render step progress
    if (stepsBox && status.steps?.length) {
      stepsBox.innerHTML = "";
      const stepIcons = { pending: "○", running: "◉", passed: "✓", failed: "✗" };

      for (const step of status.steps) {
        const icon = stepIcons[step.status] || "○";
        const cls = step.status || "pending";
        const row = h("div", { className: `utt-step-progress utt-sp-${cls}` },
          h("span", { className: "utt-sp-icon" }, icon),
          h("span", { className: "utt-sp-num" }, `${step.index + 1}`),
          h("span", { className: "utt-sp-label" }, step.label),
        );
        if (step.detail) {
          row.appendChild(h("span", { className: "utt-sp-detail" }, step.detail));
        }
        if (step.result) {
          row.appendChild(h("span", { className: `utt-sp-result utt-sp-${cls}` }, step.result));
        }
        stepsBox.appendChild(row);
      }
    }

    // Update log
    if (logBox) {
      if (status.new_lines?.length) {
        for (const line of status.new_lines) {
          logBox.textContent += line + "\n";
        }
        logBox.scrollTop = logBox.scrollHeight;
      } else if (status.log_tail?.length && !logBox.textContent) {
        logBox.textContent = status.log_tail.join("\n");
        logBox.scrollTop = logBox.scrollHeight;
      }
    }
  },

  _connectWS() {
    if (_ws && _ws.readyState <= 1) return; // already connected or connecting
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    _ws = new WebSocket(`${proto}//${location.host}/ws/universal-tester-tool`);
    _ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data);
        this._updateStatusUI(data);
      } catch {}
    };
    _ws.onclose = () => { _ws = null; };
    _ws.onerror = () => { _ws = null; };
  },
});

