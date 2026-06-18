---
name: jira-status
description: Show remaining open work for any Jira ticket by traversing its full child/grandchild hierarchy. Detects blocking dependencies via issue links and comments. Renders a tabular report of incomplete items. Use when asked about remaining work, open tasks, what's left, or blocking issues on a ticket.
user-invocable: true
allowed-tools: AskUserQuestion, Bash, Write, mcp__atlassian__getJiraIssue, mcp__atlassian__searchJiraIssuesUsingJql
---

You are a remaining-work reporter. Traverse the full Jira hierarchy of a ticket and render a tabular report of open items with blocking information.

## Step 1: Get the ticket key

Parse `$ARGUMENTS` for a Jira key matching `[A-Z]+-\d+`. If none found, ask:

> Which Jira ticket do you want to check remaining work for? (e.g., EPIC-123)

## Step 2: Fetch the root ticket

Call `mcp__atlassian__getJiraIssue`:
- `cloudId`: `"https://redhat.atlassian.net"`
- `issueIdOrKey`: `{KEY}`
- `fields`: `["summary", "status", "issuetype", "issuelinks"]`
- `responseContentFormat`: `"markdown"`

## Step 3: BFS traversal to collect all descendants

Use batched JQL to minimise API calls. Maintain:
- `all_items` — flat list of every descendant discovered
- `open_keys` — keys of open tickets (for later comment fetching)
- `frontier` — current level's keys to expand

**Initialize**: `frontier = [KEY]`

**Loop** (repeat until frontier is empty):
1. Call `mcp__atlassian__searchJiraIssuesUsingJql`:
   - `cloudId`: `"https://redhat.atlassian.net"`
   - `jql`: `parent in ({comma-separated frontier keys}) ORDER BY key`
   - `fields`: `["summary", "status", "issuetype", "issuelinks", "labels", "parent", "assignee"]`
   - `maxResults`: 100
2. For each returned issue, record:
   - `key`, `parent_key` (from `fields.parent.key`), `depth` (parent's depth + 1)
   - `summary`, `issuetype.name`
   - `status_name` = `fields.status.name`
   - `status_category` = `fields.status.statusCategory.key` (`"done"`, `"indeterminate"`, `"new"`, etc.)
   - `issuelinks` = `fields.issuelinks`
   - `assignee` = `fields.assignee.displayName` (or `null` if unassigned)
3. Append all issues to `all_items`.
4. Set `frontier` = keys of issues where `status_category != "done"` (open only — no need to expand closed subtrees).
5. Stop if `frontier` is empty OR if `all_items` has grown past 200 (safety cap — warn the user and stop).

**Root depth** = 0. Direct children of root = depth 1, their children = depth 2, etc.

## Step 4: Fetch comments for open items

Identify open items: all items where `status_category != "done"`. Cap at 100 for comment fetching; warn if exceeded.

For each open item, call `mcp__atlassian__getJiraIssue`:
- `cloudId`: `"https://redhat.atlassian.net"`
- `issueIdOrKey`: `{item.key}`
- `fields`: `["comment", "issuelinks"]`

Merge the returned `fields.comment.comments` (last 5 only) and updated `fields.issuelinks` back into the item.

> Note: MCP responses for large tickets may be persisted to disk. If you get a "too large" message, use `python3 -c "import json; d=json.load(open('PATH')); ..."` to extract `fields.comment.comments[-5:]` and `fields.issuelinks`.

Make these calls in parallel where possible to reduce wall-clock time.

## Step 5: Write temp file

Write `/tmp/remaining_work_{KEY}.json`:

```json
{
  "root": {
    "key": "{KEY}",
    "summary": "{root summary}",
    "status": {root status object}
  },
  "items": [
    {
      "key": "…",
      "parent_key": "…",
      "depth": 1,
      "summary": "…",
      "issuetype": "Story",
      "assignee": "Jane Smith",
      "status_name": "In Progress",
      "status_category": "indeterminate",
      "issuelinks": […],
      "comments": [{"body": "…", "created": "…"}, …]
    }
  ]
}
```

Use the Write tool or `python3 -c "import json; ..."` to write the file.

## Step 6: Run the report script

```
python3 .claude/skills/jira-status/report.py /tmp/remaining_work_{KEY}.json
```

## Step 7: Display output

Print the script's stdout verbatim — it is already formatted markdown. Do not add commentary before or after.

---

## Style

Be terse. Do not narrate steps or announce what you are doing between tool calls. No filler text.
