#!/usr/bin/env python3
"""
remaining-work report generator.

Usage:
    python3 report.py /tmp/remaining_work_EPIC-123.json

Input JSON structure:
    {
      "root": {"key": "…", "summary": "…", "status": {…}},
      "items": [
        {
          "key": "STORY-1", "parent_key": "EPIC-0", "depth": 1,
          "summary": "…", "issuetype": "Story",
          "status_name": "In Progress", "status_category": "indeterminate",
          "issuelinks": […],
          "comments": [{"body": "…", "created": "…"}, …]
        }, …
      ]
    }
"""

import json
import re
import sys

BLOCK_KEYWORDS = re.compile(
    r"\b(blocked|blocking|waiting on|depends on|can'?t proceed|pending)\b",
    re.IGNORECASE,
)


def status_label(cat, name):
    if cat == "done":
        return "✅ Done"
    if cat == "indeterminate":
        return "🔄 In Progress"
    return f"⏳ {name}" if name else "⏳ Not Started"


def detect_blocking(issuelinks, comments):
    """Return a short blocking string, or '' if none detected."""
    notes = []

    # 1. Formal "is blocked by" links where the linked issue is not done
    for lnk in issuelinks or []:
        ltype = (lnk.get("type") or {}).get("name", "").lower()
        if "blocked" not in ltype:
            continue
        linked = lnk.get("inwardIssue") or lnk.get("outwardIssue") or {}
        lkey = linked.get("key", "")
        lcat = (linked.get("fields") or {}).get("status", {}).get(
            "statusCategory", {}
        ).get("key", "")
        if lkey and lcat != "done":
            lname = (linked.get("fields") or {}).get("status", {}).get("name", "?")
            notes.append(f"Blocked by: {lkey} ({lname})")

    # 2. Any linked issue that is not done (non-blocking link types too)
    if not notes:
        for lnk in issuelinks or []:
            linked = lnk.get("inwardIssue") or lnk.get("outwardIssue") or {}
            lkey = linked.get("key", "")
            lcat = (linked.get("fields") or {}).get("status", {}).get(
                "statusCategory", {}
            ).get("key", "")
            if lkey and lcat not in ("done", ""):
                lname = (linked.get("fields") or {}).get("status", {}).get("name", "?")
                ltype_name = (lnk.get("type") or {}).get("name", "")
                notes.append(f"Linked ({ltype_name}): {lkey} ({lname})")
                if len(notes) >= 2:
                    break

    # 3. Comment scan (last 5 comments)
    for comment in (comments or [])[-5:]:
        body = comment.get("body") or ""
        if isinstance(body, dict):
            # ADF format — flatten to text
            body = _flatten_adf(body)
        m = BLOCK_KEYWORDS.search(body)
        if m:
            # Extract the sentence around the keyword
            start = max(0, m.start() - 40)
            end = min(len(body), m.end() + 40)
            snippet = body[start:end].replace("\n", " ").strip()
            if start > 0:
                snippet = "…" + snippet
            if end < len(body):
                snippet = snippet + "…"
            notes.append(f'Comment: "{snippet}"')
            break

    return "; ".join(notes[:2])


def _flatten_adf(node):
    """Recursively extract plain text from Atlassian Document Format (ADF)."""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""
    parts = []
    if node.get("type") == "text":
        parts.append(node.get("text", ""))
    for child in node.get("content") or []:
        parts.append(_flatten_adf(child))
    return " ".join(p for p in parts if p)


def truncate(s, n=60):
    return s if len(s) <= n else s[: n - 1] + "…"


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: report.py <json-file>")

    with open(sys.argv[1]) as f:
        data = json.load(f)

    root = data.get("root", {})
    items = data.get("items", [])

    # Separate open vs closed
    open_items = [i for i in items if i.get("status_category") != "done"]
    closed_count = len(items) - len(open_items)
    in_progress = sum(1 for i in open_items if i.get("status_category") == "indeterminate")
    not_started = len(open_items) - in_progress

    # Header
    root_key = root.get("key", "?")
    root_summary = root.get("summary", "")
    root_status = (root.get("status") or {}).get("name", "?")
    print(f"## Remaining Work: {root_key} — {root_summary}")
    print()
    print(
        f"**Root Status**: {root_status}  |  "
        f"**Open**: {len(open_items)}  |  "
        f"**In Progress**: {in_progress}  |  "
        f"**Not Started**: {not_started}  |  "
        f"**Completed (hidden)**: {closed_count}"
    )
    print()

    if not open_items:
        print("_No open work items found — all children are complete._")
        return

    # Table
    print("| Depth | Key | Type | Summary | Assignee | Status | Blocking |")
    print("|-------|-----|------|---------|----------|--------|----------|")

    for item in open_items:
        depth = item.get("depth", 1)
        key = item.get("key", "?")
        itype = item.get("issuetype", "?")
        summary = truncate(item.get("summary", ""), 60)
        assignee = item.get("assignee") or "—"
        scat = item.get("status_category", "new")
        sname = item.get("status_name", "?")
        label = status_label(scat, sname)
        blocking = detect_blocking(item.get("issuelinks"), item.get("comments"))
        print(f"| L{depth} | {key} | {itype} | {summary} | {assignee} | {label} | {blocking} |")


if __name__ == "__main__":
    main()
