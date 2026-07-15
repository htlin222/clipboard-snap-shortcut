# Turso HTTP Contract

## iOS Invocation

iOS Shortcuts has no clipboard-change automation trigger. Support both practical paths:

1. Select text, tap **Share**, and choose **Clipboard Snap**. The selection is Shortcut Input.
2. Copy text, then run **Clipboard Snap** from Shortcuts, a widget, Back Tap, the Home Screen, or the Action Button. The no-input behavior supplies the clipboard.

The shortcut accepts plain and rich text, but stores its text representation.
If neither source contains text, show a message and do not call Turso.

## Endpoint And Authentication

- Base URL: obtain with `turso db show <database> --http-url`.
- Endpoint: append `/v2/pipeline`.
- Method: `POST`.
- Header: `Authorization: Bearer <database-token>`.
- Header: `Content-Type: application/json`.
- Token scope: one database and `clips:data_add` only.

Official references:

- [Turso SQL over HTTP](https://docs.turso.tech/sdk/http/reference)
- [Turso authorization](https://docs.turso.tech/sdk/authorization)
- [Turso fine-grained permissions](https://docs.turso.tech/sdk/authorization/fine-grained-permissions)
- [Turso database token CLI](https://docs.turso.tech/cli/db/tokens/create)

## Pipeline Body

Turso's pipeline body is deeply nested. Shortcuts can mangle it when represented as structured `WFJSONValues`, so build it in a JSON Text action and send that action through `WFRequestVariable` with body type `File`. The request variable must be a direct `WFTextTokenAttachment`; wrapping it in `WFTextTokenString` produces `Content-Length: 0` at runtime.

Do not interpolate raw user text into the JSON template. Base64-encode the UTF-8 input first, which limits the dynamic value to JSON-safe ASCII, bind it as a blob, and cast it back to text in SQL.

```json
{
  "requests": [
    {
      "type": "execute",
      "stmt": {
        "sql": "INSERT INTO clips (text, source) VALUES (CAST(? AS TEXT), 'ios-shortcut')",
        "args": [
          {
            "type": "blob",
            "base64": "<Base64 Encoded Shortcut Input>"
          }
        ]
      }
    },
    {
      "type": "close"
    }
  ]
}
```

Using a bound UTF-8 blob keeps quotes, newlines, backslashes, emoji, and other copied content out of the SQL statement and JSON template while storing the original text value.

## Result Contract

Read `results`, take the first item, and read its `type` field.

- `ok`: show a saved notification with the first line of the inserted text.
- Any other value: show the first pipeline result for diagnosis.
- HTTP authentication and connectivity failures stop at **Get Contents of URL** with the system error.

## Credential Storage

The generated artifact contains only these placeholders:

- `https://DATABASE-ORG.turso.io/v2/pipeline`
- `PASTE_DATABASE_TOKEN_HERE`

Import questions replace them on the user's device. The answers remain visible in the workflow's Text actions. Use the least-privileged token, do not share a configured Shortcut, disable lock-screen execution, and rotate the token after device or Shortcut disclosure.

## Schema

Apply `../assets/schema.sql` with the authenticated Turso CLI before using the Shortcut. The database assigns the ID and UTC timestamp, so the iPhone only sends text.
