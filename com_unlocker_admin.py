"""
COM Unlocker – Standalone admin-elevated instance.

This script self-elevates via UAC if not already admin, then starts a
minimal FastAPI server with only the COM Unlocker functionality.
"""

import ctypes
import os
import socket
import subprocess
import sys
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ── Admin elevation ──────────────────────────────────────────────
def _is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _relaunch_as_admin():
    """Re-launch ourselves elevated (triggers UAC prompt)."""
    params = " ".join(f'"{a}"' for a in sys.argv)
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, None, 1,
    )
    sys.exit(0)


def _find_free_port(start: int = 8700, end: int = 8799) -> int:
    for port in range(start, end + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                s.bind(("127.0.0.1", port))
            return port
        except OSError:
            continue
    raise RuntimeError(f"No free port in {start}–{end}")


# ── Minimal app ──────────────────────────────────────────────────
def create_admin_app():
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse

    app = FastAPI(title="COM Unlocker (Admin)")

    # Register COM plugin routes
    from app.plugins.com_unlocker import plugin as com_plugin
    com_plugin.register_routes(app)

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return _STANDALONE_HTML

    return app


_STANDALONE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>COM Unlocker (Admin)</title>
<style>
:root {
  --navy: #0f1923; --navy-light: #162230; --navy-mid: #1c2d3f;
  --surface: #213347; --border: #2a3f55; --border-light: #355169;
  --green: #00b86b; --green-dim: #00995a; --green-glow: rgba(0,184,107,.15);
  --fg: #e8edf2; --fg-dim: #8899aa; --fg-muted: #5c7080;
  --red: #ef4444; --red-dim: rgba(239,68,68,.12);
  --yellow: #f59e0b; --yellow-dim: rgba(245,158,11,.12);
  --font: 'Segoe UI', system-ui, sans-serif;
  --mono: 'Cascadia Mono', 'Consolas', monospace;
  --radius: 8px;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body { font-family: var(--font); background: var(--navy); color: var(--fg);
  font-size: 14px; line-height: 1.5; height: 100%; }
.shell { max-width: 720px; margin: 0 auto; padding: 32px 24px; }
.header { display: flex; align-items: center; gap: 12px; margin-bottom: 24px; }
.header svg { width: 28px; height: 28px; color: var(--green); }
.header h1 { font-size: 20px; font-weight: 700; }
.admin-badge { display: inline-flex; align-items: center; gap: 4px;
  font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 10px;
  background: var(--green-glow); color: var(--green); }
.card { background: var(--navy-light); border: 1px solid var(--border);
  border-radius: 12px; padding: 20px; margin-bottom: 16px; }
.card-warn { border-color: rgba(245,158,11,.3); background: var(--yellow-dim); }
.card-error { border-color: rgba(239,68,68,.3); background: var(--red-dim); }
.btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 16px;
  border-radius: 6px; border: 1px solid var(--border); background: var(--navy-light);
  color: var(--fg); font-size: 13px; font-weight: 500; cursor: pointer;
  font-family: var(--font); transition: all .18s; }
.btn:hover { background: var(--navy-mid); border-color: var(--border-light); }
.btn-primary { background: var(--green); border-color: var(--green); color: #fff; }
.btn-primary:hover { background: var(--green-dim); border-color: var(--green-dim); }
.btn-danger { background: transparent; border-color: var(--red); color: var(--red); }
.btn-danger:hover { background: var(--red-dim); }
.btn-sm { padding: 4px 8px; font-size: 12px; }
.port-card { margin-bottom: 8px; }
.port-row { display: flex; justify-content: space-between; align-items: center; }
.port-info { display: flex; align-items: center; gap: 8px; }
.scan-result { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border); }
.scan-process { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; }
.spinner { display: inline-block; width: 20px; height: 20px; border: 2px solid var(--border);
  border-top-color: var(--green); border-radius: 50%; animation: spin .7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.text-muted { color: var(--fg-muted); }
.empty { text-align: center; padding: 32px; color: var(--fg-dim); }
</style>
</head>
<body>
<div class="shell">
  <div class="header">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
         stroke-linecap="round" stroke-linejoin="round">
      <rect width="18" height="11" x="3" y="11" rx="2" ry="2"/>
      <path d="M7 11V7a5 5 0 0 1 9.9-1"/>
    </svg>
    <h1>COM Unlocker</h1>
    <span class="admin-badge" id="admin-badge">Checking…</span>
  </div>
  <div id="alerts"></div>
  <div style="margin-bottom:16px">
    <button class="btn btn-primary" onclick="refresh()">↻ Refresh Ports</button>
  </div>
  <div id="ports"><div class="spinner"></div></div>
</div>
<script>
async function api(url, opts={}) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function loadStatus() {
  const s = await api('/api/com/status');
  const badge = document.getElementById('admin-badge');
  const alerts = document.getElementById('alerts');
  if (s.admin) {
    badge.textContent = '✓ Administrator';
    badge.style.background = 'var(--green-glow)';
    badge.style.color = 'var(--green)';
  } else {
    badge.textContent = '✗ Not Admin';
    badge.style.background = 'var(--red-dim)';
    badge.style.color = 'var(--red)';
  }
  if (!s.handle_found) {
    alerts.innerHTML = '<div class="card card-error"><strong>Missing Tool</strong><p class="text-muted">handle64.exe not found in com-killer/ directory</p></div>';
  }
}

async function refresh() {
  const c = document.getElementById('ports');
  c.innerHTML = '<div class="spinner"></div>';
  try {
    const ports = await api('/api/com/ports');
    c.innerHTML = '';
    if (!ports.length) { c.innerHTML = '<div class="empty">No COM ports detected</div>'; return; }
    for (const port of ports) {
      const card = document.createElement('div');
      card.className = 'card port-card';
      card.innerHTML = `
        <div class="port-row">
          <div class="port-info"><strong>${port.port}</strong><span class="text-muted">${port.desc||''}</span></div>
          <button class="btn btn-primary btn-sm" onclick="scan('${port.port}', this)">Scan</button>
        </div>`;
      c.appendChild(card);
    }
  } catch(e) { c.innerHTML = '<div class="empty">Failed to load ports</div>'; }
}

async function scan(port, btn) {
  const card = btn.closest('.port-card');
  let rd = card.querySelector('.scan-result');
  if (!rd) { rd = document.createElement('div'); rd.className = 'scan-result'; card.appendChild(rd); }
  rd.innerHTML = '<div class="spinner"></div>';
  try {
    const r = await api('/api/com/scan/' + encodeURIComponent(port));
    rd.innerHTML = '';
    if (r.locked && r.process) {
      const p = r.process;
      rd.innerHTML = `<div class="scan-process"><span>PID ${p.pid} — ${p.name}</span>
        <button class="btn btn-danger btn-sm" onclick="kill(${p.pid})">Kill</button></div>`;
    } else {
      rd.innerHTML = '<span class="text-muted">' + (r.probe_msg || 'No locks found') + '</span>';
    }
    rd.innerHTML += `<button class="btn btn-sm" style="margin-top:8px" onclick="restart('${port}')">↻ Restart Device</button>`;
  } catch(e) { rd.innerHTML = '<p>Scan failed</p>'; }
}

async function kill(pid) {
  try { await api('/api/com/kill/' + pid, { method: 'POST' }); alert('Killed ' + pid); refresh(); }
  catch(e) { alert('Kill failed: ' + e.message); }
}

async function restart(port) {
  try { await api('/api/com/restart/' + encodeURIComponent(port), { method: 'POST' }); alert('Restarted'); }
  catch(e) { alert('Restart failed: ' + e.message); }
}

loadStatus();
refresh();
</script>
</body>
</html>
"""


# ── Main ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not _is_admin():
        print("Requesting administrator privileges…")
        _relaunch_as_admin()

    import uvicorn

    port = _find_free_port()
    print(f"COM Unlocker (Admin) starting on http://127.0.0.1:{port}")
    webbrowser.open(f"http://127.0.0.1:{port}")
    uvicorn.run(create_admin_app(), host="127.0.0.1", port=port)
