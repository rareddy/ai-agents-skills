# Tool Access Preferences

When a skill or task needs to interact with GitHub, Jira, or Slack, use the following access strategies in priority order.

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
