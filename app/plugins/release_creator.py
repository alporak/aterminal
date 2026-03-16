"""
Release Creator plugin – Jira version & release ticket wizard.

Uses the official `jira` Python package for most interaction,
plus raw REST for createmeta (which the pip package handles poorly).
"""

from __future__ import annotations

import re
import os
from typing import Optional

import requests as _requests
from requests.auth import HTTPBasicAuth
from jira import JIRA, JIRAError
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.plugins.base import ToolkitPlugin
from app import config

DOMAIN = "teltonika-telematics.atlassian.net"
SERVER = f"https://{DOMAIN}"
PROJECT_KEY = "FMBP"
PROJECT_ID = 10170
RELEASE_TYPE_ID = "10114"
COMP_FIRMWARE = "10734"
COMP_SUB_ALL = "10863"
COMP_CAT_SPEC = "10759"
TEMPLATE_KEY = "FMBP-52822"
MIN_NEW_RELEASE_REV = 100

# Fields to SKIP when cloning (attachments, sprint, time-tracking)
CLONE_SKIP = {
    "attachment", "issuelinks", "parent",
    "customfield_10020",  # Sprint
    "timetracking",
}

# Fields the wizard always OVERRIDES with computed values
CLONE_OVERRIDE = {
    "project", "issuetype", "summary", "description",
    "fixVersions", "components", "assignee",
}

LINK_TYPE_NAME = "Relates"

_jira_client: JIRA | None = None


def _jira() -> JIRA:
    """Lazy-init a JIRA client from saved config."""
    global _jira_client
    if _jira_client is None:
        c = config.load_jira_config()
        _jira_client = JIRA(server=SERVER,
                            basic_auth=(c.get("email", ""), c.get("token", "")))
    return _jira_client


def _raw_auth():
    """HTTPBasicAuth for raw requests calls."""
    c = config.load_jira_config()
    return HTTPBasicAuth(c.get("email", ""), c.get("token", ""))


_HDR = {"Accept": "application/json", "Content-Type": "application/json"}


def _raw_get(path, **kw):
    return _requests.get(f"{SERVER}/rest/api/2/{path}",
                         headers=_HDR, auth=_raw_auth(), **kw)


def _raw_post(path, body):
    return _requests.post(f"{SERVER}/rest/api/2/{path}",
                          headers=_HDR, auth=_raw_auth(), json=body)


def _reset_client():
    global _jira_client
    _jira_client = None


def _rev_nums(versions, base):
    pat = re.compile(re.escape(base) + r"\.Rev\.(\d+)")
    return sorted(int(m.group(1)) for v in versions if (m := pat.search(v.get("name", ""))))


def _next_rev10(versions, base):
    nums = _rev_nums(versions, base)
    if not nums:
        return MIN_NEW_RELEASE_REV
    occupied = {(n // 10) * 10 for n in nums}
    c = MIN_NEW_RELEASE_REV
    while c in occupied:
        c += 10
    return c


def _all_free_slots(versions, base, limit=200):
    nums = _rev_nums(versions, base)
    occupied = {(n // 10) * 10 for n in nums}
    hi = max(occupied) if occupied else 0
    ceiling = hi + limit * 10
    free = []
    c = MIN_NEW_RELEASE_REV
    while c <= ceiling and len(free) < limit:
        if c not in occupied:
            free.append(c)
        c += 10
    return free


def _clean_for_create(val):
    """Reduce a cloned field value to what Jira accepts on POST."""
    if isinstance(val, list):
        return [_clean_for_create(v) for v in val]
    if isinstance(val, dict):
        if "accountId" in val:
            return {"accountId": val["accountId"]}
        if "id" in val:
            out = {"id": str(val["id"])}
            if "value" in val:
                out["value"] = val["value"]
            return out
        if "value" in val:
            return {"value": val["value"]}
        if "name" in val:
            return {"name": val["name"]}
    return val


def _api_createmeta():
    """Fetch all settable field IDs for the Release issue type (paginated)."""
    fields = {}
    start_at = 0
    while True:
        r = _raw_get(
            f"issue/createmeta/{PROJECT_KEY}/issuetypes/{RELEASE_TYPE_ID}",
            params={"startAt": start_at, "maxResults": 50},
        )
        if not r.ok:
            break
        data = r.json()
        batch = data.get("fields", data.get("values", []))
        for f in batch:
            fid = f.get("fieldId") or f.get("key", "")
            if fid:
                fields[fid] = f
        total = data.get("total", 0)
        start_at += len(batch)
        if start_at >= total or not batch:
            break
    if fields:
        return fields
    # Legacy endpoint fallback
    r = _raw_get("issue/createmeta", params={
        "projectKeys": PROJECT_KEY,
        "issuetypeIds": RELEASE_TYPE_ID,
        "expand": "projects.issuetypes.fields",
    })
    if r.ok:
        data = r.json()
        for p in data.get("projects", []):
            for it in p.get("issuetypes", []):
                return it.get("fields", {})
    return {}


def _build_clone_payload(clone_source, settable_ids, overrides):
    """Build the fields dict for issue creation.

    Iterates *settable_ids* from createmeta. Copies values from
    *clone_source* (after sanitisation), except CLONE_SKIP / CLONE_OVERRIDE
    which are replaced by *overrides*.
    """
    fields = {}
    for fid in settable_ids:
        if fid in CLONE_SKIP or fid in CLONE_OVERRIDE:
            continue
        val = clone_source.get(fid)
        # Clear or override specific fields
        if fid in [
            "versions",                # affected version
            "customfield_10165",       # firmware link
            "customfield_10167",       # configurator link
            "customfield_10129",       # start date (migrated)
            "customfield_10124",       # testing estimation
            "customfield_10131",       # telematics program
            "customfield_10197",       # Development Start Date
            "customfield_10189",       # Development End Date
        ]:
            if fid == "customfield_10131":
                fields[fid] = {"value": "FMB platform"}
            elif fid == "customfield_10197" and "customfield_10197" in overrides:
                fields[fid] = overrides["customfield_10197"]
            elif fid == "customfield_10189" and "customfield_10189" in overrides:
                fields[fid] = overrides["customfield_10189"]
            else:
                fields[fid] = None
            continue
        if val is not None:
            fields[fid] = _clean_for_create(val)
    fields.update(overrides)
    return fields


class VersionReq(BaseModel):
    name: str
    description: str = ""
    start_date: Optional[str] = None
    release_date: Optional[str] = None


class TicketReq(BaseModel):
    base: str
    rev: int
    source_key: str
    source_summary: str
    spec: Optional[str] = None
    client: Optional[str] = None
    exp: Optional[str] = None
    has_spec: bool = False
    clone_from: str = TEMPLATE_KEY
    prev_ticket_key: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[str] = None
    release_date: Optional[str] = None


class ReleaseCreatorPlugin(ToolkitPlugin):
    id = "release"
    name = "Release Creator"
    icon = "🚀"
    order = 50

    def register_routes(self, app: FastAPI):

        def _ver_dict(v):
            """Convert a jira.Version object to a JSON-friendly dict."""
            return {
                "id": v.id,
                "name": v.name,
                "description": getattr(v, "description", ""),
                "archived": getattr(v, "archived", False),
                "released": getattr(v, "released", False),
                "startDate": getattr(v, "startDate", None),
                "releaseDate": getattr(v, "releaseDate", None),
                "projectId": getattr(v, "projectId", None),
            }

        def _versions_dicts():
            """Fetch all project versions as list-of-dicts."""
            return [_ver_dict(v) for v in _jira().project_versions(PROJECT_KEY)]

        @app.get("/api/release/issue/{key}")
        async def rel_issue(key: str):
            try:
                issue = _jira().issue(key, fields="summary")
            except JIRAError as e:
                raise HTTPException(e.status_code or 400, str(e))
            return {"key": issue.key, "summary": issue.fields.summary}

        @app.get("/api/release/versions")
        async def rel_versions(base: str = ""):
            try:
                vs = _versions_dicts()
            except JIRAError as e:
                raise HTTPException(e.status_code or 500, str(e))
            if base:
                vs = [v for v in vs if base in v.get("name", "")]
            return vs

        @app.get("/api/release/find_ticket")
        async def rel_find_ticket(version: str):
            safe_v = version.replace('"', '\\"')
            jql = f'project = {PROJECT_KEY} AND issuetype = Release AND fixVersion = "{safe_v}"'
            try:
                results = _jira().search_issues(jql, maxResults=1,
                                                 fields="summary,description,fixVersions")
            except JIRAError as e:
                raise HTTPException(e.status_code or 500, str(e))
            if not results:
                return {"found": False}
            iss = results[0]
            return {
                "found": True,
                "key": iss.key,
                "summary": iss.fields.summary or "",
                "description": getattr(iss.fields, "description", "") or "",
            }

        @app.get("/api/release/free_slots")
        async def rel_free_slots(base: str):
            try:
                vs = _versions_dicts()
            except JIRAError as e:
                raise HTTPException(e.status_code or 500, str(e))
            return {
                "free_slots": _all_free_slots(vs, base),
                "next": _next_rev10(vs, base),
                "existing_revs": _rev_nums(vs, base),
            }

        @app.post("/api/release/version")
        async def rel_create_version(req: VersionReq):
            try:
                v = _jira().create_version(
                    name=req.name,
                    project=PROJECT_KEY,
                    description=req.description or "",
                    startDate=req.start_date,
                    releaseDate=req.release_date,
                )
            except JIRAError as e:
                raise HTTPException(e.status_code or 400, str(e))
            return {"ok": True, "version": _ver_dict(v)}

        @app.post("/api/release/ticket")
        async def rel_create_ticket(req: TicketReq):
            j = _jira()

            # Build version name
            spec_suffix = f"_{req.spec}" if req.spec else ""
            vname = f"{req.base}.Rev.{req.rev}{spec_suffix}"

            # Build summary
            if req.summary:
                summary = req.summary
            elif req.spec and req.client:
                summary = f"{vname} {PROJECT_KEY.replace('FMBP','FMBXXX')} SPEC={req.spec} ({req.client})"
            else:
                exp_str = req.exp or req.source_key
                summary = f"{vname} {PROJECT_KEY.replace('FMBP','FMBXXX')} EXP={exp_str}"

            # Description
            if req.description:
                desc = req.description
            else:
                desc = (
                    "*Additional Comments:*\n*-*\n\n"
                    "||*Issue ID*||*Testing guidelines for Quality Assurance engineers*||\n"
                    f"|{req.source_key}|{req.source_summary}|"
                )

            # Fetch clone source
            try:
                src = j.issue(req.clone_from)
            except JIRAError as e:
                raise HTTPException(400, f"Cannot fetch clone source {req.clone_from}: {e}")
            clone_fields = src.raw["fields"]

            # Fetch createmeta – the set of fields Jira will accept
            settable_ids = set(_api_createmeta().keys())

            # Assignee (myself)
            try:
                me = j.myself()
                assignee = {"accountId": me["accountId"]}
            except Exception:
                assignee = None

            # Components
            comps = [{"id": COMP_FIRMWARE}, {"id": COMP_SUB_ALL}]
            if req.has_spec:
                comps.append({"id": COMP_CAT_SPEC})

            # Computed overrides – always replace clone values
            overrides = {
                "project": {"key": PROJECT_KEY},
                "issuetype": {"id": RELEASE_TYPE_ID},
                "summary": summary,
                "description": desc,
                "fixVersions": [{"name": vname}],
                "components": comps,
            }
            if assignee:
                overrides["assignee"] = assignee

            # Dev Start / End dates (= start_date / release_date)
            if req.start_date:
                overrides["customfield_10197"] = req.start_date
            if req.release_date:
                overrides["customfield_10189"] = req.release_date

            # Build full payload via clone logic (same as old Streamlit code)
            fields = _build_clone_payload(clone_fields, settable_ids, overrides)

            # Create issue via raw REST (same as old code)
            r = _raw_post("issue", {"fields": fields})
            if not r.ok:
                raise HTTPException(r.status_code, r.text)
            new_key = r.json()["key"]

            # Create Previous Release link if requested (revision flow)
            if req.prev_ticket_key and new_key:
                try:
                    j.create_issue_link(LINK_TYPE_NAME, new_key, req.prev_ticket_key)
                except JIRAError:
                    pass  # non-fatal

            return {"ok": True, "key": new_key, "summary": summary}

        @app.get("/api/release/myself")
        async def rel_myself():
            try:
                return _jira().myself()
            except JIRAError as e:
                raise HTTPException(e.status_code or 500, str(e))


plugin = ReleaseCreatorPlugin()
