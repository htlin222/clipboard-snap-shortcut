# Contributing

Contributions that improve iOS compatibility, Turso security, documentation,
or the deterministic Shortcut build are welcome.

## Development

1. Install [uv](https://docs.astral.sh/uv/) and use macOS when signing a
   `.shortcut` file.
2. Run `make sync` to install the locked development tools.
3. Change the generator under `skills/clipboard-snap-shortcut/scripts/`.
4. Run `make check` and `make shortcut`.
5. Commit the regenerated public files in `dist/` with the source change.

Never commit a configured Shortcut, Turso token, `.env` file, or private build.
The public artifact must retain its two import questions and pass the secret
check in `check_shortcut.py`.

## Pull Requests

Keep changes focused and explain any action-sequence or request-contract
change. Include the iOS and macOS versions used for manual import testing when
the change affects Shortcuts behavior.
