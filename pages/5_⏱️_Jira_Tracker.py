"""
Jira Time Tracker – wrapper page for the jira-time-tracker submodule.
Loads and executes the submodule's streamlit_app.py inside this page context.
"""

import streamlit as st
import os
import sys

# Resolve paths
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JIRA_DIR = os.path.join(ROOT_DIR, "jira-time-tracker")
JIRA_APP = os.path.join(JIRA_DIR, "streamlit_app.py")

if not os.path.exists(JIRA_APP):
    st.error(
        f"Jira Time Tracker submodule not found at `{JIRA_APP}`.\n\n"
        "Make sure the submodule is initialised:\n```\ngit submodule update --init\n```"
    )
    st.stop()

# Ensure the submodule directory is on sys.path so its own imports
# (e.g. streamlit_autorefresh) resolve when executed from the toolkit.
if JIRA_DIR not in sys.path:
    sys.path.insert(0, JIRA_DIR)

# Read and compile the submodule source
with open(JIRA_APP, "r", encoding="utf-8") as _f:
    _source = _f.read()

_code = compile(_source, JIRA_APP, "exec")

# Execute in a clean namespace.  Setting __file__ to the submodule path
# ensures _APP_DIR / CONFIG_FILE / CACHE_FILE resolve to jira-time-tracker/.
exec(_code, {"__file__": JIRA_APP, "__name__": "__main__"})
