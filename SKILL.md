---
name: granola-action-items
description: Parse Granola meeting recordings, extract action items, and run a daily/weekly briefing of open items to Slack or any other channel. Use when asked to "process Granola meetings", "extract action items", "what are my open follow-ups", "daily briefing", or "weekly review of meetings".
---

# Granola Action Items

Monitors your Granola meetings, extracts summaries and action items, and runs a daily / weekly briefing of open items.

## Architecture

```
[Granola app on Mac] → cache-v3.json → fetch_granola.py → extract_actions.py → action-items.json → daily briefing
```

Two modes for the data fetch:

- **Local** (default): the skill runs on the same Mac that has Granola installed. Reads the cache file directly.
- **SSH** (optional): the skill runs on a different machine and pulls the cache file via SCP from your Granola Mac. Useful if you let an always-on agent handle the monitoring.

## Scripts

### `scripts/fetch_granola.py`

Reads Granola's `cache-v3.json` and parses out meetings, transcripts, panels, attendees.

```bash
# Local mode (default — assumes Granola is on this machine)
python3 scripts/fetch_granola.py --list
python3 scripts/fetch_granola.py --since "2026-04-01T00:00:00"
python3 scripts/fetch_granola.py --meeting-id <UUID>

# Pass an explicit local cache file
python3 scripts/fetch_granola.py --local /path/to/cache-v3.json --list

# SSH mode (Granola lives on a different machine)
export GRANOLA_SSH_HOST=you@your-mac.local
python3 scripts/fetch_granola.py --ssh --list
```

Output: JSON with `id, title, created_at, attendees, transcript, panels`.

### `scripts/extract_actions.py`

Reads meeting JSON from stdin or a file, extracts action items.

```bash
python3 scripts/fetch_granola.py --meeting-id <UUID> | python3 scripts/extract_actions.py
```

Output: JSON array of `{person, slack_id, action, due_date, priority}`.

Optionally maps people to Slack user IDs if you populate `config/people.json` (copy `config/people.example.json` to start).

## Workflows

### Workflow 1: Meeting monitor (every 30 min during business hours)

1. Read `state.json` to get the `last_checked` timestamp
2. Run: `python3 scripts/fetch_granola.py --since <last_checked>`
3. For each new meeting not in `processed_meetings`:
   - Save full meeting data to `data/meetings/YYYY-MM-DD-<slug>.md`
   - Generate a summary: key discussion points, decisions, action items
   - Notify the operator (Slack, WhatsApp, email — wire whichever you use)
   - Add the meeting ID to `processed_meetings`
4. Update `last_checked`

### Workflow 2: Daily briefing (weekdays at 8am)

Format and send to your chosen channel:

```
☀️ {Day}, {Month} {Date}

🔴 Top Priority (due today/overdue):
• item — from {meeting} ({date})

🟡 This Week:
• item — from {meeting} ({date})

📋 Open (no deadline):
• item — from {meeting} ({date})

👀 Waiting On Others:
• Person: item — from {meeting} ({date})

💀 Stale (3+ days, no deadline):
• item — from {meeting} ({date}) — {days} days old
```

See `templates/daily-briefing.md` for the full format.

### Workflow 3: Weekly review (Friday 4pm)

A roll-up of completed items, overdue items, still-open, new-this-week, and stale items. Format in `templates/weekly-review.md`.

## Hallucination prevention (mandatory)

These rules are non-negotiable. Every summary or action item list must pass these checks before sending.

### Rule 1: One meeting at a time

- Process each meeting in complete isolation
- Never have two meetings' transcripts loaded simultaneously
- Never copy action items or topics between meetings

### Rule 2: Verify every action item against the transcript

Before posting any summary, for each action item:

1. Grep the raw transcript for keywords related to the action
2. Confirm someone explicitly committed ("I will", "I'll", "let me", or was directly assigned)
3. Attribute to the person who said it or was assigned, not who suggested it
4. If the keyword doesn't appear in this meeting's transcript, DELETE the action item

**Not an action item:** "We should look into X" / "That would be cool" / "Maybe we could"

**Is an action item:** "I'll message him" / "Let me finalize that doc" / "Can you set up X this week?"

### Rule 3: Distinguish meeting-specific facts

For each factual claim in the summary:

- It must be directly stated or clearly implied in this meeting's transcript
- If you're not sure it was said in this meeting, leave it out
- When in doubt, mark as `[unattributed]` rather than guess

### Rule 4: Post-generation audit

After drafting a summary, for each action item, run:

```bash
grep -i "<keyword>" /tmp/meeting_<id>_transcript.txt
```

If a grep returns nothing, the action item is hallucinated. Remove it.

### Rule 5: Corrections

If a hallucination is caught after posting:

- Immediately post a correction to the same channel
- Update the saved meeting file
- Log the error with: date, meeting, what was wrong, root cause

## Action item schema

Each item in `data/action-items.json`:

```json
{
  "id": "uuid",
  "owner": "Alice",
  "slack_id": "U0ABCDEF123",
  "description": "Send the deal scorecard to the GP",
  "source_meeting": "GP sync",
  "source_date": "2026-04-12",
  "date_assigned": "2026-04-12",
  "due_date": "2026-04-19",
  "priority": "normal",
  "status": "open",
  "notes": ""
}
```

## Nudge logic

- Items open 3+ days with no deadline → surface in daily briefing under 💀 Stale
- Items past due date → always show first as 🔴
- When the operator says something is done → mark `status: "done"`, add `completed_date`, and note the source

## Completion tracking

When processing a new meeting transcript:

1. Load open items from `data/action-items.json`
2. Scan the transcript for context clues that an open item was completed
3. If evidence is found, mark the item `done` with `completed_date` and note: "Completed per <meeting> on <date>"

## Error handling

| Situation | Behavior |
|---|---|
| Granola Mac offline (SSH mode) | SCP times out in 10s. Log and retry next cycle. |
| No new meetings | Normal. Just update `last_checked`. |
| Empty panels / transcript | Meeting may still be in progress. Skip and check next cycle. |
| Parse errors | Log to stderr, do not crash the monitoring loop. |
