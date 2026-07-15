---
name: recent-clips
description: Fetches and summarizes clipboard text that the Clipboard Snap iOS Shortcut saved to the Turso database within a recent time window. Use when the user asks what they clipped, copied, or saved recently, asks to summarize recent clips, or runs /recent-clips.
argument-hint: "[window] e.g. 6h, 30m, 2d"
arguments: window
allowed-tools: Bash(${CLAUDE_PROJECT_DIR}/.claude/skills/recent-clips/scripts/recent_clips.py *)
---

# Recent Clips

The clips below are already fetched — the query ran before you read this. Do not
re-run it unless the user asks for a different window than the one shown.

Timestamps are Asia/Taipei. The database stores UTC, so never quote a stored
`created_at` back to the user without converting it.

## Clips

!`${CLAUDE_SKILL_DIR}/scripts/recent_clips.py "$window"`

## Your task

Summarize the clips above for the user, in the language they wrote to you in.

- Lead with the shape of the batch: how many clips, what span, and the single
  thread connecting them if there is one. If they share no theme, say that
  instead of inventing one.
- Then walk through the clips, grouping by theme rather than by timestamp when
  that reads better. Reference each by `id` so the user can pull the full record.
- Note what a bare list would not show: a clip that is already a finished draft
  versus a stray fragment, a decision waiting on a reply, an action item.
- Skip the preamble. No "here is a summary of your clips".

If the output above says no clips were saved, say so plainly and offer a wider
window. Do not pad the answer.

## Windows

`$window` accepts `30m`, `6h`, `2d` — an integer plus `m`, `h`, or `d`. It
defaults to `6h` when omitted. The window is validated against that pattern
before it reaches SQL, and the database is queried through the authenticated
`turso` CLI session on this Mac.

This repo is public, so the script reads the database name from `DB` in the
git-ignored `.env` rather than carrying it in tracked code. Never write the
database name into this file or the script.

To pull a full record or a different slice yourself:

```bash
.claude/skills/recent-clips/scripts/recent_clips.py 2d --json   # raw JSON, UTC
.claude/skills/recent-clips/scripts/recent_clips.py 6h --limit 5
make db-record ID=13                                            # one whole clip
```

If the script reports that the turso session is dead, the fix is
`turso auth login` — the user must run that themselves. If it reports that the
database name is not set, `.env` is missing a `DB=` line; `.env.example` shows
the format.
