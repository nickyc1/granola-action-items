#!/usr/bin/env python3
"""Extract action items from Granola meeting JSON.

Reads meeting JSON from stdin or a file argument. Outputs JSON array of
action items, each: {person, slack_id, action, due_date, priority}.

Optionally maps people to Slack user IDs via a `people.json` config file.
"""

import argparse
import json
import os
import re
import sys


DEFAULT_PEOPLE_CONFIG = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "config",
    "people.json",
)


def load_people(path):
    """Load name → slack_id mapping from a JSON config file."""
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
        # Normalize keys to lowercase
        return {k.lower(): v for k, v in data.items()}
    except Exception as e:
        print(f"WARN: failed to load people config from {path}: {e}", file=sys.stderr)
        return {}


def find_slack_id(name, people):
    """Look up a Slack user ID by name (case-insensitive fuzzy match)."""
    if not name or not people:
        return None
    lower = name.strip().lower()
    if lower in people:
        return people[lower]
    for key, sid in people.items():
        if key.split()[0] == lower:
            return sid
    for key, sid in people.items():
        if lower in key or key in lower:
            return sid
    return None


def extract_actions_from_panels(panels):
    """Extract action items from panel text. Returns list of raw action strings."""
    actions = []
    action_panel_keywords = ["action", "todo", "to-do", "next step", "follow", "task"]

    for title, text in panels.items():
        is_action_panel = any(k in title.lower() for k in action_panel_keywords)
        lines = text.split("\n") if "\n" in text else text.split(". ")
        for line in lines:
            line = line.strip().strip("•-▪▸► ")
            if not line:
                continue
            if is_action_panel and len(line) > 10:
                actions.append(line)
            elif any(kw in line.lower() for kw in [
                "will ", "needs to", "should ", "action:", "todo:",
                "follow up", "deadline", "by next", "responsible",
            ]):
                actions.append(line)
    return actions


def parse_action(raw_action, people):
    """Parse a raw action string into structured data."""
    person = None
    slack_id = None

    patterns = [
        r"^(\w+(?:\s\w+)?)\s*(?:will|to|should|needs to)\s",
        r"^(\w+(?:\s\w+)?)\s*[-:]\s",
        r"(?:assigned to|owner|responsible)\s*[-:]?\s*(\w+(?:\s\w+)?)",
        r"@(\w+)",
    ]
    for pat in patterns:
        m = re.search(pat, raw_action, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            sid = find_slack_id(candidate, people)
            if sid:
                person = candidate.title()
                slack_id = sid
                break
            elif not person:
                person = candidate.title()

    due_date = None
    date_patterns = [
        r"by\s+(\w+\s+\d{1,2}(?:st|nd|rd|th)?)",
        r"due\s*:?\s*(\d{4}-\d{2}-\d{2})",
        r"by\s+(next\s+\w+day)",
        r"by\s+(EOD|end of (?:day|week))",
        r"deadline\s*:?\s*(\S+)",
    ]
    for pat in date_patterns:
        m = re.search(pat, raw_action, re.IGNORECASE)
        if m:
            due_date = m.group(1)
            break

    return {
        "person": person or "Unassigned",
        "slack_id": slack_id,
        "action": raw_action,
        "due_date": due_date,
        "priority": "normal",
    }


def main():
    parser = argparse.ArgumentParser(description="Extract action items from Granola meeting JSON")
    parser.add_argument("meeting_file", nargs="?",
                        help="Path to meeting JSON file (or '-' for stdin, the default)")
    parser.add_argument("--people", default=DEFAULT_PEOPLE_CONFIG,
                        help="Path to people.json (name → slack_id map)")
    args = parser.parse_args()

    if args.meeting_file and args.meeting_file != "-":
        with open(args.meeting_file) as f:
            meeting = json.load(f)
    else:
        meeting = json.load(sys.stdin)

    if isinstance(meeting, list):
        if not meeting:
            print(json.dumps([]))
            return
        meeting = meeting[0]

    people = load_people(args.people)

    panels = meeting.get("panels", {})
    transcript = meeting.get("transcript", "")

    raw_actions = extract_actions_from_panels(panels)

    if transcript:
        for line in transcript.split("\n"):
            line_text = re.sub(r"^\[(?:microphone|system)\]\s*", "", line).strip()
            if any(kw in line_text.lower() for kw in [
                "action item", "todo", "i'll take that", "i'll handle", "let's make sure",
            ]):
                raw_actions.append(line_text)

    seen = set()
    actions = []
    for raw in raw_actions:
        if raw.lower() in seen:
            continue
        seen.add(raw.lower())
        actions.append(parse_action(raw, people))

    print(json.dumps(actions, indent=2))


if __name__ == "__main__":
    main()
