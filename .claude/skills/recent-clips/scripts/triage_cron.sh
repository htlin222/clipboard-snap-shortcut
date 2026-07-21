#!/bin/zsh
# Hourly triage runner. Fetches untagged clips, has Haiku classify them into
# status + topic (as a pure text->JSON function, no tools), then writes the tags
# back through tag_clips.py — which validates every value and only touches rows
# that are still NULL. Meant to be driven by the launchd agent installed via the
# Makefile in this skill; run it directly to test one pass.
#
# Usage: triage_cron.sh [window]   (window defaults to 2h)
set -uo pipefail

SCRIPT_DIR=${0:A:h}
SKILL_DIR=${SCRIPT_DIR:h}
LOG="$SKILL_DIR/triage_cron.log"
LOCK="/tmp/clip-triage.lock"
WINDOW="${1:-2h}"
MODEL="claude-haiku-4-5-20251001"

ts() { date +"%Y-%m-%dT%H:%M:%S%z"; }
log() { print -r -- "$(ts) $*" >>"$LOG"; }

# A directory is an atomic lock on every filesystem, so overlapping runs (a slow
# Haiku call outliving the hour) skip instead of double-classifying.
if ! mkdir "$LOCK" 2>/dev/null; then
  log "previous run still holding the lock; skipping"
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT

untagged=$("$SCRIPT_DIR/recent_clips.py" "$WINDOW" --json 2>>"$LOG" | python3 -c '
import json, sys
clips = json.load(sys.stdin)
# Cap each clip so a runaway paste cannot blow up the classifier prompt.
out = [{"id": c["id"], "text": (c["text"] or "")[:1500]}
       for c in clips if not c.get("status")]
print(json.dumps(out, ensure_ascii=False))
') || { log "fetch failed"; exit 1; }

n=$(print -r -- "$untagged" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))')
if [[ "$n" -eq 0 ]]; then
  log "nothing untagged in $WINDOW"
  exit 0
fi

# Haiku gets no tools: it is a pure classifier. tag_clips.py is the guardrail, so
# a malformed or hallucinated answer is rejected, never written.
raw=$(print -r -- "$(cat "$SCRIPT_DIR/triage_prompt.txt")

CLIPS:
$untagged" | claude -p --model "$MODEL" 2>>"$LOG") || { log "claude call failed"; exit 1; }

# Salvage the JSON array even if the model wraps it in prose or code fences.
clean=$(print -r -- "$raw" | python3 -c '
import sys
t = sys.stdin.read()
i, j = t.find("["), t.rfind("]")
sys.stdout.write(t[i:j+1] if 0 <= i < j else "[]")
')

result=$(print -r -- "$clean" | "$SCRIPT_DIR/tag_clips.py" 2>&1)
log "sent $n untagged clip(s) to Haiku -> ${result//$'\n'/ | }"
