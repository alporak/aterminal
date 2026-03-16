/* ================================================================
   Jira Tracker Plugin  –  Weekly view, log work, assigned tickets,
   folder sync, teammates, caching
   ================================================================ */
import { h, $, $$, api, toast, registerPlugin, createTabs, icons, makeColumnsResizable } from "./core.js";

/* ── Helpers ──────────────────────────────────────────────────── */
const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const ICONS = {
  ...icons,
  edit: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`,
  save: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>`,
  folder: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/></svg>`,
  paperclip: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>`,
  download: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>`,
};

const fmtSec = s => {
  const hrs = Math.floor(s / 3600), min = Math.floor((s % 3600) / 60);
  return hrs ? `${hrs}h ${min}m` : `${min}m`;
};
const isoDate = d => d.toISOString().split("T")[0];
const mondayOf = d => { const c = new Date(d); c.setDate(c.getDate() - ((c.getDay() + 6) % 7)); return c; };
const addDays = (d, n) => { const c = new Date(d); c.setDate(c.getDate() + n); return c; };

/* ── Cached assigned list (shared between tabs) ──────────────── */
let _assignedCache = null;
let _assignedCacheTs = 0;
const ASSIGNED_CACHE_TTL = 120_000; // 2 min

async function _getAssigned(force = false) {
  if (!force && _assignedCache && (Date.now() - _assignedCacheTs) < ASSIGNED_CACHE_TTL) {
    return _assignedCache;
  }
  try {
    _assignedCache = await api("/api/jira/assigned");
    _assignedCacheTs = Date.now();
  } catch (e) {
    console.error("[Jira] Failed to load assigned:", e.message);
    _assignedCache = [];
  }
  return _assignedCache;
}

/* ================================================================ */
registerPlugin({
  id: "jira", name: "Jira Tracker", order: 4,
  svgIcon: icons.clock,
  _cfg: null,
  _weekOffset: 0,
  _autoRefreshTimer: null,
  _tabs: null,

  init(container) {
    this._tabs = createTabs(container, [
      { id: "wk",  label: "Weekly View", render: c => this._renderWeekly(c) },
      { id: "asg", label: "Assigned",    render: c => this._renderAssigned(c) },
      { id: "cfg", label: "Config",      render: c => this._renderConfig(c) },
    ]);
  },

  destroy() {
    if (this._autoRefreshTimer) { clearInterval(this._autoRefreshTimer); this._autoRefreshTimer = null; }
  },

  async _ensureCfg() {
    if (!this._cfg) try {
      this._cfg = await api("/api/jira/config");
    } catch (e) { console.error("[Jira] Failed to load config:", e.message); }
    return this._cfg;
  },

  _needsCreds(c) {
    c.appendChild(h("div", { className: "empty" },
      h("div", { className: "empty-icon", html: icons.settings }),
      h("p", null, "Configure Jira credentials in the Config tab first")));
  },

  /* ================================================================
     WEEKLY VIEW
     ================================================================ */
  async _renderWeekly(c) {
    c.innerHTML = "";
    const cfg = await this._ensureCfg();
    if (!cfg?.has_token) { this._needsCreds(c); return; }

    const monday = mondayOf(addDays(new Date(), this._weekOffset * 7));
    const sunday = addDays(monday, 6);
    const weekLabel = `${isoDate(monday)}  \u2192  ${isoDate(sunday)}`;

    const cacheIndicator = h("span", { className: "wk-cache-indicator" });

    const nav = h("div", { className: "wk-toolbar" },
      h("div", { className: "wk-toolbar-left" },
        h("button", { className: "wk-nav-btn", onclick: () => { this._weekOffset--; this._renderWeekly(c); } }, "\u2039"),
        h("span", { className: "wk-week-label" }, weekLabel),
        h("button", { className: "wk-nav-btn", onclick: () => { this._weekOffset++; this._renderWeekly(c); } }, "\u203A"),
        h("button", { className: "wk-nav-btn wk-today-btn", onclick: () => { this._weekOffset = 0; this._renderWeekly(c); } }, "Today"),
      ),
      h("div", { className: "wk-toolbar-right" },
        cacheIndicator,
        h("button", {
          className: "wk-nav-btn wk-refresh-btn", title: "Force refresh from Jira",
          onclick: () => this._loadWeekly(c, monday, true),
        }, h("span", { html: icons.refresh })),
      ),
    );
    c.appendChild(nav);

    const container = h("div", { id: "wk-container" });
    c.appendChild(container);

    this._loadWeekly(c, monday, false);

    if (this._autoRefreshTimer) clearInterval(this._autoRefreshTimer);
    const ttl = (cfg.cache_ttl_minutes || 5) * 60 * 1000;
    this._autoRefreshTimer = setInterval(() => {
      console.log("[Jira] Auto-refresh triggered");
      this._loadWeekly(c, monday, true);
    }, ttl);
  },

  async _loadWeekly(c, monday, forceRefresh) {
    const container = c.querySelector("#wk-container") || c;
    const cacheInd = c.querySelector(".wk-cache-indicator");
    const weekOf = isoDate(monday);

    container.innerHTML = '<div class="loading-state"><div class="spinner"></div><p>Loading your worklogs\u2026</p></div>';

    try {
      const myUrl = `/api/jira/worklogs/weekly?week_of=${weekOf}&force_refresh=${forceRefresh}`;
      const myData = await api(myUrl);

      container.innerHTML = "";

      if (cacheInd) {
        cacheInd.textContent = myData.cached ? `cached (${myData.cache_ttl_minutes}m TTL)` : "live";
        cacheInd.className = "wk-cache-indicator" + (myData.cached ? " wk-cached" : " wk-live");
      }

      this._buildWeekTable(container, myData.users[0], monday, c);

      const cfg = this._cfg || {};
      if (cfg.teammates?.length) {
        for (const tm of cfg.teammates) {
          const tmContainer = h("div", { className: "wk-tm-loader" },
            h("span", { className: "spinner-sm" }), ` Loading ${tm.displayName || tm.accountId}\u2026`);
          container.appendChild(tmContainer);
          api(`/api/jira/worklogs/weekly?week_of=${weekOf}&account_id=${tm.accountId}&force_refresh=${forceRefresh}`)
            .then(tmData => {
              tmContainer.remove();
              if (tmData.users?.length) this._buildWeekTable(container, tmData.users[0], monday, c);
            })
            .catch(err => {
              tmContainer.innerHTML = `<span class="text-error">Failed to load ${tm.displayName}</span>`;
              console.error(err);
            });
        }
      }
    } catch (e) {
      console.error("[Jira] Weekly load failed:", e.message);
      container.innerHTML = `<div class="empty"><p>Failed to load: ${e.message}</p></div>`;
    }
  },

  _buildWeekTable(container, user, monday, parentContainer) {
    const totalSec = user.worklogs.reduce((s, w) => s + (w.time_spent_seconds || 0), 0);

    let wrapper, contentTarget;
    if (user.is_me) {
      wrapper = h("div", { className: "wk-user-block" });
      wrapper.appendChild(h("div", { className: "wk-user-hdr" },
        h("span", { className: "wk-user-name" }, user.displayName + " (You)"),
        h("span", { className: "wk-user-total" }, fmtSec(totalSec)),
      ));
      contentTarget = wrapper;
    } else {
      wrapper = h("details", { className: "wk-user-details" });
      wrapper.appendChild(h("summary", { className: "wk-user-hdr wk-clickable" },
        h("span", { className: "wk-user-name" },
          h("span", { className: "wk-caret" }, "\u25B6"),
          user.displayName || "Teammate"),
        h("span", { className: "wk-user-total" }, fmtSec(totalSec)),
      ));
      contentTarget = wrapper;
    }
    container.appendChild(wrapper);

    if (!user.worklogs.length) {
      contentTarget.appendChild(h("div", { className: "wk-empty-week" }, "No worklogs this week"));
      return;
    }

    // Group by date
    const byDate = {};
    for (const wl of user.worklogs) (byDate[wl.date] ??= []).push(wl);

    const colCount = user.is_me ? 6 : 5;
    const table = h("table", { className: "wk-tbl" });
    const thead = h("thead");
    thead.appendChild(h("tr", null,
      h("th", { className: "wk-th-day" }, "Day"),
      h("th", { className: "wk-th-ticket" }, "Ticket"),
      h("th", { className: "wk-th-summary" }, "Summary"),
      h("th", { className: "wk-th-time" }, "Time"),
      h("th", { className: "wk-th-comment" }, "Comment"),
      user.is_me ? h("th", { className: "wk-th-actions" }, "Actions") : null,
    ));
    table.appendChild(thead);

    const tbody = h("tbody");
    const sortedDates = Object.keys(byDate).sort();

    for (const dt of sortedDates) {
      const wls = byDate[dt];
      const dayD = new Date(dt + "T00:00:00");
      const dayIdx = (dayD.getDay() + 6) % 7;
      const isToday = dt === isoDate(new Date());
      const daySec = wls.reduce((s, w) => s + (w.time_spent_seconds || 0), 0);

      if (tbody.children.length > 0) {
        tbody.appendChild(h("tr", { className: "wk-row-spacer" }, h("td", { colSpan: String(colCount) })));
      }

      for (let j = 0; j < wls.length; j++) {
        const wl = wls[j];
        const tr = h("tr", { className: "wk-row" + (isToday ? " wk-row-today" : ""), "data-id": wl.id });

        if (j === 0) {
          tr.appendChild(h("td", {
            className: "wk-cell-day" + (isToday ? " wk-cell-today" : ""),
            rowSpan: String(wls.length),
          },
            h("div", { className: "wk-day-label" }, DAY_NAMES[dayIdx]),
            h("div", { className: "wk-day-date" }, dt.slice(5)),
            h("div", { className: "wk-day-subtotal" + (daySec >= 28800 ? " wk-ok" : "") }, fmtSec(daySec)),
          ));
        }

        const jiraUrl = this._cfg?.url ? `${this._cfg.url}/browse/${wl.ticket_key}` : "#";
        tr.appendChild(h("td", { className: "wk-cell-ticket" },
          h("a", { href: jiraUrl, target: "_blank", className: "wk-ticket-link" }, wl.ticket_key)));
        tr.appendChild(h("td", { className: "wk-cell-summary" }, wl.ticket_summary));
        tr.appendChild(h("td", { className: "wk-cell-time" }, wl.time_spent));
        tr.appendChild(h("td", { className: "wk-cell-comment" }, wl.comment || ""));

        if (user.is_me) {
          const actionsCell = h("td", { className: "wk-cell-actions" });
          actionsCell.appendChild(h("button", {
            className: "wk-btn-icon", title: "Edit Worklog",
            onclick: () => this._enableEditMode(tr, wl, actionsCell, parentContainer),
          }, h("span", { html: ICONS.edit })));
          actionsCell.appendChild(h("button", {
            className: "wk-btn-icon wk-btn-del", title: "Delete Worklog",
            onclick: async () => {
              if (!confirm("Delete this worklog?")) return;
              try {
                await api(`/api/jira/worklog/${wl.ticket_key}/${wl.id}`, { method: "DELETE" });
                toast("Deleted", "success");
                const wkContainer = parentContainer.closest(".tab-body") || parentContainer;
                this._renderWeekly(wkContainer);
              } catch (e) { console.error("[Jira] Delete failed:", e.message); }
            },
          }, h("span", { html: ICONS.x })));
          tr.appendChild(actionsCell);
        }
        tbody.appendChild(tr);
      }
    }
    table.appendChild(tbody);
    contentTarget.appendChild(table);
    makeColumnsResizable(table, "jira_weekly_col_widths");
  },

  _enableEditMode(tr, wl, actionsCell, parentContainer) {
    if (tr.classList.contains("wk-editing")) return;
    tr.classList.add("wk-editing");

    const timeCell = tr.querySelector(".wk-cell-time");
    const commentCell = tr.querySelector(".wk-cell-comment");
    const oldTime = timeCell.textContent;
    const oldComment = commentCell.textContent;

    timeCell.innerHTML = "";
    const timeInput = h("input", { className: "form-control input-sm", value: oldTime, style: { width: "70px", textAlign: "right" } });
    timeCell.appendChild(timeInput);

    commentCell.innerHTML = "";
    const commentInput = h("input", { className: "form-control input-sm", value: oldComment, style: { width: "100%" } });
    commentCell.appendChild(commentInput);

    const rerender = () => {
      const wkContainer = parentContainer.closest(".tab-body") || parentContainer;
      this._renderWeekly(wkContainer);
    };

    const save = async () => {
      const newTime = timeInput.value.trim();
      const newComment = commentInput.value.trim();
      if (!newTime) { timeInput.focus(); return; }
      try {
        await api(`/api/jira/worklog/${wl.ticket_key}/${wl.id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            issue_key: wl.ticket_key,
            time_spent: newTime,
            comment: newComment,
            started: wl.started.split("T")[0],
          }),
        });
        toast("Saved", "success");
        rerender();
      } catch (e) { console.error(e); }
    };

    actionsCell.innerHTML = "";
    actionsCell.appendChild(h("button", { className: "wk-btn-icon text-success", title: "Save", onclick: save },
      h("span", { html: ICONS.save })));
    actionsCell.appendChild(h("button", { className: "wk-btn-icon text-dim", title: "Cancel", onclick: rerender },
      h("span", { html: ICONS.x })));

    timeInput.addEventListener("keydown", e => { if (e.key === "Enter") save(); if (e.key === "Escape") rerender(); });
    commentInput.addEventListener("keydown", e => { if (e.key === "Enter") save(); if (e.key === "Escape") rerender(); });
    timeInput.focus();
  },

  /* ================================================================
     LOG WORK / MEETING SUBMIT HANDLERS
     ================================================================ */

  async _submitWorklog() {
    const selKey = ($("#wl-key")?.value || "").trim();
    const manKey = ($("#wl-key-manual")?.value || "").trim();
    const key = manKey || selKey;
    const time = ($("#wl-time")?.value || "").trim();
    if (!key || !time) { toast("Ticket + time required", "error"); return; }
    const payload = {
      issue_key: key, time_spent: time,
      comment: ($("#wl-cmt")?.value || "").trim(),
      started: $("#wl-date")?.value,
    };
    try {
      await api("/api/jira/worklog", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      toast(`Logged ${time} to ${key}`, "success");
      if ($("#wl-time")) $("#wl-time").value = "";
      if ($("#wl-cmt")) $("#wl-cmt").value = "";
    } catch (e) { console.error("[Jira] Add worklog failed:", e.message); }
  },

  async _submitMeeting() {
    const key = ($("#mt-key")?.value || "").trim();
    const time = ($("#mt-time")?.value || "").trim();
    if (!time) { toast("Duration required", "error"); return; }
    const payload = {
      issue_key: key, time_spent: time,
      summary: ($("#mt-cmt")?.value || "").trim(),
      started: $("#mt-date")?.value,
    };
    try {
      await api("/api/jira/meeting", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      toast(`Meeting logged (${time})`, "success");
      if ($("#mt-time")) $("#mt-time").value = "";
      if ($("#mt-cmt")) $("#mt-cmt").value = "";
    } catch (e) { console.error("[Jira] Log meeting failed:", e.message); }
  },

  /* ================================================================
     ASSIGNED  –  Log work, log meeting, assigned tickets, folder sync
     ================================================================ */
  async _renderAssigned(c) {
    c.innerHTML = '<div class="loading-state"><div class="spinner"></div><p>Loading assigned tickets\u2026</p></div>';
    const cfg = await this._ensureCfg();
    if (!cfg?.has_token) { c.innerHTML = ""; this._needsCreds(c); return; }

    const assigned = await _getAssigned(true);
    c.innerHTML = "";

    const today = isoDate(new Date());
    const yesterday = isoDate(addDays(new Date(), -1));
    const defaultMtgKey = cfg.meeting_ticket || "FMBP-44552";

    /* ── Log Work Card ────────────────────────────────────── */
    const ticketSelect = h("select", { id: "wl-key", className: "form-control" });
    ticketSelect.appendChild(h("option", { value: "" }, "\u2014 Select ticket \u2014"));
    for (const t of assigned) {
      const label = `${t.key}  \u2013  ${t.summary}`.slice(0, 80);
      ticketSelect.appendChild(h("option", { value: t.key }, label));
    }

    const ticketManual = h("input", {
      id: "wl-key-manual", className: "form-control",
      placeholder: "Or type ticket key (e.g. FMBP-12345)",
      style: { marginTop: "4px", display: "none" },
    });

    const toggleManual = h("button", {
      className: "btn btn-sm jira-toggle-manual",
      title: "Type ticket key manually",
      onclick: () => {
        const show = ticketManual.style.display === "none";
        ticketManual.style.display = show ? "block" : "none";
        if (show) { ticketSelect.value = ""; ticketManual.focus(); }
        else ticketManual.value = "";
      },
    }, "manual entry");

    c.appendChild(h("div", { className: "card" },
      h("h3", null, "Log Work"),
      h("div", { className: "form-row" },
        h("div", { className: "form-group", style: { flex: "1", minWidth: "220px" } },
          h("label", null, "Ticket"),
          ticketSelect, ticketManual, toggleManual),
        h("div", { className: "form-group", style: { flex: "0 0 100px" } },
          h("label", null, "Time"),
          h("input", { id: "wl-time", className: "form-control", placeholder: "1h 30m" })),
        h("div", { className: "form-group", style: { flex: "0 0 150px" } },
          h("label", null, "Date"),
          h("input", { id: "wl-date", className: "form-control", type: "date", value: today })),
      ),
      h("div", { className: "form-row" },
        h("div", { className: "form-group", style: { flex: "1" } },
          h("label", null, "Comment"),
          h("input", { id: "wl-cmt", className: "form-control", placeholder: "What did you work on?" })),
      ),
      h("div", { className: "btn-group", style: { marginTop: "8px" } },
        h("button", { className: "btn btn-primary", onclick: () => this._submitWorklog() }, "Log Work"),
        h("button", { className: "btn", onclick: () => { $("#wl-date").value = today; } }, "Today"),
        h("button", { className: "btn", onclick: () => { $("#wl-date").value = yesterday; } }, "Yesterday"),
      ),
    ));

    /* ── Quick time preset buttons ────────────────────────── */
    const timeInput = $("#wl-time");
    const quickTimes = ["15m", "30m", "45m", "1h", "1h 30m", "2h", "3h", "4h"];
    const quickRow = h("div", { className: "jira-quick-times" });
    for (const qt of quickTimes) {
      quickRow.appendChild(h("button", {
        className: "jira-quick-time-btn",
        onclick: () => { timeInput.value = qt; },
      }, qt));
    }
    timeInput.closest(".form-group").appendChild(quickRow);

    /* ── Meeting Log Card ─────────────────────────────────── */
    c.appendChild(h("div", { className: "card" },
      h("h3", null, "Log Meeting / Standup"),
      h("div", { className: "form-row" },
        h("div", { className: "form-group", style: { flex: "0 0 160px" } },
          h("label", null, "Meeting Ticket"),
          h("input", { id: "mt-key", className: "form-control", value: defaultMtgKey })),
        h("div", { className: "form-group", style: { flex: "0 0 100px" } },
          h("label", null, "Duration"),
          h("input", { id: "mt-time", className: "form-control", placeholder: "30m" })),
        h("div", { className: "form-group", style: { flex: "1", minWidth: "180px" } },
          h("label", null, "Comment"),
          h("input", { id: "mt-cmt", className: "form-control", placeholder: "Daily standup" })),
        h("div", { className: "form-group", style: { flex: "0 0 150px" } },
          h("label", null, "Date"),
          h("input", { id: "mt-date", className: "form-control", type: "date", value: today })),
      ),
      h("div", { className: "btn-group", style: { marginTop: "8px" } },
        h("button", { className: "btn btn-primary", onclick: () => this._submitMeeting() }, "Log Meeting"),
        h("button", { className: "btn", onclick: () => { $("#mt-date").value = today; } }, "Today"),
        h("button", { className: "btn", onclick: () => { $("#mt-date").value = yesterday; } }, "Yesterday"),
      ),
    ));

    /* ── Assigned Tickets ─────────────────────────────────── */
    if (!assigned.length) {
      c.appendChild(h("div", { className: "empty" }, h("p", null, "No assigned tickets")));
      return;
    }

    /* ── Toolbar ─────────────────────────────────────── */
    const toolbar = h("div", { className: "asg-toolbar" },
      h("span", { className: "asg-count" }, `${assigned.length} assigned tickets`),
      h("div", { className: "asg-toolbar-right" },
        cfg.tickets_folder
          ? h("span", { className: "asg-folder-path", title: cfg.tickets_folder },
              h("span", { className: "asg-folder-icon", html: ICONS.folder }),
              cfg.tickets_folder.split("\\").pop())
          : h("span", { className: "text-dim", style: { fontSize: "12px" } }, "No tickets folder configured"),
        h("button", { className: "btn btn-sm", title: "Refresh", onclick: () => {
          _assignedCache = null;
          this._renderAssigned(c);
        }}, h("span", { html: icons.refresh })),
      ),
    );
    c.appendChild(toolbar);

    /* ── Table ───────────────────────────────────────── */
    const table = h("table", { className: "wk-tbl asg-tbl" });
    const thead = h("thead");
    thead.appendChild(h("tr", null,
      h("th", { style: { width: "120px" } }, "Key"),
      h("th", null, "Summary"),
      h("th", { style: { width: "100px" } }, "Status"),
      h("th", { style: { width: "70px", textAlign: "center" } }, "Attach"),
      h("th", { style: { width: "70px", textAlign: "center" } }, "Folder"),
      h("th", { style: { width: "180px", textAlign: "right" } }, "Actions"),
    ));
    table.appendChild(thead);

    const tbody = h("tbody");
    for (const t of assigned) {
      const url = cfg.url ? `${cfg.url}/browse/${t.key}` : "#";

      // Status badge variant
      const stLower = (t.status || "").toLowerCase();
      let badgeClass = "badge-primary";
      if (stLower.includes("progress") || stLower.includes("review")) badgeClass = "badge-info";
      else if (stLower.includes("done") || stLower.includes("closed")) badgeClass = "badge-success";

      // Folder status indicator
      let folderIndicator;
      if (t.has_folder) {
        const synced = t.attachment_count > 0 && t.local_files >= t.attachment_count;
        folderIndicator = h("span", {
          className: "asg-folder-status" + (synced ? " asg-synced" : " asg-partial"),
          title: `${t.local_files} local files / ${t.attachment_count} remote attachments`,
        }, synced ? "\u2713" : `${t.local_files}/${t.attachment_count}`);
      } else if (t.attachment_count > 0) {
        folderIndicator = h("span", {
          className: "asg-folder-status asg-missing",
          title: "Not synced yet",
        }, "\u2717");
      } else {
        folderIndicator = h("span", { className: "asg-folder-status asg-none", title: "No attachments" }, "\u2014");
      }

      const tr = h("tr", { className: "wk-row" },
        h("td", { className: "wk-cell-ticket" },
          h("a", { href: url, target: "_blank", className: "wk-ticket-link" }, t.key)),
        h("td", { className: "asg-cell-summary" }, t.summary),
        h("td", null, h("span", { className: `badge ${badgeClass}` }, t.status || "")),
        h("td", { style: { textAlign: "center" } },
          t.attachment_count > 0
            ? h("span", { className: "asg-att-count", title: `${t.attachment_count} attachments` },
                h("span", { className: "asg-att-icon", html: ICONS.paperclip }), String(t.attachment_count))
            : h("span", { className: "text-dim" }, "\u2014")),
        h("td", { style: { textAlign: "center" } }, folderIndicator),
      );

      // Actions
      const actTd = h("td", { className: "asg-actions" });

      // Log work quick button – pre-selects the ticket in the dropdown above
      actTd.appendChild(h("button", {
        className: "btn btn-sm btn-primary", title: "Log work to this ticket",
        onclick: () => {
          const sel = $("#wl-key");
          if (sel) { sel.value = t.key; sel.scrollIntoView({ behavior: "smooth", block: "center" }); }
        },
      }, h("span", { className: "btn-icon", html: icons.clock })));

      // Sync button
      actTd.appendChild(h("button", {
        className: "btn btn-sm", title: "Sync attachments & open folder",
        onclick: async (ev) => {
          const btn = ev.currentTarget;
          btn.disabled = true;
          const orig = btn.innerHTML;
          btn.innerHTML = '<span class="spinner-sm"></span>';
          try {
            const res = await api(`/api/jira/ticket/${t.key}/sync?open_folder=true`, { method: "POST" });
            toast(`${t.key}: synced ${res.downloaded} new files`, "success");
            _assignedCache = null;
            this._renderAssigned(c);
          } catch (e) {
            toast(`Sync failed: ${e.message}`, "error");
            btn.disabled = false;
            btn.innerHTML = orig;
          }
        },
      }, h("span", { className: "btn-icon", html: ICONS.download })));

      // Open folder button
      actTd.appendChild(h("button", {
        className: "btn btn-sm", title: "Open folder in Explorer",
        onclick: async () => {
          try {
            await api(`/api/jira/ticket/${t.key}/open`, { method: "POST" });
          } catch (e) { toast(`Open failed: ${e.message}`, "error"); }
        },
      }, h("span", { className: "btn-icon", html: ICONS.folder })));

      tr.appendChild(actTd);
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    c.appendChild(h("div", { className: "wk-table-wrap" }, table));
    makeColumnsResizable(table, "jira_assigned_col_widths");
  },

  /* ================================================================
     CONFIG  –  Credentials, meeting ticket, cache, tickets folder,
     teammates
     ================================================================ */
  async _renderConfig(c) {
    c.innerHTML = '<div class="loading-state"><div class="spinner"></div></div>';
    try {
      const cfg = await api("/api/jira/config");
      this._cfg = cfg;
      c.innerHTML = "";

      /* ── Credentials card ─────────────────────────────── */
      c.appendChild(h("div", { className: "card" },
        h("h3", null, "Jira Credentials"),
        h("div", { className: "form-row" },
          h("div", { className: "form-group", style: { flex: "1" } },
            h("label", null, "Jira URL"),
            h("input", { id: "j-url", className: "form-control", value: cfg.url || "", placeholder: "https://jira.example.com" })),
          h("div", { className: "form-group", style: { flex: "1" } },
            h("label", null, "Email"),
            h("input", { id: "j-email", className: "form-control", value: cfg.email || "" })),
        ),
        h("div", { className: "form-row" },
          h("div", { className: "form-group", style: { flex: "1" } },
            h("label", null, "API Token"),
            h("input", { id: "j-token", className: "form-control", type: "password",
              placeholder: cfg.has_token ? "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022  (leave blank to keep)" : "Enter API token" })),
        ),
        h("div", { className: "form-row" },
          h("div", { className: "form-group", style: { flex: "0 0 160px" } },
            h("label", null, "Meeting Ticket"),
            h("input", { id: "j-mtg", className: "form-control", value: cfg.meeting_ticket || "" })),
          h("div", { className: "form-group", style: { flex: "0 0 120px" } },
            h("label", null, "Cache TTL (min)"),
            h("input", { id: "j-cache-ttl", className: "form-control", type: "number", min: "1", max: "60",
              value: String(cfg.cache_ttl_minutes || 5) })),
          h("div", { className: "form-group", style: { flex: "1" } },
            h("label", null, "Tickets Folder"),
            h("input", { id: "j-tickets-folder", className: "form-control", value: cfg.tickets_folder || "",
              placeholder: "C:\\path\\to\\_tickets" })),
        ),
        h("div", { className: "btn-group" },
          h("button", { className: "btn btn-primary", onclick: async () => {
            try {
              const upd = {
                url: ($("#j-url")?.value || "").trim(),
                email: ($("#j-email")?.value || "").trim(),
                api_token: ($("#j-token")?.value || "").trim(),
                meeting_ticket: ($("#j-mtg")?.value || "").trim(),
                cache_ttl_minutes: parseInt($("#j-cache-ttl")?.value) || 5,
                tickets_folder: ($("#j-tickets-folder")?.value || "").trim(),
              };
              await api("/api/jira/config", {
                method: "PUT", headers: { "Content-Type": "application/json" },
                body: JSON.stringify(upd),
              });
              this._cfg = null;
              toast("Configuration saved", "success");
            } catch (e) { console.error("[Jira] Save config failed:", e.message); }
          }}, "Save"),
          h("button", { className: "btn", onclick: async () => {
            try {
              const me = await api("/api/jira/myself");
              toast(`Connected as ${me.displayName || me.email || "OK"}`, "success");
            } catch (e) { toast("Connection failed", "error"); }
          }},
            h("span", { className: "btn-icon", html: icons.link }), "Test Connection"),
        ),
      ));

      /* ── Teammates card ───────────────────────────────── */
      c.appendChild(this._buildTeammateConfig(cfg.teammates || []));

    } catch (e) {
      console.error("[Jira] Load config failed:", e.message);
      c.innerHTML = `<div class="empty"><p>Failed to load config: ${e.message}</p></div>`;
    }
  },

  _buildTeammateConfig(teammates) {
    const card = h("div", { className: "card" },
      h("h3", null, "Teammates"),
      h("p", { className: "text-dim", style: { marginBottom: "12px", fontSize: "12px" } },
        "Add teammates to see their worklogs alongside yours in the Weekly View."),
    );

    const listEl = h("div", { id: "tm-list", className: "teammate-list" });
    const renderList = () => {
      listEl.innerHTML = "";
      if (!teammates.length) {
        listEl.appendChild(h("div", { className: "text-muted", style: { padding: "8px 0", fontSize: "12px" } }, "No teammates added yet"));
        return;
      }
      for (const tm of teammates) {
        listEl.appendChild(h("div", { className: "teammate-item" },
          h("span", null, tm.displayName || tm.accountId),
          h("button", { className: "btn btn-danger btn-sm", onclick: async () => {
            teammates = teammates.filter(t => t.accountId !== tm.accountId);
            try {
              await api("/api/jira/teammates", {
                method: "PUT", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ teammates }),
              });
              toast("Removed", "success");
            } catch (e) { console.error(e); }
            renderList();
          }}, h("span", { html: icons.x })),
        ));
      }
    };
    renderList();
    card.appendChild(listEl);

    const searchResults = h("div", { id: "tm-results", style: { marginTop: "8px" } });
    const searchRow = h("div", { className: "form-row", style: { marginTop: "12px" } },
      h("input", { id: "tm-search", className: "form-control", placeholder: "Search by name or email\u2026", style: { flex: "1" } }),
      h("button", { className: "btn btn-primary", onclick: async () => {
        const q = ($("#tm-search")?.value || "").trim();
        if (q.length < 2) { toast("Enter at least 2 characters", "error"); return; }
        searchResults.innerHTML = '<div class="spinner"></div>';
        try {
          const users = await api(`/api/jira/users/search?query=${encodeURIComponent(q)}`);
          searchResults.innerHTML = "";
          if (!users.length) { searchResults.appendChild(h("div", { className: "text-muted" }, "No users found")); return; }
          for (const u of users) {
            const already = teammates.some(t => t.accountId === u.accountId);
            searchResults.appendChild(h("div", { className: "teammate-search-result" },
              h("span", null, `${u.displayName} (${u.email || ""})`),
              already
                ? h("span", { className: "badge badge-primary" }, "Added")
                : h("button", { className: "btn btn-sm btn-primary", onclick: async () => {
                    teammates.push({ accountId: u.accountId, displayName: u.displayName });
                    try {
                      await api("/api/jira/teammates", {
                        method: "PUT", headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ teammates }),
                      });
                      toast(`Added ${u.displayName}`, "success");
                    } catch (e) { console.error(e); }
                    renderList();
                    searchResults.innerHTML = "";
                  }}, "Add"),
            ));
          }
        } catch (e) {
          searchResults.innerHTML = "<p>Search failed</p>";
        }
      }}, h("span", { className: "btn-icon", html: icons.search }), "Search"),
    );
    card.appendChild(searchRow);
    card.appendChild(searchResults);
    return card;
  },
});
