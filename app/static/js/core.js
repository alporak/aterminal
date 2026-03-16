/* ================================================================
   Alps Toolkit – Core Framework
   DOM helpers, toast, API, plugin registry, tabs, tables, hex
   ================================================================ */

// ─── DOM helpers ───────────────────────────────────────────────
export const $ = (sel, ctx = document) => ctx.querySelector(sel);
export const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

/** Tiny element builder. */
export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "style" && typeof v === "object") Object.assign(el.style, v);
      else if (k.startsWith("on")) el.addEventListener(k.slice(2).toLowerCase(), v);
      else if (k === "className") el.className = v;
      else if (k === "html") el.innerHTML = v;
      else el.setAttribute(k, v);
    }
  }
  for (const c of children.flat()) {
    if (c == null) continue;
    el.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return el;
}

// ─── Toast notifications ──────────────────────────────────────
export function toast(msg, type = "info", ms = 3500) {
  const box = document.getElementById("toast-container");
  const el = h("div", { className: `toast toast-${type}` }, msg);
  box.appendChild(el);
  requestAnimationFrame(() => el.classList.add("show"));
  setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 300);
  }, ms);
}

// ─── API helper ───────────────────────────────────────────────
export async function api(url, opts = {}) {
  const method = (opts.method || "GET").toUpperCase();
  let logBody = "";
  if (opts.body) {
    try { logBody = typeof opts.body === "string" ? JSON.parse(opts.body) : "(FormData)"; }
    catch { logBody = "(body)"; }
  }
  console.log(`[API] ${method} ${url}`, logBody);
  try {
    const res = await fetch(url, opts);
    if (!res.ok) {
      let msg;
      try {
        const j = await res.json();
        // Handle FastAPI validation errors (detail is an array)
        if (Array.isArray(j.detail)) {
          msg = j.detail.map(e => {
            const loc = (e.loc || []).join(" → ");
            return loc ? `${loc}: ${e.msg}` : (e.msg || JSON.stringify(e));
          }).join("; ");
        } else if (typeof j.detail === "string") {
          msg = j.detail;
        } else if (j.detail) {
          msg = JSON.stringify(j.detail);
        } else if (j.errorMessages && j.errorMessages.length) {
          msg = j.errorMessages.join("; ");
        } else {
          msg = JSON.stringify(j);
        }
      } catch { msg = await res.text(); }
      console.error(`[API] ${method} ${url} → ${res.status}:`, msg);
      throw new Error(msg || `HTTP ${res.status}`);
    }
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("json")) {
      const data = await res.json();
      console.log(`[API] ${method} ${url} → OK`, Array.isArray(data) ? `[${data.length} items]` : data);
      return data;
    }
    const text = await res.text();
    console.log(`[API] ${method} ${url} → OK (text, ${text.length} chars)`);
    return text;
  } catch (e) {
    console.error(`[API] ${method} ${url} FAILED:`, e.message);
    toast(String(e.message || e), "error");
    throw e;
  }
}

// ─── Plugin registry & navigation ────────────────────────────
export const plugins = [];
let activePlugin = null;

export function registerPlugin(p) { plugins.push(p); }

export function renderNav() {
  const nav = document.getElementById("nav");
  nav.innerHTML = "";
  plugins.sort((a, b) => (a.order || 0) - (b.order || 0));

  // Home button
  const homeBtn = h("button", {
    className: "nav-btn" + (activePlugin === null ? " active" : ""),
    onclick: () => showHome(),
  });
  homeBtn.appendChild(h("span", { className: "nav-icon", html: icons.home }));
  homeBtn.appendChild(document.createTextNode("Home"));
  nav.appendChild(homeBtn);

  for (const p of plugins) {
    const btn = h("button", {
      className: "nav-btn" + (activePlugin === p ? " active" : ""),
      onclick: () => switchPlugin(p),
    });
    if (p.svgIcon) {
      const iconSpan = h("span", { className: "nav-icon", html: p.svgIcon });
      btn.appendChild(iconSpan);
    }
    btn.appendChild(document.createTextNode(p.name));
    nav.appendChild(btn);
  }
}

function _resetMain() {
  const main = document.getElementById("main");
  if (activePlugin?.destroy) activePlugin.destroy();
  activePlugin = null;
  main.innerHTML = "";
  main.removeAttribute("style");       // clear inline styles (e.g. from Log Parser)
  return main;
}

export function switchPlugin(plugin) {
  const main = _resetMain();
  activePlugin = plugin;
  renderNav();
  plugin.init(main);
}

export function showHome() {
  const main = _resetMain();
  renderNav();

  const wrap = h("div", { className: "home-page" });
  wrap.appendChild(h("div", { className: "home-header" },
    h("h1", null, "Alps Toolkit"),
    h("p", { className: "text-dim" }, "Select a tool to get started"),
  ));

  const grid = h("div", { className: "home-grid" });
  for (const p of plugins) {
    const card = h("button", {
      className: "home-card",
      onclick: () => switchPlugin(p),
    },
      h("span", { className: "home-card-icon", html: p.svgIcon || icons.settings }),
      h("span", { className: "home-card-name" }, p.name),
    );
    grid.appendChild(card);
  }
  wrap.appendChild(grid);
  main.appendChild(wrap);
}

// ─── Tabs helper ──────────────────────────────────────────────
export function createTabs(container, tabs) {
  const bar = h("div", { className: "tab-bar" });
  const body = h("div", { className: "tab-body" });
  container.appendChild(bar);
  container.appendChild(body);
  let active = null;

  function activate(tab) {
    if (active === tab) return;
    active = tab;
    $$(".tab-btn", bar).forEach(b => b.classList.toggle("active", b.dataset.id === tab.id));
    body.innerHTML = "";
    tab.render(body);
  }
  for (const t of tabs) {
    bar.appendChild(h("button", {
      className: "tab-btn", "data-id": t.id,
      onclick: () => activate(t),
    }, t.label));
  }
  if (tabs.length) activate(tabs[0]);
  return { activate, body, bar };
}

// ─── Sortable table ──────────────────────────────────────────
export function createTable(container, columns, rows, { maxRows = 500, sortable = true } = {}) {
  if (!rows?.length) {
    container.appendChild(h("div", { className: "empty" },
      h("div", { className: "empty-icon" }, "—"),
      h("p", null, "No data")));
    return;
  }
  const wrap = h("div", { className: "table-wrap" });
  const table = h("table");
  const thead = h("thead");
  const tbody = h("tbody");
  let sortCol = null, sortAsc = true;

  function fill(data) {
    tbody.innerHTML = "";
    const slice = data.slice(0, maxRows);
    for (const row of slice) {
      const tr = h("tr");
      for (const col of columns) {
        const val = col.render ? col.render(row) : (row[col.key] ?? "");
        const td = h("td");
        if (val instanceof HTMLElement) td.appendChild(val);
        else td.textContent = String(val);
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
    if (data.length > maxRows)
      tbody.appendChild(h("tr", null,
        h("td", { colspan: String(columns.length), className: "text-muted" },
          `Showing ${maxRows} of ${data.length} rows`)));
  }

  const hr = h("tr");
  for (const col of columns) {
    hr.appendChild(h("th", {
      style: sortable ? { cursor: "pointer" } : {},
      onclick: sortable ? () => {
        if (sortCol === col.key) sortAsc = !sortAsc;
        else { sortCol = col.key; sortAsc = true; }
        const sorted = [...rows].sort((a, b) => {
          const va = a[col.key], vb = b[col.key];
          if (va == null) return 1; if (vb == null) return -1;
          const cmp = typeof va === "number" ? va - vb : String(va).localeCompare(String(vb));
          return sortAsc ? cmp : -cmp;
        });
        fill(sorted);
      } : undefined,
    }, col.label));
  }
  thead.appendChild(hr);
  table.appendChild(thead);
  table.appendChild(tbody);
  wrap.appendChild(table);
  container.appendChild(wrap);
  fill(rows);
}

// ─── Resizable table columns ─────────────────────────────────
/**
 * Make a <table> element's columns resizable by dragging header borders.
 * Optionally persists widths to localStorage under `storageKey`.
 *
 * @param {HTMLTableElement} table - The table element
 * @param {string} [storageKey] - localStorage key for persisting widths
 */
export function makeColumnsResizable(table, storageKey) {
  if (!table) return;
  table.style.tableLayout = "fixed";
  table.classList.add("tk-resizable");

  const thead = table.querySelector("thead");
  if (!thead) return;

  const ths = [...thead.querySelectorAll("th")];
  if (!ths.length) return;

  // Restore saved widths
  let saved = null;
  if (storageKey) {
    try {
      const raw = localStorage.getItem(storageKey);
      if (raw) saved = JSON.parse(raw);
    } catch {}
  }

  // Initialize widths
  requestAnimationFrame(() => {
    const tableW = table.offsetWidth;
    if (!tableW) return;

    ths.forEach((th, i) => {
      if (saved && saved[i] != null) {
        th.style.width = saved[i] + "px";
      } else if (!th.style.width) {
        th.style.width = th.offsetWidth + "px";
      }
    });

    // Add resize handles to each header except the last
    ths.forEach((th, i) => {
      if (i === ths.length - 1) return;
      th.style.position = "relative";

      const handle = document.createElement("div");
      handle.className = "tk-col-resize-handle";
      th.appendChild(handle);

      let startX, startW, nextStartW, nextTh;
      handle.addEventListener("mousedown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        startX = e.clientX;
        startW = th.offsetWidth;
        nextTh = ths[i + 1];
        nextStartW = nextTh ? nextTh.offsetWidth : 0;
        handle.classList.add("active");
        document.body.style.cursor = "col-resize";
        document.body.style.userSelect = "none";

        const onMove = (ev) => {
          const dx = ev.clientX - startX;
          const newW = Math.max(30, startW + dx);
          th.style.width = newW + "px";
          if (nextTh) {
            const nextW = Math.max(30, nextStartW - dx);
            nextTh.style.width = nextW + "px";
          }
        };
        const onUp = () => {
          handle.classList.remove("active");
          document.body.style.cursor = "";
          document.body.style.userSelect = "";
          document.removeEventListener("mousemove", onMove);
          document.removeEventListener("mouseup", onUp);
          _saveColWidths(table, ths, storageKey);
        };
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
      });
    });
  });
}

function _saveColWidths(table, ths, storageKey) {
  if (!storageKey) return;
  try {
    const widths = ths.map(th => th.offsetWidth);
    localStorage.setItem(storageKey, JSON.stringify(widths));
  } catch {}
}

// ─── Hex renderer ────────────────────────────────────────────
export function renderHex(container, hexStr, annotations) {
  const div = h("div", { className: "hex-viewer" });
  if (!annotations?.length) { div.textContent = hexStr; container.appendChild(div); return; }
  const colors = ["#e74c3c","#3498db","#2ecc71","#e67e22","#9b59b6",
                   "#1abc9c","#f1c40f","#e91e63","#00bcd4","#ff5722"];
  const hex = hexStr.replace(/\s/g, "");
  const sorted = [...annotations].sort((a, b) => a.start - b.start);
  let pos = 0;
  const fmtRange = (s, e) => {
    let r = "";
    for (let i = s; i < e && i * 2 < hex.length; i++) r += hex.substr(i * 2, 2) + " ";
    return r;
  };
  for (let i = 0; i < sorted.length; i++) {
    const ann = sorted[i], color = ann.color || colors[i % colors.length];
    if (ann.start > pos) div.appendChild(document.createTextNode(fmtRange(pos, ann.start)));
    div.appendChild(h("span", { style: { color, fontWeight: "bold" }, title: ann.label }, fmtRange(ann.start, ann.end)));
    pos = ann.end;
  }
  if (pos < hex.length / 2) div.appendChild(document.createTextNode(fmtRange(pos, hex.length / 2)));
  container.appendChild(div);
}

// ─── SVG Icons ───────────────────────────────────────────────
export const icons = {
  satellite: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 7L9 3L5 7l4 4"/><path d="m17 11 4 4-4 4-4-4"/><path d="m8 12 4 4"/><path d="m4.93 19.07 2.76-2.76"/><circle cx="4" cy="20" r="1"/></svg>`,
  file: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14,2 14,8 20,8"/></svg>`,
  unlock: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/></svg>`,
  clock: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12,6 12,12 16,14"/></svg>`,
  rocket: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/></svg>`,
  refresh: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 16h5v5"/></svg>`,
  search: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>`,
  send: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/></svg>`,
  trash: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>`,
  upload: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17,8 12,3 7,8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>`,
  plug: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22v-5"/><path d="M9 8V2"/><path d="M15 8V2"/><path d="M18 8v5a6 6 0 0 1-6 6 6 6 0 0 1-6-6V8z"/></svg>`,
  settings: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>`,
  check: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>`,
  x: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="M6 6l12 12"/></svg>`,
  alert: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>`,
  home: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>`,
  shield: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>`,
  play: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="6,3 20,12 6,21"/></svg>`,
  stop: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="5" y="5" rx="1"/></svg>`,
  link: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>`,
};

// ─── Boot ────────────────────────────────────────────────────
export function boot() {
  renderNav();
  showHome();
}
