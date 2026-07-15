[![CI](https://github.com/htlin222/clipboard-snap-shortcut/actions/workflows/ci.yml/badge.svg)](https://github.com/htlin222/clipboard-snap-shortcut/actions/workflows/ci.yml)
[![GitHub release](https://img.shields.io/github/v/release/htlin222/clipboard-snap-shortcut)](https://github.com/htlin222/clipboard-snap-shortcut/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![GitHub stars](https://img.shields.io/github/stars/htlin222/clipboard-snap-shortcut)](https://github.com/htlin222/clipboard-snap-shortcut/stargazers)

# Clipboard Snap

Clipboard Snap is an open-source **iOS Shortcut** that saves selected or copied
text from an iPhone to a **Turso/libSQL database**. It works from the Apple
Shortcuts Share Sheet and falls back to the clipboard when run directly.

The repository includes a signed, importable Shortcut, deterministic plist
generator, structural validator, Turso schema, scoped-token workflow, and
reusable Codex skill. Text is inserted through Turso SQL over HTTP with a bound
parameter, preserving quotes, line breaks, emoji, and Unicode.

## Features

- Save selected text from Safari, Notes, Mail, and other iOS Share Sheets.
- Save copied text from Shortcuts, Back Tap, a widget, or the Action Button.
- Send only parameterized SQL with an insert-only Turso database token.
- Show the saved text's first line in the success notification.
- Rebuild and validate the Apple Shortcut reproducibly with `uv` and `make`.
- Keep database credentials out of Git and the public `.shortcut` artifact.

## Install

Download [Clipboard Snap.shortcut](dist/Clipboard%20Snap.shortcut), transfer it
to the iPhone with AirDrop or iCloud Drive, and open it in Shortcuts. During
**Add Shortcut**, enter:

1. **Turso pipeline URL:** the database HTTP URL followed by `/v2/pipeline`.
2. **Turso database token:** the raw token only, without `Bearer`.

The public artifact contains placeholders and import questions. It does not
contain this project's database endpoint or token.

## iOS Limitation

iOS does not expose an Apple Shortcuts trigger for every clipboard change.
Copying text alone cannot silently run this Shortcut. Use either workflow:

1. Select text, tap **Share**, and choose **Clipboard Snap**.
2. Copy text, then run **Clipboard Snap** manually. With no Share Sheet input,
   it reads the clipboard.

## Turso Setup

### 1. Authenticate the CLI

Install the [Turso CLI](https://docs.turso.tech/cli), then confirm which account
will own the database:

```bash
turso auth login
turso auth whoami
```

This project also supports the Homebrew path explicitly:

```bash
make db-url TURSO=/opt/homebrew/bin/turso DB=clipboard-snap
```

### 2. Create the database

Create the database when needed and apply the idempotent `clips` schema:

```bash
make db DB=clipboard-snap
```

### 3. Get the Shortcut endpoint

Print the database HTTP URL:

```bash
make db-url DB=clipboard-snap
```

If the output is `https://example-org.turso.io`, enter
`https://example-org.turso.io/v2/pipeline` in the first Shortcut import
question. On macOS, copy that complete value directly with:

```bash
printf '%s/v2/pipeline' "$(turso db show clipboard-snap --http-url)" | pbcopy
```

### 4. Mint the iPhone credential

Create a database-scoped token that expires after 90 days and can only add rows
to the `clips` table:

```bash
make db-token DB=clipboard-snap
```

This runs the equivalent Turso CLI command:

```bash
turso db tokens create clipboard-snap \
  -p clips:data_add \
  --expiration 90d
```

The command prints one long JWT beginning with `eyJ`. Copy the complete token
and paste it into the second Shortcut import question. Do not add quotes or the
word `Bearer`; Clipboard Snap adds the authorization prefix. To put the token
on the Mac clipboard without displaying it:

```bash
turso db tokens create clipboard-snap \
  -p clips:data_add \
  --expiration 90d | pbcopy
```

This database token is separate from `turso auth token`. The latter authenticates
the CLI account and is not the credential to place in the iPhone Shortcut.

### 5. Verify saved records

The table stores `id`, `text`, `source`, and a database-generated UTC
`created_at` timestamp. Check recent inserts with:

```bash
make db-verify DB=clipboard-snap
```

Read the complete latest record or a specific numeric record ID with the
authenticated CLI:

```bash
make db-latest DB=clipboard-snap
make db-record DB=clipboard-snap ID=123
```

The iPhone's `clips:data_add` token cannot read these records. These commands
use the authenticated Turso CLI session on the Mac.

Set `TURSO=/opt/homebrew/bin/turso` on macOS if the CLI is not on `PATH`.

Optional Make defaults are documented in `.env.example`. Do not put a token in
that file:

```bash
cp .env.example .env
set -a; source .env; set +a
```

## Use

For selected text:

1. Select text in an app that supports the Share Sheet.
2. Tap **Share**, then choose **Clipboard Snap**.
3. Confirm the notification shows **Text saved to Turso.** followed by the
   first line of the saved text.

For copied text, copy it and run **Clipboard Snap** from the Shortcuts app. You
can also assign it in **Settings > Accessibility > Touch > Back Tap**.

On first use, iOS may request clipboard and network access. The Shortcut is
disabled while the device is locked.

## Security

Apple Shortcuts stores setup answers visibly in editable Text actions, not in
Keychain. Use the generated `clips:data_add` token, keep its lifetime short,
and never share a configured Shortcut. Rotate the token after device or
Shortcut disclosure.

The insert uses this parameterized statement:

```sql
INSERT INTO clips (text, source)
VALUES (CAST(? AS TEXT), 'ios-shortcut');
```

Clipboard Snap Base64-encodes the input for reliable Shortcuts JSON transport,
binds it as a blob argument, and casts it back to text in Turso. User text is
never interpolated into SQL or the raw JSON template. See [SECURITY.md](SECURITY.md)
for private vulnerability reporting.

## Development

Python tooling is managed by [uv](https://docs.astral.sh/uv/). No manual virtual
environment is required.

```bash
git clone https://github.com/htlin222/clipboard-snap-shortcut.git
cd clipboard-snap-shortcut
make sync
make check
make shortcut
```

Useful targets:

| Target | Purpose |
| --- | --- |
| `make build` | Generate the credential-free XML plist. |
| `make validate` | Check actions, variables, payload, and secret safety. |
| `make shortcut` | Validate and sign the public Shortcut on macOS. |
| `make open` | Build and open the public Shortcut. |
| `make db` | Create the Turso database if needed and apply the schema. |
| `make db-token` | Create a 90-day, insert-only database token. |
| `make db-latest` | Read the complete newest record with CLI authentication. |
| `make db-record ID=123` | Read one complete record by numeric ID. |
| `make configured-shortcut` | Build an ignored private artifact with a fresh token. |

To build a private preconfigured Shortcut:

```bash
make configured-shortcut \
  DB=clipboard-snap \
  ENDPOINT="https://your-database.turso.io/v2/pipeline"
```

The private artifact is written under ignored `private/`, and its temporary
plaintext plist is removed automatically. Do not publish or attach it to an
issue.

The generator follows
[Shortcuts Playground](https://github.com/viticci/shortcuts-playground-plugin)
plist, variable-wiring, import-question, validation, and signing patterns. The
request contract follows Turso's
[SQL over HTTP reference](https://docs.turso.tech/sdk/http/reference) and
[fine-grained permissions](https://docs.turso.tech/sdk/authorization/fine-grained-permissions).

## Project Layout

- `dist/Clipboard Snap.shortcut`: signed public iOS Shortcut.
- `dist/Clipboard Snap.xml`: generated, reviewable plist source.
- `skills/clipboard-snap-shortcut/`: generator, validator, references, and skill.
- `skills/clipboard-snap-shortcut/assets/schema.sql`: Turso table schema.
- `Makefile`: public build, private build, and database commands.

## Citation

Use the repository's [CITATION.cff](CITATION.cff) or [citation.bib](citation.bib):

```bibtex
@software{lin2026clipboardsnapshortcut,
  author = {Lin, Hsieh-Ting},
  title = {Clipboard Snap: Save iPhone Text to Turso with Apple Shortcuts},
  year = {2026},
  url = {https://github.com/htlin222/clipboard-snap-shortcut},
  version = {0.1.0}
}
```

## License

Clipboard Snap is released under the [MIT License](LICENSE).
