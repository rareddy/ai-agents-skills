# Tool Access Preferences

When a skill or task needs to interact with GitHub, Jira, Slack, or Google Workspace, use the following access strategies in priority order.

## Default Permission Policy

**Read operations** (search, list, get, view, fetch) may run without prompting.
**Write operations** (create, update, edit, delete, comment, transition, post, push) MUST ask the user for confirmation before executing. State what you are about to do and wait for approval.

## GitHub

Use the `gh` CLI via Bash. The user is authenticated via `gh auth`.

- Identity: `gh api /user --jq .login`
- Search PRs/commits/issues: `gh search prs`, `gh search commits`, `gh search issues`
- PR details: `gh pr view NUMBER --repo ORG/REPO --json ...`
- Commit details: `gh api /repos/ORG/REPO/commits/SHA`

## Jira

1. **Atlassian MCP** (preferred): Use `mcp__atlassian__searchJiraIssuesUsingJql`,
   `mcp__atlassian__getJiraIssue`, and related read tools if available.
2. **REST API via Bash**: If MCP is not available, check for credentials in the environment
   (`JIRA_EMAIL`/`JIRA_API_TOKEN` or `ATLASSIAN_EMAIL`/`ATLASSIAN_API_TOKEN`) and
   `JIRA_URL` (e.g. `https://yourorg.atlassian.net`). Use `curl` with basic auth:
   ```
   curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
     "$JIRA_URL/rest/api/3/search?jql=<JQL>&fields=summary,status,comment,created,updated"
   ```
3. If neither is available, skip Jira and note it as unreachable.

## Slack

1. **Slack MCP** (preferred): Use `mcp__slack__*` tools if available.
2. If not available, skip Slack and note it as unreachable.

## Google Workspace

Use the `gws` CLI via Bash.

- Files owned and edited by the user: `gws drive files list --params '{"q": "\"me\" in owners and modifiedTime > \"YYYY-MM-DDT00:00:00Z\" and modifiedTime < \"YYYY-MM-DDT00:00:00Z\"", "fields": "files(id,name,mimeType,modifiedTime)", "pageSize": 50}'`
- Document details: `gws docs documents get --params '{"documentId": "DOC_ID"}'`
- If `gws` returns an auth error (exit code 2), run `gws auth login` and walk the user through the login flow. Do NOT skip as unreachable until login has been attempted.
