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

Download the latest signed
[Clipboard Snap Shortcut](https://github.com/htlin222/clipboard-snap-shortcut/releases/latest/download/Clipboard.Snap.shortcut),
transfer it to the iPhone with AirDrop or iCloud Drive, and open it in
Shortcuts. During **Add Shortcut**, enter:

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

## Mac-to-Mac Merge via Maccy

Two or more Macs running [Maccy](https://github.com/p0deje/Maccy) can push their
plain-text clipboard history into the same shared `clips` table, so `db-verify`
/ `db-latest` show one merged timeline across the iPhone and every Mac
(distinguished by `source`).

Maccy's history lives in a Core Data SQLite store at:

```
~/Library/Containers/org.p0deje.Maccy/Data/Library/Application Support/Maccy/Storage.sqlite
```

This is a one-way push, same as the iPhone Shortcut: it reads Maccy's local
store and inserts new plain-text items (`public.utf8-plain-text`) into Turso.
It never writes back into Maccy's own database — that store is Core Data's
private format and is not safe to write into from an external script.

Before pushing, each clip is checked against a curated set of sensitive-data
patterns; a match is skipped instead of pushed. The tracked template is
[`config.toml.example`](config.toml.example); copy it to `config.toml` (which is
git-ignored) to add your own org-specific patterns. See
[Sensitive-Data Filter](#sensitive-data-filter) below.

### 1. Mint a per-Mac token (Keychain only, never a file)

```bash
make mac-token DB=clipboard-snap
```

This stores a fresh 90-day `clips:data_add` token in the login Keychain under
service `clipboard-snap-<MAC_SOURCE>` (default `MAC_SOURCE` is
`maccy-$(hostname -s)`). Run this once per Mac.

### 2. Push once

```bash
make mac-push DB=clipboard-snap
```

`scripts/push_maccy_clips.sh` tracks its own cursor per source under
`~/.local/state/clipboard-snap/`, so re-running only pushes items newer than
the last push. On a Mac with existing Maccy history, the first run pushes
everything currently in Maccy — check `make db-verify` if you want to see what
went out before setting up automatic pushes on a Mac with a long clipboard
history.

### 3. Grant Full Disk Access

Maccy's `Storage.sqlite` lives inside Maccy's own sandboxed container, so
reading it from an external process is gated by macOS's privacy protection
(TCC). When launchd runs `scripts/push_maccy_clips.sh`, the process macOS
holds responsible is the script's interpreter — `/bin/zsh`, since that is
literally what `ProgramArguments[0]` is — not `sqlite3`, even though
`sqlite3` is the one calling `open()`. Without this grant every run fails
with `sqlite3: ... authorization denied`.

Add **`/bin/zsh`** to **System Settings → Privacy & Security → Full Disk
Access**. This is broader than granting a single dedicated binary — every
zsh script on the Mac, run by anything, silently gets the same unprompted
disk access once this is set, not just this one. That's a real widening of
this Mac's attack surface, so treat it as a deliberate choice, not a
rubber-stamp step. The upside: `/bin/zsh` is a fixed system path, so unlike
a Homebrew-installed interpreter this grant does not need to be redone after
package upgrades.

### 4. Automate with launchd

The agent polls every 60 seconds (`StartInterval`), but the script itself
checks `pgrep -x Maccy` first and exits immediately, before touching the
network, if Maccy is not running. In practice this means it only ever does
work while Maccy is open.

`WatchPaths` (event-driven on `Storage.sqlite-wal` changes, so it would only
wake up on an actual copy instead of polling) was tried first but did not
reliably re-fire after the first change in testing — a known launchd
quirk — so this falls back to a short interval instead.

The shipped plist bakes in this Mac's endpoint, home path, Keychain service
name, and `--source` value. On a second Mac, copy it and hand-edit those
`<string>` values (home path, `clipboard-snap-maccy-<hostname>`,
`maccy-<hostname>`) to match that Mac before loading it:

```bash
command cp launchd/com.htlin.clipboard-snap.mac-push.plist \
  ~/Library/LaunchAgents/com.htlin.clipboard-snap.mac-push.plist
# edit ~/Library/LaunchAgents/com.htlin.clipboard-snap.mac-push.plist, then:
launchctl load ~/Library/LaunchAgents/com.htlin.clipboard-snap.mac-push.plist
```

Logs land in `/tmp/clipboard-snap-mac-push.log` / `.err`. To stop it:

```bash
launchctl unload ~/Library/LaunchAgents/com.htlin.clipboard-snap.mac-push.plist
```

### Reading the merged list

Use the existing authenticated-CLI targets — `source` already tells iPhone and
Mac rows apart:

```bash
make db-verify DB=clipboard-snap
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

### Sensitive-Data Filter

`config.toml` is a single curated list of regex patterns (credentials,
cookies, internal URLs, card numbers, wallet seed phrases, ...) that both
delivery paths check before anything reaches Turso. The tracked, sanitized
template is [`config.toml.example`](config.toml.example); the real `config.toml`
is git-ignored so your org-specific patterns stay local, and the relay falls
back to the example when it is absent:

- **`scripts/push_maccy_clips.sh`** reads `config.toml` at runtime and checks
  it with `grep -Eiq` (POSIX ERE) before pushing each Maccy clip. A match
  skips that item — its cursor still advances so it's never retried, and
  only the matched pattern's `name` is logged, never the text itself.
- **The iOS Shortcut** has the same patterns compiled into a single ICU
  regular expression at *build* time (`make build`/`make shortcut`), run
  through a native **Match Text** action before the Base64/network step. A
  match shows a "Blocked" result and stops the Shortcut instead of sending.

`config.toml` also has a second table, `[[count_patterns]]`, for values that
aren't sensitive individually but are as a batch — e.g. `bulk-8digit-numbers`
blocks a paste containing 3+ separate 8-digit chart numbers (a spreadsheet
column, a batch lookup list), even though no single 8-digit number matches
anything on its own. Neither engine's plain regex match can express "count
of matches ≥ N" directly, so each entry carries the rule twice: `grep -oE`
extraction + `grep -E` length filter + a shell count for the relay, and an
ICU `\b...\b`-bounded Match Text + a native **Count** action + a numeric
**If** (≥) for the Shortcut.

Because the Shortcut-side check is baked in rather than read at runtime,
editing `config.toml` requires rebuilding and re-importing the Shortcut
(`make shortcut`, then reinstall on the iPhone) for the change to take
effect there — the Mac-side relay picks up edits immediately on its next
run. Add new single-match patterns by copying a `[[patterns]]` block, or new
threshold rules by copying a `[[count_patterns]]` block; see the comments in
`config.toml.example` for the ERE-portability rules the regex must follow.

Test any new or edited pattern before trusting it: run `make validate` (it
rebuilds and checks the plist), and do one on-device test run of the
rebuilt Shortcut with a disposable/known-fake secret to confirm it actually
blocks before relying on it for a real credential.

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
- `config.toml.example`: tracked, sanitized template of the sensitive-data
  regex patterns shared by the relay script and the Shortcut generator; copy to
  the git-ignored `config.toml`. See [Sensitive-Data Filter](#sensitive-data-filter).
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
