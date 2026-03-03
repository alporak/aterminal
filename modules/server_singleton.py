import streamlit as st
import os
import sys
import json

# Ensure we can import from server_app (sibling folder to modules)
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from server_app.teltonika_server import TeltonikaServer

CONFIG_PATH = os.path.join(ROOT_DIR, 'toolkit_settings.json')

def _load_server_init_config():
    defaults = {'server_port': 8000, 'server_protocol': 'TCP'}
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                cfg = json.load(f)
            return {
                'server_port': cfg.get('server_port', cfg.get('tcp_port', defaults['server_port'])),
                'server_protocol': cfg.get('server_protocol', defaults['server_protocol']),
            }
    except Exception:
        pass
    return defaults

@st.cache_resource(show_spinner="Starting GPS Server...", hash_funcs={TeltonikaServer: lambda s: id(s)})
def get_global_server():
    """
    Get or create a persistent server instance. 
    Using cache_resource ensures the server survives page navigation and reloads.
    """
    cfg = _load_server_init_config()
    srv = TeltonikaServer(port=cfg['server_port'], protocol=cfg['server_protocol'])
    err = srv.start()
    return srv, err

def ensure_server_session():
    """Call this on every page to ensure server is alive and in session state."""
    srv, err = get_global_server()
    if 'server' not in st.session_state or st.session_state.server is not srv:
        st.session_state.server = srv
        st.session_state.server_start_error = err
    return srv
