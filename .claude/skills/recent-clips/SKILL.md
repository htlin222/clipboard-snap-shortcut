---
name: recent-clips
description: Fetches and summarizes clipboard text that the Clipboard Snap iOS Shortcut saved to the Turso database within a recent time window. Use when the user asks what they clipped, copied, or saved recently, asks to summarize recent clips, or runs /recent-clips.
argument-hint: "[window] e.g. 6h, 30m, 2d"
arguments: window
allowed-tools: Bash(${CLAUDE_PROJECT_DIR}/.claude/skills/recent-clips/scripts/recent_clips.py *), Bash(${CLAUDE_PROJECT_DIR}/.claude/skills/recent-clips/scripts/tag_clips.py *)
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

## Triage (runs every time, after the summary)

Each header line ends with the clip's current triage tag — `[status/topic]`, or
`[untagged]` if it has never been triaged. After writing the summary, tag every
`[untagged]` clip and write the tags back. Already-tagged clips are left alone;
never re-tag them.

Give each untagged clip two tags:

- **status** — what to *do* with it. Exactly one of: `draft` (a finished piece
  ready to publish or send), `todo` (an action item or something waiting on a
  reply), `ref` (a link or reference worth keeping), `snippet` (a code or data
  fragment), `note` (a distilled idea worth keeping), `scrap` (a stray fragment,
  likely disposable).
- **topic** — what it is *about*. Prefer a seed value: `medical`, `ai-project`,
  `writing`, `tooling`, `admin`, `misc`. If none fits, coin a new kebab-case
  topic rather than forcing `misc`.

Then write the tags back:

1. Build a JSON array of `{"id", "status", "topic"}`, one object per untagged
   clip, and write it to a scratch file (use your scratchpad directory).
2. Run `scripts/tag_clips.py --file <that file>`. It only updates rows that are
   still `NULL`, validates every status against the fixed set, and flags any
   topic beyond the seed set. Add `--dry-run` first if you want to preview.
3. Tell the user how many clips were tagged and surface any brand-new topic the
   script reported, so the taxonomy does not drift unnoticed.

If every clip in the window is already tagged, say so and skip the write.

### Automated hourly triage (launchd)

The same tagging runs unattended once an hour via a launchd agent, so clips are
usually already tagged by the time you summarise them. Each pass fetches the
untagged clips from the last 2h, has Haiku (`claude -p --model`) classify them as
a pure text→JSON step (no tools), and writes the result through `tag_clips.py`,
which is the guardrail — a malformed answer is rejected, never written.

Manage it from this skill's directory with make (macOS make 3.81, so the launchd
logic lives in `scripts/launchd.sh`, not the recipes):

```
make install     # write the plist and load it (hourly + one run now)
make status      # is it loaded? plus the last log lines
make start/stop  # kick a run now / stop the current invocation
make run         # one foreground pass, no launchd (make run WINDOW=6h)
make logs        # follow scripts/../triage_cron.log
make uninstall   # unload and remove the agent
```

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
