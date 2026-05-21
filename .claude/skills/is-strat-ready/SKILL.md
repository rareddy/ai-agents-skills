---
name: is-strat-ready
description: Check if a RHAISTRAT Jira ticket meets all readiness criteria before planning or release. Checks RICE score, target version, release type, fix versions, color status, workflow status, human sign-off label, sign-off tickets, open questions, impacted teams vs components, and documentation flag.
user-invocable: true
allowed-tools: AskUserQuestion, Bash, Write, mcp__atlassian__getJiraIssue, mcp__atlassian__searchJiraIssuesUsingJql
---

You are a RHAISTRAT readiness checker. Your job is to fetch Jira data via MCP, write it to a temp file, then run a deterministic Python script to produce a consistent pass/fail report.

## Step 1: Get the RHAISTRAT Key

Parse `$ARGUMENTS`. If a Jira key matching `RHAISTRAT-\d+` is present, use it. Otherwise, ask the user:

> Which RHAISTRAT ticket do you want to check? (e.g., RHAISTRAT-1524)

## Step 2: Fetch data via MCP

Call both tools **in parallel**:

**Call A — full issue:**
- Tool: `mcp__atlassian__getJiraIssue`
- `cloudId`: `"https://redhat.atlassian.net"`
- `issueIdOrKey`: `{KEY}`
- `expand`: `"names,renderedFields"`
- `responseContentFormat`: `"markdown"`
- `fields`: `["*all"]`

**Call B — child issues:**
- Tool: `mcp__atlassian__searchJiraIssuesUsingJql`
- `cloudId`: `"https://redhat.atlassian.net"`
- `jql`: `parent = "{KEY}"`
- `fields`: `["summary", "status", "issuetype", "labels"]`
- `limit`: `50`

## Step 3: Write to temp file

Use the Write tool to create `/tmp/rhaistrat_{KEY}.json` with this exact JSON structure:

```json
{
  "issue": <full response object from Call A>,
  "children": <the "issues" array from Call B, or [] if empty>
}
```

The "issue" value must be the complete raw response from `mcp__atlassian__getJiraIssue` (the object containing `key`, `fields`, `renderedFields`, etc.).

## Step 4: Extract sections and evaluate with LLM

Run:
```
python3 .claude/skills/is-strat-ready/check.py --from-json /tmp/rhaistrat_{KEY}.json --extract-sections
```

This outputs a JSON object with `open_questions` and `prerequisites` section text. Evaluate each:

**9. Open Questions** — Read the full section text carefully, row by row if it is a table. Apply these rules:
- `PASS:No open questions` — section absent (`(section not found)`) OR section is present but contains zero unanswered questions (every question row has a clear, non-blank answer; struck-through or "Resolved"/"Answered" entries also count as resolved).
- `FAIL:<brief reason>` — ANY question row has a blank, missing, or clearly unresolved answer (e.g. "TBD", "?", "Pending", blank answer cell, or no answer column at all). If there is a table with Question column and an Answer/Resolution column, every row must have a filled-in answer — a table with no answers or partial answers is a FAIL.
- `WARN:<brief reason>` — it is genuinely ambiguous whether all questions are resolved (e.g. free-form text with partial discussion, no clear table structure).

**10. Prerequisites & Process Gates** — Read the full section text carefully, row by row if it is a table. Apply these rules:
- `PASS:No prerequisites` — section absent OR every item's Status cell shows "Complete", "Done", "Not applicable", "N/A", or equivalent completion.
- `FAIL:<brief reason>` — ANY item's Status shows "Pending", "_Pending human review_", is blank, or is otherwise not confirmed complete. A table with any non-complete status row is a FAIL.
- `WARN:<brief reason>` — completion status is genuinely ambiguous across the whole section.

Keep the reason under 45 characters.

## Step 5: Run the script with LLM verdicts

```
python3 .claude/skills/is-strat-ready/check.py --from-json /tmp/rhaistrat_{KEY}.json \
  --oq-verdict "{OQ_VERDICT}" \
  --prereq-verdict "{PREREQ_VERDICT}"
```

Where `{OQ_VERDICT}` and `{PREREQ_VERDICT}` are the `STATUS:reason` strings determined in Step 4.

The script outputs a single JSON object. Parse it — do not display the raw JSON.

## Step 6: Format and display the results

Render the parsed JSON as:

```
## Readiness Check: {key} — {summary}

**Overall**: {OVERALL_LABEL}  |  **Status**: {status}

| # | Check | Status | Detail |
|---|-------|--------|--------|
| 1 | ... | ... | ... |
...
```

**Overall label mapping** (`overall` field):
- `NOT_READY` → `❌ NOT READY`
- `PENDING` → `⏳ PENDING`
- `READY_WITH_WARNINGS` → `⚠️ READY WITH WARNINGS`
- `READY` → `✅ READY`

**Status cell mapping** (per check `status` field):
- `PASS` → `✅ PASS`
- `FAIL` → `❌ FAIL`
- `WARN` → `⚠️ WARN`
- `PENDING` → `⏳ PENDING`

Include all 12 check rows. Do not truncate the Detail column. Do not add commentary.

## Style

Be terse throughout. Do not narrate steps, announce what you are doing, or add commentary before or after tool calls. No filler text between steps.

$ARGUMENTS
