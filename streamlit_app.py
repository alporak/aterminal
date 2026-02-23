import streamlit as st
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, timedelta
import json
import os
import time
import random
import concurrent.futures

DOMAIN = "teltonika-telematics.atlassian.net"
CONFIG_FILE = "jira_config.json"
CACHE_FILE = "worklog_cache.json"

LOADING_MESSAGES = [
    "⏳ Fetching your time logs...",
    "🔍 Analyzing worklogs...",
    "📊 Processing data...",
    "🤔 Wondering why Jira got worse...",
    "💸 Calculating if the app is worth 1500$ yet...",
    "🛰️ GPS locked on your procrastination...",
    "⚡ Running faster than GitLab CI...",
    "🎯 Hunting down those missing hours...",
    "🔧 Unlike Jira, this actually works...",
    "🚀 Launching tracker satellites...",
    "🌍 Geolocating your productivity...",
    "📞 Calling Atlassian support... just kidding",
    "🎪 Performing circus tricks...",
    "🧮 Doing math you should've done...",
    "⏰ Time is money... literally...",
    "🛠️ Pretending to work...",
    "🎰 Rolling for API response...",
    "🏃 Racing against sprint deadlines...",
    "🔮 Predicting your next excuse...",
    "💼 Justifying your existence to HR...",
    "🎭 Making up stories about productivity...",
]

# Page config must be first Streamlit command
st.set_page_config(
    page_title="Jira Time Tracker",
    page_icon="⏱️",
    layout="centered",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .block-container {
        max-width: 900px;
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #3B8ED0;
        text-align: center;
        margin-bottom: 0.5rem;
        margin-top: 0;
    }
    .status-text {
        font-size: 1rem;
        font-weight: bold;
        text-align: center;
        color: #888;
        margin: 0.5rem 0;
    }
    .teammate-button {
        display: inline-block;
        padding: 0.5rem 1rem;
        margin: 0.25rem;
        border-radius: 20px;
        background-color: #555;
        color: white;
        font-weight: bold;
        text-align: center;
    }
    .teammate-button-selected {
        background-color: #3B8ED0;
    }
    .ticket-card {
        background-color: #2b2b2b;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 8px;
    }
    .stProgress > div > div > div > div {
        background-color: #3B8ED0;
    }
    div[data-testid="stHorizontalBlock"] {
        gap: 0.5rem;
    }
    h2 {
        margin-top: 1rem;
        margin-bottom: 0.5rem;
    }
    hr {
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)

def load_config():
    """Load configuration from JSON file"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_config(config):
    """Save configuration to JSON file"""
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

def load_cache():
    """Load worklog cache from disk"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                data = json.load(f)
                return data.get("worklog_cache", {}), data.get("last_cache_time", 0)
        except:
            return {}, 0
    return {}, 0

def save_cache(worklog_cache, last_cache_time):
    """Save worklog cache to disk"""
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump({
                "worklog_cache": worklog_cache,
                "last_cache_time": last_cache_time
            }, f, indent=2)
    except Exception as e:
        # Silently fail if can't save cache - not critical
        pass

def get_date_for_view(view_mode, selected_date=None):
    """Get the date object for a view mode"""
    today = datetime.now().date()
    if view_mode == "yesterday":
        return today - timedelta(days=1)
    elif view_mode == "specific_day" and selected_date:
        return selected_date
    return None

def filter_tickets_for_date(ticket_details, target_date):
    """Filter week ticket data to only include worklogs from a specific date"""
    filtered_tickets = []
    total_seconds = 0
    
    for ticket in ticket_details:
        ticket_seconds = 0
        ticket_worklogs = []
        
        for wl in ticket.get('worklogs', []):
            if isinstance(wl, dict) and wl.get('date') == target_date:
                ticket_seconds += wl.get('seconds', 0)
                if wl.get('comment'):
                    ticket_worklogs.append(wl.get('comment'))
        
        if ticket_seconds > 0:
            filtered_tickets.append({
                'key': ticket['key'],
                'summary': ticket['summary'],
                'time': ticket_seconds / 3600,
                'worklogs': ticket_worklogs
            })
            total_seconds += ticket_seconds
    
    return total_seconds, filtered_tickets

def get_cache_key(view_mode, selected_date):
    """Generate cache key for view mode and date"""
    if view_mode == "specific_day" and selected_date:
        return f"{view_mode}_{selected_date.strftime('%Y-%m-%d')}"
    return view_mode

def get_cached_data(user_email, view_mode, selected_date, cache_duration):
    """Get cached data if available and not expired"""
    cache_key = get_cache_key(view_mode, selected_date)
    
    if user_email in st.session_state.worklog_cache:
        if view_mode in st.session_state.worklog_cache[user_email]:
            if cache_key in st.session_state.worklog_cache[user_email][view_mode]:
                cached = st.session_state.worklog_cache[user_email][view_mode][cache_key]
                total_seconds, ticket_details, display_name, cache_time = cached
                
                # Check if cache is still valid
                if time.time() - cache_time < cache_duration:
                    return total_seconds, ticket_details, display_name
                
                return None
    
    return None

def set_cached_data(user_email, view_mode, selected_date, total_seconds, ticket_details, display_name):
    """Store data in cache"""
    cache_key = get_cache_key(view_mode, selected_date)
    
    if user_email not in st.session_state.worklog_cache:
        st.session_state.worklog_cache[user_email] = {}
    
    if view_mode not in st.session_state.worklog_cache[user_email]:
        st.session_state.worklog_cache[user_email][view_mode] = {}
    
    st.session_state.worklog_cache[user_email][view_mode][cache_key] = (
        total_seconds, ticket_details, display_name, time.time()
    )
    
    # Persist cache to disk
    save_cache(st.session_state.worklog_cache, st.session_state.last_cache_time)

def clear_all_cache():
    """Clear all cached worklog data"""
    st.session_state.worklog_cache = {}
    st.session_state.last_cache_time = 0
    st.session_state.cache_loading_status = {
        'loaded': 0, 
        'total': 0, 
        'is_loading': False,
        'current_user': '',
        'current_view': ''
    }
    st.session_state.cache_completion_times = {}
    # Persist cleared cache to disk
    save_cache(st.session_state.worklog_cache, st.session_state.last_cache_time)

if 'jira_user_info' not in st.session_state:
    st.session_state.jira_user_info = {}

def get_jira_user(email, token):
    """Get current user info (cached)"""
    if email in st.session_state.jira_user_info:
        return st.session_state.jira_user_info[email]
    
    try:
        auth = HTTPBasicAuth(email, token)
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        myself = requests.get(f"https://{DOMAIN}/rest/api/3/myself", headers=headers, auth=auth).json()
        account_id = myself.get('accountId')
        my_email = myself.get('emailAddress', '').lower() # Fallback to input email
        
        user_info = {'accountId': account_id, 'email': my_email or email.lower()}
        st.session_state.jira_user_info[email] = user_info
        return user_info
    except:
        return {'accountId': None, 'email': email.lower()}

def fetch_issue_worklog(session, key, headers, auth, start_date, end_date, target_is_me, my_account_id, target_user_email):
    """Fetch worklog for a single issue (helper for threading)"""
    wl_url = f"https://{DOMAIN}/rest/api/3/issue/{key}/worklog"
    # Use session for connection pooling
    try:
        wl_resp = session.get(wl_url, headers=headers, auth=auth)
    except:
        return 0, []

    issue_seconds = 0
    worklog_entries = []
    
    if wl_resp.status_code == 200:
        worklogs = wl_resp.json().get('worklogs', [])
        # Iterate over worklogs
        for entry in worklogs:
            entry_author = entry.get('author', {})
            author_match = False
            
            if target_is_me and my_account_id:
                if entry_author.get('accountId') == my_account_id:
                    author_match = True
            
            if not author_match:
                if entry_author.get('emailAddress', '').lower() == target_user_email:
                    author_match = True
                    
            if not author_match:
                continue

            try:
                started_str = entry['started']
                # Parse with timezone if present, else fallback
                if 'T' in started_str:
                     # Check if timezone info is present (e.g. +0300)
                     if '+' in started_str or '-' in started_str[-5:]: 
                         log_dt = datetime.strptime(started_str, "%Y-%m-%dT%H:%M:%S.%f%z")
                         local_dt = log_dt.astimezone()
                         log_date_obj = local_dt.date()
                     else:
                         log_date_obj = datetime.strptime(started_str[:10], "%Y-%m-%d").date()
                else:
                    log_date_obj = datetime.strptime(started_str[:10], "%Y-%m-%d").date()
            except ValueError:
                continue

            if log_date_obj >= start_date and (not end_date or log_date_obj <= end_date):
                issue_seconds += entry['timeSpentSeconds']
                comment = entry.get('comment', '')
                # Process ADF comment structure or string
                if isinstance(comment, dict):
                     # Try to extract text from ADF
                     try:
                         text_parts = []
                         for doc_content in comment.get('content', []):
                             for node in doc_content.get('content', []):
                                 if node.get('type') == 'text':
                                     text_parts.append(node.get('text', ''))
                         comment = " ".join(text_parts)
                     except:
                         comment = "ADF Comment"
                
                # Store worklog with date info for later filtering
                worklog_entries.append({
                    'date': log_date_obj,
                    'seconds': entry['timeSpentSeconds'],
                    'comment': comment
                })
    
    return issue_seconds, worklog_entries

def fetch_jira_data(email, token, target_email, view_mode, selected_date=None):
    """Fetch Jira worklog data"""
    try:
        auth = HTTPBasicAuth(email, token)
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        
        # Get cached user info
        user_info = get_jira_user(email, token)
        my_account_id = user_info.get('accountId')
        my_email = user_info.get('email')

        target_is_me = (not target_email) or (target_email == my_email)
        target_user_email = target_email or my_email
        
        today_dt = datetime.now()
        today_date = today_dt.date()
        end_date = None

        # Range logic
        if view_mode == "specific_day" and selected_date:
            start_date = selected_date
            end_date = selected_date
            jql_date = selected_date.strftime('%Y-%m-%d')
            jql = f"worklogDate = '{jql_date}'"
        elif view_mode == "yesterday":
            start_date = today_date - timedelta(days=1)
            end_date = start_date
            jql_date = start_date.strftime('%Y-%m-%d')
            jql = f"worklogDate = '{jql_date}'"
        elif view_mode == "today":
            start_date = today_date
            end_date = today_date
            jql_date = today_date.strftime('%Y-%m-%d')
            jql = f"worklogDate = '{jql_date}'"
        else:
            start_date = today_date - timedelta(days=today_date.weekday())
            jql_date = start_date.strftime('%Y-%m-%d')
            jql = f"worklogDate >= '{jql_date}'"

        # Author logic
        if target_is_me and my_account_id:
            jql += " AND worklogAuthor = currentUser()"
        else:
            jql += f" AND worklogAuthor = '{target_user_email}'"

        # Fetch issues
        resp = requests.post(f"https://{DOMAIN}/rest/api/3/search/jql", 
                             headers=headers, auth=auth, json={"jql": jql, "fields": ["summary"], "maxResults": 100})
        issues = resp.json().get('issues', [])
        
        total_seconds = 0
        ticket_details = []

        # Use ThreadPoolExecutor for concurrent requests
        with requests.Session() as session:
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                future_to_issue = {
                    executor.submit(
                        fetch_issue_worklog, 
                        session, 
                        issue['key'], 
                        headers, 
                        auth, 
                        start_date, 
                        end_date, 
                        target_is_me, 
                        my_account_id, 
                        target_user_email
                    ): issue for issue in issues
                }
                
                for future in concurrent.futures.as_completed(future_to_issue):
                    issue = future_to_issue[future]
                    try:
                        issue_seconds, worklog_entries = future.result()
                        if issue_seconds > 0:
                            total_seconds += issue_seconds
                            ticket_details.append({
                                "key": issue['key'], 
                                "summary": issue['fields']['summary'], 
                                "time": issue_seconds / 3600,
                                "worklogs": worklog_entries
                            })
                    except Exception as e:
                        print(f"Error processing issue {issue['key']}: {e}")

        display_name = target_user_email if not target_is_me else "ME"
        return total_seconds, ticket_details, display_name, None
    
    except Exception as e:
        return 0, [], "", str(e)

def main():
    if 'config' not in st.session_state:
        st.session_state.config = load_config()
        if "teammates" not in st.session_state.config:
            st.session_state.config["teammates"] = []
    
    if 'selected_user_email' not in st.session_state:
        st.session_state.selected_user_email = ""
    
    if 'view_mode' not in st.session_state:
        st.session_state.view_mode = "today"
    
    if 'selected_date' not in st.session_state:
        st.session_state.selected_date = None
    
    if 'last_refresh' not in st.session_state:
        st.session_state.last_refresh = 0
    
    if 'refresh_enabled' not in st.session_state:
        st.session_state.refresh_enabled = False
    
    if 'refresh_interval' not in st.session_state:
        st.session_state.refresh_interval = 120
    
    if 'loading' not in st.session_state:
        st.session_state.loading = False
    
    if 'loading_message' not in st.session_state:
        st.session_state.loading_message = random.choice(LOADING_MESSAGES)
    
    # Cache for worklog data: {user_email: {view_mode: {date_key: (total_seconds, ticket_details, display_name, timestamp)}}}
    if 'worklog_cache' not in st.session_state:
        # Load cache from disk if available
        cached_worklog, cached_time = load_cache()
        st.session_state.worklog_cache = cached_worklog
        st.session_state.last_cache_time = cached_time
    
    if 'cache_loading_status' not in st.session_state:
        st.session_state.cache_loading_status = {
            'loaded': 0, 
            'total': 0, 
            'is_loading': False,
            'current_user': '',
            'current_view': ''
        }
    
    if 'last_cache_time' not in st.session_state:
        # This should already be set above, but keep for safety
        _, cached_time = load_cache()
        st.session_state.last_cache_time = cached_time
    
    if 'views_to_cache' not in st.session_state:
        # Fetch week first, then derive today/yesterday from it
        st.session_state.views_to_cache = ['week']
    
    if 'cache_completion_times' not in st.session_state:
        # Track when each user's cache was completed (for hiding checkmark after delay)
        st.session_state.cache_completion_times = {}
    
    with st.sidebar:
        st.title("⚙️ Settings")
        
        st.subheader("Auto Refresh")
        refresh_enabled = st.checkbox(
            "Enable Auto-Refresh", 
            value=st.session_state.refresh_enabled,
            key="refresh_enabled_cb"
        )
        if refresh_enabled != st.session_state.refresh_enabled:
            st.session_state.refresh_enabled = refresh_enabled
        
        refresh_interval = st.selectbox(
            "Refresh Interval",
            options=[30, 60, 120, 300, 600],
            format_func=lambda x: f"{x//60} minute{'s' if x//60 != 1 else ''}" if x >= 60 else f"{x} seconds",
            index=[30, 60, 120, 300, 600].index(st.session_state.refresh_interval),
            key="refresh_interval_sb"
        )
        if refresh_interval != st.session_state.refresh_interval:
            st.session_state.refresh_interval = refresh_interval
        
        st.divider()
        
        st.subheader("Jira Credentials")
        email = st.text_input(
            "Your Jira Email",
            value=st.session_state.config.get("email", ""),
            placeholder="name@teltonika.lt"
        )
        
        token = st.text_input(
            "API Token",
            value=st.session_state.config.get("token", ""),
            type="password",
            placeholder="Atlassian API Token"
        )
        
        if st.button("💾 Save Credentials", use_container_width=True):
            st.session_state.config["email"] = email.strip()
            st.session_state.config["token"] = token.strip()
            save_config(st.session_state.config)
            st.success("Credentials saved!")
            st.rerun()
        
        st.divider()
        
        st.subheader("Team Management")
        
        with st.form("add_teammate", clear_on_submit=True):
            new_teammate_email = st.text_input(
                "Teammate Email",
                placeholder="teammate@teltonika.lt"
            )
            new_teammate_initials = st.text_input(
                "Initials (2-3 chars)",
                max_chars=3,
                placeholder="JD"
            )
            
            if st.form_submit_button("➕ Add Teammate", use_container_width=True):
                if new_teammate_email and "@" in new_teammate_email and new_teammate_initials:
                    if not any(t['email'] == new_teammate_email for t in st.session_state.config["teammates"]):
                        st.session_state.config["teammates"].append({
                            "email": new_teammate_email.strip(),
                            "initials": new_teammate_initials.strip().upper()
                        })
                        save_config(st.session_state.config)
                        st.success(f"Added {new_teammate_initials.upper()}")
                        st.rerun()
                    else:
                        st.warning("Teammate already exists!")
                else:
                    st.error("Please fill in both fields!")
        
        if st.session_state.config["teammates"]:
            st.write("**Current Team:**")
            for idx, tm in enumerate(st.session_state.config["teammates"]):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.text(f"{tm['initials']} - {tm['email']}")
                with col2:
                    if st.button("🗑️", key=f"del_{idx}"):
                        st.session_state.config["teammates"].pop(idx)
                        save_config(st.session_state.config)
                        st.rerun()

    st.markdown('<h1 class="main-header">⏱️ Jira Time Tracker</h1>', unsafe_allow_html=True)
    
    if not st.session_state.config.get("email") or not st.session_state.config.get("token"):
        st.warning("⚠️ Please configure your Jira credentials in the sidebar to get started.")
        st.stop()
    
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        view_mode = st.radio(
            "View Mode",
            options=["today", "yesterday", "week", "specific_day"],
            format_func=lambda x: {"today": "Today", "yesterday": "Yesterday", "week": "Week", "specific_day": "Specific Day"}[x],
            horizontal=True,
            label_visibility="collapsed",
            key="view_mode_radio",
            index=["today", "yesterday", "week", "specific_day"].index(st.session_state.view_mode) if st.session_state.view_mode in ["today", "yesterday", "week", "specific_day"] else 0
        )
        if view_mode != st.session_state.view_mode:
            st.session_state.view_mode = view_mode
            st.rerun()
    
    with col2:
        if st.session_state.view_mode == "specific_day":
            today = datetime.now().date()
            date_options = [(today - timedelta(days=i)) for i in range(14)]
            
            selected_date = st.selectbox(
                "Select Date",
                options=date_options,
                format_func=lambda d: d.strftime("%A, %b %d"),
                label_visibility="collapsed",
                key="date_selector",
                index=0 if not st.session_state.selected_date else (date_options.index(st.session_state.selected_date) if st.session_state.selected_date in date_options else 0)
            )
            
            if selected_date != st.session_state.selected_date:
                st.session_state.selected_date = selected_date
                st.rerun()
    
    with col3:
        if st.button("🔄 Refresh", use_container_width=True, key="refresh_btn"):
            clear_all_cache()
            st.rerun()
    
    # Define cache duration for checking cache validity
    cache_duration = st.session_state.refresh_interval
    current_time = time.time()
    
    if st.session_state.config["teammates"]:
        st.subheader("👥 Team View")
        cols = st.columns(min(len(st.session_state.config["teammates"]) + 1, 8))
        
        with cols[0]:
            is_me_selected = st.session_state.selected_user_email == ""
            me_loading = (st.session_state.cache_loading_status['is_loading'] and 
                         st.session_state.cache_loading_status['current_user'] == '')
            
            # Check if ME has all views cached
            me_email = st.session_state.config.get("email", "")
            me_all_cached = all(
                get_cached_data(me_email, view, get_date_for_view(view), cache_duration) is not None
                for view in st.session_state.views_to_cache
            ) if me_email else False
            
            # Track completion time for ME
            if me_all_cached and 'ME' not in st.session_state.cache_completion_times:
                st.session_state.cache_completion_times['ME'] = time.time()
            
            # Check if checkmark should still be visible for ME
            show_me_checkmark = False
            if me_all_cached and 'ME' in st.session_state.cache_completion_times:
                time_since_completion = time.time() - st.session_state.cache_completion_times['ME']
                show_me_checkmark = time_since_completion < 3.0
            
            me_button_text = "ME"
            if me_loading:
                me_button_text += " ⏳"
            elif show_me_checkmark:
                me_button_text += " ✓"
            
            if st.button(
                me_button_text,
                key="me_btn",
                use_container_width=True,
                type="primary" if is_me_selected else "secondary",
                disabled=False 
            ):
                st.session_state.selected_user_email = ""
                st.rerun()
        
        for idx, tm in enumerate(st.session_state.config["teammates"]):
            with cols[idx + 1]:
                is_selected = st.session_state.selected_user_email == tm["email"]
                tm_loading = (st.session_state.cache_loading_status['is_loading'] and 
                             st.session_state.cache_loading_status['current_user'] == tm['email'])
                
                # Check if teammate has all views cached
                all_cached = all(
                    get_cached_data(tm['email'], view, get_date_for_view(view), cache_duration) is not None
                    for view in st.session_state.views_to_cache
                )
                
                # Track completion time and show checkmark only for 3 seconds
                if all_cached and tm['email'] not in st.session_state.cache_completion_times:
                    st.session_state.cache_completion_times[tm['email']] = time.time()
                
                # Check if checkmark should still be visible (within 3 seconds of completion)
                show_checkmark = False
                if all_cached and tm['email'] in st.session_state.cache_completion_times:
                    time_since_completion = time.time() - st.session_state.cache_completion_times[tm['email']]
                    show_checkmark = time_since_completion < 3.0
                
                button_text = tm["initials"]
                if tm_loading:
                    button_text += " ⏳"
                elif show_checkmark:
                    button_text += " ✓"
                
                if st.button(
                    button_text,
                    key=f"tm_{idx}",
                    use_container_width=True,
                    type="primary" if is_selected else "secondary",
                    disabled=False 
                ):
                    st.session_state.selected_user_email = tm["email"]
                    st.rerun()
    
    st.divider()
    
    should_refresh = (current_time - st.session_state.last_cache_time) > cache_duration
    
    # Clear cache if refresh interval passed
    if should_refresh:
        clear_all_cache()
        st.session_state.last_cache_time = current_time
        st.session_state.cache_loading_status = {'loaded': 0, 'total': 0, 'is_loading': False}
        # Persist the new cache time to disk
        save_cache(st.session_state.worklog_cache, st.session_state.last_cache_time)
    
    # Try to get cached data first
    target_user = st.session_state.selected_user_email or st.session_state.config["email"]
    cached_result = get_cached_data(target_user, st.session_state.view_mode, st.session_state.selected_date, cache_duration)
    
    if cached_result:
        total_seconds, ticket_details, display_name = cached_result
        error = None
    else:
        # Fetch fresh data
        st.session_state.loading_message = random.choice(LOADING_MESSAGES)
        with st.spinner(st.session_state.loading_message):
            total_seconds, ticket_details, display_name, error = fetch_jira_data(
                st.session_state.config["email"],
                st.session_state.config["token"],
                st.session_state.selected_user_email,
                st.session_state.view_mode,
                st.session_state.selected_date
            )
        
        if not error:
            # Cache the result
            set_cached_data(target_user, st.session_state.view_mode, st.session_state.selected_date, 
                          total_seconds, ticket_details, display_name)
    
    if error:
        st.error(f"❌ Error fetching data: {error}")
        st.stop()
    
    hours = total_seconds / 3600
    st.markdown(f'<h1 class="main-header">{hours:.2f}h</h1>', unsafe_allow_html=True)
    
    target = 8 if st.session_state.view_mode in ["today", "specific_day"] else 40
    progress_value = min(hours / target, 1.0)
    st.progress(progress_value)
    
    status_text = f"VIEWING: {display_name.split('@')[0].upper()} ({st.session_state.view_mode.upper()})"
    st.markdown(f'<p class="status-text">{status_text}</p>', unsafe_allow_html=True)
    
    st.divider()
    
    if not ticket_details:
        st.info("📭 No logs found for this filter.")
    else:
        st.subheader(f"📊 Logged Tickets ({len(ticket_details)})")
        
        ticket_details.sort(key=lambda x: x['time'], reverse=True)
        
        for ticket in ticket_details:
            with st.container():
                col1, col2, col3 = st.columns([1.5, 5, 1.2])
                
                with col1:
                    st.link_button(
                        ticket['key'], 
                        f"https://{DOMAIN}/browse/{ticket['key']}",
                        use_container_width=True
                    )
                
                with col2:
                    st.write(f"**{ticket['summary'][:50]}{'...' if len(ticket['summary']) > 50 else ''}**")
                    # Show worklog descriptions if any
                    if ticket.get('worklogs'):
                        for wl in ticket['worklogs']:
                            # Handle both old format (string) and new format (dict)
                            wl_text = wl.get('comment', '') if isinstance(wl, dict) else wl
                            if wl_text:
                                st.caption(f"💬 {wl_text[:100]}{'...' if len(wl_text) > 100 else ''}")
                
                with col3:
                    st.write(f"**{ticket['time']:.2f}h**")
                
                st.divider()
    
    # Show cache/refresh status
    status_parts = []
    
    if st.session_state.cache_loading_status['is_loading']:
        loaded = st.session_state.cache_loading_status['loaded']
        total = st.session_state.cache_loading_status['total']
        current_user = st.session_state.cache_loading_status.get('current_user', '')
        current_view = st.session_state.cache_loading_status.get('current_view', '')
        
        if current_user and current_view:
            tm_name = next((t['initials'] for t in st.session_state.config["teammates"] if t['email'] == current_user), 'User')
            status_parts.append(f"📥 Caching {tm_name} ({current_view}): {loaded}/{total}")
        else:
            status_parts.append(f"📥 Caching teammates: {loaded}/{total}")
    
    if st.session_state.refresh_enabled:
        time_until_refresh = int(st.session_state.refresh_interval - (current_time - st.session_state.last_cache_time))
        if time_until_refresh > 0:
            status_parts.append(f"🔄 Cache refresh in {time_until_refresh}s")
    
    if status_parts:
        st.caption(" | ".join(status_parts))
    
    # Background loading for teammates - load all view modes for each teammate (non-blocking)
    if st.session_state.config["teammates"] or st.session_state.config.get("email"):
        # Build list of all cache tasks needed
        cache_tasks = []  # [(email, view_mode, date)]
        
        # Add ME user to cache tasks
        if st.session_state.config.get("email"):
            me_email = st.session_state.config["email"]
            for view_mode in st.session_state.views_to_cache:
                view_date = get_date_for_view(view_mode)
                cache_result = get_cached_data(me_email, view_mode, view_date, cache_duration)
                if cache_result is None:
                    cache_tasks.append((me_email, view_mode, view_date))
        
        # Add teammates to cache tasks
        for tm in st.session_state.config["teammates"]:
            for view_mode in st.session_state.views_to_cache:
                view_date = get_date_for_view(view_mode)
                cache_result = get_cached_data(tm['email'], view_mode, view_date, cache_duration)
                # Only add to tasks if cache is completely missing (None returned)
                if cache_result is None:
                    cache_tasks.append((tm['email'], view_mode, view_date))
        
        if cache_tasks:
            total_tasks = len(cache_tasks)
            # Total is ME + all teammates
            total_possible = 1 + len(st.session_state.config["teammates"])
            completed_tasks = total_possible - total_tasks
            
            # Get next task
            email, view_mode, view_date = cache_tasks[0]
            
            st.session_state.cache_loading_status = {
                'loaded': completed_tasks,
                'total': 1 + len(st.session_state.config["teammates"]),
                'is_loading': True,
                'current_user': email,
                'current_view': view_mode
            }
            
            # Find user display name
            is_me = (email == st.session_state.config.get("email"))
            user_display = "ME" if is_me else next((t['initials'] for t in st.session_state.config["teammates"] if t['email'] == email), email)
            
            # Fetch in background - if it's 'week', also derive today and yesterday
            tm_total, tm_tickets, tm_display, tm_error = fetch_jira_data(
                st.session_state.config["email"],
                st.session_state.config["token"],
                "" if is_me else email,  # Pass empty string for ME
                view_mode,
                view_date
            )
            
            # Always cache the result (even if error) to prevent infinite loops
            set_cached_data(email, view_mode, view_date, tm_total, tm_tickets, tm_display)
            
            # If we just fetched 'week', derive 'today' and 'yesterday' from the same data
            if view_mode == 'week' and not tm_error and tm_tickets:
                today = datetime.now().date()
                yesterday = today - timedelta(days=1)
                
                # Filter week tickets for today
                today_total, today_tickets = filter_tickets_for_date(tm_tickets, today)
                set_cached_data(email, 'today', None, today_total, today_tickets, tm_display)
                
                # Filter week tickets for yesterday
                yesterday_total, yesterday_tickets = filter_tickets_for_date(tm_tickets, yesterday)
                set_cached_data(email, 'yesterday', yesterday, yesterday_total, yesterday_tickets, tm_display)
            
            # Double-check that cache was written successfully before continuing
            verify_cache = get_cached_data(email, view_mode, view_date, cache_duration)
            if verify_cache is None:
                # Cache write failed somehow, force it with a longer expiry
                st.session_state.worklog_cache.setdefault(email, {}).setdefault(view_mode, {})[get_cache_key(view_mode, view_date)] = (
                    tm_total, tm_tickets, tm_display or email, time.time()
                )
                # Persist the forced cache to disk
                save_cache(st.session_state.worklog_cache, st.session_state.last_cache_time)
            
            # Trigger rerun to load next task
            time.sleep(0.05)
            st.rerun()
        else:
            # All done
            st.session_state.cache_loading_status = {
                'loaded': 1 + len(st.session_state.config["teammates"]),
                'total': 1 + len(st.session_state.config["teammates"]),
                'is_loading': False,
                'current_user': '',
                'current_view': ''
            }
            # Final save of all cached data
            save_cache(st.session_state.worklog_cache, st.session_state.last_cache_time)

if __name__ == "__main__":
    main()
