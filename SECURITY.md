# Security Policy

## Reporting

Report vulnerabilities privately with
[GitHub Security Advisories](https://github.com/htlin222/clipboard-snap-shortcut/security/advisories/new).
Do not open a public issue containing a Turso token, configured Shortcut, or
database endpoint paired with credentials.

## Credential Model

The distributed Shortcut contains placeholders, not a database token. Users
should create a database-scoped, `clips:data_add` token with a short expiry.
Configured Shortcuts store that token in recoverable form and must remain
private. The workflow is disabled on the lock screen.

Only the latest tagged release receives security fixes.
