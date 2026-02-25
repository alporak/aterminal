import re as _re
import streamlit as st
import pandas as pd
import os
import sys
import json
import gzip
import tempfile
import zipfile
import shutil
import html as _html
import glob as glob_mod
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from modules.utils import (
        parse_log, create_map, create_timeline,
        create_signal_chart, create_state_timeline,
        CREG_STATES, NETWORK_ACT, REC_SEND_STATES,
    )
    import folium
    from streamlit_folium import st_folium
    import plotly.express as px
    DEPENDENCIES_OK = True
except ImportError as e:
    DEPENDENCIES_OK = False
    IMPORT_ERROR = str(e)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Settings helpers ────────────────────────────────────────────────
DEFAULT_JIRA_BASE = 'https://teltonika-telematics.atlassian.net'
_RX_TICKET = _re.compile(r'[A-Z]{2,10}-\d+')  # e.g. FMBP-54666

def load_toolkit_settings():
    config_path = os.path.join(ROOT_DIR, 'toolkit_settings.json')
    default = {
        'catcher_path': os.path.join(ROOT_DIR, 'easy-catcher', 'catcher_mod', 'Catcher.exe'),
        'clg2txt_path': os.path.join(ROOT_DIR, 'easy-catcher', 'catcher_mod', 'Clg2Txt.exe'),
        'db_path': '',
        'tickets_folder': '',
        'jira_base_url': DEFAULT_JIRA_BASE,
    }
    if not os.path.exists(config_path):
        return default
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            s = json.load(f)
        c = s.get('catcher_path', default['catcher_path'])
        if not os.path.isabs(c): c = os.path.join(ROOT_DIR, c)
        t = s.get('clg2txt_path', default['clg2txt_path'])
        if not os.path.isabs(t): t = os.path.join(ROOT_DIR, t)
        return {
            'catcher_path': c, 'clg2txt_path': t,
            'db_path': s.get('db_path', ''),
            'tickets_folder': s.get('tickets_folder', ''),
            'jira_base_url': s.get('jira_base_url', DEFAULT_JIRA_BASE),
        }
    except Exception:
        return default

def save_toolkit_settings(settings):
    try:
        with open(os.path.join(ROOT_DIR, 'toolkit_settings.json'), 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=4)
        return True
    except Exception as e:
        st.error(f"Save failed: {e}")
        return False


# ── Easy Catcher dump processor ─────────────────────────────────────
EASY_CATCHER_OK = False
PROCESS_DUMPS = None
EC_ERROR = ""
try:
    from modules.easy_catcher_adapter import process_dumps
    PROCESS_DUMPS = process_dumps
    EASY_CATCHER_OK = True
except Exception as e:
    EC_ERROR = str(e)


# ── Ticket auto-detection ───────────────────────────────────────────
def detect_ticket_from_filename(filename: str) -> str:
    """Try to find which ticket folder contains *filename*.
    
    Returns a string like 'FMBP-54666' or 'FMBP-54666: <suffix>' where suffix
    is the filename stripped of typical 15-digit IMEI patterns.
    """
    cfg = load_toolkit_settings()
    tickets_root = cfg.get('tickets_folder', '')
    ticket_id = None
    
    # 1. Search in tickets folder
    if tickets_root and os.path.isdir(tickets_root):
        try:
            for entry in os.scandir(tickets_root):
                if entry.is_dir():
                    candidate = os.path.join(entry.path, filename)
                    if os.path.exists(candidate):
                        ticket_id = entry.name
                        break
        except Exception:
            pass
            
    # 2. Fallback regex
    if not ticket_id:
        m = _RX_TICKET.search(filename)
        if m:
            ticket_id = m.group(0)

    # 3. Suffix extraction (Last underscore strategy)
    # If filename has underscores (common in our logs: "..._logs_12345.zip"),
    # take the last part. Else use full filename.
    if '_' in filename:
        suffix = filename.rsplit('_', 1)[-1]
    else:
        suffix = filename

    if ticket_id:
        return f"{ticket_id}: {suffix}"
        
    return suffix


def _jira_url(ticket_key: str) -> str | None:
    """Return a Jira browse URL if *ticket_key* looks like a ticket id."""
    if not _RX_TICKET.fullmatch(ticket_key):
        return None
    cfg = load_toolkit_settings()
    base = cfg.get('jira_base_url', DEFAULT_JIRA_BASE).rstrip('/')
    return f"{base}/browse/{ticket_key}"


def _extract_ticket_id(name: str) -> str | None:
    """Extract a Jira ticket id from an analysis name."""
    m = _RX_TICKET.search(name)
    return m.group(0) if m else None


# ── Analysis session persistence ────────────────────────────────────
ANALYSES_DIR = os.path.join(ROOT_DIR, 'output', 'analyses')
ANALYSES_INDEX = os.path.join(ANALYSES_DIR, 'index.json')
MAX_RECENT = 30


def _ensure_analyses_dir():
    os.makedirs(ANALYSES_DIR, exist_ok=True)


def _load_index():
    """Return list of analysis entries (newest first)."""
    _ensure_analyses_dir()
    if not os.path.exists(ANALYSES_INDEX):
        return []
    try:
        with open(ANALYSES_INDEX, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def _save_index(entries):
    _ensure_analyses_dir()
    with open(ANALYSES_INDEX, 'w', encoding='utf-8') as f:
        json.dump(entries[:MAX_RECENT], f, indent=2)


def save_analysis(raw_content: str, display_name: str, source_files: list,
                  catcher_work_dir: str | None = None):
    """Persist a parsed analysis so it can be reopened later.

    Saves the raw concatenated log text as gzip (good compression for text)
    and copies any catcher artifacts (.clg, .log, .dmp) next to it.
    Returns the analysis id (folder name).
    """
    _ensure_analyses_dir()
    ts = datetime.now()
    analysis_id = ts.strftime('%Y%m%d_%H%M%S')
    analysis_dir = os.path.join(ANALYSES_DIR, analysis_id)
    os.makedirs(analysis_dir, exist_ok=True)

    # 1. Save compressed log content
    gz_path = os.path.join(analysis_dir, 'log_content.gz')
    with gzip.open(gz_path, 'wt', encoding='utf-8', compresslevel=6) as gz:
        gz.write(raw_content)

    # 2. Copy catcher artefacts (CLG, LOG, DMP) if available
    artifacts_copied = []
    if catcher_work_dir and os.path.isdir(catcher_work_dir):
        parent = os.path.dirname(catcher_work_dir)  # temp_root
        for root, _, files in os.walk(parent):
            for fn in files:
                ext = os.path.splitext(fn)[1].lower()
                if ext in ('.clg', '.log', '.dmp', '.txt'):
                    src = os.path.join(root, fn)
                    dst = os.path.join(analysis_dir, fn)
                    # Avoid name collision
                    if os.path.exists(dst):
                        base, e = os.path.splitext(fn)
                        dst = os.path.join(analysis_dir, f"{base}_{len(artifacts_copied)}{e}")
                    try:
                        shutil.copy2(src, dst)
                        artifacts_copied.append(fn)
                    except Exception:
                        pass

    # 3. Save metadata
    meta = {
        'id': analysis_id,
        'name': display_name,
        'created': ts.isoformat(),
        'source_files': source_files,
        'artifacts': artifacts_copied,
    }
    with open(os.path.join(analysis_dir, 'meta.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)

    # 4. Update index (prepend, trim to MAX_RECENT)
    idx = _load_index()
    idx.insert(0, meta)
    _save_index(idx)

    return analysis_id


def load_analysis(analysis_id: str):
    """Load compressed log content and re-parse it.  Returns (content_str, meta) or (None, None)."""
    analysis_dir = os.path.join(ANALYSES_DIR, analysis_id)
    gz_path = os.path.join(analysis_dir, 'log_content.gz')
    meta_path = os.path.join(analysis_dir, 'meta.json')
    if not os.path.exists(gz_path):
        return None, None
    with gzip.open(gz_path, 'rt', encoding='utf-8') as gz:
        content = gz.read()
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)
    return content, meta


def load_analysis_from_path(folder_path: str):
    """Load an analysis from an arbitrary folder path."""
    gz_path = os.path.join(folder_path, 'log_content.gz')
    meta_path = os.path.join(folder_path, 'meta.json')
    if not os.path.exists(gz_path):
        return None, None
    with gzip.open(gz_path, 'rt', encoding='utf-8') as gz:
        content = gz.read()
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)
    return content, meta


def rename_analysis(analysis_id: str, new_name: str):
    """Rename an analysis (update meta + index)."""
    meta_path = os.path.join(ANALYSES_DIR, analysis_id, 'meta.json')
    if os.path.exists(meta_path):
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        meta['name'] = new_name
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2)
    idx = _load_index()
    for entry in idx:
        if entry.get('id') == analysis_id:
            entry['name'] = new_name
            break
    _save_index(idx)


# ── Parse & store helper ────────────────────────────────────────────
def parse_and_store(content, file_name):
    data_points, events, structured_logs, modem_info = parse_log(content)
    st.session_state['data_points'] = data_points
    st.session_state['events'] = events
    st.session_state['structured_logs'] = structured_logs
    st.session_state['modem_info'] = modem_info
    st.session_state['file_name'] = file_name
    return data_points, events, structured_logs, modem_info


# ── Page config ─────────────────────────────────────────────────────
st.set_page_config(page_title="Log Parser", page_icon="🔍", layout="wide")
st.title("🔍 Log Parser")
st.caption("Combined log analyzer: AT commands · GSM signal · device states · GPS")

if not DEPENDENCIES_OK:
    st.error(f"Missing deps: {IMPORT_ERROR}\n\n`pip install folium streamlit-folium plotly pandas`")
    st.stop()


# ── Sidebar ─────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")
    with st.expander("Catcher Config", expanded=False):
        cfg = load_toolkit_settings()
        new_db = st.text_input("Release Vault Path", value=cfg.get('db_path', ''))
        if new_db != cfg.get('db_path', ''):
            cfg['db_path'] = new_db
            if save_toolkit_settings(cfg):
                st.success("Saved"); st.rerun()
    with st.expander("Jira & Tickets", expanded=False):
        cfg = load_toolkit_settings()
        new_jira = st.text_input("Jira Base URL", value=cfg.get('jira_base_url', DEFAULT_JIRA_BASE))
        new_tickets = st.text_input("Tickets Folder", value=cfg.get('tickets_folder', ''),
                                     help="Root folder where ticket sub-folders live (e.g. _tickets). "
                                          "Used to auto-detect analysis names.")
        _cfg_changed = False
        if new_jira != cfg.get('jira_base_url', DEFAULT_JIRA_BASE):
            cfg['jira_base_url'] = new_jira; _cfg_changed = True
        if new_tickets != cfg.get('tickets_folder', ''):
            cfg['tickets_folder'] = new_tickets; _cfg_changed = True
        if _cfg_changed:
            if save_toolkit_settings(cfg):
                st.success("Saved"); st.rerun()

    st.subheader("Event Filters")
    show_ignition  = st.checkbox("Ignition", value=True)
    show_gps       = st.checkbox("GPS", value=True)
    show_movement  = st.checkbox("Movement", value=True)
    show_sleep     = st.checkbox("Sleep", value=True)
    show_network   = st.checkbox("Network / Operator", value=True)
    show_record    = st.checkbox("Record Sending", value=True)
    show_modem     = st.checkbox("Modem / GPRS", value=True)

    FILTER_MAP = {
        'Ignition': show_ignition, 'GPS State': show_gps, 'No Fix Reason': show_gps,
        'Movement': show_movement, 'Sleep Mode': show_sleep,
        'Network': show_network, 'Operator': show_network,
        'Record Sending': show_record, 'Modem': show_modem, 'GPRS': show_modem,
        'Trip Status': show_movement, 'Trip Info': show_movement,
        'Static Navigation': show_gps,
    }


def filtered_events(events):
    return [e for e in events if FILTER_MAP.get(e.get('Type', ''), True)]


# ── Tabs ────────────────────────────────────────────────────────────
tab_upload, tab_timeline, tab_modem, tab_map, tab_events, tab_raw = st.tabs([
    "📁 Upload", "📊 Timeline", "📡 Modem & Signal",
    "🗺️ Map", "📋 Events", "📝 Raw Log"
])


# ━━━━━━━━━━━━ TAB: Upload ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_upload:
    # ── Upload new files ────────────────────────────────────────────
    uploaded_files = st.file_uploader(
        "Upload device log files (.log, .txt) or Easy Catcher dump archives (.zip)",
        type=['log', 'txt', 'zip'], accept_multiple_files=True,
    )

    if uploaded_files:
        st.success(f"{len(uploaded_files)} file(s) selected")
        for uf in uploaded_files:
            st.write(f"- {uf.name} ({uf.size:,} bytes)")

        # Auto-detect a name from the ticket folder structure
        auto_name = detect_ticket_from_filename(uploaded_files[0].name)
        analysis_name = st.text_input(
            "Analysis name", value=auto_name,
            help="Defaults to the ticket folder name if found. Edit freely.",
            key='analysis_name_input',
        )

        if st.button("🔍 Parse", type="primary", use_container_width=True):
            with st.spinner("Parsing..."):
                all_content = ""
                parsed_name_parts = []
                last_catcher_work_dir = None

                for uf in uploaded_files:
                    is_zip = uf.name.lower().endswith('.zip')

                    if not is_zip:
                        # Plain log / txt
                        all_content += uf.read().decode('utf-8', errors='ignore') + "\n"
                        parsed_name_parts.append(uf.name)
                    else:
                        # ZIP with .dmp files → Easy Catcher processing
                        if not EASY_CATCHER_OK:
                            st.error(f"Easy Catcher unavailable: {EC_ERROR}")
                            continue

                        prev_root = st.session_state.get('ec_temp_root')
                        if prev_root and os.path.exists(prev_root):
                            shutil.rmtree(prev_root, ignore_errors=True)

                        temp_root = tempfile.mkdtemp(prefix='modem_dbg_')
                        extract_root = os.path.join(temp_root, 'extracted')
                        process_root = os.path.join(temp_root, 'input')
                        os.makedirs(extract_root, exist_ok=True)
                        os.makedirs(process_root, exist_ok=True)

                        zip_path = os.path.join(temp_root, uf.name)
                        with open(zip_path, 'wb') as zf:
                            zf.write(uf.getvalue())

                        with zipfile.ZipFile(zip_path, 'r') as archive:
                            for member in archive.infolist():
                                mp = Path(member.filename)
                                if member.is_dir() or mp.is_absolute() or '..' in mp.parts:
                                    continue
                                archive.extract(member, extract_root)

                        dmp_files = []
                        for root, _, files in os.walk(extract_root):
                            for fn in files:
                                if fn.lower().endswith('.dmp'):
                                    dmp_files.append(os.path.join(root, fn))

                        if not dmp_files:
                            shutil.rmtree(temp_root, ignore_errors=True)
                            st.error(f"No .dmp files in {uf.name}")
                            continue

                        for idx, dmp_file in enumerate(sorted(dmp_files), 1):
                            dest = f"{idx:04d}_{os.path.basename(dmp_file)}"
                            shutil.copy2(dmp_file, os.path.join(process_root, dest))

                        tk_cfg = load_toolkit_settings()
                        tool_paths = {
                            'CATCHER_EXE': tk_cfg['catcher_path'],
                            'CLG2TXT_EXE': tk_cfg['clg2txt_path'],
                            'DB_PATH': tk_cfg['db_path'],
                        }

                        log_container = st.empty()
                        proc_logs = []
                        def _log(msg):
                            proc_logs.append(str(msg))
                            log_container.code('\n'.join(proc_logs[-12:]), language='text')

                        output_log = PROCESS_DUMPS(process_root, tool_paths, log_cb=_log)
                        log_container.empty()

                        if not output_log or not os.path.exists(output_log):
                            st.error(f"Failed to process {uf.name}")
                            with st.expander("Processing log"):
                                st.code('\n'.join(proc_logs) or "No output")
                            continue

                        with open(output_log, 'rb') as lf:
                            all_content += lf.read().decode('utf-8', errors='ignore') + "\n"
                        parsed_name_parts.append(f"{uf.name} → {os.path.basename(output_log)}")

                        st.session_state['ec_temp_root'] = temp_root
                        st.session_state['ec_work_dir'] = process_root
                        st.session_state['ec_proc_logs'] = proc_logs
                        last_catcher_work_dir = process_root

                if all_content.strip():
                    display_name = analysis_name.strip() or " + ".join(parsed_name_parts)
                    data_points, events, structured_logs, modem_info = parse_and_store(
                        all_content, display_name)

                    # Save analysis for later reopen
                    with st.spinner("Saving analysis..."):
                        aid = save_analysis(
                            all_content, display_name,
                            parsed_name_parts,
                            catcher_work_dir=last_catcher_work_dir,
                        )
                        st.session_state['current_analysis_id'] = aid

                    # Summary metrics
                    c1, c2, c3, c4, c5 = st.columns(5)
                    c1.metric("GPS Points", len(data_points))
                    c2.metric("Events", len(events))
                    c3.metric("AT Commands", len(modem_info['at_commands']))
                    c4.metric("Signal Readings", len(modem_info['signal_readings']))
                    c5.metric("Log Lines", len(structured_logs))

                    st.success("Parsing complete — analysis saved. Check the other tabs.")
                else:
                    st.warning("No parseable content found.")
    else:
        st.info("Upload device log files to get started.")

    # ── Reopen Recent Analysis ──────────────────────────────────────
    st.divider()
    _reopen_col1, _reopen_col2 = st.columns([3, 1])
    with _reopen_col1:
        st.subheader("📂 Reopen Recent Analysis")

    recent = _load_index()
    if recent:
        # Build display labels
        labels = []
        for entry in recent:
            created = entry.get('created', '')
            try:
                dt = datetime.fromisoformat(created)
                date_str = dt.strftime('%Y-%m-%d %H:%M')
            except Exception:
                date_str = created[:16] if created else '?'
            name = entry.get('name', entry.get('id', '?'))
            labels.append(f"{date_str}  —  {name}")

        selected_idx = st.selectbox(
            "Recent analyses (last 30)",
            range(len(labels)),
            format_func=lambda i: labels[i],
            key='recent_analysis_select',
        )

        sel_entry = recent[selected_idx]

        # Jira link for the selected analysis
        _sel_ticket = _extract_ticket_id(sel_entry.get('name', ''))
        with _reopen_col2:
            if _sel_ticket:
                _url = _jira_url(_sel_ticket)
                if _url:
                    st.link_button(f"🔗 {_sel_ticket}", _url, use_container_width=True)

        rc1, rc2, rc3 = st.columns([2, 2, 1])

        with rc1:
            if st.button("🔄 Load selected", use_container_width=True):
                with st.spinner("Loading & re-parsing..."):
                    content, meta = load_analysis(sel_entry['id'])
                    if content:
                        display = meta.get('name', sel_entry['id'])
                        parse_and_store(content, display)
                        st.session_state['current_analysis_id'] = sel_entry['id']
                        st.success(f"Loaded: {display}")
                        st.rerun()
                    else:
                        st.error("Analysis file not found or corrupted.")

        with rc2:
            new_name = st.text_input(
                "Rename", value=sel_entry.get('name', ''),
                key='rename_input', label_visibility='collapsed',
                placeholder='Enter new name (e.g. ticket id)...',
            )

        with rc3:
            if st.button("✏️ Rename", use_container_width=True):
                if new_name and new_name != sel_entry.get('name', ''):
                    rename_analysis(sel_entry['id'], new_name)
                    st.success(f"Renamed → {new_name}")
                    st.rerun()

        # Show artifacts for this analysis
        analysis_dir = os.path.join(ANALYSES_DIR, sel_entry['id'])
        if os.path.isdir(analysis_dir):
            artifacts = [f for f in os.listdir(analysis_dir)
                         if f not in ('meta.json', 'log_content.gz')]
            if artifacts:
                with st.expander(f"Saved artifacts ({len(artifacts)} files)"):
                    for af in sorted(artifacts):
                        fpath = os.path.join(analysis_dir, af)
                        sz = os.path.getsize(fpath)
                        st.write(f"- {af} ({sz:,} bytes)")
    else:
        st.caption("No saved analyses yet. Parse a log file to create one.")

    # ── Open analysis from folder path ──────────────────────────────
    st.divider()
    with st.expander("📁 Open analysis from folder", expanded=False):
        folder_path = st.text_input(
            "Analysis folder path",
            placeholder="Paste path to a folder containing log_content.gz + meta.json",
            key='manual_analysis_path',
        )
        if folder_path and st.button("📂 Open", key='open_manual'):
            with st.spinner("Loading & re-parsing..."):
                content, meta = load_analysis_from_path(folder_path)
                if content:
                    display = meta.get('name', os.path.basename(folder_path))
                    parse_and_store(content, display)
                    st.session_state['current_analysis_id'] = meta.get('id', '')
                    st.success(f"Loaded: {display}")
                    st.rerun()
                else:
                    st.error("No valid analysis found in that folder (missing log_content.gz).")


# ━━━━━━━━━━━━ TAB: Timeline ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_timeline:
    if 'events' not in st.session_state or not st.session_state['events']:
        st.info("No data. Upload and parse logs first.")
    else:
        events = filtered_events(st.session_state['events'])
        modem_info = st.session_state.get('modem_info', {})

        # ── State Timeline (Gantt) ──
        st.subheader("Device State Timeline")
        try:
            state_fig = create_state_timeline(events)
            if state_fig:
                st.plotly_chart(state_fig, use_container_width=True)
            else:
                st.caption("Not enough state transitions for a timeline.")
        except Exception as e:
            st.error(f"State timeline error: {e}")

        # ── Signal Chart ──
        signal_readings = modem_info.get('signal_readings', [])
        if signal_readings:
            st.subheader("GSM Signal Strength")
            try:
                sig_fig = create_signal_chart(signal_readings)
                if sig_fig:
                    st.plotly_chart(sig_fig, use_container_width=True)
                # Quick signal stats
                df_sig = pd.DataFrame(signal_readings)
                cols = st.columns(4)
                if 'RSRP_dBm' in df_sig.columns and df_sig['RSRP_dBm'].notna().any():
                    vals = df_sig['RSRP_dBm'].dropna()
                    cols[0].metric("RSRP avg", f"{vals.mean():.0f} dBm")
                    cols[1].metric("RSRP min", f"{vals.min():.0f} dBm")
                if 'SINR_dB' in df_sig.columns and df_sig['SINR_dB'].notna().any():
                    vals = df_sig['SINR_dB'].dropna()
                    cols[2].metric("SINR avg", f"{vals.mean():.1f} dB")
                if 'CSQ' in df_sig.columns and df_sig['CSQ'].notna().any():
                    vals = df_sig['CSQ'].dropna()
                    cols[3].metric("CSQ avg", f"{vals.mean():.1f}")
            except Exception as e:
                st.error(f"Signal chart error: {e}")

        # ── Event Scatter ──
        st.subheader("Event Scatter")
        try:
            scatter_fig = create_timeline(events)
            if scatter_fig:
                st.plotly_chart(scatter_fig, use_container_width=True)
            else:
                st.caption("No discrete events to display.")
        except Exception as e:
            st.error(f"Event scatter error: {e}")


# ━━━━━━━━━━━━ TAB: Modem & Signal ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_modem:
    if 'modem_info' not in st.session_state:
        st.info("No data. Upload and parse logs first.")
    else:
        modem_info = st.session_state['modem_info']
        events = st.session_state.get('events', [])

        # ── Device Identity ──
        dev_id = modem_info.get('device_identity', {})
        if dev_id:
            st.subheader("🪪 Device Identity")
            _id_fields = [
                ('imei', 'IMEI'), ('imsi', 'IMSI'), ('iccid', 'ICCID'),
                ('hw_ver', 'Device Model'), ('modem_type', 'Modem Type'),
                ('fw_version', 'FW Version'), ('fw_revision', 'FW Revision'),
                ('bl_ver', 'Bootloader'), ('hw_mod', 'HW Mod'),
                ('sim_status', 'SIM Status'),
                ('network_type', 'Network Type'), ('band', 'Band'),
                ('model', 'AT Model'), ('manufacturer', 'Manufacturer'),
            ]
            rows_html = []
            for field, label in _id_fields:
                val = dev_id.get(field)
                if val:
                    rows_html.append(
                        f"<div class='id-item'><div class='id-key'>{_html.escape(label)}</div>"
                        f"<div class='id-val'>{_html.escape(str(val))}</div></div>"
                    )
            if rows_html:
                st.markdown(
                    """
                    <style>
                    .id-grid {
                        display: grid;
                        grid-template-columns: repeat(3, minmax(0, 1fr));
                        gap: 0.35rem 0.55rem;
                        margin-top: 0.2rem;
                    }
                    .id-item {
                        border: 1px solid rgba(128,128,128,0.28);
                        border-radius: 6px;
                        padding: 0.3rem 0.45rem;
                        background: rgba(127,127,127,0.06);
                    }
                    .id-key {
                        font-size: 0.68rem;
                        opacity: 0.8;
                        line-height: 1.1;
                        margin-bottom: 0.15rem;
                    }
                    .id-val {
                        font-size: 0.74rem;
                        line-height: 1.2;
                        overflow-wrap: anywhere;
                        word-break: break-word;
                        white-space: normal;
                    }
                    @media (max-width: 1200px) {
                        .id-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
                    }
                    </style>
                    """,
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div class='id-grid'>{''.join(rows_html)}</div>",
                    unsafe_allow_html=True,
                )
            st.divider()

        # ── Quick Status ──
        st.subheader("Network Summary")
        net_events = [e for e in events if e['Type'] in ('Network', 'Operator')]
        if net_events:
            c1, c2, c3 = st.columns(3)
            operators = [e['Value'] for e in events if e['Type'] == 'Operator']
            net_states = [e['Value'] for e in events if e['Type'] == 'Network']
            if operators:
                c1.metric("Last Operator", operators[-1])
                c2.metric("Operator Changes", len(operators))
            if net_states:
                c3.metric("Last Network State", net_states[-1])

            st.dataframe(
                pd.DataFrame(net_events)[['Timestamp', 'Type', 'Value', 'Details']],
                use_container_width=True, height=250,
            )
        else:
            st.caption("No network/operator events found in logs.")

        st.divider()

        # ── AT Commands ──
        st.subheader("AT Commands")
        at_cmds = modem_info.get('at_commands', [])
        if at_cmds:
            df_at = pd.DataFrame(at_cmds)

            # Ensure classification columns exist (backwards compat)
            if 'Category' not in df_at.columns:
                df_at['Category'] = 'Other'
            if 'Description' not in df_at.columns:
                df_at['Description'] = ''
            if 'Group' not in df_at.columns:
                df_at['Group'] = range(len(df_at))

            # ── Filters row ──
            fc1, fc2, fc3 = st.columns(3)

            with fc1:
                at_filter = st.text_input(
                    "🔍 Filter AT commands",
                    placeholder="CSQ, COPS, CREG, CIMI, QNWINFO...",
                )

            with fc2:
                all_categories = sorted(set(df_at['Category'].dropna()) - {''})
                cat_filter = st.multiselect(
                    "Category",
                    options=all_categories,
                    default=[],
                    placeholder="All categories",
                )

            with fc3:
                dir_filter = st.multiselect(
                    "Direction",
                    options=['CMD', 'RSP', 'INFO'],
                    default=['CMD', 'RSP', 'INFO'],
                )

            # Apply filters
            df_at_view = df_at[df_at['Direction'].isin(dir_filter)]
            if at_filter:
                mask = df_at_view['Content'].str.contains(at_filter, case=False, na=False)
                df_at_view = df_at_view[mask]
            if cat_filter:
                df_at_view = df_at_view[df_at_view['Category'].isin(cat_filter)]

            st.write(f"{len(df_at_view)} entries shown (of {len(df_at)} total)")

            # ── View mode toggle ──
            view_mode = st.radio(
                "View", ["Flat", "Conversation"],
                horizontal=True, label_visibility="collapsed",
            )

            if view_mode == "Flat":
                st.dataframe(
                    df_at_view, use_container_width=True, height=500,
                    column_config={
                        "Timestamp": st.column_config.TextColumn("Time", width="medium"),
                        "Direction": st.column_config.TextColumn("Dir", width="small"),
                        "Content": st.column_config.TextColumn("Content", width="large"),
                        "Category": st.column_config.TextColumn("Category", width="small"),
                        "Description": st.column_config.TextColumn("Description", width="medium"),
                        "LineNum": st.column_config.NumberColumn("#", width="small"),
                        "Group": None,  # hide
                    }
                )
            else:
                # Conversation view: group by TX/RX pairs
                if 'Group' in df_at_view.columns:
                    groups = df_at_view.groupby('Group', sort=False)
                    conv_lines = []
                    for gid, grp in groups:
                        cmds = grp[grp['Direction'] == 'CMD']
                        rsps = grp[grp['Direction'].isin(['RSP', 'INFO'])]
                        cmd_str = ', '.join(cmds['Content'].tolist()) if not cmds.empty else ''
                        rsp_str = ' | '.join(rsps['Content'].tolist()) if not rsps.empty else ''
                        ts = grp['Timestamp'].iloc[0] if not grp.empty else ''
                        cat = cmds['Category'].iloc[0] if not cmds.empty else (
                            rsps['Category'].iloc[0] if not rsps.empty else '')
                        desc = cmds['Description'].iloc[0] if not cmds.empty else (
                            rsps['Description'].iloc[0] if not rsps.empty else '')
                        conv_lines.append({
                            'Time': ts,
                            'Command': cmd_str,
                            'Response': rsp_str,
                            'Category': cat,
                            'Description': desc,
                        })
                    df_conv = pd.DataFrame(conv_lines)
                    if not df_conv.empty:
                        st.dataframe(
                            df_conv, use_container_width=True, height=500,
                            column_config={
                                "Time": st.column_config.TextColumn("Time", width="medium"),
                                "Command": st.column_config.TextColumn("Command", width="large"),
                                "Response": st.column_config.TextColumn("Response", width="large"),
                                "Category": st.column_config.TextColumn("Cat", width="small"),
                                "Description": st.column_config.TextColumn("Description", width="medium"),
                            }
                        )
                    else:
                        st.caption("No conversations to display.")
                else:
                    st.caption("Group data not available for conversation view.")

            # Download
            at_text = "\n".join(
                f"[{r['Timestamp']}] {r['Direction']:>4} | {r.get('Category',''):>10} | {r['Content']}"
                for _, r in df_at_view.iterrows()
            )
            st.download_button(
                "💾 Download AT Log", data=at_text,
                file_name="at_commands.txt", mime="text/plain",
                use_container_width=True,
            )
        else:
            st.caption("No AT commands found. Ensure log contains [AT.CMD] / [AT.RSP] / [ATCMD] tags.")

        st.divider()

        # ── Record Sending ──
        st.subheader("Record Sending")
        rec_events = [e for e in events if e['Type'] == 'Record Sending']
        if rec_events:
            df_rec = pd.DataFrame(rec_events)[['Timestamp', 'Value', 'Details']]
            st.dataframe(df_rec, use_container_width=True, height=250)
        else:
            st.caption("No record sending state changes found.")


# ━━━━━━━━━━━━ TAB: Map ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_map:
    if 'data_points' not in st.session_state:
        st.info("No data. Upload and parse logs first.")
    else:
        data_points = st.session_state.get('data_points', [])
        source = st.session_state.get('file_name', 'log')

        if not data_points:
            st.info(f"Parsed **{source}** — no GPS points found.")
        else:
            st.write(f"{len(data_points)} GPS points from **{source}**")
            try:
                map_obj = create_map(data_points)
                if map_obj:
                    st_folium(map_obj, width=None, height=600,
                              returned_objects=[], key='main_map')
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Points", len(data_points))
                    speeds = [p['speed'] for p in data_points if p['speed'] > 0]
                    c2.metric("Avg Speed", f"{sum(speeds)/len(speeds):.1f} km/h" if speeds else "0")
                    c3.metric("Max Speed", f"{max(p['speed'] for p in data_points):.1f} km/h")
                    moving = sum(1 for p in data_points if p['speed'] > 5)
                    c4.metric("Moving", f"{moving}/{len(data_points)}")
                else:
                    st.warning("Could not generate map.")
            except Exception as e:
                st.error(f"Map error: {e}")


# ━━━━━━━━━━━━ TAB: Events Table ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_events:
    if 'events' not in st.session_state or not st.session_state['events']:
        st.info("No data. Upload and parse logs first.")
    else:
        events = filtered_events(st.session_state['events'])
        if not events:
            st.info("All events filtered out. Adjust sidebar filters.")
        else:
            df_ev = pd.DataFrame(events)

            search = st.text_input("🔍 Search events", placeholder="Search...")
            if search:
                mask = df_ev.astype(str).apply(
                    lambda row: row.str.contains(search, case=False, na=False).any(), axis=1)
                df_ev = df_ev[mask]
                st.write(f"{len(df_ev)} matches")

            st.dataframe(
                df_ev, use_container_width=True, height=600,
                column_config={
                    "Timestamp": st.column_config.TextColumn("Timestamp", width="medium"),
                    "Type": st.column_config.TextColumn("Type", width="small"),
                    "Value": st.column_config.TextColumn("Value", width="small"),
                    "Details": st.column_config.TextColumn("Details", width="large"),
                    "Log": st.column_config.TextColumn("Log Line", width="large"),
                }
            )

            csv = df_ev.to_csv(index=False)
            st.download_button(
                "💾 Download Events CSV", data=csv,
                file_name=f"events_{st.session_state.get('file_name', 'export')}.csv",
                mime="text/csv", use_container_width=True,
            )


# ━━━━━━━━━━━━ TAB: Raw Log ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_raw:
    if 'structured_logs' not in st.session_state or not st.session_state['structured_logs']:
        st.info("No data. Upload and parse logs first.")
    else:
        logs = st.session_state['structured_logs']
        df_logs = pd.DataFrame(logs)
        st.write(f"{len(df_logs)} log lines")

        c1, c2 = st.columns(2)
        with c1:
            all_mods = sorted(set(df_logs['Module'].dropna()) - {''})
            sel_mods = st.multiselect("Filter by Module", options=all_mods, default=[])
            if sel_mods:
                df_logs = df_logs[df_logs['Module'].isin(sel_mods)]
        with c2:
            all_types = sorted(set(df_logs['Type'].dropna()) - {''})
            sel_types = st.multiselect("Filter by Type", options=all_types, default=[])
            if sel_types:
                df_logs = df_logs[df_logs['Type'].isin(sel_types)]

        search_log = st.text_input("🔍 Search log content", placeholder="Search messages...")
        if search_log:
            df_logs = df_logs[df_logs['Message'].str.contains(search_log, case=False, na=False)]
            st.write(f"{len(df_logs)} matches")

        st.dataframe(
            df_logs, use_container_width=True, height=600,
            column_config={
                "Line": st.column_config.NumberColumn("Line", width="small"),
                "Time": st.column_config.TextColumn("Time", width="small"),
                "Type": st.column_config.TextColumn("Type", width="small"),
                "Module": st.column_config.TextColumn("Module", width="small"),
                "Level": st.column_config.TextColumn("Level", width="small"),
                "Message": st.column_config.TextColumn("Message", width="large"),
            }
        )
