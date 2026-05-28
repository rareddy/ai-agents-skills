#!/usr/bin/env python3
"""
slack_token_refresh.py — Validate Slack web tokens from ~/.claude/mcp.json.

Reads xoxc/xoxd tokens, tests them against auth.test, and outputs JSON.
If tokens are missing or expired, exits with a non-zero code and a message
telling the user to run /slack-login to refresh them.

Usage:
    python3 slack_token_refresh.py

Output (stdout):
    {"status": "valid",   "user": "rareddy", "team": "redhat"}
    {"status": "expired", "message": "Run /slack-login to refresh tokens"}
"""

import json
import sys
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

MCP_CONFIG   = Path.home() / ".claude" / "mcp.json"
XOXC_KEY     = "SLACK_XOXC_TOKEN"
XOXD_KEY     = "SLACK_XOXD_TOKEN"


# ── Module 1: Token I/O ───────────────────────────────────────────────────────

def read_tokens():
    """Return (xoxc, xoxd) from ~/.claude/mcp.json, or (None, None)."""
    try:
        cfg = json.loads(MCP_CONFIG.read_text())
        env = cfg.get("mcpServers", {}).get("slack", {}).get("env", {})
        return env.get(XOXC_KEY), env.get(XOXD_KEY)
    except (FileNotFoundError, json.JSONDecodeError):
        return None, None


# ── Module 2: Token validation ────────────────────────────────────────────────

def validate_tokens(xoxc, xoxd):
    """
    Call auth.test with xoxc/xoxd. Returns dict with 'ok', 'user', 'team'
    on success, or raises ValueError with the error string on failure.
    """
    if not xoxc or not xoxd:
        raise ValueError("missing")

    req = Request(
        "https://slack.com/api/auth.test",
        headers={
            "Authorization": f"Bearer {xoxc}",
            "Cookie": f"d={xoxd}",
        },
    )
    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except (URLError, json.JSONDecodeError) as e:
        raise ValueError(f"network error: {e}") from e

    if not data.get("ok"):
        raise ValueError(data.get("error", "unknown"))

    return {"user": data.get("user"), "team": data.get("team")}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    xoxc, xoxd = read_tokens()

    try:
        info = validate_tokens(xoxc, xoxd)
    except ValueError as e:
        print(json.dumps({
            "status": "expired",
            "reason": str(e),
            "message": "Slack tokens are missing or expired. Run /slack-login to refresh them.",
        }))
        sys.exit(1)

    print(json.dumps({"status": "valid", "user": info["user"], "team": info["team"]}))


if __name__ == "__main__":
    main()
