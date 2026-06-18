---
name: slack-login
description: Extracts Slack XOXC and XOXD tokens by opening a browser for the user to log in, then configures the Slack MCP server for both Claude Code and Cursor. Use when the user says "Slack login", "extract Slack tokens", "set up Slack MCP", "configure Slack", "refresh Slack tokens", or wants to connect their Slack workspace to the AI assistant.
---

# Slack Login

## Instructions

### 1. Check prerequisites

1. Verify Python 3.11+ is available: `python3 --version`
2. Check if the `playwright` pip package is installed: `python3 -c "import playwright"`. If it fails, install it globally: `sudo pip3 install playwright`
3. Check if Chromium is installed for Playwright: `python3 -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(headless=True); b.close(); p.stop()"`. If it fails, run: `playwright install chromium`

### 2. Determine workspace URL

Parse the user's prompt for a workspace URL or name:

- If the prompt contains a full URL (e.g., `https://redhat.enterprise.slack.com`), use that URL.
- If the prompt contains a workspace name but not a full URL, construct it: `https://<name>.slack.com`
- Otherwise default to `https://app.slack.com/client/`

### 3. Run the extraction script

Run the bundled script with a long Bash timeout (600 seconds / 10 minutes) to allow for slow SSO/MFA logins:

```bash
python3 scripts/slack-login.py --workspace <URL> --json --output ~/.slack_tokens.env --timeout 300
```

The script path is relative to this skill's directory.

**Before running**, tell the user:

> A browser window is about to open. Log in to your Slack workspace there, wait until the workspace fully loads (you see channels and messages), then come back here. The script will automatically detect when you're logged in and extract the tokens.

**Important**: The script prints status messages to stderr and the JSON result to stdout. Parse the JSON from stdout.

### 4. Parse the result

- If the script exits 0, parse the JSON from stdout. It contains `xoxc_token`, `xoxd_token`, and `team_id`.
- If the script fails (non-zero exit), show the stderr output to the user and suggest:
  - Make sure they fully logged in and waited for the workspace to load
  - Try running again — the browser profile is persistent so SSO may be faster next time
  - Check network/VPN connectivity

### 5. Configure the Slack MCP server

#### 5a. Configure Claude Code MCP (`~/.claude/mcp.json`)

Read `~/.claude/mcp.json` (create it if it doesn't exist — start with `{"mcpServers": {}}`).

Add or update the `slack` entry under `mcpServers`:

```json
{
  "mcpServers": {
    "slack": {
      "command": "<HOME>/slack-mcp/.venv/bin/python",
      "args": ["slack_mcp_server.py"],
      "cwd": "<HOME>/slack-mcp",
      "env": {
        "SLACK_XOXC_TOKEN": "<xoxc_token>",
        "SLACK_XOXD_TOKEN": "<xoxd_token>"
      }
    }
  }
}
```

Replace `<HOME>` with the actual home directory path, and fill in the extracted tokens.

#### 5b. Configure Cursor MCP (`.cursor/mcp.json` in project root)

Read `.cursor/mcp.json` in the project root (create it if it doesn't exist — start with `{"mcpServers": {}}`).

Add or update the `slack` entry under `mcpServers` with the same structure as above.

### 6. Verify and report

Tell the user:

1. What was configured (show the paths of both MCP config files updated)
2. That they should **restart their editor** or **reload MCP servers** for the changes to take effect
3. Suggest testing with: "Try asking me to `use the slack whoami tool` to verify the connection works"

## Example prompts

- "Slack login"
- "extract Slack tokens"
- "set up Slack MCP"
- "Slack login https://redhat.enterprise.slack.com"
- "refresh my Slack tokens"
