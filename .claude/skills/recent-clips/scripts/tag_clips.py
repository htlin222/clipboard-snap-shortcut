#!/usr/bin/env python3
"""Write triage tags (status + topic) back to clips in the Turso database.

Reads a JSON array of {"id", "status", "topic"} objects on stdin and updates the
matching rows. Only rows that are still untagged (status IS NULL) are touched, so
re-running over an overlapping window never rewrites a clip that was already
triaged. The authenticated `turso` CLI session supplies write access; the
insert-only token the Shortcut carries is unrelated and not used here.

Usage:
    echo '[{"id":142,"status":"draft","topic":"ai-project"}]' | tag_clips.py
    tag_clips.py --dry-run < mappings.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# status is a closed vocabulary: an unknown value is a mistake, not a new bucket.
STATUS_VOCAB = {"draft", "todo", "ref", "snippet", "note", "scrap"}
# topic is a growable seed set: values outside it are allowed but flagged so the
# taxonomy does not silently sprout near-duplicate synonyms.
TOPIC_SEED = {"medical", "ai-project", "writing", "tooling", "admin", "misc"}
# A topic must be kebab-case so it is safe to inline into SQL and stays tidy.
TOPIC_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

PROJECT_ROOT = Path(
    os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[4]
)


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


def run_sql(db: str, sql: str) -> str:
    """Run one SQL batch through the authenticated turso CLI, returning stdout."""
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
    return result.stdout


def parse_mappings(raw: str) -> list[dict]:
    """Validate the stdin JSON into a list of {id, status, topic} dicts."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"error: stdin is not valid JSON: {exc}")
    if not isinstance(data, list):
        raise SystemExit("error: expected a JSON array of {id, status, topic}")

    seen: set[int] = set()
    mappings: list[dict] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise SystemExit(f"error: item {i} is not an object")
        try:
            clip_id = int(item["id"])
        except (KeyError, TypeError, ValueError):
            raise SystemExit(f"error: item {i} has a missing or non-integer id")
        status = str(item.get("status", "")).strip()
        topic = str(item.get("topic", "")).strip()
        if status not in STATUS_VOCAB:
            raise SystemExit(
                f"error: id {clip_id} has status {status!r}; "
                f"must be one of {sorted(STATUS_VOCAB)}"
            )
        if not TOPIC_PATTERN.match(topic):
            raise SystemExit(
                f"error: id {clip_id} has topic {topic!r}; "
                "must be kebab-case (lowercase letters, digits, hyphens)"
            )
        if clip_id in seen:
            raise SystemExit(f"error: id {clip_id} appears more than once")
        seen.add(clip_id)
        mappings.append({"id": clip_id, "status": status, "topic": topic})
    return mappings


def current_status(db: str, ids: list[int]) -> dict[int, str | None]:
    """Return the current status of each id (present rows only)."""
    id_list = ",".join(str(i) for i in ids)
    sql = (
        "SELECT json_group_array(json_object('id', id, 'status', status)) AS j "
        f"FROM clips WHERE id IN ({id_list});"
    )
    payload = next(
        (
            line.strip()
            for line in run_sql(db, sql).splitlines()
            if line.strip().startswith("[")
        ),
        "[]",
    )
    rows = json.loads(payload)
    return {row["id"]: row["status"] for row in rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", default=None, help="Turso database name (default: DB from .env)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and report the plan without writing",
    )
    parser.add_argument(
        "--file",
        default=None,
        help="read the JSON mappings from this path instead of stdin",
    )
    args = parser.parse_args()

    if args.file:
        raw = Path(args.file).read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()
    mappings = parse_mappings(raw)
    if not mappings:
        print("no mappings on stdin; nothing to do")
        return 0

    db = resolve_db(args.db)
    existing = current_status(db, [m["id"] for m in mappings])

    to_write: list[dict] = []
    skipped_tagged: list[int] = []
    missing: list[int] = []
    for m in mappings:
        if m["id"] not in existing:
            missing.append(m["id"])
        elif existing[m["id"]] is not None:
            skipped_tagged.append(m["id"])
        else:
            to_write.append(m)

    new_topics = sorted({m["topic"] for m in to_write} - TOPIC_SEED)

    # status is drawn from a closed set and topic is kebab-case validated, so both
    # are safe to inline. ids are ints. The IS NULL guard is a second line of
    # defence: even a stale plan cannot clobber an already-triaged row.
    statements = [
        f"UPDATE clips SET status='{m['status']}', topic='{m['topic']}' "
        f"WHERE id={m['id']} AND status IS NULL;"
        for m in to_write
    ]

    if args.dry_run:
        print("DRY RUN — no writes.")
    elif statements:
        run_sql(db, "\n".join(statements))

    print(f"updated {len(to_write)} clip(s)")
    if skipped_tagged:
        print(f"skipped {len(skipped_tagged)} already-tagged: {skipped_tagged}")
    if missing:
        print(f"skipped {len(missing)} not found: {missing}")
    if new_topics:
        print(f"new topic(s) beyond the seed set: {new_topics}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
