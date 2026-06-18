#!/usr/bin/env python3
"""
Slack Token Extractor — Non-interactive edition for AI agent use.

Extracts Slack XOXC and XOXD tokens using Playwright automation.
Designed to run without any stdin interaction: opens a browser,
waits for the user to log in, polls for tokens automatically,
and saves the result.

Requirements:
    pip install playwright
    playwright install chromium

Usage:
    python slack-login.py --workspace https://mycompany.slack.com --json
    python slack-login.py --json --output ~/.slack_tokens.env --timeout 300
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    print("Error: Playwright not installed.", file=sys.stderr)
    print("Install with: pip install playwright && playwright install chromium", file=sys.stderr)
    sys.exit(1)


DEFAULT_PROFILE_DIR = Path.home() / ".slack-token-extractor" / "browser-profile"
DEFAULT_OUTPUT_FILE = ".slack_tokens.env"


def _resolve_team_and_xoxc_from_page(page) -> tuple[str | None, str | None]:
    """Best-effort team ID + xoxc from URL and Slack web client storage (incl. Enterprise Grid).

    Returns (None, None) when the page is mid-navigation and the execution context is gone.
    """
    try:
        return page.evaluate(
            """() => {
    const out = { teamId: null, token: null };
    const href = location.href;
    let m = href.match(/\\/client\\/(T[A-Z0-9]+)/);
    if (m) out.teamId = m[1];

    function pickTeamToken(obj) {
        if (!obj || typeof obj !== 'object') return;
        const teams = obj.teams;
        if (!teams || typeof teams !== 'object') return;
        for (const [tid, data] of Object.entries(teams)) {
            if (!data || typeof data !== 'object') continue;
            const tok = data.token;
            if (typeof tok === 'string' && tok.startsWith('xoxc-')) {
                if (!out.token) {
                    out.token = tok;
                    if (!out.teamId && typeof tid === 'string') out.teamId = tid;
                }
            }
        }
    }

    function tryParse(raw) {
        if (!raw || typeof raw !== 'string') return;
        try { pickTeamToken(JSON.parse(raw)); } catch (e) {}
    }

    tryParse(localStorage.getItem('localConfig_v2'));
    for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (!k) continue;
        if (k === 'localConfig_v2') continue;
        if (k.includes('localConfig') || k.includes('slack') || k === 'teams') {
            tryParse(localStorage.getItem(k));
        }
    }
    for (let i = 0; i < sessionStorage.length; i++) {
        const k = sessionStorage.key(i);
        if (!k) continue;
        if (k.includes('slack') || k.includes('Config')) {
            tryParse(sessionStorage.getItem(k));
        }
    }

    if (!out.teamId) {
        m = href.match(/\\/(T[A-Z0-9]{8,})\\//);
        if (m) out.teamId = m[1];
    }
    return [out.teamId, out.token];
}"""
        )
    except PlaywrightError:
        return None, None


def _wait_for_slack_client_ready(page, max_wait_s: int = 300) -> tuple[str | None, str | None]:
    """Poll until URL or storage exposes a team id and xoxc token.

    Handles mid-navigation context destruction by catching errors and retrying.
    """
    deadline = time.monotonic() + max_wait_s
    step_s = 3.0
    last_team, last_tok = None, None
    while time.monotonic() < deadline:
        last_team, last_tok = _resolve_team_and_xoxc_from_page(page)
        if last_tok and last_team:
            return last_team, last_tok
        if last_tok and not last_team:
            return None, last_tok
        try:
            page.wait_for_timeout(int(step_s * 1000))
        except PlaywrightError:
            time.sleep(step_s)
    return last_team, last_tok


def _lookup_team_id_for_xoxc(page, xoxc_token: str) -> str | None:
    """Find workspace key in localStorage whose token matches the given xoxc value."""
    try:
        return page.evaluate(
            """(want) => {
    function scan(obj) {
        if (!obj || typeof obj !== 'object') return null;
        const teams = obj.teams;
        if (!teams || typeof teams !== 'object') return null;
        for (const [tid, data] of Object.entries(teams)) {
            if (data && data.token === want) return tid;
        }
        return null;
    }
    try {
        const hit = scan(JSON.parse(localStorage.getItem('localConfig_v2') || '{}'));
        if (hit) return hit;
    } catch (e) {}
    for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (!k) continue;
        try {
            const raw = localStorage.getItem(k);
            if (!raw || raw.charAt(0) !== '{') continue;
            const hit = scan(JSON.parse(raw));
            if (hit) return hit;
        } catch (e) {}
    }
    return null;
}""",
            xoxc_token,
        )
    except PlaywrightError:
        return None


def extract_tokens(
    workspace_url: str = "https://app.slack.com/client/",
    headless: bool = False,
    profile_dir: Path = DEFAULT_PROFILE_DIR,
    timeout: int = 300,
) -> dict | None:
    """
    Extract XOXC token and XOXD cookie from Slack.
    Non-interactive: polls for tokens automatically after the browser opens.

    Args:
        workspace_url: Slack workspace URL to open
        headless: Run browser in headless mode (requires existing session)
        profile_dir: Directory for persistent browser profile
        timeout: Max seconds to wait for login/tokens (default 300)

    Returns:
        Dictionary with 'xoxc_token', 'xoxd_token', and 'team_id' or None on failure
    """
    profile_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        print(f"Launching browser (headless={headless})...", file=sys.stderr)
        print(f"Profile directory: {profile_dir}", file=sys.stderr)

        browser = p.chromium.launch_persistent_context(
            str(profile_dir),
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-dev-shm-usage",
            ],
            viewport={"width": 1280, "height": 800},
        )

        try:
            page = browser.pages[0] if browser.pages else browser.new_page()

            print(f"Navigating to {workspace_url}...", file=sys.stderr)
            try:
                page.goto(workspace_url, wait_until="domcontentloaded", timeout=60000)
            except PlaywrightError as e:
                print(f"Error: Navigation failed: {e}", file=sys.stderr)
                print(
                    "Check the URL, network/VPN, and TLS (corporate proxies sometimes break Chromium).",
                    file=sys.stderr,
                )
                return None

            # Wait for page to load
            try:
                page.wait_for_load_state("domcontentloaded", timeout=30000)
            except PlaywrightTimeout:
                pass
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PlaywrightTimeout:
                pass

            # Check if we need to log in — just print a message and start polling
            current_url = page.url
            if (
                "signin" in current_url
                or "sign_in" in current_url
                or "ssb/signin" in current_url
            ):
                if headless:
                    print("Error: Not logged in and running in headless mode.", file=sys.stderr)
                    print("Run without --headless first to log in.", file=sys.stderr)
                    return None

                print("", file=sys.stderr)
                print("=" * 60, file=sys.stderr)
                print("A browser window has opened.", file=sys.stderr)
                print("Please log in to Slack there.", file=sys.stderr)
                print(f"Waiting up to {timeout} seconds for login...", file=sys.stderr)
                print("=" * 60, file=sys.stderr)

                # Poll for the URL to change away from signin
                signin_deadline = time.monotonic() + timeout
                while time.monotonic() < signin_deadline:
                    try:
                        cur = page.url
                    except PlaywrightError:
                        time.sleep(3)
                        continue
                    if not ("signin" in cur or "sign_in" in cur or "ssb/signin" in cur):
                        break
                    try:
                        page.wait_for_timeout(3000)
                    except PlaywrightError:
                        time.sleep(3)

                # Wait for page to settle after login
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=30000)
                except PlaywrightTimeout:
                    pass
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except PlaywrightTimeout:
                    pass

            # Enterprise Grid stores tokens under app.slack.com, not *.enterprise.slack.com.
            # Re-acquire page reference in case the redirect opened a new tab.
            try:
                current_host = (urlparse(page.url).netloc or "").lower()
            except PlaywrightError:
                current_host = ""
                page = browser.pages[-1] if browser.pages else page

            if current_host.endswith(".enterprise.slack.com") or "/client/" not in getattr(page, 'url', ''):
                target = "https://app.slack.com/client/"
                print(f"Opening Slack web client: {target}", file=sys.stderr)
                try:
                    page.goto(target, wait_until="domcontentloaded", timeout=60000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except PlaywrightTimeout:
                        pass
                except PlaywrightError as e:
                    print(f"Warning: navigation to {target} failed: {e}", file=sys.stderr)
                    # The page may have been replaced — re-acquire
                    if browser.pages:
                        page = browser.pages[-1]
                        print(f"Switched to page: {page.url}", file=sys.stderr)

            print(f"Waiting for Slack session (team ID + xoxc) up to {timeout}s...", file=sys.stderr)
            team_id, xoxc_token = _wait_for_slack_client_ready(page, max_wait_s=timeout)

            if xoxc_token and not team_id:
                team_id = _lookup_team_id_for_xoxc(page, xoxc_token)

            if not xoxc_token:
                # Fallback: try to find in page content
                try:
                    xoxc_token = page.evaluate("""() => {
                        const match = document.body.innerHTML.match(/"token":"(xoxc-[^"]+)"/);
                        return match ? match[1] : null;
                    }""")
                except PlaywrightError:
                    xoxc_token = None
                if xoxc_token and not team_id:
                    team_id = _lookup_team_id_for_xoxc(page, xoxc_token)

            if not team_id:
                print("Error: Could not determine team ID.", file=sys.stderr)
                print(f"Current URL: {page.url}", file=sys.stderr)
                return None

            if not xoxc_token:
                print("Error: Could not find XOXC token.", file=sys.stderr)
                print("Make sure you're logged in and the workspace is fully loaded.", file=sys.stderr)
                return None

            print(f"Found team ID: {team_id}", file=sys.stderr)
            print(f"Found XOXC token: {xoxc_token[:25]}...{xoxc_token[-10:]}", file=sys.stderr)

            # Extract XOXD cookie
            print("Extracting XOXD token from cookies...", file=sys.stderr)
            cookies = browser.cookies()
            xoxd_token = None

            for cookie in cookies:
                domain = cookie.get("domain") or ""
                if cookie.get("name") == "d" and "slack.com" in domain:
                    xoxd_token = cookie["value"]
                    break

            if not xoxd_token:
                print("Error: Could not find 'd' cookie (XOXD token).", file=sys.stderr)
                return None

            print(f"Found XOXD token: {xoxd_token[:25]}...{xoxd_token[-10:]}", file=sys.stderr)

            return {
                "xoxc_token": xoxc_token,
                "xoxd_token": xoxd_token,
                "team_id": team_id,
            }
        finally:
            browser.close()


def save_tokens(tokens: dict, output_file: str) -> None:
    """Save tokens to a .env file with secure permissions."""
    with open(output_file, "w") as f:
        f.write(f"# Slack tokens extracted by slack-login.py\n")
        f.write(f"# Team ID: {tokens['team_id']}\n\n")
        f.write(f"SLACK_MCP_XOXC_TOKEN={tokens['xoxc_token']}\n")
        f.write(f"SLACK_MCP_XOXD_TOKEN={tokens['xoxd_token']}\n")

    os.chmod(output_file, 0o600)
    print(f"Tokens saved to: {output_file}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Extract Slack XOXC and XOXD tokens using Playwright (non-interactive)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --json                      # Extract and print JSON to stdout
  %(prog)s --headless --json           # Headless (needs prior login)
  %(prog)s --workspace https://myco.slack.com --json
  %(prog)s --json --output ~/.slack_tokens.env
        """,
    )
    parser.add_argument(
        "--workspace", "-w",
        default="https://app.slack.com/client/",
        help="Slack workspace URL (default: app.slack.com)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run in headless mode (requires existing session)",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output file for tokens (auto-saves when provided)",
    )
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=DEFAULT_PROFILE_DIR,
        help=f"Browser profile directory (default: {DEFAULT_PROFILE_DIR})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print tokens as JSON to stdout (for agent parsing)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Max seconds to wait for login/tokens (default: 300)",
    )

    args = parser.parse_args()

    print("=" * 60, file=sys.stderr)
    print("Slack Token Extractor — Non-interactive", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    tokens = extract_tokens(
        workspace_url=args.workspace,
        headless=args.headless,
        profile_dir=args.profile_dir,
        timeout=args.timeout,
    )

    if not tokens:
        sys.exit(1)

    print("", file=sys.stderr)
    print("Extraction successful!", file=sys.stderr)

    # Always save if --output is provided
    if args.output:
        save_tokens(tokens, args.output)

    # Print JSON to stdout for agent parsing
    if args.json:
        print(json.dumps(tokens))
    else:
        print(f"SLACK_MCP_XOXC_TOKEN={tokens['xoxc_token']}")
        print(f"SLACK_MCP_XOXD_TOKEN={tokens['xoxd_token']}")
        print(f"SLACK_TEAM_ID={tokens['team_id']}")

    print("Done!", file=sys.stderr)


if __name__ == "__main__":
    main()
