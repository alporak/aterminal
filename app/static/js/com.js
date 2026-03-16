/* ================================================================
   COM Unlocker Plugin
   ================================================================ */
import { h, $, api, toast, registerPlugin, icons } from "./core.js";

registerPlugin({
  id: "com", name: "COM Unlocker", order: 3,
  svgIcon: icons.unlock,

  init(container) { this._c = container; this._render(); },
  destroy() {},

  async _render() {
    const c = this._c; c.innerHTML = "";
    let status;
    try { status = await api("/api/com/status"); }
    catch {
      c.appendChild(h("div", { className: "card" },
        h("p", { className: "text-muted" }, "COM Unlocker unavailable")));
      return;
    }

    if (!status.admin)
      c.appendChild(h("div", { className: "card card-warn" },
        h("div", { className: "card-alert" },
          h("span", { className: "card-alert-icon", html: icons.alert }),
          h("div", null,
            h("strong", null, "Not Administrator"),
            h("p", { className: "text-muted" }, "Run as administrator for full functionality"),
            h("button", { className: "btn btn-primary", style: { marginTop: ".5rem" },
              onclick: async () => {
                try {
                  await api("/api/com/launch_admin", { method: "POST" });
                  toast("Admin instance launching…", "success");
                } catch (e) {
                  toast("Failed to launch: " + e.message, "error");
                }
              }},
              h("span", { className: "btn-icon", html: icons.shield }), "Open with Admin Rights")))));

    if (!status.handle_found)
      c.appendChild(h("div", { className: "card card-error" },
        h("div", { className: "card-alert" },
          h("span", { className: "card-alert-icon", html: icons.alert }),
          h("div", null,
            h("strong", null, "Missing Tool"),
            h("p", { className: "text-muted" }, "handle64.exe not found in com-killer/ directory")))));

    c.appendChild(h("button", { className: "btn", style: { marginBottom: "1rem" },
      onclick: () => this._render() },
      h("span", { className: "btn-icon", html: icons.refresh }), "Refresh Ports"));

    try {
      const ports = await api("/api/com/ports");
      if (!ports.length) {
        c.appendChild(h("div", { className: "empty" },
          h("div", { className: "empty-icon", html: icons.plug }),
          h("p", null, "No COM ports detected")));
        return;
      }
      for (const port of ports) {
        const card = h("div", { className: "card port-card" });
        card.appendChild(h("div", { className: "port-row" },
          h("div", { className: "port-info" },
            h("strong", null, port.port),
            h("span", { className: "text-muted" }, port.desc || "")),
          h("button", { className: "btn btn-primary btn-sm", onclick: async () => {
            let rd = $(".scan-result", card);
            if (!rd) { rd = h("div", { className: "scan-result" }); card.appendChild(rd); }
            rd.innerHTML = '<div class="spinner"></div>';
            try {
              const r = await api(`/api/com/scan/${encodeURIComponent(port.port)}`);
              rd.innerHTML = "";
              if (r.locked && r.process) {
                const p = r.process;
                rd.appendChild(h("div", { className: "scan-process" },
                  h("span", null, `PID ${p.pid} — ${p.name}`),
                  h("button", { className: "btn btn-danger btn-sm", onclick: async () => {
                    await api(`/api/com/kill/${p.pid}`, { method: "POST" });
                    toast(`Killed ${p.pid}`, "success");
                  }}, "Kill")));
              } else {
                rd.appendChild(h("span", { className: "text-muted" }, r.probe_msg || "No locks found"));
              }
              rd.appendChild(h("button", { className: "btn btn-sm", style: { marginTop: ".5rem" },
                onclick: async () => {
                  try {
                    await api(`/api/com/restart/${encodeURIComponent(port.port)}`, { method: "POST" });
                    toast("Restarted", "success");
                  } catch (e) { console.error("[COM] Restart failed:", e.message); }
                }},
                h("span", { className: "btn-icon", html: icons.refresh }), "Restart"));
            } catch (e) { console.error("[COM] Scan failed:", e.message); rd.innerHTML = "<p>Scan failed</p>"; }
          }},
            h("span", { className: "btn-icon", html: icons.search }), "Scan"),
        ));
        c.appendChild(card);
      }
    } catch (e) { console.error("[COM] Load ports failed:", e.message); }
  },
});
