#!/usr/bin/env python3
"""Fetch and parse Granola meeting data.

Two modes:
- --local PATH    Read from a local cache file (default behavior on the machine running Granola)
- --ssh           Pull the cache file from a remote machine over SCP (set GRANOLA_SSH_HOST env var)

Granola stores its data at ~/Library/Application Support/Granola/cache-v3.json on the
machine where the Granola app is installed.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime


DEFAULT_GRANOLA_PATH = "~/Library/Application Support/Granola/cache-v3.json"


def ssh_copy_granola(ssh_host, remote_path, dest_path):
    """SCP the Granola cache file to a local temp path."""
    try:
        result = subprocess.run(
            [
                "scp",
                "-o", "ConnectTimeout=10",
                "-o", "StrictHostKeyChecking=accept-new",
                f"{ssh_host}:{remote_path}",
                dest_path,
            ],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            print(f"ERROR: SCP failed: {result.stderr.strip()}", file=sys.stderr)
            return False
        return True
    except subprocess.TimeoutExpired:
        print("ERROR: SCP timed out (remote may be offline)", file=sys.stderr)
        return False
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return False


def extract_prosemirror_text(node):
    """Recursively extract plain text from a ProseMirror document node."""
    if not node or not isinstance(node, dict):
        return ""
    parts = []
    if node.get("type") == "text":
        parts.append(node.get("text", ""))
    for child in node.get("content", []):
        parts.append(extract_prosemirror_text(child))
    return " ".join(parts).strip()


def parse_granola(file_path):
    """Parse the Granola cache-v3.json and return documents, transcripts, panels."""
    with open(file_path, "r") as f:
        raw = json.load(f)

    cache_str = raw.get("cache", "{}")
    if isinstance(cache_str, str):
        cache = json.loads(cache_str)
    else:
        cache = cache_str

    state = cache if "documents" in cache else cache.get("state", cache)
    documents = state.get("documents", {})
    transcripts = state.get("transcripts", {})
    document_panels = state.get("documentPanels", {})
    return documents, transcripts, document_panels


def build_meeting(doc_id, doc, transcripts, panels):
    """Build a clean meeting dict from raw Granola data."""
    segments = transcripts.get(doc_id, [])
    if isinstance(segments, dict):
        segments = segments.get("segments", [])
    transcript_text = "\n".join(
        f"[{s.get('source', '?')}] {s.get('text', '')}" for s in segments
    ) if segments else ""

    panel_data = panels.get(doc_id, {})
    panel_summaries = {}
    if isinstance(panel_data, dict):
        for panel_key, panel in panel_data.items():
            if isinstance(panel, dict):
                title = panel.get("title", panel_key)
                content = panel.get("content", {})
                text = extract_prosemirror_text(content)
                if text:
                    panel_summaries[title] = text

    people = doc.get("people", [])
    if isinstance(people, list):
        attendees = [
            p.get("name", p.get("email", "unknown")) if isinstance(p, dict) else str(p)
            for p in people
        ]
    else:
        attendees = []

    cal = doc.get("google_calendar_event", {}) or {}

    return {
        "id": doc_id,
        "title": doc.get("title", "Untitled"),
        "created_at": doc.get("created_at", ""),
        "updated_at": doc.get("updated_at", ""),
        "transcribe": doc.get("transcribe", False),
        "attendees": attendees,
        "calendar_event": {
            "summary": cal.get("summary", ""),
            "start": cal.get("start", ""),
            "end": cal.get("end", ""),
        } if cal else None,
        "transcript": transcript_text,
        "panels": panel_summaries,
    }


def main():
    parser = argparse.ArgumentParser(description="Fetch Granola meeting data")
    parser.add_argument("--list", action="store_true", help="List recent meetings (title, date, id)")
    parser.add_argument("--since", type=str, help="ISO timestamp — only meetings created after this")
    parser.add_argument("--meeting-id", type=str, help="Fetch a specific meeting by UUID")
    parser.add_argument("--limit", type=int, default=20, help="Max meetings to return for --list")
    parser.add_argument("--local", type=str, help="Path to a local cache-v3.json file")
    parser.add_argument("--ssh", action="store_true",
                        help="Pull from a remote machine via SCP. Set GRANOLA_SSH_HOST env var.")
    parser.add_argument("--ssh-host", type=str, default=os.environ.get("GRANOLA_SSH_HOST"),
                        help="SSH host string (user@host). Default: $GRANOLA_SSH_HOST")
    parser.add_argument("--ssh-path", type=str, default=DEFAULT_GRANOLA_PATH,
                        help=f"Remote Granola cache path (default: {DEFAULT_GRANOLA_PATH})")
    args = parser.parse_args()

    if args.ssh:
        if not args.ssh_host:
            print("ERROR: --ssh requires --ssh-host or $GRANOLA_SSH_HOST", file=sys.stderr)
            sys.exit(2)
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tmp.close()
        cache_path = tmp.name
        if not ssh_copy_granola(args.ssh_host, args.ssh_path, cache_path):
            sys.exit(1)
        cleanup = True
    elif args.local:
        cache_path = os.path.expanduser(args.local)
        cleanup = False
    else:
        cache_path = os.path.expanduser(DEFAULT_GRANOLA_PATH)
        cleanup = False

    try:
        documents, transcripts, document_panels = parse_granola(cache_path)
    except FileNotFoundError:
        print(f"ERROR: Granola cache not found at {cache_path}", file=sys.stderr)
        print("Tip: Granola must be installed and have run at least once on this machine.",
              file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to parse Granola data: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if cleanup and os.path.exists(cache_path):
            os.unlink(cache_path)

    if not documents:
        print(json.dumps({"error": "No documents found in Granola data"}))
        sys.exit(1)

    if args.meeting_id:
        doc = documents.get(args.meeting_id)
        if not doc:
            print(json.dumps({"error": f"Meeting {args.meeting_id} not found"}))
            sys.exit(1)
        meeting = build_meeting(args.meeting_id, doc, transcripts, document_panels)
        print(json.dumps(meeting, indent=2))
        return

    meetings = []
    for doc_id, doc in documents.items():
        created = doc.get("created_at", "")
        title = doc.get("title", "Untitled")

        if args.since and created:
            try:
                since_dt = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                if created_dt <= since_dt:
                    continue
            except (ValueError, TypeError):
                pass

        if args.list:
            meetings.append({"id": doc_id, "title": title, "created_at": created})
        else:
            meetings.append(build_meeting(doc_id, doc, transcripts, document_panels))

    meetings.sort(key=lambda m: m.get("created_at", ""), reverse=True)

    if args.list:
        meetings = meetings[:args.limit]

    print(json.dumps(meetings, indent=2))


if __name__ == "__main__":
    main()
