#!/usr/bin/env python3
"""
RHAISTRAT readiness checker — deterministic, script-based.

Usage (direct API, needs env vars):
    python3 check.py RHAISTRAT-1523

Usage (pre-fetched JSON, no env vars needed):
    python3 check.py --from-json /tmp/rhaistrat_RHAISTRAT-1523.json

Auth (only needed for direct API mode):
    JIRA_EMAIL       or  ATLASSIAN_EMAIL
    JIRA_API_TOKEN   or  ATLASSIAN_API_TOKEN

Pre-fetched mode expects a JSON file written with:
    {"issue": <getJiraIssue response>, "children": <searchJiraIssues response>}
"""

import os
import re
import sys
import json
import base64
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from html.parser import HTMLParser

# ── Jira config ───────────────────────────────────────────────────────────────
JIRA_BASE = "https://redhat.atlassian.net"

# Confirmed custom-field IDs for redhat.atlassian.net
F_RICE       = "customfield_10864"  # RICE Score
F_TARGET_VER = "customfield_10855"  # Target Version
F_REL_TYPE   = "customfield_10851"  # Release Type
F_COLOR      = "customfield_10712"  # Color Status
F_PROD_DOCS  = "customfield_10665"  # Product Documentation Required

SIGNOFF_LABEL    = "strat-creator-human-sign-off"
SIGNOFF_KEYWORDS = {"sign-off", "sign off", "signoff", "approval", "approve", "rhoai integrations"}

# ── Auth ──────────────────────────────────────────────────────────────────────
def _auth_header():
    email = os.environ.get("JIRA_EMAIL") or os.environ.get("ATLASSIAN_EMAIL")
    token = os.environ.get("JIRA_API_TOKEN") or os.environ.get("ATLASSIAN_API_TOKEN")
    if not email or not token:
        sys.exit(
            "ERROR: Set JIRA_EMAIL and JIRA_API_TOKEN (or ATLASSIAN_EMAIL / "
            "ATLASSIAN_API_TOKEN) environment variables."
        )
    creds = base64.b64encode(f"{email}:{token}".encode()).decode()
    return {"Authorization": f"Basic {creds}", "Accept": "application/json"}


def _get(path, params=None):
    url = JIRA_BASE + path
    if params:
        url += "?" + urlencode(params)
    req = Request(url, headers=_auth_header())
    with urlopen(req) as resp:
        return json.loads(resp.read())


# ── Jira fetching ──────────────────────────────────────────────────────────────
def fetch_issue(key):
    return _get(
        f"/rest/api/3/issue/{key}",
        {"fields": "*all", "expand": "renderedFields,names"},
    )


def fetch_children(key):
    try:
        data = _get(
            "/rest/api/3/search",
            {
                "jql": f'parent = "{key}"',
                "fields": "summary,status,issuetype,labels",
                "maxResults": 50,
            },
        )
        return data.get("issues", [])
    except Exception:
        return []


# ── HTML → plain text ─────────────────────────────────────────────────────────
class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("br", "p", "tr", "li", "h1", "h2", "h3", "h4", "td", "th"):
            self.parts.append("\n")
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html):
    p = _TextExtractor()
    p.feed(html or "")
    return "".join(p.parts)



def extract_section_text(markdown_text, heading):
    """Return the content of a named section from the markdown description, or '' if not found.

    Uses the raw markdown (fields.description) instead of rendered HTML to avoid
    HTML entity encoding issues (e.g. &amp;) and inner-tag anchors (e.g. <a name="...">).
    Matches ## or ### headings case-insensitively.
    """
    if not markdown_text:
        return ""
    pattern = rf'(?:^|\n)#{{1,4}}\s+{re.escape(heading)}\s*\n(.*?)(?=\n#{{1,4}}\s+|\Z)'
    m = re.search(pattern, markdown_text, re.DOTALL | re.IGNORECASE)
    if not m:
        return ""
    return m.group(1).strip()


def parse_impacted_teams(rendered_html):
    """Return team names from an 'Impacted Teams' <h> section in the description.

    Extracts <td> cells from the first column of the table under the heading,
    skipping the header row, separator rows, and external/N/A teams.
    """
    if not rendered_html:
        return []

    # Find the Impacted Teams <h> heading
    h_match = re.search(
        r'<h([1-4])[^>]*>(?:[^<]*<[^/][^>]*>)*\s*Impacted\s+Teams\s*(?:</[^>]+>)*\s*</h\1>',
        rendered_html, re.IGNORECASE
    )
    if not h_match:
        return []

    level = h_match.group(1)
    after = rendered_html[h_match.end():]
    next_h = re.search(rf'<h[1-{level}][^>]*>', after, re.IGNORECASE)
    section_html = after[:next_h.start()] if next_h else after

    teams = []
    # Extract first <td> of each row (table data, not header)
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', section_html, re.IGNORECASE | re.DOTALL)
    for row in rows:
        # Skip header rows (<th>)
        if re.search(r'<th', row, re.IGNORECASE):
            continue
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.IGNORECASE | re.DOTALL)
        if not cells:
            continue
        team_html = cells[0]
        team = html_to_text(team_html).strip()
        if not team or len(team) < 2:
            continue
        if re.search(r'N/A\s*\(external\)|external', team, re.IGNORECASE):
            continue
        # Skip obvious column-header text
        if re.match(r'^(?:Team|Owner\s+Team|Component|Status|Involvement)$', team, re.IGNORECASE):
            continue
        teams.append(team)
    return teams


# ── Component fuzzy matching ───────────────────────────────────────────────────
def _normalize(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def team_matches_components(team, components):
    team_n = _normalize(team)
    for c in components:
        cn = _normalize(c.get("name", ""))
        if team_n in cn or cn in team_n:
            return True
    # word-level overlap (words > 3 chars)
    team_words = {_normalize(w) for w in re.split(r"[\s/,]+", team) if len(w) > 3}
    for c in components:
        cn_words = {_normalize(w) for w in re.split(r"[\s/,\-]+", c.get("name", "")) if len(w) > 3}
        if team_words & cn_words:
            return True
    return False


# ── Result constants ──────────────────────────────────────────────────────────
PASS    = "PASS"
FAIL    = "FAIL"
WARN    = "WARN"
PENDING = "PENDING"   # LLM-evaluated checks — filled in by the skill


# ── Individual checks ─────────────────────────────────────────────────────────
def _field_value(fields, field_id):
    v = fields.get(field_id)
    if isinstance(v, dict):
        return v.get("value") or v.get("name") or str(v)
    if isinstance(v, list) and v:
        return ", ".join(
            (i.get("value") or i.get("name") or str(i)) if isinstance(i, dict) else str(i)
            for i in v
        )
    return v


def check_rice(fields):
    val = fields.get(F_RICE)
    if val is None or val == "" or val == 0:
        return FAIL, "RICE Score not set or zero"
    try:
        if float(val) == 0:
            return FAIL, "RICE Score is zero"
    except (TypeError, ValueError):
        pass
    return PASS, f"RICE Score = {val}"


def check_target_version(fields):
    val = _field_value(fields, F_TARGET_VER)
    if not val:
        return FAIL, "Target Version not set"
    return PASS, f"Target Version = {val}"


def check_release_type(fields):
    val = _field_value(fields, F_REL_TYPE)
    if not val:
        return FAIL, "Release Type not set"
    return PASS, f"Release Type = {val}"


def check_fix_versions(fields):
    fv = fields.get("fixVersions") or []
    if not fv:
        return FAIL, "No fix versions set"
    names = ", ".join(v.get("name", "?") for v in fv)
    return PASS, f"Fix Versions = {names}"


def check_color_status(fields):
    val = _field_value(fields, F_COLOR)
    if not val or val.lower() in ("not selected", "none"):
        return WARN, "Color Status not set"
    return PASS, f"Color Status = {val}"


def check_workflow_status(status_name):
    if status_name.lower() in ("backlog", "new"):
        return FAIL, f"Status is '{status_name}'"
    return PASS, f"Status = {status_name}"


def check_signoff_label(fields):
    labels = fields.get("labels") or []
    if SIGNOFF_LABEL in labels:
        return PASS, f"Label '{SIGNOFF_LABEL}' present"
    return WARN, f"Label '{SIGNOFF_LABEL}' absent"


def check_signoff_tickets(issue_links, children):
    found = []
    for lnk in issue_links:
        lt = lnk.get("type", {}).get("name", "").lower()
        linked = lnk.get("inwardIssue") or lnk.get("outwardIssue") or {}
        summary = linked.get("fields", {}).get("summary", "").lower()
        k = linked.get("key", "")
        if any(kw in lt or kw in summary for kw in SIGNOFF_KEYWORDS):
            found.append(f"{k}: {linked.get('fields', {}).get('summary', '')}")
    for child in children:
        summary = child.get("fields", {}).get("summary", "").lower()
        k = child.get("key", "")
        if any(kw in summary for kw in SIGNOFF_KEYWORDS):
            found.append(f"{k}: {child.get('fields', {}).get('summary', '')}")
    if found:
        return PASS, "Sign-off ticket(s): " + "; ".join(found[:3])
    all_linked = [
        (lnk.get("inwardIssue") or lnk.get("outwardIssue") or {}).get("key", "")
        for lnk in issue_links
    ]
    all_linked = [k for k in all_linked if k]
    detail = f"Linked issues: {', '.join(all_linked)}" if all_linked else "No linked issues"
    return WARN, f"No sign-off tickets found. {detail}"


def check_open_questions(fields_desc):
    text = extract_section_text(fields_desc or "", "Open Questions")
    return PENDING, text or "(section not found in description)"


def check_prerequisites(fields_desc):
    text = extract_section_text(fields_desc or "", "Prerequisites & Process Gates")
    return PENDING, text or "(section not found in description)"


def check_impacted_teams(fields, rendered_desc):
    components = fields.get("components") or []
    teams = parse_impacted_teams(rendered_desc or "")
    if not teams:
        return PASS, "No impacted teams found in description"
    unmatched = [t for t in teams if not team_matches_components(t, components)]
    if unmatched:
        return FAIL, "Teams without matching component: " + ", ".join(unmatched[:5])
    return PASS, f"All {len(teams)} team(s) matched to components"


def check_product_docs(fields):
    val = _field_value(fields, F_PROD_DOCS)
    if not val:
        return WARN, "Product Documentation Required field not set"
    components = fields.get("components") or []
    comp_names_lower = {_normalize(c.get("name", "")) for c in components}
    doc_present = any("doc" in cn for cn in comp_names_lower)
    if val.lower() in ("yes", "true", "1"):
        if doc_present:
            return PASS, "Docs required and 'Documentation' component present"
        return FAIL, "Docs required but 'Documentation' component missing"
    return PASS, f"Product Documentation Required = {val}"


# ── Check names ───────────────────────────────────────────────────────────────
CHECKS = [
    "RICE Score set",
    "Target Version set",
    "Release Type set",
    "Fix Versions set",
    "Color Status set",
    "Status not in Backlog/New",
    "strat-creator-human-sign-off label applied",
    "Sign-off tickets linked",
    "Open Questions",
    "Prerequisites & Process Gates",
    "Impacted Teams \u2192 Components match",
    'Product Docs field + "Documentation" component',
]


# ── Verdict parsing (for LLM-supplied overrides) ──────────────────────────────
def _parse_verdict(s):
    """Parse 'PASS:reason', 'FAIL:reason', or 'WARN:reason' from a CLI flag."""
    parts = s.split(":", 1)
    status_map = {"PASS": PASS, "FAIL": FAIL, "WARN": WARN}
    sev = status_map.get(parts[0].strip().upper(), PENDING)
    reason = parts[1].strip() if len(parts) > 1 else ""
    return (sev, reason)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    argv = sys.argv[1:]

    # Parse flags before positional args
    extract_mode  = False
    oq_override   = None
    prereq_override = None
    remaining     = []
    i = 0
    while i < len(argv):
        if argv[i] == "--extract-sections":
            extract_mode = True
        elif argv[i] in ("--oq-verdict", "--prereq-verdict") and i + 1 < len(argv):
            if argv[i] == "--oq-verdict":
                oq_override = argv[i + 1]
            else:
                prereq_override = argv[i + 1]
            i += 1
        else:
            remaining.append(argv[i])
        i += 1
    args = remaining

    # Load issue data
    if args and args[0] == "--from-json":
        if len(args) < 2:
            sys.exit("Usage: check.py --from-json <path>")
        with open(args[1]) as f:
            payload = json.load(f)
        issue    = payload.get("issue", {})
        children = payload.get("children", [])
    else:
        if not args:
            sys.exit("Usage: check.py RHAISTRAT-<number>  |  check.py --from-json <path>")
        key = args[0].strip().upper()
        if not re.match(r"RHAISTRAT-\d+$", key):
            sys.exit(f"Invalid key: {key}. Expected format: RHAISTRAT-1234")
        print(f"Fetching {key} …", file=sys.stderr)
        issue = fetch_issue(key)
        print("Fetching child issues …", file=sys.stderr)
        children = fetch_children(key)

    fields        = issue.get("fields", {})
    rendered      = issue.get("renderedFields", {})
    rendered_desc = rendered.get("description", "")
    fields_desc   = fields.get("description") or ""
    status_name   = fields.get("status", {}).get("name", "Unknown")
    summary       = fields.get("summary", "")
    issue_links   = fields.get("issuelinks") or []
    key           = issue.get("key", args[0] if args else "?")

    # --extract-sections: output section text for LLM evaluation, then exit
    if extract_mode:
        oq_text     = extract_section_text(fields_desc, "Open Questions")
        prereq_text = extract_section_text(fields_desc, "Prerequisites & Process Gates")
        print(json.dumps({
            "open_questions": oq_text or "(section not found)",
            "prerequisites":  prereq_text or "(section not found)",
        }))
        return

    # Resolve LLM-evaluated checks — use supplied verdict or fall back to PENDING
    oq_result     = _parse_verdict(oq_override)     if oq_override     else check_open_questions(fields_desc)
    prereq_result = _parse_verdict(prereq_override) if prereq_override else check_prerequisites(fields_desc)

    results = [
        check_rice(fields),
        check_target_version(fields),
        check_release_type(fields),
        check_fix_versions(fields),
        check_color_status(fields),
        check_workflow_status(status_name),
        check_signoff_label(fields),
        check_signoff_tickets(issue_links, children),
        oq_result,
        prereq_result,
        check_impacted_teams(fields, rendered_desc),
        check_product_docs(fields),
    ]

    fails   = sum(1 for sev, _ in results if sev == FAIL)
    warns   = sum(1 for sev, _ in results if sev == WARN)
    pending = sum(1 for sev, _ in results if sev == PENDING)

    if fails:
        overall = "NOT_READY"
    elif pending:
        overall = "PENDING"
    elif warns:
        overall = "READY_WITH_WARNINGS"
    else:
        overall = "READY"

    print(json.dumps({
        "key":     key,
        "summary": summary,
        "status":  status_name,
        "overall": overall,
        "counts":  {"fail": fails, "warn": warns, "pending": pending,
                    "pass": len(results) - fails - warns - pending},
        "checks":  [
            {"n": i + 1, "name": CHECKS[i], "status": sev, "detail": detail}
            for i, (sev, detail) in enumerate(results)
        ],
    }))


if __name__ == "__main__":
    main()
