---
name: clone-sign-off-tickets
description: Clone sign-off ticket templates (Dev Preview, Tech Preview, or GA) from a RHAISTRAT ticket's release type. Creates sign-off tickets in RHOAIENG with cleaned titles, sets component, creates child tasks and their subtasks, and links to the STRAT ticket. Detects if sign-off tickets already exist.
user-invocable: true
allowed-tools: AskUserQuestion, mcp__jira__jira_get_issue, mcp__jira__jira_search, mcp__jira__jira_create_issue, mcp__jira__jira_update_issue, mcp__jira__jira_create_issue_link, mcp__jira__jira_get_link_types
---

# SAFETY RULES — STRICTLY ENFORCED

**You MUST obey these rules. Violations are unrecoverable.**

1. **NEVER delete any JIRA issue.** No delete tool is available to you.
2. **NEVER modify the STRAT ticket.** It is read-only.
3. **NEVER modify the template ticket or its subtasks.** They are read-only.
4. **NEVER modify any pre-existing JIRA issue.**
5. **The ONLY write operations allowed are:**
   - `jira_create_issue` — to create the clone parent and its subtasks
   - `jira_update_issue` — ONLY on keys returned from your own `jira_create_issue` calls in this session
   - `jira_create_issue_link` — to link the new clone to the STRAT ticket
6. **Before any write call, verify the target key was created by you in this session.** If unsure, stop and ask the user.

---

## Step 1: Get the RHAISTRAT Key

Parse `$ARGUMENTS`. If a Jira key matching `RHAISTRAT-\d+` is present, use it. Also look for optional overrides:
- `component=<name>` — override component

If no RHAISTRAT key is found, ask:

> Which RHAISTRAT ticket should I use? (e.g., RHAISTRAT-1524)

## Step 2: Fetch the STRAT Ticket

Fetch the STRAT issue:
- Tool: `jira_get_issue`
- `issue_key`: `{STRAT_KEY}`

Extract these values from the response:
- **Release Type** — field `customfield_10851` (known ID). Read `.value` or `.name` from the field object.
- **Component(s)** — from `fields.components[].name`
If the STRAT ticket has no component set, inform the user and ask them to provide a value.

If the Release Type field (`customfield_10851`) is empty or not set, display the following and **stop**:

```
## Missing Release Type

**STRAT ticket:** {STRAT_KEY} — {STRAT summary}

The Release Type field is not set on this STRAT ticket. Cannot determine which template to clone.

Please set the Release Type (Dev Preview, Tech Preview, or GA) on the STRAT ticket and try again.
```

**Do not proceed further.** Exit the skill.

## Step 2b: Check for Existing Sign-Off Tickets

Inspect the STRAT ticket's `issuelinks` field. Look for any linked **RHOAIENG** issues that are **Epics** (issue type = Epic). Any RHOAIENG Epic linked to the STRAT is likely a sign-off clone — regardless of its summary text, since clones get renamed after creation.

If any linked RHOAIENG Epics are found, display them and **ask** the user:

```
## Possible Existing Sign-Off Tickets

**STRAT ticket:** {STRAT_KEY} — {STRAT summary}

The following RHOAIENG Epic(s) are already linked to this STRAT:

| Key | Summary | Status | Link Type |
|-----|---------|--------|-----------|
| {key} | {summary} | {status} | {link_type} |
```

Options:
- "These are sign-off tickets — stop" (Recommended)
- "These are NOT sign-off tickets — proceed"

If the user confirms they are sign-off tickets, **stop and exit**. If the user says proceed, continue to Step 3.

## Step 3: Map Release Type to Template

Use this lookup table (match case-insensitively):

| Release Type | Template Key |
|---|---|
| Dev Preview | RHOAIENG-31244 |
| Technology Preview | RHOAIENG-31290 |
| GA | RHOAIENG-31303 |

Also handle common variations:
- "dev preview", "DP" → RHOAIENG-31244
- "technology preview", "Tech Preview", "TP" → RHOAIENG-31290
- "ga", "General Availability" → RHOAIENG-31303

If the release type does not match any entry, show the raw value to the user and ask them to pick: Dev Preview, Technology Preview, or GA.

## Step 4: Confirm with User

Display a summary and ask for confirmation using `AskUserQuestion`:

```
## Clone Sign-Off Tickets

**STRAT ticket:** {STRAT_KEY} — {STRAT summary}
**Release Type:** {release_type}
**Template to clone:** {TEMPLATE_KEY}
**Component:** {component} (from STRAT)
```

Options:
- "Proceed with these values" (Recommended)
- "Override component"

If the user overrides, ask for the new value, then re-confirm.

## Step 5: Fetch Template and Full Hierarchy

**5a** — Fetch in parallel:

**Call A — template issue:**
- Tool: `jira_get_issue`
- `issue_key`: `{TEMPLATE_KEY}`

**Call B — template children (level 1):**
- Tool: `jira_search`
- `jql`: `parent = "{TEMPLATE_KEY}" ORDER BY created ASC`
- `limit`: `50`

Extract from template:
- **issue_type**: the issue type name (e.g., "Epic")
- **summary**: the title (to be cleaned in Step 6)
- **description**: full description (copy as-is to clone)

Extract from each child:
- **key**, **summary**, **description**, **issue_type**

**5b** — For each child issue from 5a that is NOT a Sub-task (i.e., issue types like Task or Story), fetch its own children:
- Tool: `jira_search`
- `jql`: `parent = "{CHILD_KEY}" ORDER BY created ASC`
- `limit`: `50`

These are the **grandchildren** (typically Sub-tasks). Run these searches in parallel for all applicable children.

The result is a tree:
```
Template (Epic)
├── Child 1 (Task) — from 5a
│   ├── Grandchild 1a (Sub-task) — from 5b
│   └── Grandchild 1b (Sub-task) — from 5b
└── Child 2 (Task) — from 5a
    ├── Grandchild 2a (Sub-task) — from 5b
    └── Grandchild 2b (Sub-task) — from 5b
```

## Step 6: Clean Titles

**Parent title** — take the template's summary and apply these transformations (case-insensitive):
- `[Template]` → remove
- `[Component/Feature Name]` → replace with `[{component}/{STRAT summary}]` where `{component}` is the first component from the STRAT and `{STRAT summary}` is the STRAT ticket's summary
- Handle any casing variations: `[Component/feature Name]`, `[Component/Feature name]`, etc.
- Collapse multiple spaces to a single space
- Trim leading/trailing whitespace

Example: `[Template] Tech Preview - ODH and RHOAI Integrations [Component/feature Name]` with component "AI Hub" and STRAT summary "Add Eagle3 Models to RHOAI Catalog" → `Tech Preview - ODH and RHOAI Integrations [AI Hub/Add Eagle3 Models to RHOAI Catalog]`

**Child and subtask titles** — for each child or subtask:
- Remove `[CLONE]` prefix (case-insensitive)
- Remove leading ` - ` or ` – ` after removing `[CLONE]`
- Trim leading/trailing whitespace

## Step 7: Create Clone Parent

Call `jira_create_issue`:
- `project_key`: `"RHOAIENG"`
- `summary`: cleaned parent title from Step 6
- `issue_type`: same as the template's issue type
- `description`: template's description (verbatim)
- `components`: component value (from STRAT or user override)

**Record the returned issue key as `CLONE_KEY`.** This is the ONLY pre-existing issue you may now modify (along with subtasks you create below).

## Step 8: Create Child Tasks and Their Sub-tasks

**8a — Create child Tasks** under the clone parent Epic.

For each child from Step 5a, call `jira_create_issue`:
- `project_key`: `"RHOAIENG"`
- `summary`: cleaned child title (from Step 6)
- `issue_type`: same as the template child's issue type (e.g., "Task")
- `description`: child's description (copy as-is; use empty string if none)
- `components`: same component as the parent clone
- `additional_fields`: `{"parent": {"key": "{CLONE_KEY}"}}`

**Record each created child key as `CHILD_CLONE_KEY_N`.**

**8b — Create grandchild Sub-tasks** under each cloned child Task.

For each grandchild from Step 5b, call `jira_create_issue`:
- `project_key`: `"RHOAIENG"`
- `summary`: cleaned grandchild title (from Step 6)
- `issue_type`: `"Sub-task"`
- `description`: grandchild's description (copy as-is; use empty string if none)
- `components`: same component as the parent clone
- `additional_fields`: `{"parent": {"key": "{CHILD_CLONE_KEY_N}"}}` (the cloned child, NOT the clone Epic)

**Record all created keys.** These plus `CLONE_KEY` are the only issues you may modify.

If there are more than 10 total issues to create, inform the user of progress (e.g., "Creating issue 5 of 15...").

## Step 9: Link to STRAT

**Call A** — Find the parent-child link type:
- Tool: `jira_get_link_types`
- Look for a link type with "parent" or "child" in its name or inward/outward descriptions

**Call B** — Create the link (after A returns):
- Tool: `jira_create_issue_link`
- `link_type`: the parent-child link type name from Call B
- Set the keys so that STRAT is the parent and CLONE is the child:
  - If the link type's inward description contains "is child of": `inward_issue_key` = `{CLONE_KEY}`, `outward_issue_key` = `{STRAT_KEY}`
  - If the link type's inward description contains "is parent of": `inward_issue_key` = `{STRAT_KEY}`, `outward_issue_key` = `{CLONE_KEY}`
  - Use your judgment based on the link type definitions to ensure the STRAT appears as parent

## Step 10: Display Summary

```
## Sign-Off Tickets Created

**Clone Epic:** {CLONE_KEY} — {cleaned title}
**STRAT parent:** {STRAT_KEY}
**Release Type:** {release_type}
**Component:** {component}
**Total issues created:** {total_count}

{CLONE_KEY} — {cleaned epic title}
├── {CHILD_CLONE_KEY_1} — {cleaned child 1 title}
│   ├── {GRANDCHILD_KEY_1a} — {cleaned grandchild title}
│   └── {GRANDCHILD_KEY_1b} — {cleaned grandchild title}
└── {CHILD_CLONE_KEY_2} — {cleaned child 2 title}
    ├── {GRANDCHILD_KEY_2a} — {cleaned grandchild title}
    └── {GRANDCHILD_KEY_2b} — {cleaned grandchild title}

**Link:** {CLONE_KEY} is child of {STRAT_KEY}
```

## Style

Be terse. Do not narrate steps or add filler text between tool calls. Show the confirmation summary (Step 4) and the final summary (Step 10), nothing else.

$ARGUMENTS
