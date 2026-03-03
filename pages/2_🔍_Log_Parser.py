import re as _re
import streamlit as st
import pandas as pd
import os
import sys
import json
import gzip
import tempfile
import zipfile
import numpy as np
import shutil
import html as _html
import glob as glob_mod
import pickle
import subprocess
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

# Ensure GPS Server is running globally
from modules.server_singleton import ensure_server_session
ensure_server_session()

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


def launch_catcher(clg_path: str):
    """Launch Easy Catcher with the given CLG file."""
    cfg = load_toolkit_settings()
    catcher_exe = cfg.get('catcher_path')
    if not catcher_exe or not os.path.exists(catcher_exe):
        # Fail silently or just warning if setting is missing, but user asked for it.
        # st.toast("Catcher path not configured", icon="⚠️")
        return
    
    if not os.path.exists(clg_path):
        return

    try:
        # Launch independent process
        if os.name == 'nt':
            subprocess.Popen([catcher_exe, clg_path], cwd=os.path.dirname(catcher_exe), 
                             creationflags=0x00000008, close_fds=True)
        else:
            subprocess.Popen([catcher_exe, clg_path], cwd=os.path.dirname(catcher_exe), close_fds=True)
            
        st.toast(f"🚀 Launched Catcher: {os.path.basename(clg_path)}")
    except Exception as e:
        st.error(f"Failed to launch Catcher: {e}")


def find_clg_in_folder(folder_path: str) -> str | None:
    """Return path to the first .clg file in the folder."""
    if not folder_path or not os.path.exists(folder_path): return None
    for f in os.listdir(folder_path):
        if f.lower().endswith('.clg'):
            return os.path.join(folder_path, f)
    return None


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


def find_ticket_folder_for_file(filename: str) -> str | None:
    """Find containing folder if *filename* exists inside a subdir of tickets_folder."""
    cfg = load_toolkit_settings()
    tickets_root = cfg.get('tickets_folder', '')
    if tickets_root and os.path.exists(tickets_root):
        try:
            for entry in os.scandir(tickets_root):
                if entry.is_dir():
                    candidate = os.path.join(entry.path, filename)
                    if os.path.exists(candidate):
                        return entry.path
        except Exception:
            pass
    return None


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
                  catcher_work_dir: str | None = None,
                  parsed_data: dict | None = None):
    """Persist a parsed analysis so it can be reopened later.

    Saves the raw concatenated log text as gzip (good compression for text)
    and copies any catcher artifacts (.clg, .log, .dmp) next to it.
    
    If 'parsed_data' is a dict, it will be pickled and gzipped to 'parsed_data.pkl.gz'.
    
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

    # 1.1 Save parsed data (pickle + gzip)
    if parsed_data:
        pkl_path = os.path.join(analysis_dir, 'parsed_data.pkl.gz')
        try:
            with gzip.open(pkl_path, 'wb', compresslevel=3) as gz:
                pickle.dump(parsed_data, gz, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as e:
            print(f"Failed to save parsed cache: {e}")

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
    """Load compressed log content and re-parse it.  Returns (content, meta, parsed_cache)."""
    analysis_dir = os.path.join(ANALYSES_DIR, analysis_id)
    if not os.path.exists(analysis_dir):
        return None, None, None

    gz_path = os.path.join(analysis_dir, 'log_content.gz')
    meta_path = os.path.join(analysis_dir, 'meta.json')
    pkl_path = os.path.join(analysis_dir, 'parsed_data.pkl.gz')
    
    # 1. Load content
    content = None
    if os.path.exists(gz_path):
        try:
            with gzip.open(gz_path, 'rt', encoding='utf-8') as gz:
                content = gz.read()
        except Exception:
            pass

    # 2. Load meta
    meta = {}
    if os.path.exists(meta_path):
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
        except Exception:
            pass

    # 3. Load parsed cache if available
    parsed_cache = None
    if os.path.exists(pkl_path):
        try:
            with gzip.open(pkl_path, 'rb') as gz:
                parsed_cache = pickle.load(gz)
        except Exception:
            pass

    return content, meta, parsed_cache


def load_analysis_from_path(folder_path: str):
    """Load from folder. Returns (content, meta, parsed_cache)."""
    gz_path = os.path.join(folder_path, 'log_content.gz')
    meta_path = os.path.join(folder_path, 'meta.json')
    pkl_path = os.path.join(folder_path, 'parsed_data.pkl.gz')

    if not os.path.exists(gz_path):
        return None, None, None

    with gzip.open(gz_path, 'rt', encoding='utf-8') as gz:
        content = gz.read()

    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)
            
    parsed_cache = None
    if os.path.exists(pkl_path):
        try:
            with gzip.open(pkl_path, 'rb') as gz:
                parsed_cache = pickle.load(gz)
        except Exception:
            pass

    return content, meta, parsed_cache


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


def restore_from_cache(parsed_cache, display_name):
    """Restore session state from loaded cache."""
    st.session_state['data_points'] = parsed_cache.get('data_points', [])
    ev_list = parsed_cache.get('events', [])
    log_list = parsed_cache.get('structured_logs', [])
    modem_info = parsed_cache.get('modem_info', {})
    
    st.session_state['events'] = ev_list
    st.session_state['structured_logs'] = log_list
    st.session_state['modem_info'] = modem_info
    
    # Re-hydrate DataFrames
    st.session_state['df_events'] = pd.DataFrame(ev_list) if ev_list else pd.DataFrame()
    st.session_state['df_structured_logs'] = pd.DataFrame(log_list) if log_list else pd.DataFrame()
    
    # Restore or re-compute DF AT
    # If the cache was created before we started saving df_at, we need to rebuild it
    at_cmds = modem_info.get('at_commands', [])
    if at_cmds:
        df_at = pd.DataFrame(at_cmds)
        if 'Category' not in df_at.columns: df_at['Category'] = ''
        if 'Description' not in df_at.columns: df_at['Description'] = ''
        
        # Fast ConvID gen
        conv_ids = []
        current_id = 0
        for d in df_at['Direction']:
            if d == 'CMD': current_id += 1
            conv_ids.append(current_id)
        df_at['ConvID'] = conv_ids
        st.session_state['df_at'] = df_at
    else:
        st.session_state['df_at'] = pd.DataFrame()

    st.session_state['file_name'] = display_name


# ── Parse & store helper ────────────────────────────────────────────
@st.cache_data
def get_df_from_records(records):
    return pd.DataFrame(records)

def parse_and_store(content, file_name):
    data_points, events, structured_logs, modem_info = parse_log(content)
    # Store directly as DataFrames to avoid re-creation on every rerun
    st.session_state['data_points'] = data_points
    # Store raw lists for legacy compatibility with other tabs
    st.session_state['events'] = events
    st.session_state['structured_logs'] = structured_logs
    
    # Pre-compute DataFrames for heavy tabs
    st.session_state['df_events'] = pd.DataFrame(events) if events else pd.DataFrame()
    st.session_state['df_structured_logs'] = pd.DataFrame(structured_logs) if structured_logs else pd.DataFrame()
    
    # Pre-compute AT Command DataFrame with ConvID
    at_cmds = modem_info.get('at_commands', [])
    if at_cmds:
        df_at = pd.DataFrame(at_cmds)
        # Ensure classification columns exist
        for col in ['Category', 'Description']:
            if col not in df_at.columns: df_at[col] = ''
        
        # Calculate ConvID once and stick it in the dataframe
        conv_ids = []
        current_id = 0
        for d in df_at['Direction']:
            if d == 'CMD': current_id += 1
            conv_ids.append(current_id)
        df_at['ConvID'] = conv_ids
        st.session_state['df_at'] = df_at
    else:
        st.session_state['df_at'] = pd.DataFrame()

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
                            with st.expander("Processing log", expanded=False):
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
                            parsed_data={
                                'data_points': data_points,
                                'events': events,
                                'structured_logs': structured_logs,
                                'modem_info': modem_info
                            }
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

                    # Auto-launch Catcher
                    _an_dir = os.path.join(ANALYSES_DIR, aid)
                    _clg_path = find_clg_in_folder(_an_dir)
                    if _clg_path:
                        launch_catcher(_clg_path)

                    # Automatic Save to Source Folder
                    if uploaded_files:
                        try:
                            _src_folder = find_ticket_folder_for_file(uploaded_files[0].name)
                            if _src_folder:
                                _base = os.path.splitext(uploaded_files[0].name)[0]
                                _out_path = os.path.join(_src_folder, f"{_base}_parsed.txt")
                                with open(_out_path, 'w', encoding='utf-8') as _f:
                                    _f.write(all_content)
                                st.success(f"💾 Automatically saved parsed log to: `{_out_path}`")
                                
                                # Auto-save CLG if available from Catcher processing
                                if last_catcher_work_dir and os.path.isdir(last_catcher_work_dir):
                                    for _f in os.listdir(last_catcher_work_dir):
                                        if _f.lower().endswith('.clg'):
                                            _src_clg = os.path.join(last_catcher_work_dir, _f)
                                            _dest_clg = os.path.join(_src_folder, f"{_base}.clg")
                                            # Avoid overwriting if possible or just overwrite? User implied "copy it".
                                            # Using shutil.copy2
                                            shutil.copy2(_src_clg, _dest_clg)
                                            st.success(f"💾 Automatically saved CLG to: `{_dest_clg}`")
                            else:
                                st.caption("Note: Auto-save skipped (Original file not found in tickets folder).")
                        except Exception as _e:
                            st.warning(f"Auto-save failed: {_e}")

                    st.download_button(
                        label="💾 Download Parsed TXT",
                        data=all_content,
                        file_name=f"{analysis_name.strip() or 'log'}_parsed.txt",
                        mime="text/plain",
                        use_container_width=True,
                    )
                    with st.expander("👁️ Preview Parsed Content", expanded=False):
                        st.text(all_content[:5000])
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
                with st.spinner("Loading..."):
                    content, meta, parsed_cache = load_analysis(sel_entry['id'])
                    
                    if parsed_cache:
                        display = meta.get('name', sel_entry['id'])
                        restore_from_cache(parsed_cache, display)
                        st.session_state['current_analysis_id'] = sel_entry['id']
                        st.success(f"Restored: {display} (Cached)")
                        
                        _clg = find_clg_in_folder(os.path.join(ANALYSES_DIR, sel_entry['id']))
                        if _clg: launch_catcher(_clg)
                        
                        st.rerun()
                    elif content:
                        st.info("Cache miss: Re-parsing logs...")
                        display = meta.get('name', sel_entry['id'])
                        data_points, events, structured_logs, modem_info = parse_and_store(content, display)
                        
                        # Save cache for next time
                        try:
                            parsed_cache = {
                                'data_points': data_points,
                                'events': events,
                                'structured_logs': structured_logs,
                                'modem_info': modem_info
                            }
                            # We don't want to create a new folder, just update the existing one
                            # We can reuse save_analysis logic but we need the path.
                            # Or just construct the path manually since we know the ID.
                            analysis_dir = os.path.join(ANALYSES_DIR, sel_entry['id'])
                            pkl_path = os.path.join(analysis_dir, 'parsed_data.pkl.gz')
                            with gzip.open(pkl_path, 'wb', compresslevel=3) as gz:
                                pickle.dump(parsed_cache, gz, protocol=pickle.HIGHEST_PROTOCOL)
                        except Exception as e:
                            print(f"Failed to backfill cache: {e}")
                            
                        st.session_state['current_analysis_id'] = sel_entry['id']
                        st.success(f"Loaded: {display} (Cache created)")

                        _clg = find_clg_in_folder(os.path.join(ANALYSES_DIR, sel_entry['id']))
                        if _clg: launch_catcher(_clg)

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
                with st.expander(f"Saved artifacts ({len(artifacts)} files)", expanded=False):
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
            with st.spinner("Loading..."):
                content, meta, parsed_cache = load_analysis_from_path(folder_path)
                
                if parsed_cache:
                    display = meta.get('name', os.path.basename(folder_path))
                    restore_from_cache(parsed_cache, display)
                    st.session_state['current_analysis_id'] = meta.get('id', '')
                    st.success(f"Restored: {display} (Cached)")
                    
                    _clg = find_clg_in_folder(folder_path)
                    if _clg: launch_catcher(_clg)
                    
                    st.rerun()
                elif content:
                    st.info("Cache miss: Re-parsing logs...")
                    display = meta.get('name', os.path.basename(folder_path))
                    data_points, events, structured_logs, modem_info = parse_and_store(content, display)
                    
                    try:
                        parsed_cache = {
                            'data_points': data_points,
                            'events': events,
                            'structured_logs': structured_logs,
                            'modem_info': modem_info
                        }
                        pkl_path = os.path.join(folder_path, 'parsed_data.pkl.gz')
                        with gzip.open(pkl_path, 'wb', compresslevel=3) as gz:
                            pickle.dump(parsed_cache, gz, protocol=pickle.HIGHEST_PROTOCOL)
                    except Exception as e:
                        print(f"Failed to backfill cache for manual open: {e}")

                    st.session_state['current_analysis_id'] = meta.get('id', '')
                    st.success(f"Loaded: {display} (Cache created)")
                    
                    _clg = find_clg_in_folder(folder_path)
                    if _clg: launch_catcher(_clg)
                    
                    st.rerun()
                else:
                    st.error("No valid analysis found in that folder.")


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
        # Use pre-computed DataFrame from session state
        df_at = st.session_state.get('df_at', pd.DataFrame())
        
        if not df_at.empty:
            # ── Filters row ──
            with st.expander("🔎 Filter & Search", expanded=False):
                with st.form("at_search_form"):
                    fc1, fc2, fc3 = st.columns(3)
                    with fc1:
                        at_filter = st.text_input(
                            "Search content",
                            placeholder="CSQ, COPS, CREG...",
                        )
                    with fc2:
                        # Cached unique values
                        cats = sorted(df_at['Category'].unique())
                        cat_filter = st.multiselect(
                            "Category",
                            options=cats,
                            default=[],
                            placeholder="All categories",
                        )
                    with fc3:
                        dir_filter = st.multiselect(
                            "Show Directions",
                            options=['CMD', 'RSP', 'INFO'],
                            default=['CMD', 'RSP', 'INFO'],
                        )
                    submitted = st.form_submit_button("Search")

            # Apply filters
            # 1. Base filter by Text & Category
            
            # Optimized search: if user searches, we find match indices, get their ConvIDs
            # calculate the mask for the WHOLE conversation efficiently
            active_ids = None

            if at_filter:
                match_mask = df_at['Content'].str.contains(at_filter, case=False, na=False)
                active_ids = df_at.loc[match_mask, 'ConvID'].unique()
            
            if cat_filter:
                # Filter first by cat, find those IDs
                cat_mask = df_at['Category'].isin(cat_filter)
                cat_ids = df_at.loc[cat_mask, 'ConvID'].unique()
                if active_ids is not None:
                    active_ids = np.intersect1d(active_ids, cat_ids)
                else:
                    active_ids = cat_ids

            if at_filter or cat_filter:
                if active_ids is not None and len(active_ids) > 0:
                    df_context = df_at[df_at['ConvID'].isin(active_ids)] # view is fine, no copy needed yet
                else:
                    df_context = pd.DataFrame(columns=df_at.columns)
            else:
                # No filters active, show all
                df_context = df_at
            
            # Final view filter (hide INFO if unchecked)
            if not df_context.empty:
                df_at_view = df_context[df_context['Direction'].isin(dir_filter)]
            else:
                df_at_view = df_context

            st.write(f"{len(df_at_view)} entries shown")

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
                # Conversation view: group by ConvID (Vectorized)
                # Use ConvID if available, else fall back to Group or just range
                group_col = 'ConvID' if 'ConvID' in df_at_view.columns else 'Group'
                
                if group_col in df_at_view.columns:
                    # 1. Prepare base data
                    # We want one row per conversation.
                    # This DF is already filtered by what the user searched.
                    
                    if len(df_at_view) > 20000:
                        st.warning("Too many results for conversation view. Showing first 2000.")
                        df_at_view = df_at_view.iloc[:10000] # Safe limit for groupby
                    
                    df_view_copy = df_at_view.copy()
                    
                    # Separate CMD vs RSP content
                    df_view_copy['CmdContent'] = df_view_copy['Content'].where(df_view_copy['Direction'] == 'CMD', None)
                    df_view_copy['RspContent'] = df_view_copy['Content'].where(df_view_copy['Direction'].isin(['RSP', 'INFO']), None)
                    
                    # Aggregate
                    # this reduces ~30k groups to 30k rows effectively
                    df_conv = df_view_copy.groupby(group_col, sort=False).agg({
                        'Timestamp': 'first',
                        'Category': 'first',
                        'Description': 'first',
                        'CmdContent': lambda x: ', '.join(x.dropna().astype(str)),
                        'RspContent': lambda x: ' | '.join(x.dropna().astype(str)),
                    }).reset_index()
                    
                    # Rename for display
                    df_conv.rename(columns={
                        'CmdContent': 'Command',
                        'RspContent': 'Response',
                        'Timestamp': 'Time'
                    }, inplace=True)
                    
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
    df_raw_ev = st.session_state.get('df_events', pd.DataFrame())
    if df_raw_ev.empty:
        st.info("No data. Upload and parse logs first.")
    else:
        # Apply sidebar filters (vectorized)
        # FILTER_MAP keys match 'Type' values or default to True
        # Get list of allowed types based on current checkbox states
        valid_types = [t for t in df_raw_ev['Type'].unique() if FILTER_MAP.get(t, True)]
        df_ev = df_raw_ev[df_raw_ev['Type'].isin(valid_types)].copy()
        
        if df_ev.empty:
            st.info("All events filtered out. Adjust sidebar filters.")
        else:
            with st.form("events_filter_form"):
                col_s1, col_s2 = st.columns([3, 1])
                with col_s1:
                    search = st.text_input("Search events", placeholder="Type to search...", label_visibility="collapsed")
                with col_s2:
                    submitted = st.form_submit_button("🔍 Search", use_container_width=True)

            if search:
                # Optimized search across all columns
                mask = df_ev.astype(str).agg(' '.join, axis=1).str.contains(search, case=False, na=False)
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
    df_logs_raw = st.session_state.get('df_structured_logs', pd.DataFrame())
    
    if df_logs_raw.empty:
        st.info("No data. Upload and parse logs first.")
    else:
        # Work on a view/copy
        df_logs = df_logs_raw
        st.write(f"{len(df_logs)} log lines")

        with st.form("raw_log_filters"):
            c1, c2 = st.columns(2)
            # Use cached unique values if possible, or calculate once
            # Since df_logs_raw is constant per parsing, uniques are constant
            mods = sorted(df_logs['Module'].dropna().unique())
            types = sorted(df_logs['Type'].dropna().unique())
            
            with c1:
                sel_mods = st.multiselect("Filter by Module", options=mods, default=[])
            with c2:
                sel_types = st.multiselect("Filter by Type", options=types, default=[])

            search_log = st.text_input("Search content", placeholder="Search messages...", label_visibility="collapsed")
            submitted = st.form_submit_button("🔍 Apply Filters", use_container_width=True)

        # Apply filters
        start_time = datetime.now()
        if sel_mods:
            df_logs = df_logs[df_logs['Module'].isin(sel_mods)]
        if sel_types:
            df_logs = df_logs[df_logs['Type'].isin(sel_types)]

        if search_log:
             df_logs = df_logs[df_logs['Message'].str.contains(search_log, case=False, na=False)]
             st.caption(f"Search took {(datetime.now()-start_time).total_seconds():.2f}s")
        
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
