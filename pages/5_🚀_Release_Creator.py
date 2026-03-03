"""
Release Creator – FMBP release version & release ticket wizard.

Flow:
  1. Enter a source ticket (user story, bug, etc.)
  2. Choose: New Release or Revision
  3. Configure release parameters
  4. Preview & create the Jira version
  5. Preview & create the release ticket (clone of template / previous rev)
"""

import streamlit as st
import requests
from requests.auth import HTTPBasicAuth
import json
import os
import re
from datetime import date, timedelta

# ─── Config ───────────────────────────────────────────────────────────
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import sys
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)
from modules.server_singleton import ensure_server_session
ensure_server_session()

JIRA_DIR = os.path.join(ROOT_DIR, "jira-time-tracker")
JIRA_CFG = os.path.join(JIRA_DIR, "jira_config.json")
DOMAIN = "teltonika-telematics.atlassian.net"
PROJECT_KEY = "FMBP"
PROJECT_ID = 10170
RELEASE_TYPE_ID = "10114"          # Issue‑type "Release"
COMP_FIRMWARE = "10734"
COMP_SUB_ALL = "10863"
COMP_CAT_SPEC = "10759"
TEMPLATE_KEY = "FMBP-52822"       # canonical template for *new* releases
MIN_NEW_RELEASE_REV = 100

# ─── Jira helpers ─────────────────────────────────────────────────────

def _cfg():
    if os.path.exists(JIRA_CFG):
        with open(JIRA_CFG) as f:
            return json.load(f)
    return {}


def _auth():
    c = _cfg()
    return HTTPBasicAuth(c.get("email", ""), c.get("token", ""))


_HDR = {"Accept": "application/json", "Content-Type": "application/json"}


def _get(path, **kw):
    return requests.get(
        f"https://{DOMAIN}/rest/api/2/{path}",
        headers=_HDR, auth=_auth(), **kw,
    )


def _post(path, body):
    return requests.post(
        f"https://{DOMAIN}/rest/api/2/{path}",
        headers=_HDR, auth=_auth(), json=body,
    )


# ─── API wrappers ─────────────────────────────────────────────────────

def api_issue(key):
    r = _get(f"issue/{key}")
    return r.json() if r.ok else None


def api_versions():
    r = _get(f"project/{PROJECT_KEY}/versions")
    return r.json() if r.ok else []


def api_create_version(name, desc, start, release):
    return _post("version", {
        "name": name,
        "description": desc,
        "project": PROJECT_KEY,
        "projectId": PROJECT_ID,
        "startDate": start,
        "releaseDate": release,
        "archived": False,
        "released": False,
    })


def api_myself():
    r = _get("myself")
    return r.json() if r.ok else None


def api_search(jql, fields="key,summary,description,fixVersions"):
    r = _get("search", params={"jql": jql, "fields": fields, "maxResults": 100})
    return r.json().get("issues", []) if r.ok else []


def api_create_issue(fields):
    return _post("issue", {"fields": fields})


def api_createmeta():
    """Fetch all fields (with required flags) for the Release issue type."""
    fields = {}
    start_at = 0
    while True:
        r = _get(
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
    r = _get("issue/createmeta", params={
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


# ─── Clone helpers ────────────────────────────────────────────────────

# Fields to SKIP when cloning (even if settable): they are either
# attachment references (can't copy), sprint-specific, or time-tracking.
_CLONE_SKIP = {
    "attachment", "issuelinks", "parent",
    "customfield_10020",  # Sprint
    "timetracking",
}

# Fields the wizard always OVERRIDES with computed values.
_CLONE_OVERRIDE = {
    "project", "issuetype", "summary", "description",
    "fixVersions", "components", "assignee",
}


def _clean_for_create(val):
    """Reduce a cloned field value to what Jira accepts on POST.

    Strips out read-only noise (self, avatarUrls, …) while keeping
    the identifiers Jira needs (id, value, accountId, name).
    """
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


def _build_clone_payload(clone_source, settable_ids, overrides):
    """Build the ``fields`` dict for issue creation.

    *clone_source*  – ``fields`` dict from the source ticket (GET issue).
    *settable_ids*  – set of field IDs that the create endpoint accepts.
    *overrides*     – dict of fields the wizard computes (summary, desc, …).

    Every settable field that has a value in *clone_source* is copied
    (after sanitisation), except those in ``_CLONE_SKIP`` /
    ``_CLONE_OVERRIDE`` which are replaced by *overrides*.
    """
    fields = {}
    for fid in settable_ids:
        if fid in _CLONE_SKIP or fid in _CLONE_OVERRIDE:
            continue
        val = clone_source.get(fid)
        # Clear/override specific fields as requested
        if fid in [
            "versions",                # affected version
            "customfield_10163",       # task requester
            "customfield_10165",       # firmware link
            "customfield_10167",       # configurator link
            "customfield_10129",       # start date (migrated)
            "customfield_10124",       # testing estimation
            "customfield_10131",       # telematics program
            "customfield_10197",       # Development Start Date
            "customfield_10189",       # Development End Date
        ]:
            # Set telematics program to FMB platform
            if fid == "customfield_10131":
                fields[fid] = {"value": "FMB platform"}
            # Set start/end dates from overrides if present
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


# ─── Pure logic ───────────────────────────────────────────────────────

def _rev_nums(versions, base):
    """All revision numbers that match *base*.Rev.NNN (with or without _spec)."""
    pat = re.compile(re.escape(base) + r"\.Rev\.(\d+)")
    return sorted(
        int(m.group(1))
        for v in versions
        if (m := pat.search(v.get("name", "")))
    )


def _next_rev10(versions, base):
    """First available ×10 slot, scanning upward from MIN_NEW_RELEASE_REV."""
    nums = _rev_nums(versions, base)
    if not nums:
        return MIN_NEW_RELEASE_REV
    # occupied blocks: any Rev in [N*10 .. N*10+9] means block N*10 is taken
    occupied = {(n // 10) * 10 for n in nums}
    c = MIN_NEW_RELEASE_REV
    while c in occupied:
        c += 10
    return c


def _all_free_rev10(versions, base, limit=200):
    """Return the first `limit` free ×10 slots (ascending), starting at MIN_NEW_RELEASE_REV."""
    nums = _rev_nums(versions, base)
    occupied = {(n // 10) * 10 for n in nums}
    hi = max(occupied) if occupied else 0
    # scan up to well past the highest occupied block
    ceiling = hi + limit * 10
    free = []
    c = MIN_NEW_RELEASE_REV
    while c <= ceiling and len(free) < limit:
        if c not in occupied:
            free.append(c)
        c += 10
    return free


def _parse_ver(name):
    """'04.02.00.Rev.510_245' → ('04.02.00', 510, '245').
       '04.02.00.Rev.510'     → ('04.02.00', 510, None)."""
    m = re.match(r"^(\d+\.\d+\.\d+)\.Rev\.(\d+)(?:_(\S+))?$", name)
    return (m.group(1), int(m.group(2)), m.group(3)) if m else (None, None, None)


def _version_sort_key(name):
    """Sort by numeric revision first, then by spec suffix (if present)."""
    base, rev, suffix = _parse_ver(name)
    if rev is None:
        return (-1, "", name)
    suffix_key = suffix or ""
    return (rev, suffix_key, name)


def _parse_summ(s):
    """Release ticket summary → ('SPEC'|'EXP', detail, client_or_None)."""
    m = re.match(r"[\d.]+\.Rev\.\d+\s+FMBXXX\s+SPEC=(\d+)\s+\((.+?)\)", s or "")
    if m:
        return "SPEC", m.group(1), m.group(2)
    m = re.match(r"[\d.]+\.Rev\.\d+\s+FMBXXX\s+EXP=(.+)", s or "")
    if m:
        return "EXP", m.group(1), None
    return None, None, None


# ── builders ──────────────────────────────────────────────────────────

def _vname(base, rev, spec=None):
    s = f"{base}.Rev.{rev}"
    return f"{s}_{spec}" if spec else s


def _spec_desc(num, ocean):
    return f"FMBXXX SPEC={num} (eM2M_SPECIDL_{ocean}_SO_{str(num).zfill(4)})"


def _exp_desc(s):
    return f"FMBXXX EXP={s}"


def _spec_summ(base, rev, num, client):
    # Add spec suffix and full spec string
    spec_suffix = f"_{num}" if num else ""
    spec_string = f"eM2M_SPECIDL_{client}_SO_{str(num).zfill(4)}"
    return f"{base}.Rev.{rev}{spec_suffix} FMBXXX SPEC={num} ({spec_string})"


def _exp_summ(base, rev, s):
    return f"{base}.Rev.{rev} FMBXXX EXP={s}"


def _desc_table(key, summary):
    return (
        "*Additional Comments:*\n*-*\n\n"
        "||*Issue ID*||*Testing guidelines for Quality Assurance engineers*||\n"
        f"|{key}|{summary}|"
    )


def _wiki_to_html(wiki):
    """Best-effort Jira wiki markup to HTML for preview."""
    lines = wiki.split("\n")
    out = []
    for ln in lines:
        # bold: *text*
        ln = re.sub(r'\*(.+?)\*', r'<b>\1</b>', ln)
        # table header row: ||hdr||hdr||
        if ln.startswith("||"):
            cells = [c.strip() for c in ln.split("||") if c.strip()]
            out.append(
                '<tr>' + ''.join(
                    f'<th style="border:1px solid #555;padding:4px 8px;background:#e8e8e8;color:#111;">{c}</th>'
                    for c in cells
                ) + '</tr>'
            )
            continue
        # table data row: |val|val|
        if ln.startswith("|"):
            cells = [c.strip() for c in ln.split("|") if c.strip()]
            out.append(
                '<tr>' + ''.join(
                    f'<td style="border:1px solid #555;padding:4px 8px;">{c}</td>'
                    for c in cells
                ) + '</tr>'
            )
            continue
        # regular line
        out.append(f'<p style="margin:2px 0;">{ln}</p>' if ln.strip() else '<br>')

    # wrap consecutive <tr> in <table>
    html = []
    in_table = False
    for part in out:
        if part.startswith('<tr>'):
            if not in_table:
                html.append('<table style="border-collapse:collapse;margin:8px 0;">')
                in_table = True
            html.append(part)
        else:
            if in_table:
                html.append('</table>')
                in_table = False
            html.append(part)
    if in_table:
        html.append('</table>')
    return '\n'.join(html)


def _find_rel_ticket(vname):
    """Find the Release issue whose fixVersion == vname."""
    iss = api_search(
        f'project={PROJECT_KEY} AND issuetype=Release AND fixVersion="{vname}"'
    )
    return iss[0] if iss else None


# ═══════════════════════════════════════════════════════════════════════
#  Streamlit page
# ═══════════════════════════════════════════════════════════════════════

st.set_page_config(page_title="Release Creator", page_icon="🚀", layout="centered")

cfg = _cfg()
if not cfg.get("email") or not cfg.get("token"):
    st.error("⚠️ Jira credentials not set – configure them in the **Jira Tracker** page sidebar.")
    st.stop()

st.title("🚀 Release Creator")
st.caption(f"Create {PROJECT_KEY} release versions & tickets")

# ─── Session state defaults ───────────────────────────────────────────
_D = dict(
    rc_src=None,              # {"key", "summary"}
    rc_vs=None,               # cached version list
    rc_base="",               # searched base string
    rc_nrev=None,             # next available rev (new release)
    rc_free_slots=[],         # all free ×10 slots
    rc_slot_idx=0,            # current index into rc_free_slots
    rc_rel_tickets=None,      # {vname: {"key": ..., "summary": ...}} cache
    rc_prev_tk=None,          # previous release ticket (revision)
    rc_prev_vdesc="",         # previous version description
    rc_prev_searched="",      # version name that was searched
    rc_ver_ok=None,           # created version response
    rc_tkt_ok=None,           # created ticket response
    rc_prev_type=None,        # last selected release type
    rc_meta=None,             # createmeta field definitions
    rc_clone_data=None,       # full clone source issue fields
)
for k, v in _D.items():
    st.session_state.setdefault(k, v)

if st.sidebar.button("🔄 Start Over", use_container_width=True):
    for k, v in _D.items():
        st.session_state[k] = v
    st.rerun()

# ─── ① Source Ticket ──────────────────────────────────────────────────
st.header("① Source Ticket")
c1, c2 = st.columns([4, 1])
key_in = c1.text_input("key", placeholder="FMBP-12345", label_visibility="collapsed")
if c2.button("Fetch", use_container_width=True) and key_in:
    with st.spinner("Fetching…"):
        iss = api_issue(key_in.strip().upper())
    if iss:
        st.session_state.rc_src = {
            "key": iss["key"],
            "summary": iss["fields"]["summary"],
        }
        # reset downstream
        for k in ("rc_ver_ok", "rc_tkt_ok", "rc_prev_tk", "rc_vs", "rc_nrev", "rc_clone_data"):
            st.session_state[k] = _D[k]
        st.rerun()
    else:
        st.error(f"**{key_in}** not found")

src = st.session_state.rc_src
if src:
    st.success(f"**{src['key']}** — {src['summary']}")
if not src:
    st.stop()

# ─── ② Release Type ──────────────────────────────────────────────────
st.divider()
st.header("② New Release or Revision?")
rtype = st.radio(
    "type", ["New Release", "Revision"],
    horizontal=True, label_visibility="collapsed",
)

# Reset creation state when the user switches type
if rtype != st.session_state.rc_prev_type:
    st.session_state.rc_prev_type = rtype
    st.session_state.rc_ver_ok = None
    st.session_state.rc_tkt_ok = None
    st.session_state.rc_prev_tk = None
    st.session_state.rc_clone_data = None

st.divider()

# ─── Output variables filled by either path ───────────────────────────
ver_name = ver_desc = tkt_summ = None
rel_date = None
has_spec = False
ready = False

# ═══════════════════════════════════════════════════════════════════════
#  ③‑A  NEW RELEASE
# ═══════════════════════════════════════════════════════════════════════
if rtype == "New Release":
    st.header("③ New Release")

    base_in = st.text_input("Base version", placeholder="04.02.00")

    sc, _ = st.columns([1, 3])
    if sc.button("🔎 Search") and base_in:
        with st.spinner("Loading versions…"):
            vs = api_versions()
        b = base_in.strip()
        st.session_state.rc_vs = vs
        st.session_state.rc_base = b
        free = _all_free_rev10(vs, b)
        st.session_state.rc_free_slots = free
        st.session_state.rc_slot_idx = 0
        st.session_state.rc_nrev = free[0] if free else _next_rev10(vs, b)
        st.session_state.rc_rel_tickets = None
        st.session_state.rc_ver_ok = None
        st.session_state.rc_tkt_ok = None
        st.rerun()

    nrev = st.session_state.rc_nrev
    base = st.session_state.rc_base
    free_slots = st.session_state.rc_free_slots
    slot_idx = st.session_state.rc_slot_idx

    if nrev and base:
        vs = st.session_state.rc_vs or []
        nums = _rev_nums(vs, base)
        matching_vs = sorted(
            [v for v in vs if base in v.get("name", "")],
            key=lambda v: _version_sort_key(v.get("name", "")),
            reverse=True,
        )

        # ── Slot navigator ────────────────────────────────────────────
        nav1, nav2, nav3 = st.columns([1, 3, 1])
        with nav1:
            if st.button("⬅️ Prev", use_container_width=True, disabled=(slot_idx <= 0)):
                st.session_state.rc_slot_idx = slot_idx - 1
                st.session_state.rc_nrev = free_slots[slot_idx - 1]
                st.rerun()
        with nav2:
            total_free = len(free_slots)
            st.markdown(
                f'<div style="text-align:center;padding:6px 0;">'
                f'**{len(matching_vs)}** versions for <code>{base}</code> · '
                f'Selected: <b>Rev.{nrev}</b> '
                f'<span style="color:#888;">({slot_idx + 1}/{total_free} free slots)</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with nav3:
            if st.button("Next ➡️", use_container_width=True, disabled=(slot_idx >= len(free_slots) - 1)):
                st.session_state.rc_slot_idx = slot_idx + 1
                st.session_state.rc_nrev = free_slots[slot_idx + 1]
                st.rerun()

        # ── All versions with descriptions & release ticket links ─────
        with st.expander(f"📦 All versions ({len(matching_vs)})", expanded=False):
            # Batch-fetch release tickets once (None = not yet loaded)
            rel_map = st.session_state.rc_rel_tickets
            if rel_map is None:
                rel_map = {}
                with st.spinner("Loading release tickets…"):
                    vnames = [v["name"] for v in matching_vs]
                    # fetch in chunks of 40 to stay within JQL / URL limits
                    for i in range(0, len(vnames), 40):
                        chunk = vnames[i : i + 40]
                        jql_in = ", ".join(f'"{n}"' for n in chunk)
                        tickets = api_search(
                            f'project={PROJECT_KEY} AND issuetype=Release '
                            f'AND fixVersion in ({jql_in})',
                            fields="key,summary,fixVersions",
                        )
                        for t in tickets:
                            for fv in t["fields"].get("fixVersions", []):
                                rel_map[fv["name"]] = {
                                    "key": t["key"],
                                    "summary": t["fields"]["summary"],
                                }
                st.session_state.rc_rel_tickets = rel_map

            rows = []
            for v in matching_vs:
                vn = v.get("name", "")
                _, rev, _ = _parse_ver(vn)
                desc = v.get("description", "") or "—"
                rt = rel_map.get(vn)
                link = f"https://{DOMAIN}/browse/{rt['key']}" if rt else None
                rows.append({
                    "Version": vn,
                    "Rev": rev if rev is not None else 0,
                    "Description": desc,
                    "Release Ticket": link,
                })

            st.markdown(
                '<div style="max-height:400px;overflow-y:auto;">',
                unsafe_allow_html=True,
            )
            st.dataframe(
                rows,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Version": st.column_config.TextColumn(width="medium"),
                    "Rev": st.column_config.NumberColumn(width="small", format="%d"),
                    "Description": st.column_config.TextColumn(width="large"),
                    "Release Ticket": st.column_config.LinkColumn(
                        width="small", display_text=r"(FMBP-\d+)"
                    ),
                },
            )
            st.markdown('</div>', unsafe_allow_html=True)

        is_spec = st.checkbox("Spec release?")

        if is_spec:
            sc1, sc2 = st.columns(2)
            spec_num = sc1.text_input("Spec number", placeholder="245")
            ocean = sc2.text_input("Client / Ocean string", placeholder="Effortech")
            if spec_num and ocean:
                ver_name = _vname(base, nrev, spec_num)
                ver_desc = _spec_desc(spec_num, ocean)
                tkt_summ = _spec_summ(base, nrev, spec_num, ocean)
                has_spec = True
                ready = True
        else:
            exp_in = st.text_input("EXP string", placeholder="expfw/yellowfox_lib")
            if exp_in:
                ver_name = _vname(base, nrev)
                ver_desc = _exp_desc(exp_in)
                tkt_summ = _exp_summ(base, nrev, exp_in)
                ready = True

        rel_date = st.date_input(
            "Release date",
            value=date.today() + timedelta(days=14),
        )

# ═══════════════════════════════════════════════════════════════════════
#  ③‑B  REVISION
# ═══════════════════════════════════════════════════════════════════════
else:
    st.header("③ Revision")

    prev_in = st.text_input(
        "Previous version name",
        placeholder="04.02.00.Rev.510_245",
    )
    if not prev_in:
        st.stop()

    pv = prev_in.strip()
    base, prev_rev, spec_sfx = _parse_ver(pv)
    if not base:
        st.error("Cannot parse – expected `XX.XX.XX.Rev.NNN` or `XX.XX.XX.Rev.NNN_SSS`")
        st.stop()

    new_rev = prev_rev + 1
    new_vname = _vname(base, new_rev, spec_sfx)
    st.info(f"`{pv}`  →  `{new_vname}`  *(Rev +1)*")

    # Reset if user changed the version input
    if st.session_state.rc_prev_searched != pv:
        st.session_state.rc_prev_tk = None
        st.session_state.rc_ver_ok = None
        st.session_state.rc_tkt_ok = None
        st.session_state.rc_clone_data = None

    # Find previous release ticket
    fc, _ = st.columns([1, 3])
    need_find = (
        fc.button("🔎 Find Previous Release Ticket")
        if not st.session_state.rc_prev_tk
        else False
    )

    if need_find:
        with st.spinner("Searching…"):
            t = _find_rel_ticket(pv)
            vs = api_versions()
        if t:
            st.session_state.rc_prev_tk = {
                "key": t["key"],
                "summary": t["fields"]["summary"],
            }
            st.session_state.rc_prev_searched = pv
            vdesc = ""
            for v in vs:
                if v["name"] == pv:
                    vdesc = v.get("description", "")
                    break
            st.session_state.rc_prev_vdesc = vdesc
            st.session_state.rc_ver_ok = None
            st.session_state.rc_tkt_ok = None
            st.rerun()
        else:
            st.warning(f"No release ticket with fixVersion = `{pv}`")

    pt = st.session_state.rc_prev_tk
    if pt:
        st.success(f"Cloning from **{pt['key']}** — {pt['summary']}")

        sty, sd1, sd2 = _parse_summ(pt["summary"])
        prev_vdesc = st.session_state.get("rc_prev_vdesc", "")

        ver_name = new_vname
        ver_desc = prev_vdesc

        if sty == "SPEC":
            tkt_summ = _spec_summ(base, new_rev, sd1, sd2)
        elif sty == "EXP":
            tkt_summ = _exp_summ(base, new_rev, sd1)
        else:
            tkt_summ = f"{base}.Rev.{new_rev}"

        has_spec = bool(spec_sfx)

        rel_date = st.date_input(
            "Release date",
            value=date.today() + timedelta(days=14),
            key="rc_rev_rdate",
        )
        ready = True

# ═══════════════════════════════════════════════════════════════════════
#  ④ Preview & Create
# ═══════════════════════════════════════════════════════════════════════
if ready and ver_name and tkt_summ:
    st.divider()
    st.header("④ Preview & Create")

    # ── Load create-issue metadata (settable fields list) ───────────────
    if st.session_state.rc_meta is None:
        with st.spinner("Loading field metadata…"):
            st.session_state.rc_meta = api_createmeta()

    # ── Load clone source (template for New Release, prev ticket for Revision)
    if st.session_state.rc_clone_data is None:
        clone_key = (
            st.session_state.rc_prev_tk["key"]
            if rtype == "Revision" and st.session_state.rc_prev_tk
            else TEMPLATE_KEY
        )
        with st.spinner(f"Loading clone source ({clone_key})…"):
            iss = api_issue(clone_key)
            st.session_state.rc_clone_data = iss.get("fields", {}) if iss else {}

    clone_fields = st.session_state.rc_clone_data or {}

    default_desc = _desc_table(src["key"], src["summary"])

    # ── Editable fields ───────────────────────────────────────────────
    st.subheader("Version")
    ec1, ec2 = st.columns(2)
    ver_name = ec1.text_input("Version name", value=ver_name, key="rc_ed_vname")
    ver_desc = ec2.text_input("Version description", value=ver_desc or "", key="rc_ed_vdesc")

    st.subheader("Ticket")
    tkt_summ = st.text_input("Ticket summary", value=tkt_summ, key="rc_ed_tsumm")

    dc1, dc2 = st.columns(2)
    start_date = dc1.date_input("Start date", value=date.today(), key="rc_ed_sdate")
    rel_date = dc2.date_input("Release date", value=rel_date, key="rc_ed_rdate")

    st.markdown("**Description**")
    desc_mode = st.radio(
        "desc_mode", ["✏️ Raw (wiki markup)", "👁️ Rich preview"],
        horizontal=True, label_visibility="collapsed",
    )
    if desc_mode.startswith("✏"):
        tkt_desc = st.text_area(
            "Description (wiki)", value=default_desc, height=180,
            key="rc_ed_desc", label_visibility="collapsed",
        )
    else:
        tkt_desc = st.session_state.get("rc_ed_desc", default_desc)
        st.markdown(
            f'<div style="border:1px solid #444;border-radius:6px;padding:12px;background:#1e1e1e;">'
            f'{_wiki_to_html(tkt_desc)}</div>',
            unsafe_allow_html=True,
        )
        with st.expander("Edit raw wiki markup", expanded=False):
            tkt_desc = st.text_area(
                "raw", value=tkt_desc, height=140,
                key="rc_ed_desc_alt", label_visibility="collapsed",
            )

    st.divider()

    # ── Create version ────────────────────────────────────────────────
    vc = st.session_state.rc_ver_ok
    if vc:
        st.success(f"✅ Version **{ver_name}** ready  (id {vc['id']})")
    else:
        v_col1, v_col2 = st.columns(2)
        with v_col1:
            if st.button("✅ Create Version", type="primary", use_container_width=True):
                with st.spinner("Creating version…"):
                    r = api_create_version(
                        ver_name, ver_desc,
                        str(start_date), str(rel_date),
                    )
                if r.ok:
                    st.session_state.rc_ver_ok = r.json()
                    st.rerun()
                else:
                    st.error(
                        f"❌ {r.status_code}: {r.text}\n\n"
                        "If you lack *Manage Versions* permission, create the version "
                        "manually in Jira and enter its ID below."
                    )
        with v_col2:
            manual_vid = st.text_input(
                "Or enter existing version ID",
                placeholder="e.g. 14510",
                key="rc_manual_vid",
            )
            if manual_vid and manual_vid.strip().isdigit():
                if st.button("🔗 Use this version ID", use_container_width=True):
                    st.session_state.rc_ver_ok = {
                        "id": int(manual_vid.strip()),
                        "name": ver_name,
                    }
                    st.rerun()

    # ── Create release ticket ─────────────────────────────────────────
    if st.session_state.rc_ver_ok:
        tc = st.session_state.rc_tkt_ok
        if tc:
            k = tc["key"]
            st.success(f"✅ Release ticket **{k}** created!")
            st.link_button(
                f"🔗 Open {k} in Jira",
                f"https://{DOMAIN}/browse/{k}",
                use_container_width=True,
            )
        else:
            if st.button(
                "🎫 Create Release Ticket",
                type="primary",
                use_container_width=True,
            ):
                with st.spinner("Creating release ticket…"):
                    me = api_myself()
                    ver = st.session_state.rc_ver_ok

                    comps = [{"id": COMP_FIRMWARE}, {"id": COMP_SUB_ALL}]
                    if has_spec:
                        comps.append({"id": COMP_CAT_SPEC})

                    # Computed overrides – these always replace clone values
                    overrides = {
                        "project": {"key": PROJECT_KEY},
                        "issuetype": {"id": RELEASE_TYPE_ID},
                        "summary": tkt_summ,
                        "description": tkt_desc,
                        "fixVersions": [{"id": str(ver["id"])}],
                        "components": comps,
                    }
                    if me:
                        overrides["assignee"] = {"accountId": me["accountId"]}

                    # Build payload: clone source fields + overrides
                    settable = set((st.session_state.rc_meta or {}).keys())
                    fields = _build_clone_payload(
                        clone_fields, settable, overrides,
                    )

                    r = api_create_issue(fields)

                if r.ok:
                    st.session_state.rc_tkt_ok = r.json()
                    st.rerun()
                else:
                    st.error(f"❌ {r.status_code}: {r.text}")
