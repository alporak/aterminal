# ─────────────────────────────────────────────────────────────────────────────
#  Adding meetings time – log standup/meeting work to FMBP-44552
# ─────────────────────────────────────────────────────────────────────────────
def _render_meetings_time_section():
    from datetime import date
    config = _load_jira_config()
    email = config.get("email", "")
    token = config.get("token", "")
    st.divider()
    st.subheader("🕒 Meetings Logging")
    if not email or not token:
        st.warning("Configure Jira credentials in the sidebar.")
        return
    today = date.today()
    default_summary = f"{today.month:02}.{today.day:02} standup"
    def parse_time_input(text: str) -> int | None:
        import re
        text = text.strip().lower()
        if not text:
            return None
        m = re.fullmatch(r"(\d+):(\d{1,2})", text)
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60
        h_match = re.search(r"(\d+(?:\.\d+)?)\s*h", text)
        m_match = re.search(r"(\d+(?:\.\d+)?)\s*m", text)
        if h_match or m_match:
            hours = float(h_match.group(1)) if h_match else 0
            mins = float(m_match.group(1)) if m_match else 0
            return int(hours * 3600 + mins * 60)
        try:
            val = float(text)
            if val < 0:
                return None
            return int(val * 60)
        except ValueError:
            return None

    with st.form("add_meeting_time_form", clear_on_submit=True):
        time_input = st.text_input("Time (e.g. 1h 30m, 45m, 1:30)", value="30m")
        summary = st.text_input("Summary", value=default_summary)
        submit = st.form_submit_button("Add meeting time")
        if submit:
            seconds = parse_time_input(time_input)
            if seconds is None or seconds <= 0:
                st.error("Invalid time format. Use e.g. '1h 30m', '45m', '1:30', or minutes.")
            else:
                import requests
                from datetime import datetime
                started_dt = datetime.now()
                started_str = started_dt.strftime("%Y-%m-%dT%H:%M:%S.000+0000")
                body = {
                    "timeSpentSeconds": seconds,
                    "started": started_str,
                    "comment": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": summary}] if summary else [],
                            }
                        ],
                    },
                }
                headers = {"Accept": "application/json", "Content-Type": "application/json"}
                auth = requests.auth.HTTPBasicAuth(email, token)
                resp = requests.post(
                    f"https://teltonika-telematics.atlassian.net/rest/api/3/issue/FMBP-44552/worklog",
                    headers=headers, auth=auth, json=body,
                    params={"adjustEstimate": "auto", "notifyUsers": "false"},
                )
                if resp.status_code in (200, 201):
                    st.success(f"Meeting time added to FMBP-44552 ({time_input})")
                else:
                    try:
                        err = resp.json()
                        st.error(f"Failed: {resp.status_code} {err}")
                    except Exception:
                        st.error(f"Failed: {resp.status_code} {resp.text}")

import streamlit as st
import os
import sys
import json
import requests
from requests.auth import HTTPBasicAuth

# Resolve paths
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JIRA_DIR = os.path.join(ROOT_DIR, "jira-time-tracker")
JIRA_APP = os.path.join(JIRA_DIR, "streamlit_app.py")
JIRA_CONFIG = os.path.join(JIRA_DIR, "jira_config.json")
JIRA_DOMAIN = "teltonika-telematics.atlassian.net"

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


# ═════════════════════════════════════════════════════════════════════════
#  Open Ticket Directory – utility added by the toolkit wrapper
# ═════════════════════════════════════════════════════════════════════════

def _load_jira_config():
    """Load the jira_config.json from the submodule directory."""
    if os.path.exists(JIRA_CONFIG):
        try:
            with open(JIRA_CONFIG, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_jira_config(config):
    """Save back to jira_config.json."""
    with open(JIRA_CONFIG, "w") as f:
        json.dump(config, f, indent=2)


def _find_ticket_folder(base_dir: str, ticket_key: str):
    """
    Look for an existing folder matching the ticket key.
    Checks for: <ticket_key>, <ticket_key>_attachments
    Returns the path if found, else None.
    """
    for name in (ticket_key, f"{ticket_key}_attachments"):
        candidate = os.path.join(base_dir, name)
        if os.path.isdir(candidate):
            return candidate
    return None


def _download_attachments(email: str, token: str, ticket_key: str, dest_dir: str):
    """
    Download all attachments from a Jira issue into dest_dir.
    Returns (success: bool, message: str).
    """
    auth = HTTPBasicAuth(email, token)
    headers = {"Accept": "application/json"}

    try:
        resp = requests.get(
            f"https://{JIRA_DOMAIN}/rest/api/3/issue/{ticket_key}",
            headers=headers, auth=auth,
            params={"fields": "attachment"},
        )
        if resp.status_code != 200:
            return False, f"Failed to fetch issue: HTTP {resp.status_code}"

        attachments = resp.json().get("fields", {}).get("attachment", [])
        if not attachments:
            return True, "No attachments found on this ticket."

        os.makedirs(dest_dir, exist_ok=True)
        downloaded = 0
        for att in attachments:
            file_url = att.get("content")
            filename = att.get("filename", "unknown")
            if not file_url:
                continue

            file_path = os.path.join(dest_dir, filename)
            
            # Simple check: if file exists, we assume it's the same file and skip.
            # (To handle same-name files properly, one would need to check size/hash or maintain a mapping,
            # but for this use case, skipping existing filenames is the standard "resume/sync" behavior).
            if os.path.exists(file_path):
                continue

            file_resp = requests.get(file_url, auth=auth, stream=True)
            if file_resp.status_code == 200:
                with open(file_path, "wb") as f:
                    for chunk in file_resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                downloaded += 1

        if downloaded > 0:
            return True, f"Downloaded {downloaded} new attachment(s)."
        else:
            return True, "No new attachments found."

    except Exception as e:
        return False, str(e)


def _open_in_explorer(path: str):
    """Open a folder in Windows Explorer."""
    os.startfile(path)


def _render_tickets_folder_sidebar():
    """Add the tickets folder config to the sidebar (configure once)."""
    config = _load_jira_config()
    tickets_folder = config.get("tickets_folder", "")

    with st.sidebar:
        st.divider()
        st.subheader("📂 Tickets Folder")
        new_folder = st.text_input(
            "Tickets folder path",
            value=tickets_folder,
            key="tickets_folder_input",
            placeholder=r"C:\Users\you\tickets",
            help="Base directory where ticket attachment folders are stored.",
        )
        if new_folder != tickets_folder:
            config["tickets_folder"] = new_folder
            _save_jira_config(config)


def _render_ticket_directory_section():
    """Render the 'Open Ticket Directory' UI section."""
    config = _load_jira_config()
    email = config.get("email", "")
    token = config.get("token", "")
    tickets_folder = config.get("tickets_folder", "")

    st.divider()
    st.subheader("📂 Open Ticket Directory")

    if not tickets_folder:
        st.warning("Set a tickets folder path in the sidebar to enable this feature.")
        return

    # Reuse the assigned tickets already loaded by the Log Work section
    assigned = st.session_state.get("assigned_tickets")
    if assigned is None:
        st.info("⏳ Assigned tickets not loaded yet. Expand **Log Work** above first, or wait for reload.")
        return

    if not assigned:
        st.info("No assigned tickets found.")
        return

    # Same dropdown format as Log Work
    ticket_options = [
        f"{t['key']}  {'🔵' if t['status'].lower() in ('in progress', 'in development', 'in review') else '⚪'}  {t['summary'][:60]}"
        for t in assigned
    ]

    selected_idx = st.selectbox(
        "Ticket",
        range(len(ticket_options)),
        format_func=lambda i: ticket_options[i],
        key="ticket_dir_sel",
        label_visibility="collapsed",
    )
    
    ticket_key = assigned[selected_idx]["key"]

    col1, col2 = st.columns(2)
    with col1:
        if st.button("📂 Open Ticket Directory", key="open_ticket_dir_btn", use_container_width=True):
            existing = _find_ticket_folder(tickets_folder, ticket_key)
            dest_dir = existing if existing else os.path.join(tickets_folder, ticket_key)

            # unexpected error handling or just message
            synced = False
            if email and token:
                with st.spinner(f"Syncing attachments for {ticket_key}..."):
                    ok, msg = _download_attachments(email, token, ticket_key, dest_dir)
                    if ok:
                        if "No new attachments" not in msg:
                            st.success(msg)
                        synced = True
                    else:
                        st.error(f"Sync failed: {msg}")

            if os.path.exists(dest_dir) and os.path.isdir(dest_dir):
                _open_in_explorer(dest_dir)
                if not synced and not (email and token):
                    st.warning("Opened local folder without syncing (credentials missing).")
            else:
                if not (email and token):
                    st.error("Folder not found and cannot download (credentials missing).")
                elif not os.path.exists(dest_dir):
                    st.info("No files downloaded; folder was not created.")

    with col2:
        st.link_button(
            "🌐 Open Jira Ticket",
            f"https://{JIRA_DOMAIN}/browse/{ticket_key}",
            use_container_width=True,
        )


# Inject sidebar config + render the ticket directory section
_render_tickets_folder_sidebar()
_render_ticket_directory_section()
_render_meetings_time_section()

# Read and compile the submodule source
with open(JIRA_APP, "r", encoding="utf-8") as _f:
    _source = _f.read()

_code = compile(_source, JIRA_APP, "exec")

# Execute in a clean namespace.  Setting __file__ to the submodule path
# ensures _APP_DIR / CONFIG_FILE / CACHE_FILE resolve to jira-time-tracker/.
exec(_code, {"__file__": JIRA_APP, "__name__": "__main__"})
