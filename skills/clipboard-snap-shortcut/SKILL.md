---
name: clipboard-snap-shortcut
description: Build, regenerate, validate, and sign the Clipboard Snap Apple Shortcut that sends selected or copied iOS text to a Turso database through SQL over HTTP, and inspect the stored records with the authenticated Turso CLI. Use when creating or changing the .shortcut/.xml artifact, its Turso table and scoped token setup, retrieving saved clips, Share Sheet or clipboard behavior, import-time credential questions, or user documentation for this workflow.
---

# Clipboard Snap Shortcut

Build an importable iOS Shortcut that writes text to Turso without committing a database URL or token.

## Required Behavior

- Accept `WFStringContentItem` and `WFRichTextContentItem` from the Share Sheet.
- Use `WFWorkflowNoInputBehaviorGetClipboard` when run without shared input.
- Do not claim that iOS can automatically trigger on every clipboard change. Use Share Sheet invocation or manual invocation after Copy.
- Send `POST <database-http-url>/v2/pipeline` with Bearer authentication.
- Base64-encode the text, bind it as a blob argument, and cast it back to text in SQL. Never interpolate selected text into SQL or raw JSON.
- Keep the endpoint and database token in Text actions populated by import questions.
- Use an insert-only, database-scoped Turso token for the `clips` table.
- Disable lock-screen execution because the Shortcut can read the clipboard and contains a credential.
- On success, show `Text saved to Turso.` with the first line of the inserted text as the notification preview.
- Never put a real token in source files, logs, examples, or the default artifact. Only create an ignored private artifact with `--token-stdin` when the user explicitly requests embedded credentials.

## Build Workflow

1. Read [references/turso-http.md](references/turso-http.md) before changing the request, schema, authentication, or credential flow.
2. Generate the unsigned plist from the repository root:

   ```bash
   uv run skills/clipboard-snap-shortcut/scripts/build_shortcut.py \
     --output "dist/Clipboard Snap.xml"
   ```

3. Run the focused structural validator:

   ```bash
   uv run skills/clipboard-snap-shortcut/scripts/check_shortcut.py \
     "dist/Clipboard Snap.xml"
   ```

4. Validate with Shortcuts Playground when it is available. Resolve its skill directory, then run:

   ```bash
   uv run "$SHORTCUTS_PLAYGROUND_SKILL_DIR/scripts/validate_shortcut.py" \
     "dist/Clipboard Snap.xml" --target-macos 27 --target-platform ios
   ```

5. Sign on macOS with Apple's CLI:

   ```bash
   uv run skills/clipboard-snap-shortcut/scripts/sign_shortcut.py \
     "dist/Clipboard Snap.xml" \
     --output "dist/Clipboard Snap.shortcut"
   ```

6. Verify both artifacts are non-empty. Do not run the Shortcut against a live database without explicit permission and a test token.

## Database Setup

Use the full path requested by this project:

```bash
/opt/homebrew/bin/turso db create clipboard-snap
/opt/homebrew/bin/turso db shell clipboard-snap \
  < skills/clipboard-snap-shortcut/assets/schema.sql
/opt/homebrew/bin/turso db show clipboard-snap --http-url
/opt/homebrew/bin/turso db tokens create clipboard-snap \
  -p clips:data_add --expiration 90d
```

If the database already exists, skip `db create`. If the installed CLI rejects `data_add`, update the CLI rather than granting a broader token; `data_add` is Turso's documented insert permission.

## Read Saved Records

Use the authenticated Mac CLI for reads. Do not broaden or reuse the iPhone's
insert-only token. From the repository root, retrieve the full latest record:

```bash
make db-latest \
  TURSO=/opt/homebrew/bin/turso \
  DB=clipboard-snap
```

List the ten latest previews:

```bash
make db-verify \
  TURSO=/opt/homebrew/bin/turso \
  DB=clipboard-snap
```

Retrieve one full record only after validating that the requested ID is a
positive integer:

```bash
make db-record \
  TURSO=/opt/homebrew/bin/turso \
  DB=clipboard-snap \
  ID=123
```

When the user asks for the latest message, report the record ID, UTC timestamp,
source, and exact text returned by `make db-latest`. If no row is returned, say
that the table is empty. Do not expose CLI authentication material or mint a
read token for this task.

## Credential Rules

- Ask for the complete pipeline endpoint, ending in `/v2/pipeline`.
- Ask for the raw database token only; add `Bearer ` in the Authorization header.
- Explain that Shortcuts stores Text action contents visibly in the workflow editor. This is not Keychain storage.
- Recommend a 90-day insert-only token and document rotation. Allow a non-expiring token only after explaining the increased impact of device or Shortcut disclosure.
- On rotation, edit the `Turso database token` Text action or re-import the Shortcut.

## Editing Rules

- Preserve action indexes `2` and `3` unless updating `WFWorkflowImportQuestions` in the same change.
- Preserve parameter binding in the Turso payload:

  ```sql
  INSERT INTO clips (text, source) VALUES (CAST(? AS TEXT), 'ios-shortcut')
  ```

- Preserve the JSON Text body and connect it to `WFRequestVariable` with a direct `WFTextTokenAttachment`. A `WFTextTokenString` wrapper imports but sends a zero-byte request body.
- Preserve the pipeline `close` request.
- Keep the first two Comment actions and the wiring comment immediately before the If block.
- Regenerate the XML from the script after changes. Do not hand-edit the generated plist.
- Update the root `README.md` when setup, invocation, key placement, or rotation changes.

## Resources

- `scripts/build_shortcut.py`: deterministic XML plist generator.
- `scripts/check_shortcut.py`: focused contract and secret-safety validator.
- `scripts/sign_shortcut.py`: binary-plist conversion and Apple signing wrapper.
- `references/turso-http.md`: API, security, payload, and iOS behavior reference.
- `assets/schema.sql`: Turso table schema applied before importing the Shortcut.
