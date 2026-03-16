"""
Jira Tracker plugin – Weekly worklogs, meetings, assigned tickets, teammates.
Includes in-memory cache with configurable TTL.
"""

from __future__ import annotations

import os
import re
import sys
import time as _time
from datetime import datetime, date, timedelta
from typing import Optional, List

import requests as _req
from requests.auth import HTTPBasicAuth
from jira import JIRA, JIRAError
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.plugins.base import ToolkitPlugin
from app import config

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOMAIN = "teltonika-telematics.atlassian.net"
SERVER = f"https://{DOMAIN}"

_jira_client: JIRA | None = None


def _jira() -> JIRA:
    global _jira_client
    if _jira_client is None:
        c = config.load_jira_config()
        _jira_client = JIRA(server=SERVER,
                            basic_auth=(c.get("email", ""), c.get("token", "")))
    return _jira_client


def _reset_jira_client():
    global _jira_client
    _jira_client = None

# ── In-memory cache ─────────────────────────────────────────────
# key → { "data": ..., "ts": epoch }
_wl_cache: dict[str, dict] = {}


def _cache_ttl() -> int:
    """Return cache TTL in seconds from config (default 5 min)."""
    c = config.load_jira_config()
    return int(c.get("cache_ttl_minutes", 5)) * 60


def _cache_key(account_id: str, d_from: str, d_to: str) -> str:
    return f"{account_id}|{d_from}|{d_to}"


def _cache_get(key: str):
    entry = _wl_cache.get(key)
    if not entry:
        return None
    if _time.time() - entry["ts"] > _cache_ttl():
        del _wl_cache[key]
        return None
    return entry


def _cache_put(key: str, data):
    _wl_cache[key] = {"data": data, "ts": _time.time()}


def _cache_clear(account_id: str = None):
    if account_id is None:
        _wl_cache.clear()
        return
    keys_to_del = [k for k in _wl_cache if k.startswith(account_id + "|")]
    for k in keys_to_del:
        del _wl_cache[k]


def _auth():
    c = config.load_jira_config()
    return HTTPBasicAuth(c.get("email", ""), c.get("token", ""))


def _headers():
    return {"Accept": "application/json", "Content-Type": "application/json"}


def _api(method, path, **kw):
    url = f"https://{DOMAIN}/rest/api/3/{path}"
    return getattr(_req, method)(url, headers=_headers(), auth=_auth(), **kw)


# ── Models ──────────────────────────────────────────────────────────

class WorklogReq(BaseModel):
    issue_key: str
    time_spent: str           # e.g. "1h 30m", "45m"
    comment: str = ""
    started: Optional[str] = None   # ISO date YYYY-MM-DD or full datetime


class MeetingReq(BaseModel):
    time_spent: str
    summary: str = ""
    issue_key: str = ""
    started: Optional[str] = None


class JiraConfigReq(BaseModel):
    url: Optional[str] = ""
    email: str
    api_token: str
    meeting_ticket: Optional[str] = ""
    tickets_folder: Optional[str] = None
    teammates: Optional[list] = None   # list of {accountId, displayName}
    cache_ttl_minutes: Optional[int] = None

class TeammatesReq(BaseModel):
    teammates: list



# ── Helpers ─────────────────────────────────────────────────────────

def _parse_time(text: str) -> int | None:
    """Parse human time input to seconds."""
    text = text.strip().lower()
    if not text:
        return None
    m = re.fullmatch(r"(\d+):(\d{1,2})", text)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60
    h = re.search(r"(\d+(?:\.\d+)?)\s*h", text)
    mi = re.search(r"(\d+(?:\.\d+)?)\s*m", text)
    if h or mi:
        hrs = float(h.group(1)) if h else 0
        mins = float(mi.group(1)) if mi else 0
        return int(hrs * 3600 + mins * 60)
    try:
        v = float(text)
        return int(v * 60) if v >= 0 else None
    except ValueError:
        return None


def _to_jira_datetime(date_str: str) -> str:
    """Convert YYYY-MM-DD or full datetime to Jira datetime string."""
    if not date_str:
        return datetime.now().strftime("%Y-%m-%dT%H:%M:%S.000+0000")
    if len(date_str) == 10:
        return f"{date_str}T12:00:00.000+0000"
    return date_str


def _week_range(ref_date: str = "") -> tuple[str, str]:
    """Return (monday, sunday) ISO date strings for the week containing ref_date."""
    if ref_date:
        d = date.fromisoformat(ref_date)
    else:
        d = date.today()
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    return monday.isoformat(), sunday.isoformat()


def _extract_comment(w: dict) -> str:
    c = w.get("comment")
    if not c:
        return ""
    if isinstance(c, str):
        return c
    if isinstance(c, dict):
        parts = []
        for block in c.get("content", []):
            for inline in block.get("content", []):
                if inline.get("type") == "text":
                    parts.append(inline.get("text", ""))
        return " ".join(parts)
    return ""


def _build_comment(text: str) -> dict:
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": text}] if text else [],
            }
        ],
    }


def _fetch_worklogs_for_user(account_id: str, date_from: str, date_to: str,
                              display_name: str = "") -> tuple[list[dict], bool]:
    """Fetch all worklogs for a given user in a date range.
    Returns (worklogs, from_cache)."""
    ck = _cache_key(account_id, date_from, date_to)
    cached = _cache_get(ck)
    if cached is not None:
        return cached["data"], True

    jql = (f"worklogAuthor = '{account_id}' "
           f"AND worklogDate >= '{date_from}' "
           f"AND worklogDate <= '{date_to}' "
           f"ORDER BY updated DESC")
    try:
        raw_issues = _jira().search_issues(jql, maxResults=50, fields="summary")
    except JIRAError as e:
        print(f"[Jira] search failed ({e.status_code}): {e.text[:200]}")
        return [], False

    issues = [{"key": i.key, "fields": {"summary": i.fields.summary}} for i in raw_issues]
    result = []

    for issue in issues:
        key = issue["key"]
        summary = issue["fields"]["summary"]
        wr = _api("get", f"issue/{key}/worklog")
        if not wr.ok:
            continue
        for w in wr.json().get("worklogs", []):
            if w.get("author", {}).get("accountId") != account_id:
                continue
            w_date = w.get("started", "")[:10]
            if w_date < date_from or w_date > date_to:
                continue
            result.append({
                "id": w["id"],
                "ticket_key": key,
                "ticket_summary": summary,
                "date": w_date,
                "started": w.get("started", ""),
                "time_spent": w.get("timeSpent", ""),
                "time_spent_seconds": w.get("timeSpentSeconds", 0),
                "comment": _extract_comment(w),
                "author": display_name or w.get("author", {}).get("displayName", ""),
                "author_id": account_id,
            })

    result.sort(key=lambda x: x.get("started", ""), reverse=True)
    _cache_put(ck, result)
    return result, False


class JiraTrackerPlugin(ToolkitPlugin):
    id = "jira"
    name = "Jira Tracker"
    icon = "⏱️"
    order = 40

    def register_routes(self, app: FastAPI):

        # ── Config ──────────────────────────────────────────────

        @app.get("/api/jira/config")
        async def jira_config():
            c = config.load_jira_config()
            s = config.load()
            return {
                "url": s.get("jira_base_url", f"https://{DOMAIN}"),
                "email": c.get("email", ""),
                "has_token": bool(c.get("token")),
                "api_token": "",
                "meeting_ticket": c.get("meeting_ticket", "FMBP-44552"),
                "tickets_folder": c.get("tickets_folder", ""),
                "teammates": c.get("teammates", []),
                "cache_ttl_minutes": int(c.get("cache_ttl_minutes", 5)),
            }

        @app.put("/api/jira/config")
        async def jira_config_save(req: JiraConfigReq):
            c = config.load_jira_config()
            c["email"] = req.email
            if req.api_token:
                c["token"] = req.api_token
            if req.meeting_ticket is not None:
                c["meeting_ticket"] = req.meeting_ticket
            if req.tickets_folder is not None:
                c["tickets_folder"] = req.tickets_folder
            if req.teammates is not None:
                c["teammates"] = req.teammates
            if req.cache_ttl_minutes is not None:
                c["cache_ttl_minutes"] = req.cache_ttl_minutes
            config.save_jira_config(c)
            if req.url:
                config.save({"jira_base_url": req.url})
            _reset_jira_client()
            return {"ok": True}

        # ── Identity ────────────────────────────────────────────

        @app.get("/api/jira/myself")
        async def jira_myself():
            r = _api("get", "myself")
            if r.ok:
                d = r.json()
                return {
                    "accountId": d.get("accountId"),
                    "displayName": d.get("displayName"),
                    "email": d.get("emailAddress"),
                }
            return {"error": r.status_code}

        # ── User search (for teammate config) ──────────────────

        @app.get("/api/jira/users/search")
        async def jira_user_search(query: str = ""):
            if not query or len(query) < 2:
                return []
            r = _api("get", "user/search", params={"query": query, "maxResults": 10})
            if not r.ok:
                raise HTTPException(r.status_code, r.text)
            return [
                {
                    "accountId": u.get("accountId"),
                    "displayName": u.get("displayName"),
                    "email": u.get("emailAddress", ""),
                    "avatarUrl": u.get("avatarUrls", {}).get("24x24", ""),
                }
                for u in r.json()
                if u.get("accountType") == "atlassian"
            ]

        # ── Teammates (saved list with display names) ──────────

        @app.get("/api/jira/teammates")
        async def jira_teammates():
            c = config.load_jira_config()
            saved = c.get("teammates", [])
            if not saved:
                return []
            return saved

        @app.put("/api/jira/teammates")
        async def jira_teammates_save(req: TeammatesReq):
            c = config.load_jira_config()
            c["teammates"] = req.teammates
            config.save_jira_config(c)
            return {"ok": True}

        # ── Assigned tickets ────────────────────────────────────

        @app.get("/api/jira/assigned")
        async def jira_assigned():
            jql = ("assignee=currentUser() AND statusCategory != Done "
                   "ORDER BY updated DESC")
            try:
                raw = _jira().search_issues(
                    jql, maxResults=50,
                    fields="summary,status,priority,attachment")
            except JIRAError as e:
                raise HTTPException(e.status_code or 500, str(e))
            issues = []
            for i in raw:
                f = i.raw["fields"]
                issues.append({"key": i.key, "fields": f})

            c = config.load_jira_config()
            tickets_folder = c.get("tickets_folder", "")

            result = []
            for i in issues:
                f = i["fields"]
                key = i["key"]
                priority = f.get("priority")
                attachments = f.get("attachment", [])
                att_count = len(attachments) if attachments else 0

                # Check local folder status
                has_folder = False
                local_files = 0
                if tickets_folder:
                    dest = os.path.join(tickets_folder, key)
                    if os.path.isdir(dest):
                        has_folder = True
                        local_files = len([
                            fn for fn in os.listdir(dest)
                            if os.path.isfile(os.path.join(dest, fn))
                        ])

                result.append({
                    "key": key,
                    "summary": f["summary"],
                    "status": f["status"]["name"],
                    "priority": priority.get("name", "") if priority else "",
                    "priority_icon": priority.get("iconUrl", "") if priority else "",
                    "attachment_count": att_count,
                    "has_folder": has_folder,
                    "local_files": local_files,
                })
            return result

        @app.get("/api/jira/ticket/{key}/folder")
        async def jira_ticket_folder_info(key: str):
            """Check local folder status for a ticket."""
            c = config.load_jira_config()
            folder = c.get("tickets_folder", "")
            if not folder:
                return {"configured": False}
            dest = os.path.join(folder, key)
            exists = os.path.isdir(dest)
            files = []
            if exists:
                files = [
                    fn for fn in os.listdir(dest)
                    if os.path.isfile(os.path.join(dest, fn))
                ]
            return {"configured": True, "exists": exists, "path": dest, "files": files}

        # ── Weekly worklogs ─────────────────────────────────────

        @app.get("/api/jira/worklogs/weekly")
        async def jira_worklogs_weekly(week_of: str = "", account_id: str = "", force_refresh: bool = False):
            """
            Returns worklogs for the week containing `week_of` for a specific user.
            If `account_id` is empty, fetches for current user (myself).
            Response: { monday, sunday, users: [ { accountId, displayName, worklogs } ], cached, ttl }
            """
            d_from, d_to = _week_range(week_of)
            users_data = []
            from_cache = False

            if not account_id:
                # Fetch myself
                me_r = _api("get", "myself")
                if not me_r.ok:
                    raise HTTPException(me_r.status_code, "Cannot fetch current user")
                me = me_r.json()
                t_id = me["accountId"]
                t_name = me.get("displayName", "Me")
                is_me = True
            else:
                # Fetch specific user (teammate)
                # We need display name. Check config or basic user info? 
                # For simplicity, we might just use the ID or ask frontend to pass name?
                # Let's try to find name in config first to save an API call
                c = config.load_jira_config()
                found = next((t for t in c.get("teammates", []) if t.get("accountId") == account_id), None)
                t_id = account_id
                t_name = found.get("displayName", "Teammate") if found else "Teammate"
                is_me = False
                
                # Verify if it's actually me requested by ID
                me_r = _api("get", "myself")
                if me_r.ok and me_r.json().get("accountId") == account_id:
                    is_me = True
                    t_name = me_r.json().get("displayName")

            if force_refresh:
                _cache_clear(t_id)

            wl, was_cached = _fetch_worklogs_for_user(t_id, d_from, d_to, t_name)
            
            users_data.append({
                "accountId": t_id,
                "displayName": t_name,
                "is_me": is_me,
                "worklogs": wl,
            })

            return {
                "monday": d_from,
                "sunday": d_to,
                "users": users_data,
                "cached": was_cached,
                "cache_ttl_minutes": _cache_ttl() // 60,
            }

        # ── Legacy worklogs endpoint ────────────────────────────

        @app.get("/api/jira/worklogs")
        async def jira_worklogs(issue_key: str = "", date_from: str = "", date_to: str = ""):
            if not issue_key:
                me_r = _api("get", "myself")
                if not me_r.ok:
                    raise HTTPException(me_r.status_code, "Cannot fetch current user")
                me = me_r.json()
                d_from = date_from or date.today().isoformat()
                d_to = date_to or date.today().isoformat()
                wl, _ = _fetch_worklogs_for_user(me["accountId"], d_from, d_to,
                                                 me.get("displayName", ""))
                return wl

            r = _api("get", f"issue/{issue_key}/worklog")
            if not r.ok:
                raise HTTPException(r.status_code, r.text)
            wl = r.json().get("worklogs", [])
            me_r2 = _api("get", "myself")
            my_id = me_r2.json().get("accountId") if me_r2.ok else None
            if my_id:
                wl = [w for w in wl if w.get("author", {}).get("accountId") == my_id]

            issue_r = _api("get", f"issue/{issue_key}", params={"fields": "summary"})
            issue_summary = ""
            if issue_r.ok:
                issue_summary = issue_r.json().get("fields", {}).get("summary", "")

            return [
                {
                    "id": w["id"],
                    "ticket_key": issue_key,
                    "ticket_summary": issue_summary,
                    "date": w.get("started", "")[:10],
                    "started": w.get("started", ""),
                    "time_spent": w.get("timeSpent", ""),
                    "time_spent_seconds": w.get("timeSpentSeconds", 0),
                    "comment": _extract_comment(w),
                }
                for w in wl
            ]

        # ── Add worklog ─────────────────────────────────────────

        @app.post("/api/jira/worklog")
        async def jira_add_worklog(req: WorklogReq):
            secs = _parse_time(req.time_spent)
            if not secs or secs <= 0:
                raise HTTPException(400, "Invalid time format")
            started = _to_jira_datetime(req.started)
            body = {
                "timeSpentSeconds": secs,
                "started": started,
                "comment": _build_comment(req.comment),
            }
            r = _api("post", f"issue/{req.issue_key}/worklog",
                      json=body, params={"adjustEstimate": "auto", "notifyUsers": "false"})
            if r.status_code in (200, 201):
                _cache_clear()   # invalidate so next fetch gets fresh data
                return {"ok": True, "id": r.json().get("id")}
            raise HTTPException(r.status_code, r.text)

        # ── Update worklog ──────────────────────────────────────

        @app.put("/api/jira/worklog/{issue_key}/{worklog_id}")
        async def jira_update_worklog(issue_key: str, worklog_id: str, req: WorklogReq):
            secs = _parse_time(req.time_spent)
            if not secs or secs <= 0:
                raise HTTPException(400, "Invalid time format")
            started = _to_jira_datetime(req.started)
            body = {
                "timeSpentSeconds": secs,
                "started": started,
                "comment": _build_comment(req.comment),
            }
            r = _api("put", f"issue/{issue_key}/worklog/{worklog_id}",
                      json=body, params={"adjustEstimate": "auto", "notifyUsers": "false"})
            if r.status_code in (200, 201):
                _cache_clear()  # invalidate
                return {"ok": True, "id": r.json().get("id")}
            raise HTTPException(r.status_code, r.text)

        # ── Delete worklog ──────────────────────────────────────

        @app.delete("/api/jira/worklog/{issue_key}/{worklog_id}")
        async def jira_del_worklog(issue_key: str, worklog_id: str):
            r = _api("delete", f"issue/{issue_key}/worklog/{worklog_id}",
                      params={"adjustEstimate": "auto", "notifyUsers": "false"})
            if r.status_code in (200, 204):
                _cache_clear()   # invalidate
            return {"ok": r.status_code in (200, 204)}

        # ── Cache management ────────────────────────────────────

        @app.post("/api/jira/cache/clear")
        async def jira_cache_clear():
            _cache_clear()
            return {"ok": True}

        # ── Meeting shortcut ────────────────────────────────────

        @app.post("/api/jira/meeting")
        async def jira_meeting(req: MeetingReq):
            secs = _parse_time(req.time_spent)
            if not secs or secs <= 0:
                raise HTTPException(400, "Invalid time")
            issue_key = req.issue_key
            if not issue_key:
                c2 = config.load_jira_config()
                issue_key = c2.get("meeting_ticket", "FMBP-44552")
            started = _to_jira_datetime(req.started)
            body = {
                "timeSpentSeconds": secs,
                "started": started,
                "comment": _build_comment(req.summary or f"{date.today():%m.%d} standup"),
            }
            r = _api("post", f"issue/{issue_key}/worklog",
                      json=body, params={"adjustEstimate": "auto", "notifyUsers": "false"})
            if r.status_code in (200, 201):
                return {"ok": True}
            raise HTTPException(r.status_code, r.text)

        # ── Sync attachments ────────────────────────────────────


        @app.post("/api/jira/ticket/{key}/open")
        async def jira_open_folder(key: str):
            c = config.load_jira_config()
            folder = c.get("tickets_folder", "")
            if not folder:
                 raise HTTPException(400, "Tickets folder not configured")
            dest = os.path.join(folder, key)
            if not os.path.isdir(dest):
                 os.makedirs(dest, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(dest)
            return {"ok": True}

        @app.post("/api/jira/ticket/{key}/sync")
        async def jira_sync_attachments(key: str, open_folder: bool = False):
            c = config.load_jira_config()
            folder = c.get("tickets_folder", "")
            if not folder:
                raise HTTPException(400, "Tickets folder not configured")
            
            # Sanitize key (simple alphanumeric check)
            if not re.match(r"^[\w-]+$", key):
                 raise HTTPException(400, "Invalid ticket key")

            dest = os.path.join(folder, key)
            os.makedirs(dest, exist_ok=True)

            # Open folder immediately if requested (even if sync fails later)
            if open_folder and sys.platform == "win32":
                os.startfile(dest)

            r = _api("get", f"issue/{key}", params={"fields": "attachment"})
            if not r.ok:
                raise HTTPException(r.status_code, r.text)
            
            atts = r.json().get("fields", {}).get("attachment", [])
            downloaded = 0
            
            if atts:
                for att in atts:
                    url = att.get("content")
                    fname = att.get("filename", "unknown")
                    if not url:
                        continue
                    fp = os.path.join(dest, fname)
                    if os.path.exists(fp):
                        continue
                    fr = _req.get(url, auth=_auth(), stream=True)
                    if fr.status_code == 200:
                        with open(fp, "wb") as f:
                            for chunk in fr.iter_content(8192):
                                f.write(chunk)
                        downloaded += 1
            
            return {"ok": True, "downloaded": downloaded, "path": dest}


plugin = JiraTrackerPlugin()
