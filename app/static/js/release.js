/* ================================================================
   Release Creator Plugin  –  New Release + Revision wizard
   ================================================================ */
import { h, $, api, toast, registerPlugin, createTabs, createTable, icons, makeColumnsResizable } from "./core.js";

/* ── Jira wiki ↔ HTML helpers ──────────────────────────────────── */
function _esc(t) { return (t || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
function _inlineFmt(t) {
  return _esc(t).replace(/\*([^*]+)\*/g, "<b>$1</b>").replace(/_([^_]+)_/g, "<i>$1</i>");
}
function _jiraToHtml(wiki) {
  const lines = (wiki || "").split("\n");
  let html = "", inTbl = false;
  for (const raw of lines) {
    const line = raw.trim();
    if (line.startsWith("||") && line.endsWith("||")) {
      if (!inTbl) { html += '<table class="jira-preview-tbl">'; inTbl = true; }
      html += "<tr>" + line.slice(2, -2).split("||").map(c =>
        `<th style="border:1px solid var(--tk-border);padding:4px">${_inlineFmt(c)}</th>`).join("") + "</tr>";
    } else if (line.startsWith("|") && line.endsWith("|")) {
      if (!inTbl) { html += '<table class="jira-preview-tbl">'; inTbl = true; }
      html += "<tr>" + line.slice(1, -1).split("|").map(c =>
        `<td style="border:1px solid var(--tk-border);padding:4px">${_inlineFmt(c)}</td>`).join("") + "</tr>";
    } else {
      if (inTbl) { html += "</table>"; inTbl = false; }
      if (line) html += _inlineFmt(line) + "<br>";
    }
  }
  if (inTbl) html += "</table>";
  return html;
}

/* ── Version string parser ─────────────────────────────────────── */
function _parseVersion(name) {
  const m = (name || "").match(/^(.+?)\.Rev\.(\d+)(?:_(.+))?$/);
  return m ? { base: m[1], rev: parseInt(m[2], 10), spec: m[3] || null } : null;
}

/* ── Plugin ────────────────────────────────────────────────────── */
registerPlugin({
  id: "release", name: "Release Creator", order: 5,
  svgIcon: icons.rocket,
  _st: {},

  init(container) {
    this._st = {};
    createTabs(container, [
      { id: "cr",  label: "Create Release", render: c => this._renderWizard(c) },
      { id: "ver", label: "Versions",       render: c => this._renderVersions(c) },
    ]);
  },
  destroy() { this._st = {}; },

  /* Re-render wizard, preserving container ref */
  _refresh(c) { this._renderWizard(c); },

  /* ================================================================
     WIZARD
     ================================================================ */
  _renderWizard(c) {
    c.innerHTML = "";
    const st = this._st;

    this._step1(c);
    if (!st.source_key) return;
    this._step2(c);
    if (!st.release_type) return;
    if (st.release_type === "new") this._step3New(c);
    else this._step3Rev(c);
    if (!st.ready) return;
    this._step4(c);
  },

  /* ── Step 1: Source Ticket ───────────────────────────────── */
  _step1(c) {
    const st = this._st;
    const card = h("div", { className: "card" });
    card.appendChild(h("h3", null, "\u2460 Source Ticket"));
    const row = h("div", { className: "form-row" });
    row.appendChild(h("input", { id: "rel-src", className: "form-control",
      placeholder: "FMBP-12345", style: { flex: "1" }, value: st.source_key || "" }));
    row.appendChild(h("button", { className: "btn btn-primary", onclick: async () => {
      const key = ($("#rel-src").value || "").trim().toUpperCase();
      if (!key) { toast("Enter a ticket key", "error"); return; }
      try {
        const d = await api(`/api/release/issue/${encodeURIComponent(key)}`);
        st.source_key = d.key; st.source_summary = d.summary || "";
        this._refresh(c);
      } catch (e) { toast(`Fetch failed: ${e.message}`, "error"); }
    }}, h("span", { className: "btn-icon", html: icons.search }), "Fetch"));
    card.appendChild(row);
    if (st.source_key) {
      card.appendChild(h("div", { className: "badge badge-info", style: { marginTop: "8px", display: "inline-block" } },
        `${st.source_key} — ${st.source_summary}`));
    }
    c.appendChild(card);
  },

  /* ── Step 2: Release Type ────────────────────────────────── */
  _step2(c) {
    const st = this._st;
    const card = h("div", { className: "card" });
    card.appendChild(h("h3", null, "\u2461 Release Type"));
    const row = h("div", { className: "btn-group" });
    const mkBtn = (lbl, val) => h("button", {
      className: "btn" + (st.release_type === val ? " btn-primary" : ""),
      onclick: () => {
        st.release_type = val;
        st.ready = false; st.free_slots = null; st.prev_ticket = null;
        this._refresh(c);
      },
    }, lbl);
    row.appendChild(mkBtn("New Release", "new"));
    row.appendChild(mkBtn("Revision", "rev"));
    card.appendChild(row);
    c.appendChild(card);
  },

  /* ── Step 3-A: New Release ───────────────────────────────── */
  _step3New(c) {
    const st = this._st;
    const card = h("div", { className: "card" });
    card.appendChild(h("h3", null, "\u2462 New Release"));

    /* Base version */
    card.appendChild(h("label", null, "Base version string"));
    const baseRow = h("div", { className: "form-row" });
    baseRow.appendChild(h("input", { id: "rel-base", className: "form-control",
      placeholder: "FMB.Ver.04.02.00", style: { flex: "1" }, value: st.base || "" }));
    baseRow.appendChild(h("button", { className: "btn btn-primary", onclick: async () => {
      const base = ($("#rel-base").value || "").trim();
      if (!base) { toast("Enter a base version string", "error"); return; }
      st.base = base;
      try {
        const d = await api(`/api/release/free_slots?base=${encodeURIComponent(base)}`);
        st.free_slots = d.free_slots || [];
        st.next_rev = d.next;
        st.existing_revs = d.existing_revs || [];
        /* also load recent matching versions for expander */
        try {
          st.recent_versions = await api(`/api/release/versions?base=${encodeURIComponent(base)}`);
        } catch (_) { st.recent_versions = []; }
        this._refresh(c);
      } catch (e) { toast(`Search failed: ${e.message}`, "error"); }
    }}, h("span", { className: "btn-icon", html: icons.search }), "Search"));
    card.appendChild(baseRow);

    if (!st.free_slots?.length) { c.appendChild(card); return; }

    /* Next free slot */
    card.appendChild(h("div", { style: { margin: "10px 0 4px" } },
      h("strong", null, `Next free \u00d710 slot: Rev.${st.next_rev}`),
      h("span", { className: "text-muted" }, ` (${st.existing_revs.length} existing revisions)`)));

    /* Expander – recent matching versions */
    if (st.recent_versions?.length) {
      const details = h("details", { style: { margin: "6px 0 12px" } });
      details.appendChild(h("summary", { style: { cursor: "pointer", color: "var(--tk-accent)" } },
        `Show ${st.recent_versions.length} matching versions`));
      const list = h("div", { style: { maxHeight: "200px", overflowY: "auto", fontSize: "12px", marginTop: "4px" } });
      for (const v of st.recent_versions.slice(-30).reverse())
        list.appendChild(h("div", { className: "text-muted" }, v.name || JSON.stringify(v)));
      details.appendChild(list);
      card.appendChild(details);
    }

    /* Spec or Standard */
    card.appendChild(h("label", null, "Release kind"));
    const kindRow = h("div", { className: "btn-group", style: { marginBottom: "8px" } });
    const mkK = (lbl, val) => h("button", {
      className: "btn btn-sm" + (st.is_spec === val ? " btn-primary" : ""),
      onclick: () => { st.is_spec = val; this._refresh(c); },
    }, lbl);
    kindRow.appendChild(mkK("Standard (EXP)", false));
    kindRow.appendChild(mkK("Spec Release", true));
    card.appendChild(kindRow);

    if (st.is_spec === undefined) { c.appendChild(card); return; }

    if (st.is_spec) {
      card.appendChild(h("div", { className: "form-row" },
        h("div", { className: "form-group", style: { flex: "1" } },
          h("label", null, "Spec number"), h("input", { id: "rel-spec", className: "form-control",
            placeholder: "e.g. 245", value: st.spec || "" })),
        h("div", { className: "form-group", style: { flex: "1" } },
          h("label", null, "Client / Ocean string"), h("input", { id: "rel-client", className: "form-control",
            placeholder: "e.g. eM2M_SPECIDL_Effortech_SO_0245", value: st.client || "" })),
      ));
    } else {
      card.appendChild(h("div", { className: "form-group" },
        h("label", null, "EXP string"), h("input", { id: "rel-exp", className: "form-control",
          placeholder: "e.g. expfw/yellowfox_lib", value: st.exp || "" })));
    }

    /* Release date */
    const twoWeeks = new Date(Date.now() + 14 * 86400e3).toISOString().slice(0, 10);
    card.appendChild(h("div", { className: "form-row" },
      h("div", { className: "form-group", style: { flex: "1" } },
        h("label", null, "Start Date"), h("input", { id: "rel-start", type: "date",
          className: "form-control", value: st.start_date || new Date().toISOString().slice(0, 10) })),
      h("div", { className: "form-group", style: { flex: "1" } },
        h("label", null, "Release Date"), h("input", { id: "rel-end", type: "date",
          className: "form-control", value: st.release_date || twoWeeks })),
    ));

    /* Continue */
    card.appendChild(h("button", { className: "btn btn-primary", style: { marginTop: "8px" },
      onclick: () => {
        st.spec = st.is_spec ? ($("#rel-spec") || {}).value || "" : "";
        st.client = st.is_spec ? ($("#rel-client") || {}).value || "" : "";
        st.exp = !st.is_spec ? ($("#rel-exp") || {}).value || "" : "";
        st.start_date = ($("#rel-start") || {}).value || "";
        st.release_date = ($("#rel-end") || {}).value || "";
        st.rev = st.next_rev;
        /* Build defaults for preview */
        const specSuffix = st.spec ? `_${st.spec}` : "";
        st.version_name = `${st.base}.Rev.${st.rev}${specSuffix}`;
        if (st.is_spec && st.spec && st.client) {
          st.summary_text = `${st.version_name} FMBXXX SPEC=${st.spec} (${st.client})`;
          st.ver_desc = `FMBXXX SPEC=${st.spec} (${st.client})`;
        } else {
          st.summary_text = `${st.version_name} FMBXXX EXP=${st.exp || st.source_key}`;
          st.ver_desc = `FMBXXX EXP=${st.exp || st.source_key}`;
        }
        st.desc_text = "*Additional Comments:*\n*-*\n\n"
          + "||*Issue ID*||*Testing guidelines for Quality Assurance engineers*||\n"
          + `|${st.source_key}|${st.source_summary}|`;
        st.clone_from = null; // template clone for new releases
        st.prev_ticket_key = null;
        st.ready = true;
        this._refresh(c);
      },
    }, "Continue \u2192"));

    c.appendChild(card);
  },

  /* ── Step 3-B: Revision ──────────────────────────────────── */
  _step3Rev(c) {
    const st = this._st;
    const card = h("div", { className: "card" });
    card.appendChild(h("h3", null, "\u2462 Revision"));

    card.appendChild(h("label", null, "Previous version (full name or partial, e.g. 292_242)"));
    const row = h("div", { className: "form-row" });
    row.appendChild(h("input", { id: "rel-prev", className: "form-control",
      placeholder: "e.g. 292_242 or FMB.Ver.04.02.00.Rev.510_245", style: { flex: "1" }, value: st.prev_version || "" }));
    row.appendChild(h("button", { className: "btn btn-primary", onclick: async () => {
      const input = ($("#rel-prev").value || "").trim();
      if (!input) { toast("Enter a version name or partial match", "error"); return; }

      let name = input;
      let parsed = _parseVersion(name);

      /* If not a full version string, do a loose search */
      if (!parsed) {
        try {
          const versions = await api(`/api/release/versions?base=${encodeURIComponent(input)}`);
          if (!versions?.length) { toast(`No versions found matching "${input}"`, "error"); return; }
          let matched;
          if (versions.length === 1) {
            matched = versions[0];
          } else {
            /* Multiple matches – find the best one (exact substring on Rev.NNN part) */
            matched = versions.find(v => v.name?.includes(`.Rev.${input}`) || v.name?.endsWith(input))
              || versions[versions.length - 1];
          }
          name = matched.name;
          parsed = _parseVersion(name);
          st.prev_ver_desc = matched.description || "";
          if (parsed) toast(`Matched: ${name}`, "success");
          else { toast(`Found "${name}" but couldn't parse it`, "error"); return; }
        } catch (e) { toast(`Search failed: ${e.message}`, "error"); return; }
      }
      st.prev_version = name;
      st.base = parsed.base;
      st.prev_rev = parsed.rev;
      st.rev = parsed.rev + 1;
      st.spec = parsed.spec || "";
      /* Search for the previous release ticket */
      try {
        const d = await api(`/api/release/find_ticket?version=${encodeURIComponent(name)}`);
        if (d.found) {
          st.prev_ticket = d;
        } else {
          st.prev_ticket = null;
          toast("No release ticket found for that version — will clone from template", "warning");
        }
      } catch (e) { st.prev_ticket = null; toast(`Search failed: ${e.message}`, "error"); }
      this._refresh(c);
    }}, h("span", { className: "btn-icon", html: icons.search }), "Parse & Search"));
    card.appendChild(row);

    if (!st.rev) { c.appendChild(card); return; }

    const specSuffix = st.spec ? `_${st.spec}` : "";
    const newName = `${st.base}.Rev.${st.rev}${specSuffix}`;

    card.appendChild(h("div", { style: { margin: "10px 0" } },
      h("div", null, h("strong", null, "Base: "), st.base),
      h("div", null, h("strong", null, "Previous Rev: "), String(st.prev_rev),
        st.spec ? h("span", null, `  Spec: ${st.spec}`) : ""),
      h("div", null, h("strong", null, "New Rev: "), h("span", { style: { color: "var(--tk-accent)" } }, String(st.rev)),
        " \u2192 ", h("code", null, newName)),
    ));

    if (st.prev_ticket) {
      card.appendChild(h("div", { className: "badge badge-info", style: { marginBottom: "8px", display: "inline-block" } },
        `Previous ticket: ${st.prev_ticket.key} — ${st.prev_ticket.summary}`));
    }

    /* Release date */
    const twoWeeks = new Date(Date.now() + 14 * 86400e3).toISOString().slice(0, 10);
    card.appendChild(h("div", { className: "form-row" },
      h("div", { className: "form-group", style: { flex: "1" } },
        h("label", null, "Start Date"), h("input", { id: "rel-start", type: "date",
          className: "form-control", value: st.start_date || new Date().toISOString().slice(0, 10) })),
      h("div", { className: "form-group", style: { flex: "1" } },
        h("label", null, "Release Date"), h("input", { id: "rel-end", type: "date",
          className: "form-control", value: st.release_date || twoWeeks })),
    ));

    /* Continue */
    card.appendChild(h("button", { className: "btn btn-primary", style: { marginTop: "8px" },
      onclick: () => {
        st.start_date = ($("#rel-start") || {}).value || "";
        st.release_date = ($("#rel-end") || {}).value || "";
        st.version_name = newName;
        /* Copy summary format from previous ticket, or build default */
        if (st.prev_ticket?.summary) {
          st.summary_text = st.prev_ticket.summary.replace(
            /\.Rev\.\d+/g, `.Rev.${st.rev}`);
        } else {
          if (st.spec)
            st.summary_text = `${newName} FMBXXX SPEC=${st.spec}`;
          else
            st.summary_text = `${newName} FMBXXX EXP=${st.source_key}`;
        }
        /* Version description: duplicate from previous, or empty */
        st.ver_desc = st.prev_ver_desc || "";
        st.desc_text = "*Additional Comments:*\n*-*\n\n"
          + "||*Issue ID*||*Testing guidelines for Quality Assurance engineers*||\n"
          + `|${st.source_key}|${st.source_summary}|`;
        /* Clone from previous release ticket if found, else template */
        st.clone_from = st.prev_ticket?.key || null;
        st.prev_ticket_key = st.prev_ticket?.key || null;
        st.ready = true;
        this._refresh(c);
      },
    }, "Continue \u2192"));

    c.appendChild(card);
  },

  /* ── Step 4: Preview & Create ────────────────────────────── */
  _step4(c) {
    const st = this._st;
    const card = h("div", { className: "card" });
    card.appendChild(h("h3", null, "\u2463 Preview & Create"));

    /* Version name (editable) */
    card.appendChild(h("div", { className: "form-group" },
      h("label", null, "Version Name"),
      h("input", { id: "p-vname", className: "form-control", value: st.version_name })));

    /* Version description (editable) */
    card.appendChild(h("div", { className: "form-group" },
      h("label", null, "Version Description"),
      h("input", { id: "p-verdesc", className: "form-control", value: st.ver_desc || "",
        placeholder: "e.g. FMBXXX SPEC=242 (client) or FMBXXX EXP=expfw/..." })));

    /* Summary (editable) */
    card.appendChild(h("div", { className: "form-group" },
      h("label", null, "Ticket Summary"),
      h("input", { id: "p-summary", className: "form-control", value: st.summary_text })));

    /* Description – raw / rich toggle */
    const descLabel = h("div", { style: { display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" } });
    descLabel.appendChild(h("label", { style: { margin: 0 } }, "Ticket Description"));
    const rawBtn = h("button", { className: "btn btn-sm btn-primary", id: "desc-raw-btn",
      onclick: () => { $("#desc-raw").style.display = ""; $("#desc-rich").style.display = "none";
        $("#desc-raw-btn").classList.add("btn-primary"); $("#desc-rich-btn").classList.remove("btn-primary"); } }, "Raw");
    const richBtn = h("button", { className: "btn btn-sm", id: "desc-rich-btn",
      onclick: () => {
        const ta = $("#desc-raw");
        const rv = $("#desc-rich");
        rv.innerHTML = _jiraToHtml(ta.value);
        ta.style.display = "none"; rv.style.display = "";
        $("#desc-rich-btn").classList.add("btn-primary"); $("#desc-raw-btn").classList.remove("btn-primary");
      } }, "Rich Preview");
    descLabel.appendChild(rawBtn); descLabel.appendChild(richBtn);
    card.appendChild(descLabel);
    card.appendChild(h("textarea", { id: "desc-raw", className: "form-control",
      rows: "6", style: { fontFamily: "monospace", fontSize: "12px" } }, st.desc_text));
    card.appendChild(h("div", { id: "desc-rich",
      style: { display: "none", padding: "8px", border: "1px solid var(--tk-border)",
        borderRadius: "6px", background: "var(--tk-card-bg)", minHeight: "60px" } }));

    /* Dates (editable) */
    card.appendChild(h("div", { className: "form-row", style: { marginTop: "8px" } },
      h("div", { className: "form-group", style: { flex: "1" } },
        h("label", null, "Start Date"),
        h("input", { id: "p-start", type: "date", className: "form-control", value: st.start_date })),
      h("div", { className: "form-group", style: { flex: "1" } },
        h("label", null, "Release Date"),
        h("input", { id: "p-end", type: "date", className: "form-control", value: st.release_date })),
    ));

    /* Info line */
    if (st.clone_from)
      card.appendChild(h("div", { className: "text-muted", style: { fontSize: "12px", marginBottom: "4px" } },
        `Cloning from: ${st.clone_from}` + (st.prev_ticket_key ? ` • Will link to previous: ${st.prev_ticket_key}` : "")));

    /* Buttons */
    const btnRow = h("div", { className: "btn-group", style: { marginTop: "8px" } });

    /* Helper to read current form values */
    const _formValues = () => {
      const vname = $("#p-vname").value;
      const parsed = _parseVersion(vname);
      return {
        vname,
        verDesc: ($("#p-verdesc") || {}).value || "",
        summary: $("#p-summary").value,
        description: $("#desc-raw").value,
        startDate: $("#p-start").value || null,
        releaseDate: $("#p-end").value || null,
        base: parsed?.base || st.base,
        rev: parsed?.rev || st.rev,
      };
    };

    /* Create Version – opens Jira releases page + shows copyable name/desc */
    const RELEASES_URL = "https://teltonika-telematics.atlassian.net/projects/FMBP?selectedItem=com.atlassian.jira.jira-projects-plugin%3Arelease-page";
    btnRow.appendChild(h("button", { className: "btn btn-primary", onclick: () => {
      const f = _formValues();
      window.open(RELEASES_URL, "_blank");
      /* Show copyable fields */
      const box = $("#rel-ver-copy"); box.innerHTML = ""; box.style.display = "";
      const mkCopy = (label, val) => {
        const row = h("div", { style: { display: "flex", alignItems: "center", gap: "6px", marginBottom: "4px" } });
        row.appendChild(h("strong", { style: { minWidth: "90px" } }, label));
        const inp = h("input", { className: "form-control", value: val, readOnly: true,
          style: { flex: "1", fontFamily: "monospace", fontSize: "12px" } });
        row.appendChild(inp);
        row.appendChild(h("button", { className: "btn btn-sm", title: "Copy",
          onclick: () => { navigator.clipboard.writeText(val); toast("Copied!", "success"); }
        }, "\ud83d\udccb"));
        return row;
      };
      box.appendChild(mkCopy("Name:", f.vname));
      box.appendChild(mkCopy("Description:", f.verDesc));
      box.appendChild(mkCopy("Start Date:", f.startDate || ""));
      box.appendChild(mkCopy("Release Date:", f.releaseDate || ""));
    }}, "Create Version (manual)"));

    /* Create Ticket button */
    btnRow.appendChild(h("button", { className: "btn btn-primary", onclick: async (ev) => {
      const btn = ev.currentTarget; btn.disabled = true;
      const orig = btn.innerHTML;
      btn.innerHTML = '<span class="spinner-sm"></span> Creating\u2026';
      const f = _formValues();
      const ticketBody = {
        base: f.base, rev: f.rev,
        source_key: st.source_key, source_summary: st.source_summary,
        summary: f.summary, description: f.description,
      };
      if (st.spec) ticketBody.spec = st.spec;
      if (st.client) ticketBody.client = st.client;
      if (st.exp) ticketBody.exp = st.exp;
      if (st.is_spec) ticketBody.has_spec = true;
      if (st.clone_from) ticketBody.clone_from = st.clone_from;
      if (st.prev_ticket_key) ticketBody.prev_ticket_key = st.prev_ticket_key;
      if (f.startDate) ticketBody.start_date = f.startDate;
      if (f.releaseDate) ticketBody.release_date = f.releaseDate;
      try {
        const tRes = await api("/api/release/ticket", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(ticketBody),
        });
        toast(`Ticket ${tRes.key} created!`, "success");
        const res = $("#rel-result"); res.innerHTML = "";
        const jiraUrl = `https://teltonika-telematics.atlassian.net/browse/${tRes.key}`;
        res.appendChild(h("div", { className: "card", style: { background: "var(--tk-success-bg, #1a3a2a)", marginTop: "12px" } },
          h("p", null, "\u2705 Release ticket created!"),
          h("p", null, h("strong", null, "Version: "), f.vname),
          h("p", null, h("strong", null, "Ticket: "), h("a", { href: jiraUrl, target: "_blank", style: { color: "var(--tk-accent)" } }, tRes.key),
            " \u2014 ", tRes.summary || ""),
          h("button", { className: "btn btn-primary btn-sm", style: { marginTop: "6px" },
            onclick: () => window.open(jiraUrl, "_blank") }, "Open in Jira"),
        ));
      } catch (e) { toast(`Ticket creation failed: ${e.message}`, "error"); }
      finally { btn.disabled = false; btn.innerHTML = orig; }
    }}, "Create Ticket"));

    btnRow.appendChild(h("button", { className: "btn", onclick: () => { this._st = {}; this._refresh(c); } }, "Reset"));

    card.appendChild(btnRow);
    card.appendChild(h("div", { id: "rel-ver-copy", style: { display: "none", marginTop: "10px", padding: "8px",
      border: "1px solid var(--tk-border)", borderRadius: "6px", background: "var(--tk-card-bg)" } }));
    card.appendChild(h("div", { id: "rel-result" }));
    c.appendChild(card);
  },

  /* ================================================================
     VERSIONS TAB
     ================================================================ */
  async _renderVersions(c) {
    c.innerHTML = "";
    c.appendChild(h("div", { className: "card" },
      h("div", { className: "form-row" },
        h("input", { id: "ver-q", className: "form-control", placeholder: "Filter by base (e.g. FMB.Ver.04.02.00)\u2026",
          style: { flex: "1" } }),
        h("button", { className: "btn btn-primary", onclick: async () => {
          const q = ($("#ver-q").value || "").trim();
          const ld = document.getElementById("ver-list");
          ld.innerHTML = '<div class="spinner"></div>';
          try {
            let url = "/api/release/versions";
            if (q) url += `?base=${encodeURIComponent(q)}`;
            const vrs = await api(url);
            ld.innerHTML = "";
            createTable(ld,
              [{ key: "name", label: "Name" },
               { key: "released", label: "Released", render: r => r.released ? h("span", { className: "badge badge-green" }, "Yes") : "" },
               { key: "releaseDate", label: "Date" },
               { key: "description", label: "Description" }],
              vrs);
            const tbl = ld.querySelector("table");
            if (tbl) makeColumnsResizable(tbl, "release_ver_col_widths");
          } catch (e) { ld.innerHTML = "<p>Failed to load versions</p>"; }
        }}, h("span", { className: "btn-icon", html: icons.search }), "Search")),
    ));
    c.appendChild(h("div", { id: "ver-list" }));
  },
});
