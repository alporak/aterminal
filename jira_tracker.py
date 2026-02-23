import customtkinter as ctk
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, timedelta
import json
import os
import threading
import webbrowser

DOMAIN = "teltonika-telematics.atlassian.net"
CONFIG_FILE = "jira_config.json"

class JiraTimeTracker(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Jira Time Tracker Utility")
        self.geometry("520x800")
        self.resizable(False, False)
        ctk.set_appearance_mode("Dark")
        
        self.config = self.load_config()
        if "teammates" not in self.config:
            self.config["teammates"] = []
        if "auto_refresh_enabled" not in self.config:
            self.config["auto_refresh_enabled"] = False
        if "auto_refresh_interval" not in self.config:
            self.config["auto_refresh_interval"] = 120
            
        self.current_view = "today"
        self.selected_user_email = ""
        self.selected_date = None
        self.loading_animation_active = False
        self.loading_animation_state = 0
        self.auto_refresh_job = None

        self.tab_view = ctk.CTkTabview(self)
        self.tab_view.pack(padx=10, pady=10, fill="both", expand=True)

        self.tab_dashboard = self.tab_view.add("Dashboard")
        self.tab_settings = self.tab_view.add("Settings")

        self.setup_dashboard()
        self.setup_settings()

        if self.config.get("email") and self.config.get("token"):
            self.refresh_data()
        else:
            self.tab_view.set("Settings")

    def setup_dashboard(self):
        self.header_frame = ctk.CTkFrame(self.tab_dashboard, fg_color="transparent")
        self.header_frame.pack(pady=10, padx=15, fill="x")

        self.view_toggle = ctk.CTkSegmentedButton(self.header_frame, values=["today", "week", "specific_day"], 
                                                 command=self.set_view)
        self.view_toggle.set("today")
        self.view_toggle.pack(side="left")
        
        self.date_picker_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        
        from datetime import date
        today = date.today()
        self.date_options = [(today - timedelta(days=i)) for i in range(14)]
        date_strings = [d.strftime("%A, %b %d") for d in self.date_options]
        
        self.date_dropdown = ctk.CTkOptionMenu(self.date_picker_frame, values=date_strings,
                                               command=self.on_date_selected, width=200)
        self.date_dropdown.set(date_strings[0])
        self.date_dropdown.pack(side="left", padx=5)

        self.teammates_scroll = ctk.CTkScrollableFrame(self.tab_dashboard, height=50, orientation="horizontal", 
                                                      fg_color="transparent", label_text="Team View")
        self.teammates_scroll.pack(fill="x", padx=15, pady=5)
        self.render_teammates() 

        self.lbl_hours = ctk.CTkLabel(self.tab_dashboard, text="0.00h", font=("Roboto", 60, "bold"), text_color="#3B8ED0")
        self.lbl_hours.pack(pady=15)

        self.progress = ctk.CTkProgressBar(self.tab_dashboard, width=380, height=12)
        self.progress.set(0)
        self.progress.pack(pady=5)

        self.lbl_status = ctk.CTkLabel(self.tab_dashboard, text="Status: IDLE", font=("Roboto", 12, "bold"), text_color="gray")
        self.lbl_status.pack(pady=5)

        self.scroll_frame = ctk.CTkScrollableFrame(self.tab_dashboard, width=460, height=350, fg_color="#1a1a1a")
        self.scroll_frame.pack(padx=10, pady=10, fill="both", expand=True)

        self.btn_refresh = ctk.CTkButton(self.tab_dashboard, text="Refresh Data", command=self.refresh_data, 
                                         height=45, font=("Roboto", 15, "bold"))
        self.btn_refresh.pack(pady=15, padx=30, fill="x")

        self.loading_overlay = ctk.CTkFrame(self, fg_color=("#1a1a1a", "#1a1a1a"))
        
        overlay_content = ctk.CTkFrame(self.loading_overlay, fg_color="#2b2b2b", corner_radius=20, border_width=2, border_color="#3B8ED0")
        overlay_content.place(relx=0.5, rely=0.5, anchor="center")
        
        self.loading_spinner = ctk.CTkProgressBar(overlay_content, width=300, height=10, mode="indeterminate", progress_color="#3B8ED0")
        self.loading_spinner.pack(padx=40, pady=(40, 20))
        
        self.loading_label = ctk.CTkLabel(overlay_content, text="", font=("Roboto", 20, "bold"), text_color="#3B8ED0")
        self.loading_label.pack(padx=40, pady=(10, 40))

    def setup_settings(self):
        ctk.CTkLabel(self.tab_settings, text="Your Jira Email").pack(pady=(20, 5), padx=25, anchor="w")
        self.entry_email = ctk.CTkEntry(self.tab_settings, placeholder_text="name@teltonika.lt")
        self.entry_email.pack(pady=5, padx=25, fill="x")
        self.entry_email.insert(0, self.config.get("email", ""))

        ctk.CTkLabel(self.tab_settings, text="API Token").pack(pady=(15, 5), padx=25, anchor="w")
        self.entry_token = ctk.CTkEntry(self.tab_settings, placeholder_text="Atlassian API Token", show="*")
        self.entry_token.pack(pady=5, padx=25, fill="x")
        self.entry_token.insert(0, self.config.get("token", ""))

        self.btn_save = ctk.CTkButton(self.tab_settings, text="Save & Connect", fg_color="#27ae60", command=self.save_config)
        self.btn_save.pack(pady=30, padx=25, fill="x")

        ctk.CTkLabel(self.tab_settings, text="Auto Refresh").pack(pady=(20, 5), padx=25, anchor="w")
        
        self.auto_refresh_enabled = ctk.CTkCheckBox(self.tab_settings, text="Enable Auto-Refresh",
                                                    command=self.toggle_auto_refresh)
        self.auto_refresh_enabled.pack(pady=5, padx=25, anchor="w")
        
        if self.config.get("auto_refresh_enabled", False):
            self.auto_refresh_enabled.select()
        
        refresh_frame = ctk.CTkFrame(self.tab_settings, fg_color="transparent")
        refresh_frame.pack(fill="x", padx=25, pady=5)
        
        ctk.CTkLabel(refresh_frame, text="Interval:").pack(side="left", padx=(0, 5))
        
        self.refresh_interval_dropdown = ctk.CTkOptionMenu(refresh_frame, 
                                                           values=["30 seconds", "1 minute", "2 minutes", "5 minutes", "10 minutes"],
                                                           command=self.on_interval_changed)
        interval_map = {30: "30 seconds", 60: "1 minute", 120: "2 minutes", 300: "5 minutes", 600: "10 minutes"}
        current_interval = self.config.get("auto_refresh_interval", 120)
        self.refresh_interval_dropdown.set(interval_map.get(current_interval, "2 minutes"))
        self.refresh_interval_dropdown.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(self.tab_settings, text="Manage Team").pack(pady=(20, 5), padx=25, anchor="w")
        self.team_mgmt_frame = ctk.CTkFrame(self.tab_settings, fg_color="transparent")
        self.team_mgmt_frame.pack(fill="x", padx=25)
        
        self.setting_teammate_entry = ctk.CTkEntry(self.team_mgmt_frame, placeholder_text="teammate@teltonika.lt")
        self.setting_teammate_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        self.btn_add_teammate = ctk.CTkButton(self.team_mgmt_frame, text="+ Add", width=60, 
                                             fg_color="#3B8ED0", command=self.add_teammate)
        self.btn_add_teammate.pack(side="right")
        
        self.teammates_list_frame = ctk.CTkScrollableFrame(self.tab_settings, height=150, fg_color="#2b2b2b")
        self.teammates_list_frame.pack(fill="x", padx=25, pady=(10, 20))
        self.render_teammates_settings()

    def add_teammate(self):
        email = self.setting_teammate_entry.get().strip()
        if not email or "@" not in email: return
        
        parts = email.split('@')[0].split('.')
        if len(parts) >= 2:
            initials = f"{parts[0][0]}{parts[1][0]}".upper()
        else:
            initials = email[:2].upper()
            
        dialog = ctk.CTkInputDialog(text="Enter Initials (2-3 chars):", title="Save User")
        val = dialog.get_input()
        if val: initials = val.upper()[:3]
        
        if not any(t['email'] == email for t in self.config["teammates"]):
            self.config["teammates"].append({"email": email, "initials": initials})
            self._save_to_disk()
            self.render_teammates()
            self.render_teammates_settings()
            self.setting_teammate_entry.delete(0, 'end')

    def remove_teammate(self, email):
        self.config["teammates"] = [t for t in self.config["teammates"] if t['email'] != email]
        self._save_to_disk()
        self.render_teammates()
        self.render_teammates_settings()

    def select_teammate(self, email):
        self.selected_user_email = email
        self.refresh_data()

    def render_teammates(self):
        for w in self.teammates_scroll.winfo_children(): w.destroy()
        
        if not self.config["teammates"]:
            ctk.CTkLabel(self.teammates_scroll, text="You can add teammates in Settings to track their times", 
                        text_color="gray", font=("Roboto", 12)).pack(padx=10, pady=5)
            return

        for tm in self.config["teammates"]:
            is_selected = (self.selected_user_email == tm["email"])
            fg = "#3B8ED0" if is_selected else "#555"
            
            btn = ctk.CTkButton(self.teammates_scroll, text=tm["initials"], width=40, height=40,
                                corner_radius=20, fg_color=fg,
                                command=lambda e=tm["email"]: self.select_teammate(e))
            btn.pack(side="left", padx=5)

    def render_teammates_settings(self):
        for w in self.teammates_list_frame.winfo_children(): w.destroy()
        
        if not self.config["teammates"]:
            ctk.CTkLabel(self.teammates_list_frame, text="No teammates added yet", 
                        text_color="gray").pack(pady=20)
            return
        
        for tm in self.config["teammates"]:
            row = ctk.CTkFrame(self.teammates_list_frame, fg_color="#1a1a1a")
            row.pack(fill="x", pady=3, padx=5)
            
            ctk.CTkLabel(row, text=tm["initials"], width=40, font=("Roboto", 14, "bold"), 
                        text_color="#3B8ED0").pack(side="left", padx=10, pady=8)
            
            ctk.CTkLabel(row, text=tm["email"], font=("Roboto", 12)).pack(side="left", padx=5)
            
            ctk.CTkButton(row, text="✕", width=30, height=30, fg_color="#e74c3c",
                         command=lambda e=tm["email"]: self.remove_teammate(e)).pack(side="right", padx=10)

    def _save_to_disk(self):
        with open(CONFIG_FILE, "w") as f: json.dump(self.config, f)

    def set_view(self, value):
        self.current_view = value
        
        if value == "specific_day":
            self.date_picker_frame.pack(side="left", padx=(10, 0))
            if not self.selected_date:
                from datetime import date
                self.selected_date = date.today()
                self.date_dropdown.set(self.selected_date.strftime("%A, %b %d"))
        else:
            self.date_picker_frame.pack_forget()
            self.selected_date = None
            self.refresh_data()
    
    def on_date_selected(self, date_string):
        for d in self.date_options:
            if d.strftime("%A, %b %d") == date_string:
                self.selected_date = d
                break
        if self.current_view == "specific_day":
            self.refresh_data()
    
    def toggle_auto_refresh(self):
        self.config["auto_refresh_enabled"] = self.auto_refresh_enabled.get() == 1
        self._save_to_disk()
        
        if self.config["auto_refresh_enabled"]:
            self.schedule_auto_refresh()
        else:
            if self.auto_refresh_job:
                self.after_cancel(self.auto_refresh_job)
                self.auto_refresh_job = None
    
    def on_interval_changed(self, interval_string):
        interval_map = {"30 seconds": 30, "1 minute": 60, "2 minutes": 120, "5 minutes": 300, "10 minutes": 600}
        self.config["auto_refresh_interval"] = interval_map.get(interval_string, 120)
        self._save_to_disk()
        
        if self.config.get("auto_refresh_enabled", False):
            if self.auto_refresh_job:
                self.after_cancel(self.auto_refresh_job)
            self.schedule_auto_refresh()
    
    def schedule_auto_refresh(self):
        if self.config.get("auto_refresh_enabled", False):
            interval_ms = self.config.get("auto_refresh_interval", 120) * 1000
            self.auto_refresh_job = self.after(interval_ms, self.auto_refresh_callback)
    
    def auto_refresh_callback(self):
        self.refresh_data()
        self.schedule_auto_refresh()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f: return json.load(f)
            except: return {}
        return {}

    def save_config(self):
        self.config["email"] = self.entry_email.get().strip()
        self.config["token"] = self.entry_token.get().strip()
        with open(CONFIG_FILE, "w") as f: json.dump(self.config, f)
        self.tab_view.set("Dashboard")
        
        if self.config.get("auto_refresh_enabled", False):
            self.schedule_auto_refresh()
        
        self.refresh_data()

    def refresh_data(self):
        self._start_loading()
        
        cfg = {
            "email": self.config.get("email"),
            "token": self.config.get("token")
        }
        target_input = self.selected_user_email
        view_mode = self.current_view
        
        threading.Thread(target=self._fetch_jira_data, args=(cfg, target_input, view_mode), daemon=True).start()

    def _start_loading(self):
        self.loading_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.loading_spinner.start()
        self.loading_animation_active = True
        self.loading_animation_state = 0
        self._animate_loading_text()
        self.update_idletasks()

    def _animate_loading_text(self):
        if not self.loading_animation_active:
            return
        
        animations = [
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
        
        self.loading_label.configure(text=animations[self.loading_animation_state])
        self.loading_animation_state = (self.loading_animation_state + 1) % len(animations)
        
        if self.loading_animation_active:
            self.after(800, self._animate_loading_text)

    def _fetch_jira_data(self, cfg, target_input, view_mode):
        if not cfg["email"] or not cfg["token"]: 
            self.after(0, self._stop_loading)
            return

        self.after(0, lambda: self.btn_refresh.configure(state="disabled", text="Connecting..."))
        
        try:
            auth = HTTPBasicAuth(cfg["email"], cfg["token"])
            headers = {"Accept": "application/json", "Content-Type": "application/json"}
            
            my_account_id = None
            try:
                myself = requests.get(f"https://{DOMAIN}/rest/api/3/myself", headers=headers, auth=auth).json()
                my_account_id = myself.get('accountId')
                my_email = myself.get('emailAddress', '').lower()
            except:
                my_email = cfg["email"].lower()

            target_is_me = (not target_input) or (target_input == my_email)
            target_user_email = target_input or my_email
            
            today_dt = datetime.now()
            today_date = today_dt.date()

            if view_mode == "specific_day" and self.selected_date:
                start_date = self.selected_date
                jql_date = self.selected_date.strftime('%Y-%m-%d')
                jql = f"worklogDate = '{jql_date}'"
            elif view_mode == "today":
                start_date = today_date
                jql_date = today_date.strftime('%Y-%m-%d')
                jql = f"worklogDate = '{jql_date}'"
            else:
                start_date = today_date - timedelta(days=today_date.weekday())
                jql_date = start_date.strftime('%Y-%m-%d')
                jql = f"worklogDate >= '{jql_date}'"

            if target_is_me and my_account_id:
                jql += " AND worklogAuthor = currentUser()"
            else:
                jql += f" AND worklogAuthor = '{target_user_email}'"

            resp = requests.post(f"https://{DOMAIN}/rest/api/3/search/jql", 
                                 headers=headers, auth=auth, json={"jql": jql, "fields": ["summary", "worklog"], "maxResults": 100})
            issues = resp.json().get('issues', [])
            
            total_seconds = 0
            ticket_details = []

            for issue in issues:
                key = issue['key']
                
                wl_data = issue['fields'].get('worklog', {})
                worklogs = wl_data.get('worklogs', [])
                if wl_data.get('total', 0) > len(worklogs):
                    wl_url = f"https://{DOMAIN}/rest/api/3/issue/{key}/worklog"
                    wl_resp = requests.get(wl_url, headers=headers, auth=auth)
                    if wl_resp.status_code == 200:
                        worklogs = wl_resp.json().get('worklogs', [])

                issue_seconds = 0
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
                            log_dt = datetime.strptime(started_str, "%Y-%m-%dT%H:%M:%S.%f%z")
                            local_dt = log_dt.astimezone()
                            log_date_obj = local_dt.date()
                        except ValueError:
                            log_date_obj = datetime.strptime(entry['started'][:10], "%Y-%m-%d").date()

                        if log_date_obj >= start_date:
                            issue_seconds += entry['timeSpentSeconds']
                
                if issue_seconds > 0:
                    total_seconds += issue_seconds
                    ticket_details.append({"key": key, "summary": issue['fields']['summary'], "time": issue_seconds / 3600})

            display_name = target_user_email if not target_is_me else "ME"
            self.after(0, lambda: self.update_ui(total_seconds, ticket_details, display_name))
        except Exception as e:
            print(f"Sync Error: {e}")
            self.after(0, lambda: self.btn_refresh.configure(state="normal", text="Sync Error"))
            self.after(0, self._stop_loading)

    def _stop_loading(self):
        self.loading_animation_active = False
        self.loading_spinner.stop()
        self.loading_overlay.place_forget()

    def update_ui(self, total_seconds, ticket_details, target_user):
        self._stop_loading()
        for w in self.scroll_frame.winfo_children(): w.destroy()
        
        hours = total_seconds / 3600
        self.lbl_hours.configure(text=f"{hours:.2f}h")
        target = 8 if self.current_view in ["today", "specific_day"] else 40
        self.progress.set(min(hours / target, 1.0))
        self.lbl_status.configure(text=f"VIEWING: {target_user.split('@')[0].upper()} ({self.current_view.upper()})")

        if not ticket_details:
            ctk.CTkLabel(self.scroll_frame, text="No logs found for this filter.", text_color="gray").pack(pady=30)
        else:
            for t in sorted(ticket_details, key=lambda x: x['time'], reverse=True):
                frame = ctk.CTkFrame(self.scroll_frame, fg_color="#2b2b2b")
                frame.pack(fill="x", pady=3, padx=5)
                
                ctk.CTkButton(frame, text=t['key'], width=85, height=26, font=("Roboto", 11, "bold"),
                             command=lambda k=t['key']: webbrowser.open(f"https://{DOMAIN}/browse/{k}")).pack(side="left", padx=8, pady=8)
                
                info = f"{t['time']:.2f}h | {t['summary'][:35]}..."
                ctk.CTkLabel(frame, text=info, font=("Roboto", 11)).pack(side="left", padx=5)

        self.btn_refresh.configure(state="normal", text="Refresh Data")

if __name__ == "__main__":
    app = JiraTimeTracker()
    app.mainloop()