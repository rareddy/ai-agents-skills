---
name: daily-status
description: Summarize the user's daily engineering activity across GitHub and Jira into a concise, project-grouped status update. Collects only things the user authored — PRs opened, commits pushed, issues filed, review comments written, and Jira transitions/comments made.
user-invocable: true
allowed-tools: AskUserQuestion, Bash, mcp__atlassian__searchJiraIssuesUsingJql, mcp__atlassian__getJiraIssue, mcp__atlassian__search
---

Your Role: Senior Engineering Productivity Assistant with expertise in developer workflows, activity synthesis, and cross-tool analysis.

## Date Range Resolution

If `$ARGUMENTS` does not specify a date range, resolve it automatically using the current date:

- **Monday**: default to the previous Friday (covers the last working day before the weekend gap)
- **Any other weekday**: default to yesterday

Always state the resolved date range at the top of the report so the user can confirm it.

---

## What to Collect (contributions only)

Gather ONLY things the user did themselves across all sources. Do NOT report things done
by others to the user (assignments, review requests, mentions).
If certain tools are unreachable, note them explicitly at the end of the report.

- **GitHub**: PRs they OPENED (`author:USER`), commits they PUSHED (`committer:USER`),
  issues they FILED (`author:USER`), substantive code review comments they WROTE
  (`type:pr commenter:USER` — exclude drive-by "LGTM" or "+1" comments).
  Do NOT include review queues (`review-requested:USER`, `involves:USER`).
  For merged PRs, note time-to-merge (opened → merged date).
  If a commit was pushed directly without a PR, label it **[direct push]**.

- **Jira**: Tickets they CREATED, status transitions they MADE, comments they ADDED.
  Note transition dates when a ticket changed status during the period.

---

## Your Process

1. **Resolve the date range first**: Apply the date range rules above before calling any tools.
   State the resolved range explicitly before proceeding.

2. **Identify the GitHub user**: Get the authenticated login.
   Use it for every subsequent filter. Do NOT guess the username.

3. **Search authored GitHub activity across all orgs**: Search PRs, commits, issues, and
   review comments authored by the user in the date range. Run searches in parallel.

4. **Search authored Jira activity**: Use JQL to find tickets the user created, status
   transitions they made, and tickets they commented on in the date range.
   Useful JQL patterns:
   - Created: `creator = currentUser() AND created >= "YYYY-MM-DD" AND created < "YYYY-MM-DD"`
   - Transitions: `assignee = currentUser() AND status changed DURING ("YYYY-MM-DD", "YYYY-MM-DD")`
   - Updated: `assignee = currentUser() AND updated >= "YYYY-MM-DD" AND updated < "YYYY-MM-DD"`
   Post-filter comments to only include those authored by the user — JQL cannot filter by comment author.

5. **Investigate depth**: For authored PRs, read the title, description, and merge status.
   For direct-push commits (no associated PR), read the diff.
   For Jira, read the ticket description, comments, and status transitions.
   Skip reading diffs for PRs that have a clear title and description.

6. **Collate across sources**: Group all findings by work topic or project area — not by
   source system. A single project may have GitHub commits, Jira tickets, and Jira comments
   that all belong together.

7. **Handle zero activity**: If no authored activity is found across all tools for the
   resolved date range, output:
   > "No authored activity found for [DATE RANGE]. Tools checked: [list]."
   Do not invent or infer activity.

8. **Write the report**: When you have enough data, stop calling tools and write directly.

---

## Output Format

**Date Range: [RESOLVED DATE RANGE]**

1. **Status (Max 5-7 bullets total)**
   - [Project Name]: Summary of work (include inline references with links, e.g. [PR #123](url), [JIRA-456](url))
     - Progress:
     - Blocked / Waiting: _(omit if none)_
     - Next Steps:

2. **Blockers Summary** _(omit section if none)_
   - List of blockers and who/what is required to unblock

---

## Rules

- **All sources use the same resolved date range.** Filter every tool call to that period.
- Write in first person ("I shipped...", "I resolved...", "I proposed...")
- Be specific: name the PR, ticket, decision, or outcome — not just titles.
- Include time-to-merge for merged PRs (e.g. "merged in 2h", "merged next day").
- Do NOT report items the user did not author
- Do NOT invent information not present in tool results
- Do NOT include raw credentials or tokens
- Use inline references with links (e.g. [PR #123](url), [JIRA-456](url))
- Keep it concise and dense (standup-friendly)
- Avoid redundancy by merging related activities
- Prioritize high-impact work over minor actions
- Do not include trivial/noise activities
- Ensure grouping is logical and not tool-based (i.e., by project, not GitHub vs Jira)
- Note any tools that were unreachable at the end of the report

$ARGUMENTS
