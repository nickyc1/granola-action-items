# Hallucination Prevention

LLMs hallucinate action items confidently. A meeting transcript becomes a set of action items, and one or two of them never actually happened — but the LLM produced them with full confidence. If you post those to Slack, you damage trust both with the team (who can't find where they "committed") and with the agent (it gets dismissed as unreliable).

This doc is the deeper protocol for catching hallucinations before they ship.

## Why this matters more than other AI outputs

In most AI workflows, a hallucination is annoying. In a meeting tracker, a hallucination is a credibility-destroying event:

- Someone reads "Erik: send the deal scorecard by Friday" in Slack
- They DM Erik to follow up
- Erik says he never committed to that
- Now Erik distrusts the meeting notes
- Now the team distrusts every future Slack post from the agent
- The skill is dead

You only get one shot at this. Get the prevention rules right.

## The five-rule protocol

### Rule 1: One meeting at a time

Process each meeting in complete isolation. Never have two meetings' transcripts loaded simultaneously.

Why: LLMs cross-contaminate. A topic discussed in meeting A bleeds into the summary of meeting B if both are in the same context.

Implementation: clear the working context between meetings. If the skill is processing a batch, run each meeting in a fresh subprocess or fresh LLM call.

### Rule 2: Verify every action item against the transcript

Before posting any summary, for each action item the LLM produced:

1. Extract 2-3 keywords from the action item
2. Grep the raw transcript for those keywords (case-insensitive)
3. Confirm someone explicitly committed: "I will," "I'll," "let me," or was directly assigned
4. Attribute to the person who said it or was assigned, not who suggested it
5. If the keywords don't appear in this meeting's transcript: DELETE the action item

Code pattern:

```python
def verify_action_items(action_items, transcript):
    verified = []
    removed = []
    transcript_lower = transcript.lower()
    
    for action in action_items:
        # Extract keywords (4+ char words)
        keywords = [w for w in re.findall(r'\b\w{4,}\b', action['action'].lower())]
        # At least one keyword must appear
        found = any(kw in transcript_lower for kw in keywords)
        # Plus a commitment phrase nearby
        has_commitment = any(
            phrase in transcript_lower 
            for phrase in ["i'll", "i will", "let me", "i can", "i'll take", "i can handle"]
        )
        if found and has_commitment:
            verified.append(action)
        else:
            removed.append({**action, 'reason': 'no transcript match'})
    
    return verified, removed
```

The pattern: keyword presence + commitment phrase presence. Both required.

### Rule 3: Distinguish meeting-specific facts

For each factual claim the summary makes (number, date, name, decision):

- It must be directly stated or clearly implied in THIS meeting's transcript
- If you're not sure it was said here, leave it out
- When in doubt, mark as `[unattributed]` rather than guess

Common contamination sources:

- LLM remembers something from a previous meeting and applies it here
- LLM fills in plausible-sounding numbers ("the deal closed last quarter") that weren't in the transcript
- LLM attributes a quote to the wrong person

The fix: for any factual claim in the output, the verifier grep step (Rule 2) should also confirm the specific noun / number / name appears in the transcript.

### Rule 4: Post-generation audit

After the LLM produces the summary, run a programmatic audit:

```python
def audit_summary(summary_obj, transcript):
    issues = []
    
    # Check every action item against the transcript
    for action in summary_obj['action_items']:
        keywords = extract_keywords(action['action'])
        if not any(kw in transcript.lower() for kw in keywords):
            issues.append(f"Action item not grounded: {action['action']}")
    
    # Check every named person was actually in the meeting
    attendees_lower = [a.lower() for a in summary_obj['attendees']]
    for action in summary_obj['action_items']:
        owner = action.get('owner', '').lower()
        if owner and owner not in [a.split()[0] for a in attendees_lower]:
            issues.append(f"Attributed to non-attendee: {owner}")
    
    # Check no decisions reference dates / numbers outside the transcript
    for decision in summary_obj['decisions']:
        # Extract any specific noun / number
        # Verify it appears in the transcript
        pass
    
    return issues
```

If the audit returns issues, either:

1. Strip the problematic line and continue
2. Re-run the LLM with explicit instructions about what NOT to include
3. Halt and ask the operator to review manually

The skill defaults to option 1 (strip and continue) plus logging the removed items.

### Rule 5: Corrections protocol

If a hallucination is caught after the summary was posted:

1. Immediately post a correction to the same channel ("Correction: I incorrectly attributed [X] to [person]. They did not commit to that.")
2. Update the saved meeting file
3. Log the error in `data/hallucination-log.md` with: date, meeting, what was wrong, root cause

The log isn't just documentation — it's the dataset that lets you improve the prevention rules over time. Patterns in the log surface new probe questions for the verifier.

## What an action item IS

Use these as the heuristic during extraction:

- **"I'll [verb] [object]"** — explicit personal commitment
- **"Let me [verb]"** — same
- **"Can you [verb] by [date]?"** + acknowledgment ("sure," "yeah," "I'll do it") — assigned commitment
- **"We agreed [person] will [verb]"** — recorded decision

## What an action item is NOT

These look like action items but aren't:

- **"We should look into [X]"** — aspirational, no commitment
- **"That would be cool"** — speculation
- **"Maybe we could [verb]"** — hypothetical
- **"Someone needs to [verb]"** — no owner
- **"Let's [verb] sometime"** — vague, no deadline, no specific owner

The grep step catches the keyword. The commitment-phrase requirement catches the difference between "we should" and "I'll."

## When you cannot grep the transcript

If you only have the panel (Granola's auto-generated summary) and not the full transcript:

- Apply the same rules against the panel content
- Add a warning to the output: "Summary generated from auto-summary only; full transcript not available. Verify before acting."
- Try harder to get the full transcript next time

The full transcript is the ground truth. The panel is the LLM's first summary, which has already smoothed over some details.

## The trust ledger

Track over time:

| Date | Meeting | Action items posted | Hallucinations caught | Hallucinations missed |
|---|---|---|---|---|
| | | | | |

Goal: keep the "missed" column at zero. The "caught" column going up over time is fine — it means the verifier is doing its job.

If a "missed" hallucination ever lands in Slack and someone notices, the trust hit is large. Optimize hard against this column.

## The single most important rule

**If the verifier is unsure, drop the item.**

Missing one real action item is recoverable — the operator can add it manually. Posting one fake action item is not — the trust hit takes weeks to recover.

Default the skill to err on the side of dropping. Lower recall in exchange for higher precision.
