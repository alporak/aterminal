"""
Teltonika GPS Server – Streamlit UI
Real-time device monitoring with @st.fragment auto-refresh.
No full-page polling — only data sections re-render every ~1 s.
"""

import streamlit as st
import time
import pandas as pd
import json
import os
import sys
import datetime as _dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server_app.teltonika_server import (
    TeltonikaServer, io_name, IO_ELEMENT_NAMES,
    refresh_io_names, annotate_packet,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="GPS Server", page_icon="📡", layout="wide")

# ── Compact CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; padding-bottom: 0; }
    [data-testid="stMetric"] { padding: 0.4rem 0; }
    [data-testid="stMetricValue"] { font-size: 1.1rem; }
    [data-testid="stMetricLabel"] { font-size: 0.75rem; }
    .server-status {
        display: inline-block; padding: 2px 10px; border-radius: 12px;
        font-size: 0.8rem; font-weight: 600; margin-left: 8px;
        vertical-align: middle;
    }
    .status-on  { background: #0e6b0e; color: #fff; }
    .status-off { background: #6b0e0e; color: #fff; }
    /* Hex viewer */
    .hex-viewer {
        font-family: 'Cascadia Mono','Consolas','Courier New',monospace;
        font-size: 12.5px; line-height: 1.7;
        background: #0d1117; border-radius: 8px;
        padding: 12px 16px; overflow: auto; max-height: 480px;
        border: 1px solid #30363d;
    }
    .hex-viewer .hr { white-space: nowrap; }
    .hex-viewer .ho { color: #6e7681; margin-right: 12px; user-select: none; }
    .hex-viewer .hb {
        padding: 1px 2px; border-radius: 2px; margin: 0 1px;
        cursor: default; color: #e6edf3;
    }
    .hex-viewer .ha { margin-left: 14px; color: #8b949e; letter-spacing: 0.5px; }
    .hex-legend { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px; }
    .hex-legend span {
        font-size: 11px; padding: 1px 7px; border-radius: 3px;
        color: #fff; white-space: nowrap;
    }
    .log-entry { font-family: monospace; font-size: 0.82rem; padding: 1px 0; }
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  Configuration helpers
# ═══════════════════════════════════════════════════════════════════════════════

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                           'toolkit_settings.json')
DEFAULT_AVL_EXCEL = (
    r"C:\Users\orak.al\Documents\fmb-firmware\teltonika_app"
    r"\inc\event_queue\eq_avl_ids\FMB_AVL_IDS.xlsx"
)


def load_config() -> dict:
    defaults = {'server_port': 8000, 'server_protocol': 'TCP',
                'avl_ids_path': DEFAULT_AVL_EXCEL}
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                cfg = json.load(f)
            return {
                'server_port': cfg.get('server_port',
                                       cfg.get('tcp_port', defaults['server_port'])),
                'server_protocol': cfg.get('server_protocol',
                                           defaults['server_protocol']),
                'avl_ids_path': cfg.get('avl_ids_path', defaults['avl_ids_path']),
            }
    except Exception:
        pass
    return defaults


def save_config(port: int, protocol: str, avl_path: str | None = None):
    try:
        cfg = {}
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                cfg = json.load(f)
        cfg.pop('tcp_port', None); cfg.pop('udp_port', None)
        cfg['server_port'] = port
        cfg['server_protocol'] = protocol
        if avl_path is not None:
            cfg['avl_ids_path'] = avl_path
        with open(CONFIG_PATH, 'w') as f:
            json.dump(cfg, f, indent=4)
        return True
    except Exception as e:
        st.error(f"Config save error: {e}")
        return False


def save_avl_path(avl_path: str):
    try:
        cfg = {}
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                cfg = json.load(f)
        cfg['avl_ids_path'] = avl_path
        with open(CONFIG_PATH, 'w') as f:
            json.dump(cfg, f, indent=4)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
#  Server singleton (session-state)
# ═══════════════════════════════════════════════════════════════════════════════

if 'server' not in st.session_state:
    cfg = load_config()
    srv = TeltonikaServer(port=cfg['server_port'], protocol=cfg['server_protocol'])
    err = srv.start()
    st.session_state.server_start_error = err
    st.session_state.server = srv

server: TeltonikaServer = st.session_state.server

if 'io_selected_cols' not in st.session_state:
    st.session_state.io_selected_cols = []

if 'avl_loaded' not in st.session_state:
    cfg = load_config()
    avl_path = cfg.get('avl_ids_path', DEFAULT_AVL_EXCEL)
    if avl_path and os.path.isfile(avl_path):
        err = refresh_io_names(avl_path)
        st.session_state.avl_load_error = err
    else:
        st.session_state.avl_load_error = None
    st.session_state.avl_loaded = True


# ═══════════════════════════════════════════════════════════════════════════════
#  Hex viewer HTML builder
# ═══════════════════════════════════════════════════════════════════════════════

def build_hex_html(raw_hex: str, annotations: list[dict]) -> str:
    try:
        data = bytes.fromhex(raw_hex)
    except Exception:
        return f'<pre style="color:#e6edf3">{raw_hex}</pre>'
    n = len(data)
    if n == 0:
        return '<p style="color:#8b949e">Empty packet</p>'

    byte_bg  = [''] * n
    byte_tip = [''] * n
    for ann in annotations:
        for i in range(ann['s'], min(ann['e'], n)):
            byte_bg[i]  = ann['color']
            byte_tip[i] = ann['label']

    seen = set(); legend = []
    for ann in annotations:
        if ann['color'] not in seen:
            seen.add(ann['color'])
            short = ann['label'].split(':')[0].split('=')[0].strip()[:25]
            legend.append(f'<span style="background:{ann["color"]}">{short}</span>')
    legend_html = f'<div class="hex-legend">{"".join(legend)}</div>' if legend else ''

    rows = []
    for off in range(0, n, 16):
        chunk = data[off:off + 16]
        hcells = []; acells = []
        for i, b in enumerate(chunk):
            idx = off + i
            bg  = byte_bg[idx]
            tip = (byte_tip[idx].replace('"', '&quot;')
                   .replace("'", '&#39;').replace('<', '&lt;'))
            if bg:
                hcells.append(f'<span class="hb" style="background:{bg}" '
                              f'title="{tip}">{b:02X}</span>')
            else:
                hcells.append(f'<span class="hb" title="{tip}">{b:02X}</span>')
            ch = chr(b) if 32 <= b < 127 else '·'
            if ch in ('<', '>', '&'):
                ch = {'<': '&lt;', '>': '&gt;', '&': '&amp;'}[ch]
            astyle = f' style="background:{bg}"' if bg else ''
            acells.append(f'<span{astyle} title="{tip}">{ch}</span>')
        for _ in range(16 - len(hcells)):
            hcells.append('<span class="hb" style="color:transparent">  </span>')
        hl = ' '.join(hcells[:8]); hr = ' '.join(hcells[8:])
        rows.append(f'<div class="hr"><span class="ho">{off:08X}</span>'
                    f'{hl}  {hr}<span class="ha">{"".join(acells)}</span></div>')

    return f'{legend_html}<div class="hex-viewer">{"".join(rows)}</div>'


# ═══════════════════════════════════════════════════════════════════════════════
#  @st.fragment — auto-refreshing data sections (partial re-render only)
# ═══════════════════════════════════════════════════════════════════════════════

# ── Sidebar live metrics / devices / queue ────────────────────────────────────
@st.fragment(run_every="1s")
def _sidebar_live():
    srv: TeltonikaServer = st.session_state.get('server')
    if not srv:
        return

    with srv.lock:
        n_rec = len(srv.parsed_records)
        n_cmd = len(srv.command_history)
        n_raw = len(srv.raw_messages)
        n_log = len(srv.log_messages)

    mc1, mc2 = st.columns(2)
    mc1.metric("Records", n_rec)
    mc2.metric("Commands", n_cmd)
    mc3, mc4 = st.columns(2)
    mc3.metric("Raw Msgs", n_raw)
    mc4.metric("Logs", n_log)

    st.divider()

    # Devices
    st.subheader("🔌 Devices")
    devices = srv.get_connected_devices()
    if devices:
        for d in devices:
            st.markdown(
                f"**{d['IMEI']}** · {d['Protocol']}  \n"
                f"<small>{d['Address']} · {d['Status']}</small>",
                unsafe_allow_html=True,
            )
    else:
        st.caption("No devices connected")

    # Queue
    q_status = srv.get_queue_status()
    if q_status:
        st.divider()
        st.subheader("📬 Queue")
        for im, qs in q_status.items():
            active = qs.get('active')
            st.text(f"{im}: {qs['queued']} queued"
                    + (f" | ⏳ {active}" if active else ""))


# ── Live Data table ───────────────────────────────────────────────────────────
@st.fragment(run_every="1s")
def _live_data_table():
    srv: TeltonikaServer = st.session_state.get('server')
    if not srv:
        return

    with srv.lock:
        records = list(srv.parsed_records)
    selected_ios = st.session_state.get('io_selected_cols', [])

    if not records:
        st.info("Waiting for data…")
        return

    rows = []
    for rec in records:
        row = {
            'IMEI': rec.get('IMEI', ''),
            'Proto': rec.get('Protocol', ''),
            'Timestamp': rec.get('Timestamp', ''),
            'Lat': rec.get('Latitude', ''),
            'Lon': rec.get('Longitude', ''),
            'Speed': rec.get('Speed', ''),
            'Angle': rec.get('Angle', ''),
            'Sats': rec.get('Satellites', ''),
            'Alt': rec.get('Altitude', ''),
            'Prio': rec.get('Priority', ''),
            'EvtIO': rec.get('Event_IO', ''),
        }
        io = rec.get('IO_Data', {})
        for iid in selected_ios:
            row[io_name(iid)] = io.get(iid, '')
        rows.append(row)

    st.dataframe(pd.DataFrame(rows), use_container_width=True, height=550)
    st.caption(f"{len(records)} records · live")


# ── Recent command responses ──────────────────────────────────────────────────
@st.fragment(run_every="1s")
def _cmd_responses():
    srv: TeltonikaServer = st.session_state.get('server')
    if not srv:
        return

    with srv.lock:
        recent = list(srv.command_history[:15])

    if not recent:
        st.caption("No responses yet — send a command above")
        return

    for e in recent:
        ts   = e.get('timestamp', '')
        cmd  = e.get('command', '')
        resp = e.get('response', '')
        dur  = e.get('duration_ms', 0)
        im   = e.get('imei', '')

        if resp.startswith('⏱'):
            icon, clr = '⏱️', 'orange'
        elif resp.strip():
            icon, clr = '✅', 'green'
        else:
            icon, clr = '❓', 'gray'

        st.markdown(
            f"**{icon} [{ts}]** `{im}` · `{cmd}` → "
            f"<span style='color:{clr}'>"
            f"{resp[:120]}{'…' if len(resp) > 120 else ''}</span>"
            f" <small>({dur}ms)</small>",
            unsafe_allow_html=True,
        )


# ── Command history ──────────────────────────────────────────────────────────
@st.fragment(run_every="2s")
def _history_view():
    srv: TeltonikaServer = st.session_state.get('server')
    if not srv:
        return

    with srv.lock:
        hist = list(srv.command_history)

    if not hist:
        st.info("No command history yet.")
        return

    df = pd.DataFrame(hist)
    show = ['timestamp', 'imei', 'protocol', 'command', 'response', 'duration_ms']
    existing = [c for c in show if c in df.columns]
    st.dataframe(df[existing], use_container_width=True, height=500)

    with st.expander("Detail view", expanded=False):
        sel_i = st.selectbox(
            "Entry", range(len(hist)),
            format_func=lambda i: (
                f"[{hist[i]['timestamp']}] {hist[i]['command']} → "
                f"{hist[i]['response'][:60]}"
                f"{'…' if len(hist[i]['response']) > 60 else ''}"
            ),
            key="hist_detail_sel",
        )
        if sel_i is not None:
            e = hist[sel_i]
            c1, c2 = st.columns(2)
            c1.markdown(f"**Time:** {e['timestamp']}  \n"
                        f"**IMEI:** {e['imei']}  \n"
                        f"**Proto:** {e['protocol']}  \n"
                        f"**Duration:** {e['duration_ms']} ms")
            c2.markdown("**Command:**")
            c2.code(e['command'], language=None)
            c2.markdown("**Response:**")
            c2.code(e['response'], language=None)

    st.caption("live")


# ── Raw messages hex viewer ──────────────────────────────────────────────────
@st.fragment(run_every="1s")
def _raw_messages_view():
    srv: TeltonikaServer = st.session_state.get('server')
    if not srv:
        return

    with srv.lock:
        raw = list(srv.raw_messages[:200])

    if not raw:
        st.info("No raw messages yet.")
        return

    # Read filter state (widgets are in parent scope, values in session_state)
    search_q    = st.session_state.get('raw_search', '')
    dir_filter  = st.session_state.get('raw_dir', 'All')
    type_filter = st.session_state.get('raw_type', 'All')

    filtered = raw

    if search_q:
        sq = search_q.upper().replace(' ', '')
        filtered = [m for m in filtered if sq in m['hex']]

    if dir_filter == "RX ⬇️":
        filtered = [m for m in filtered if m['direction'] == 'RX']
    elif dir_filter == "TX ⬆️":
        filtered = [m for m in filtered if m['direction'] == 'TX']

    if type_filter != "All":
        def _ok(m):
            h, d, ln = m['hex'], m['direction'], m['length']
            if type_filter == "IMEI":
                return (ln == 17 and h.startswith('000F')) or (ln == 1 and h == '01')
            if type_filter == "ACK":
                return d == 'TX' and ln <= 7
            if type_filter == "Command":
                return ln >= 12 and h[:8] == '00000000' and h[16:18] in ('0C', '0D')
            if type_filter == "Data":
                if ln >= 12 and h[:8] == '00000000' and h[16:18] in ('08', '8E', '10'):
                    return True
                return d == 'RX' and ln > 10 and not h.startswith('00000000')
            return True
        filtered = [m for m in filtered if _ok(m)]

    st.caption(f"Showing {len(filtered)}/{len(raw)} messages"
               + (" · filtered" if len(filtered) != len(raw) else ""))

    if not filtered:
        st.warning("No messages match filter")
        return

    # Build label for each message
    opts = []
    for m in filtered[:100]:
        icon = "⬇" if m['direction'] == "RX" else "⬆"
        h, ln = m['hex'], m['length']
        pt = ""
        if ln == 17 and h.startswith('000F'):
            pt = "IMEI"
        elif ln == 1 and h == '01':
            pt = "ACK"
        elif ln == 4 and h.startswith('000000'):
            pt = "DataACK"
        elif ln == 7:
            pt = "UDP-ACK"
        elif ln >= 12 and h[:8] == '00000000':
            pt = {'08': 'Codec8', '8E': 'Codec8E', '10': 'Codec16',
                  '0C': 'Codec12', '0D': 'Codec13'}.get(h[16:18], 'Frame')
        elif ln > 10:
            pt = "UDP-Data"
        else:
            pt = f"{ln}B"
        opts.append(f"{icon} [{m['timestamp']}] {m['protocol']} {pt} ({ln}B)")

    sel = st.selectbox("Select message", range(len(opts)),
                       format_func=lambda i: opts[i], key="_raw_sel")

    if sel is not None and sel < len(filtered):
        msg = filtered[sel]
        st.markdown(f"**{msg['direction']}** · {msg['protocol']} · "
                    f"{msg['length']} bytes · {msg['timestamp']}")

        annotations = annotate_packet(msg['hex'], msg['protocol'])
        st.markdown(build_hex_html(msg['hex'], annotations),
                    unsafe_allow_html=True)

        with st.expander("📋 Parsed fields", expanded=False):
            if annotations:
                ann_rows = []
                for a in annotations:
                    rng = (f"{a['s']:04X}–{a['e']-1:04X}"
                           if a['e'] - a['s'] > 1 else f"{a['s']:04X}")
                    ann_rows.append({
                        'Offset': rng,
                        'Bytes': a['e'] - a['s'],
                        'Hex': msg['hex'][a['s']*2:a['e']*2],
                        'Field': a['label'],
                    })
                st.dataframe(pd.DataFrame(ann_rows),
                             use_container_width=True,
                             height=min(400, 35 + len(ann_rows) * 35),
                             hide_index=True)
            else:
                st.caption("No annotations")

        with st.expander("📄 Raw hex (copyable)"):
            st.code(msg['hex'], language=None)


# ── Logs ──────────────────────────────────────────────────────────────────────
@st.fragment(run_every="2s")
def _logs_view():
    srv: TeltonikaServer = st.session_state.get('server')
    if not srv:
        return

    with srv.lock:
        logs = list(srv.log_messages[:200])

    if not logs:
        st.info("No logs yet.")
        return

    lq = st.session_state.get('log_search', '')
    if lq:
        lq_lower = lq.lower()
        logs = [l for l in logs if
                lq_lower in l['message'].lower() or lq_lower in l['type'].lower()]

    st.caption(f"{len(logs)} log entries")

    icons = {
        "IMEI": "🆔", "DATA": "📊", "ACK": "✅", "CMD": "📤",
        "CONN": "🔌", "DISC": "🔴", "ERROR": "❌", "START": "🟢",
        "STOP": "⛔", "SCHEDULE": "⏰", "RESP": "📩", "WARN": "⚠️",
        "INFO": "ℹ️",
    }

    lines = []
    for l in logs[:200]:
        ic  = icons.get(l['type'], '·')
        msg = l['message'].replace('<', '&lt;').replace('>', '&gt;')
        lines.append(
            f'<div class="log-entry">{ic} '
            f'<span style="color:#6e7681">[{l["timestamp"]}]</span> '
            f'<span style="color:#58a6ff;font-weight:600">{l["type"]}</span>: '
            f'{msg}</div>'
        )

    st.markdown(
        '<div style="max-height:500px;overflow-y:auto;background:#0d1117;'
        'border-radius:8px;padding:8px 12px;border:1px solid #30363d">'
        + ''.join(lines) + '</div>',
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Header
# ═══════════════════════════════════════════════════════════════════════════════

sc = "status-on" if server.running else "status-off"
sl = "RUNNING" if server.running else "STOPPED"
st.markdown(
    f'<h2 style="margin:0">📡 GPS Server'
    f'<span class="server-status {sc}">{sl}</span></h2>',
    unsafe_allow_html=True,
)
st.caption(f"{server.protocol_mode} · port {server.port}")

if st.session_state.get('server_start_error'):
    st.error(f"⚠️ Server failed to start: {st.session_state.server_start_error}")


# ═══════════════════════════════════════════════════════════════════════════════
#  Sidebar
# ═══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("⚙️ Server")

    # ── Start / Stop / Restart ────────────────────────────────────────────────
    c_on, c_off, c_rst = st.columns(3)
    with c_on:
        if st.button("▶️ Start", use_container_width=True, disabled=server.running):
            err = server.start()
            st.session_state.server_start_error = err
            st.rerun()
    with c_off:
        if st.button("⏹ Stop", use_container_width=True, disabled=not server.running):
            server.stop()
            st.session_state.server_start_error = None
            st.rerun()
    with c_rst:
        if st.button("🔄 Restart", use_container_width=True):
            server.stop(); time.sleep(0.3)
            cfg = load_config()
            srv = TeltonikaServer(port=cfg['server_port'],
                                 protocol=cfg['server_protocol'])
            err = srv.start()
            st.session_state.server = srv
            st.session_state.server_start_error = err
            st.rerun()

    c_clr, _ = st.columns([1, 1])
    with c_clr:
        if st.button("🗑️ Clear data", use_container_width=True):
            with server.lock:
                server.parsed_records.clear()
                server.raw_messages.clear()
                server.log_messages.clear()
                server.command_history.clear()
            st.rerun()

    st.divider()

    # ── Live metrics / devices / queue (auto-refreshing fragment) ─────────────
    _sidebar_live()

    st.divider()

    # ── Port & Protocol ───────────────────────────────────────────────────────
    st.subheader("🔧 Settings")
    cur = load_config()
    with st.form("settings_form"):
        port_in  = st.number_input("Port", 1024, 65535, value=cur['server_port'])
        proto_in = st.radio("Protocol", ["TCP", "UDP"], horizontal=True,
                            index=0 if cur['server_protocol'] == 'TCP' else 1)
        if st.form_submit_button("💾 Save & Restart", use_container_width=True):
            check_err = TeltonikaServer.check_port(port_in, proto_in)
            if check_err and server.running:
                if port_in != server.port or proto_in != server.protocol_mode:
                    st.error(f"Port {port_in} unavailable: {check_err}")
                else:
                    save_config(port_in, proto_in)
                    st.success("Saved (same config)")
            else:
                if save_config(port_in, proto_in):
                    server.stop(); time.sleep(0.3)
                    nsrv = TeltonikaServer(port=port_in, protocol=proto_in)
                    err = nsrv.start()
                    st.session_state.server = nsrv
                    st.session_state.server_start_error = err
                    if err:
                        st.error(err)
                    else:
                        st.success("Saved & restarted")
                    st.rerun()

    st.divider()

    # ── AVL IDs ───────────────────────────────────────────────────────────────
    st.subheader("📑 AVL IO Names")
    avl_path_in = st.text_input(
        "Excel path", value=cur.get('avl_ids_path', DEFAULT_AVL_EXCEL),
        key="avl_path_input",
        help="Path to FMB_AVL_IDS.xlsx with MainTable sheet")
    ac1, ac2 = st.columns(2)
    with ac1:
        if st.button("🔄 Load", use_container_width=True, key="avl_refresh"):
            save_avl_path(avl_path_in)
            err = refresh_io_names(avl_path_in)
            if err:
                st.error(err)
            else:
                st.success(f"Loaded {len(IO_ELEMENT_NAMES)} IOs")
            st.session_state.avl_loaded = True
            st.rerun()
    with ac2:
        st.caption(f"{len(IO_ELEMENT_NAMES)} IDs loaded")

    if st.session_state.get('avl_load_error'):
        st.warning(f"AVL load: {st.session_state.avl_load_error}")


# ═══════════════════════════════════════════════════════════════════════════════
#  Main tabs
# ═══════════════════════════════════════════════════════════════════════════════

tab_data, tab_cmd, tab_schedule, tab_test, tab_interval, tab_history, tab_raw = \
    st.tabs([
        "📋 Live Data", "📨 Commands", "⏰ Schedule", "🧪 Test Seq",
        "🔁 Interval", "📚 History", "📝 Raw / Hex",
    ])


# ─── Tab 1: Live Data ────────────────────────────────────────────────────────
with tab_data:
    # IO column configurator (static — no fragment, avoids widget jitter)
    with server.lock:
        all_io_ids = set()
        for r in server.parsed_records:
            all_io_ids.update(r.get('IO_Data', {}).keys())
    all_io_ids = sorted(all_io_ids)

    if all_io_ids:
        with st.expander("⚙️ Configure visible IO columns", expanded=False):
            default_sel = st.session_state.io_selected_cols or all_io_ids[:10]
            selected_ios = st.multiselect(
                "IO Elements", options=all_io_ids,
                default=[x for x in default_sel if x in all_io_ids],
                format_func=lambda x: f"{io_name(x)} ({x})",
            )
            st.session_state.io_selected_cols = selected_ios

    # Data table (auto-refreshing fragment)
    _live_data_table()


# ─── Tab 2: Send Commands ────────────────────────────────────────────────────
with tab_cmd:
    st.subheader("Send Command")
    devices = server.get_connected_devices()

    if not devices:
        st.warning("No devices connected")
    else:
        dev_opts = [f"{d['IMEI']} ({d['Protocol']})" for d in devices]
        sel = st.selectbox("Device", dev_opts, key="cmd_dev")
        idx = dev_opts.index(sel)
        imei = devices[idx]['IMEI']

        command = st.text_input("Command",
                                placeholder="getver, getgps, setparam …",
                                key="cmd_input")

        c1, c2 = st.columns([1, 3])
        with c1:
            if st.button("📤 Send", use_container_width=True):
                if command.strip():
                    server.send_command(imei, command.strip())
                    st.success(f"Queued → {imei}")
                else:
                    st.warning("Enter a command")
        with c2:
            qs = server.get_queue_status(imei)
            if qs and (qs['queued'] or qs['active']):
                st.info(f"Queue: {qs['queued']} pending"
                        + (f" | waiting: {qs['active']}" if qs['active'] else ""))

    st.divider()
    st.subheader("Recent Responses")
    _cmd_responses()     # ← auto-refreshing fragment


# ─── Tab 3: Schedule ─────────────────────────────────────────────────────────
with tab_schedule:
    st.subheader("Schedule Commands")
    st.caption("Queued when the device next sends data.")

    sc_imei = st.text_input("IMEI", key="sch_imei")
    sc_cmd  = st.text_input("Command", key="sch_cmd", placeholder="getver")

    if st.button("⏰ Schedule"):
        if sc_imei and sc_cmd:
            server.schedule_command(sc_imei.strip(), sc_cmd.strip())
            st.success(f"Scheduled for {sc_imei}")
        else:
            st.warning("Enter IMEI and command")

    st.divider()
    with server.lock:
        scheduled = dict(server.scheduled_commands)
    if any(v for v in scheduled.values()):
        for im, cmds in scheduled.items():
            if cmds:
                st.markdown(f"**{im}**")
                for c in cmds:
                    st.text(f"  → {c}")
    else:
        st.caption("No pending scheduled commands")


# ─── Tab 4: Test Sequences ───────────────────────────────────────────────────
with tab_test:
    st.subheader("Test Sequence")
    st.caption("Send the same command N times, waiting for each response.")
    devices = server.get_connected_devices()

    if not devices:
        st.warning("No devices connected")
    else:
        dev_opts = [f"{d['IMEI']} ({d['Protocol']})" for d in devices]
        ts_sel = st.selectbox("Device", dev_opts, key="ts_dev")
        ts_idx = dev_opts.index(ts_sel)
        ts_imei = devices[ts_idx]['IMEI']

        ts_cmd     = st.text_input("Command", key="ts_cmd", placeholder="getver")
        ts_n       = st.number_input("Count", 1, 200, 5, key="ts_n")
        ts_timeout = st.number_input("Response timeout (s)", 1.0, 120.0, 10.0,
                                     step=1.0, key="ts_to")

        if st.button("🧪 Run"):
            if ts_cmd:
                bar    = st.progress(0)
                status = st.empty()
                for i in range(ts_n):
                    with server.lock:
                        init_count = len(server.command_history)
                    server.send_command(ts_imei, ts_cmd)
                    status.text(f"Sent {i+1}/{ts_n}, waiting…")
                    bar.progress((i + 0.5) / ts_n)
                    t0 = time.time(); got = False
                    while time.time() - t0 < ts_timeout:
                        with server.lock:
                            if len(server.command_history) > init_count:
                                got = True; break
                        time.sleep(0.1)
                    status.text(f"{'Response' if got else 'Timeout'} "
                                f"{i+1}/{ts_n} {'✓' if got else '✗'}")
                    bar.progress((i + 1) / ts_n)
                    if i < ts_n - 1:
                        time.sleep(0.3)
                st.success(f"Sequence done – {ts_n} commands sent")
            else:
                st.warning("Enter a command")


# ─── Tab 5: Interval Commands ────────────────────────────────────────────────
with tab_interval:
    st.subheader("🔁 Interval Commands")
    st.caption("Repeatedly send a command at a fixed interval for a given duration.")
    devices = server.get_connected_devices()

    if not devices:
        st.warning("No devices connected")
    else:
        dev_opts = [f"{d['IMEI']} ({d['Protocol']})" for d in devices]
        iv_sel = st.selectbox("Device", dev_opts, key="iv_dev")
        iv_idx = dev_opts.index(iv_sel)
        iv_imei = devices[iv_idx]['IMEI']

        iv_cmd = st.text_input("Command", value="getinfo", key="iv_cmd")

        def _to_sec(val, unit):
            return val * {'s': 1, 'min': 60, 'h': 3600}[unit]

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Interval**")
            ic1, ic2 = st.columns([2, 1])
            iv_val  = ic1.number_input("Value", 0, 3600, 20, key="iv_v")
            iv_unit = ic2.selectbox("Unit", ['s', 'min', 'h'], key="iv_u")
            iv_sec  = _to_sec(iv_val, iv_unit)
            st.caption(f"= {iv_sec}s")
        with c2:
            st.markdown("**Duration**")
            dc1, dc2 = st.columns([2, 1])
            du_val  = dc1.number_input("Value", 0, 24, 1, key="du_v")
            du_unit = dc2.selectbox("Unit", ['s', 'min', 'h'], index=2, key="du_u")
            du_sec  = _to_sec(du_val, du_unit)
            st.caption(f"= {du_sec}s")

        expected = max(1, int(du_sec / iv_sec)) if iv_sec > 0 and du_sec > 0 else 1
        st.info(f"≈ {expected} commands ({du_sec}s / {iv_sec}s)"
                if iv_sec > 0 and du_sec > 0 else "Single send")

        wait_rec = st.checkbox("🔄 Wait for record before each send", key="iv_wait")

        if 'iv_running' not in st.session_state:
            st.session_state.iv_running = False
        if 'iv_result' not in st.session_state:
            st.session_state.iv_result = None

        b1, b2, _ = st.columns([1, 1, 2])
        with b1:
            if st.button("▶️ Start", use_container_width=True,
                         disabled=st.session_state.iv_running):
                if iv_cmd:
                    st.session_state.iv_running = True
                    st.session_state.iv_result = None
                    st.rerun()
                else:
                    st.warning("Enter a command")
        with b2:
            if st.button("⏹ Stop", use_container_width=True,
                         disabled=not st.session_state.iv_running, type="secondary"):
                server.stop_interval_command(iv_imei)
                st.info("Stop requested…")

        if st.session_state.iv_running:
            with st.spinner(f"Sending '{iv_cmd}' every {iv_sec}s for {du_sec}s…"):
                res = server.send_command_with_interval(
                    iv_imei, iv_cmd, iv_sec, du_sec, wait_for_record=wait_rec)
                st.session_state.iv_result = res
                st.session_state.iv_running = False
                st.rerun()

        if st.session_state.iv_result:
            r = st.session_state.iv_result
            if r.get('stopped'):
                st.info("⏹ Stopped by user")
            elif r['success'] and not r['errors']:
                st.success("✅ Completed successfully")
            elif r['commands_sent']:
                st.warning("⚠️ Done with errors")
            else:
                st.error("❌ Failed")

            m1, m2, m3 = st.columns(3)
            m1.metric("Sent", r['commands_sent'])
            m2.metric("Errors", len(r['errors']))
            if expected > 0 and not r.get('stopped'):
                m3.metric("Rate", f"{r['commands_sent']/expected*100:.0f}%")

            if r['errors']:
                with st.expander("Errors"):
                    for i, e in enumerate(r['errors'], 1):
                        st.text(f"{i}. {e}")

            if st.button("Clear result", key="iv_clr"):
                st.session_state.iv_result = None
                st.rerun()


# ─── Tab 6: Command History ──────────────────────────────────────────────────
with tab_history:
    _history_view()     # ← auto-refreshing fragment


# ─── Tab 7: Raw / Hex ────────────────────────────────────────────────────────
with tab_raw:
    raw_tab1, raw_tab2 = st.tabs(["📨 Raw Messages", "📝 Logs"])

    with raw_tab1:
        # Filter controls (static — outside fragment to avoid input jitter)
        fc1, fc2, fc3 = st.columns([3, 1, 1])
        with fc1:
            st.text_input("🔍 Search hex", placeholder="Search hex content…",
                          key="raw_search", label_visibility="collapsed")
        with fc2:
            st.selectbox("Direction", ["All", "RX ⬇️", "TX ⬆️"],
                         key="raw_dir", label_visibility="collapsed")
        with fc3:
            st.selectbox("Type", ["All", "Data", "ACK", "IMEI", "Command"],
                         key="raw_type", label_visibility="collapsed")

        # Display (auto-refreshing fragment)
        _raw_messages_view()

    with raw_tab2:
        st.text_input("🔍 Search logs", placeholder="Filter log messages…",
                      key="log_search", label_visibility="collapsed")
        _logs_view()     # ← auto-refreshing fragment
