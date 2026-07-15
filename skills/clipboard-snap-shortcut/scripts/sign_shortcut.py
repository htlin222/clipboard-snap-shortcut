#!/usr/bin/env python3
"""Validate, convert, and sign Clipboard Snap with Apple's shortcuts CLI."""

from __future__ import annotations

import argparse
import plistlib
import shutil
import subprocess
import tempfile
from pathlib import Path

from check_shortcut import validate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("shortcut", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("anyone", "people-who-know-me"),
        default="anyone",
    )
    parser.add_argument("--allow-configured-token", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if shutil.which("shortcuts") is None:
        raise SystemExit("Apple's shortcuts CLI is required; run this on macOS")

    validate(
        args.shortcut,
        allow_configured_token=args.allow_configured_token,
    )
    with args.shortcut.open("rb") as source:
        workflow = plistlib.load(source)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    prefix = f"{args.shortcut.stem}-sign-input-"
    with tempfile.NamedTemporaryFile(prefix=prefix, suffix=".shortcut") as temp:
        plistlib.dump(workflow, temp, fmt=plistlib.FMT_BINARY, sort_keys=False)
        temp.flush()
        result = subprocess.run(
            [
                "shortcuts",
                "sign",
                "--mode",
                args.mode,
                "--input",
                temp.name,
                "--output",
                str(args.output),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            details = result.stderr.strip() or result.stdout.strip()
            raise SystemExit(details or "Apple's shortcuts signer failed")
    if not args.output.is_file() or args.output.stat().st_size == 0:
        raise SystemExit("shortcuts sign did not create a non-empty output file")
    print(f"Signed {args.output} ({args.output.stat().st_size} bytes, mode={args.mode})")


if __name__ == "__main__":
    main()
