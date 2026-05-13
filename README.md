# granola-action-items

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://makeapullrequest.com)


A [Claude Code](https://claude.com/claude-code) skill that turns your Granola meeting recordings into a tracked action-item system with daily briefings.

[Granola](https://granola.ai) records and transcribes your meetings. This skill reads Granola's local cache, extracts the action items, tracks them across days, and surfaces what's due, what's overdue, and what's gone stale on your radar.

## Why this exists

Granola gives you the meeting transcript. It doesn't tell you what you committed to two weeks ago and never did. That's where action items go to die. This skill is the watchdog.

## What it does

1. **Monitor** — every 30 minutes during business hours, check Granola for new meetings
2. **Extract** — parse panels and transcripts for action items, attribute to the speaker
3. **Track** — store items with owner, due date, priority, status
4. **Brief** — daily morning briefing of what's due, what's overdue, what's stale
5. **Review** — Friday weekly roll-up of completed, open, overdue, and new items

## Requirements

- [Claude Code](https://claude.com/claude-code)
- [Granola](https://granola.ai) installed on a Mac (the skill reads its local cache file)
- Python 3.9+

The skill runs locally by default. If you want an always-on agent monitoring meetings, you can also run it from a different machine and pull the Granola cache via SSH.

## Install

```bash
git clone https://github.com/nickyc1/granola-action-items.git ~/.claude/skills/granola-action-items
```

Optional: copy `config/people.example.json` to `config/people.json` and map your teammates' names to their Slack user IDs. The skill will then output `<@SLACK_ID>` tags ready to paste into Slack.

Restart Claude Code. The skill is available.

## Usage

In Claude Code:

```
Use granola-action-items to extract action items from my last meeting.
```

```
Run a daily briefing on my open action items.
```

```
Pull all meetings from the last 7 days, summarize each, and roll up the action items.
```

For automated runs, schedule the meeting monitor every 30 minutes during business hours via cron, launchd, or any agent scheduler.

## Hallucination prevention

The skill enforces five non-negotiable rules — see `SKILL.md`:

1. **One meeting at a time** — never load two transcripts simultaneously
2. **Verify every action item against the transcript** — grep the keyword, if it's not there, delete the item
3. **Distinguish meeting-specific facts** — don't bleed context across meetings
4. **Post-generation audit** — programmatic grep against the transcript before sending
5. **Corrections** — if a hallucination is caught after posting, correct it immediately and log the error

LLMs hallucinate action items confidently. The grep-verification step is the only thing that reliably catches them.

## Repo structure

```
granola-action-items/
├── SKILL.md                              # the skill prompt Claude Code reads
├── scripts/
│   ├── fetch_granola.py                  # parse Granola cache, local or SSH
│   └── extract_actions.py                # extract action items from meeting JSON
├── config/
│   └── people.example.json               # name → slack_id map (copy to people.json)
├── templates/
│   ├── daily-briefing.md
│   ├── weekly-review.md
│   └── meeting-summary.md
└── README.md
```

## License

MIT — see [LICENSE](LICENSE).

Built by [Nick Christensen](https://github.com/nickyc1).
