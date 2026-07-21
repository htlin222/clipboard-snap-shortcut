#!/usr/bin/env python3
"""Fetch clips saved to the Turso database within a time window."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

WINDOW_PATTERN = re.compile(r"^(\d+)([mhd])$")
UNITS = {"m": "minutes", "h": "hours", "d": "days"}
DEFAULT_WINDOW = "6h"
DEFAULT_TZ = "Asia/Taipei"
# This repo is public, so the database name lives in the git-ignored .env only.
PROJECT_ROOT = Path(
    os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[4]
)

# `turso db shell` only renders padded tables, so the whole result set is
# aggregated into one JSON row: json_group_array escapes the newlines inside each
# clip, keeping the payload on a single parseable line. The short `j` alias stops
# the renderer from wrapping the header across lines.
QUERY = """
SELECT json_group_array(json_object(
    'id', id, 'created_at', created_at, 'source', source, 'text', text,
    'status', status, 'topic', topic
)) AS j FROM (
    SELECT id, created_at, source, text, status, topic FROM clips
    WHERE created_at >= strftime('%Y-%m-%dT%H:%M:%fZ', 'now', ?)
    ORDER BY created_at DESC LIMIT ?
);
"""


def load_env(path: Path) -> dict[str, str]:
    """Read simple KEY=value lines from .env; avoids a python-dotenv dependency."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("\"'")
    return values


def resolve_db(explicit: str | None) -> str:
    """Resolve the database name from --db, the environment, then .env."""
    if explicit:
        return explicit
    from_env = os.environ.get("DB") or load_env(PROJECT_ROOT / ".env").get("DB")
    if not from_env:
        raise SystemExit(
            "error: database name not set.\n"
            f"Add a DB=<name> line to {PROJECT_ROOT / '.env'} (git-ignored), "
            "copying .env.example, or pass --db <name>."
        )
    return from_env


def to_modifier(window: str) -> str:
    """Turn a window like '6h' into a SQLite datetime modifier like '-6 hours'."""
    match = WINDOW_PATTERN.match(window)
    if not match:
        raise ValueError(f"window must look like 30m, 6h, or 2d (got: {window!r})")
    amount, unit = int(match.group(1)), match.group(2)
    if amount == 0:
        raise ValueError("window must be greater than zero")
    return f"-{amount} {UNITS[unit]}"


def fetch(db: str, modifier: str, limit: int) -> list[dict]:
    """Run the query through the authenticated turso CLI and return the clips."""
    # `turso db shell` takes no bind variables, so the two placeholders are filled
    # by hand. Both are safe by construction, not by escaping: `modifier` is built
    # from a regex-validated integer plus a fixed unit word, and `limit` is an int.
    # Never widen this to interpolate a caller-supplied string.
    sql = QUERY.replace("?", f"'{modifier}'", 1).replace("?", str(limit), 1)
    env = {**os.environ, "TURSO_NO_UPDATE": "1"}
    try:
        result = subprocess.run(
            ["turso", "db", "shell", db, sql],
            capture_output=True,
            text=True,
            check=True,
            env=env,
            timeout=60,
        )
    except FileNotFoundError:
        raise SystemExit(
            "turso CLI not found. Install it: brew install tursodatabase/tap/turso"
        )
    except subprocess.TimeoutExpired:
        raise SystemExit("turso CLI timed out after 60s")
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise SystemExit(
            f"turso query failed: {detail}\nIs the session live? Run: turso auth login"
        )

    # Skip the table header by taking the row that actually holds the array.
    payload = next(
        (
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip().startswith("[")
        ),
        None,
    )
    if payload is None:
        raise SystemExit(
            f"could not find a JSON row in turso output:\n{result.stdout[:500]}"
        )
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        raise SystemExit(f"could not parse turso output as JSON:\n{payload[:500]}")


def to_local(created_at: str, tz: ZoneInfo) -> str:
    """Render a stored UTC timestamp in local time; clips are read by a human."""
    try:
        stamp = datetime.fromisoformat(created_at).astimezone(tz)
    except ValueError:
        return created_at  # Show the raw value rather than dropping the clip.
    return stamp.strftime("%Y-%m-%d %H:%M %Z")


def render(clips: list[dict], window: str, tz: ZoneInfo) -> str:
    """Format clips as readable records; JSON escapes would obscure the text."""
    if not clips:
        return f"No clips saved in the last {window}."
    untagged = sum(1 for clip in clips if not clip.get("status"))
    header = f"{len(clips)} clip(s) in the last {window}, newest first"
    if untagged:
        header += f" ({untagged} untagged — triage these)"
    blocks = [header + ":\n"]
    for clip in clips:
        # Show any existing triage tags so the summariser only tags what is NULL.
        tag = (
            f"[{clip['status']}/{clip.get('topic') or '?'}]"
            if clip.get("status")
            else "[untagged]"
        )
        blocks.append(
            f"=== id={clip['id']} | {to_local(clip['created_at'], tz)} | "
            f"{clip['source']} | {tag} ===\n"
            f"{clip['text']}\n"
        )
    return "\n".join(blocks)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "window",
        nargs="?",
        default=DEFAULT_WINDOW,
        help=f"how far back to look: 30m, 6h, 2d (default: {DEFAULT_WINDOW})",
    )
    parser.add_argument(
        "--json", action="store_true", help="emit raw JSON instead of text"
    )
    parser.add_argument(
        "--db", default=None, help="Turso database name (default: DB from .env)"
    )
    parser.add_argument(
        "--limit", type=int, default=200, help="max clips to return (default: 200)"
    )
    parser.add_argument(
        "--tz",
        default=os.environ.get("CLIPS_TZ", DEFAULT_TZ),
        help=f"IANA zone for displayed timestamps (default: {DEFAULT_TZ})",
    )
    args = parser.parse_args()

    # An omitted slash-command argument arrives as an empty string, not as None.
    window = args.window.strip() or DEFAULT_WINDOW
    if args.limit < 1:
        raise SystemExit("--limit must be at least 1")

    try:
        modifier = to_modifier(window)
    except ValueError as exc:
        raise SystemExit(f"error: {exc}")

    try:
        tz = ZoneInfo(args.tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise SystemExit(f"error: unknown time zone {args.tz!r}")

    clips = fetch(resolve_db(args.db), modifier, args.limit)
    if args.json:
        # Raw mode keeps created_at as the stored UTC value.
        print(json.dumps(clips, ensure_ascii=False, indent=2))
    else:
        print(render(clips, window, tz))
    return 0


if __name__ == "__main__":
    sys.exit(main())
