#!/bin/zsh
# launchd lifecycle for the hourly clip-triage runner. The repo's make is 3.81
# (no .ONESHELL), so the plist heredoc and multi-line logic live here rather than
# in a recipe. Driven by the skill Makefile: install / uninstall / start / stop /
# status. Paths are derived from this script's location, so nothing machine
# specific is committed.
set -uo pipefail

SCRIPT_DIR=${0:A:h}
SKILL_DIR=${SCRIPT_DIR:h}
REPO=${SKILL_DIR:h:h:h}
RUNNER="$SCRIPT_DIR/triage_cron.sh"
LOG="$SKILL_DIR/triage_cron.log"

LABEL="com.htlin.clip-triage"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
INTERVAL="${INTERVAL:-3600}"
BIN_PATH="/opt/homebrew/bin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

install_agent() {
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>$RUNNER</string>
  </array>
  <key>StartInterval</key><integer>$INTERVAL</integer>
  <key>RunAtLoad</key><true/>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>$BIN_PATH</string></dict>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
EOF
  plutil -lint "$PLIST" >/dev/null || { print -r -- "plist failed lint"; return 1; }
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load -w "$PLIST"
  print -r -- "installed $LABEL: every ${INTERVAL}s, log -> $LOG"
}

uninstall_agent() {
  launchctl unload -w "$PLIST" 2>/dev/null || true
  rip "$PLIST" 2>/dev/null || command rm -f "$PLIST"
  print -r -- "removed $LABEL"
}

start_agent() {
  launchctl start "$LABEL" && print -r -- "started $LABEL (see: make status)"
}

stop_agent() {
  launchctl stop "$LABEL" 2>/dev/null || true
  print -r -- "stopped current run of $LABEL"
}

status_agent() {
  if [[ -f "$PLIST" ]]; then print -r -- "plist:   $PLIST"; else print -r -- "plist:   (not installed)"; fi
  # Capture rather than `grep -q` a live pipe: under pipefail, grep -q closing the
  # pipe early makes launchctl take SIGPIPE and the pipeline reports failure.
  local found
  found=$(launchctl list 2>/dev/null | grep -F "$LABEL" || true)
  if [[ -n "$found" ]]; then
    print -r -- "loaded:  yes  (pid/last-exit/label below)"
    print -r -- "  $found"
  else
    print -r -- "loaded:  no"
  fi
  if [[ -f "$LOG" ]]; then
    print -r -- "--- last log lines ---"
    tail -n 8 "$LOG"
  fi
}

case "${1:-}" in
  install)   install_agent ;;
  uninstall) uninstall_agent ;;
  start)     start_agent ;;
  stop)      stop_agent ;;
  status)    status_agent ;;
  *) print -r -- "usage: launchd.sh {install|uninstall|start|stop|status}"; exit 2 ;;
esac
