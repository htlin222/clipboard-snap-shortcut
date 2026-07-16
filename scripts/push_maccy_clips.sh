#!/bin/zsh
# Push new plain-text Maccy clips to the shared Turso clips table.
set -euo pipefail

DB="$HOME/Library/Containers/org.p0deje.Maccy/Data/Library/Application Support/Maccy/Storage.sqlite"
SOURCE="maccy-$(hostname -s)"
STATE="$HOME/.local/state/clipboard-snap/$SOURCE.cursor"
ENDPOINT=""
KEYCHAIN_SERVICE="clipboard-snap-$SOURCE"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --db) DB="$2"; shift 2 ;;
    --state) STATE="$2"; shift 2 ;;
    --endpoint) ENDPOINT="$2"; shift 2 ;;
    --keychain-service) KEYCHAIN_SERVICE="$2"; shift 2 ;;
    --source) SOURCE="$2"; shift 2 ;;
    *) print -u2 "unknown argument: $1"; exit 2 ;;
  esac
done

if [[ -z "$ENDPOINT" ]]; then
  print -u2 "--endpoint is required"
  exit 2
fi

if ! pgrep -x Maccy >/dev/null 2>&1; then
  print "Maccy is not running, skipping"
  exit 0
fi

TOKEN=$(security find-generic-password -a "$USER" -s "$KEYCHAIN_SERVICE" -w)

mkdir -p "${STATE:h}"
since=0
[[ -f "$STATE" ]] && since=$(<"$STATE")

SQL="SELECT i.Z_PK, hex(c.ZVALUE)
     FROM ZHISTORYITEM i
     JOIN ZHISTORYITEMCONTENT c ON c.ZITEM = i.Z_PK
     WHERE c.ZTYPE = 'public.utf8-plain-text' AND i.Z_PK > $since
     ORDER BY i.Z_PK ASC;"

pushed=0
cursor=$since
while IFS='|' read -r pk hex_value; do
  [[ -z "$pk" ]] && continue

  if [[ -z "$hex_value" ]]; then
    cursor=$pk
    print "$cursor" > "$STATE"
    continue
  fi

  b64=$(print -r -- "$hex_value" | xxd -r -p | base64 | tr -d '\n')
  payload=$(printf '{"requests":[{"type":"execute","stmt":{"sql":"INSERT INTO clips (text, source) VALUES (CAST(? AS TEXT), ?)","args":[{"type":"blob","base64":"%s"},{"type":"text","value":"%s"}]}},{"type":"close"}]}' \
    "$b64" "$SOURCE")

  response=$(curl -sS -X POST "$ENDPOINT" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "$payload")

  if ! print -r -- "$response" | grep -Eq '"results":\[\{"type":"ok"'; then
    print "stopped at item $pk: $response"
    exit 1
  fi

  cursor=$pk
  pushed=$((pushed + 1))
  print "$cursor" > "$STATE"
done < <(sqlite3 -readonly -separator '|' "$DB" "$SQL")

print "pushed $pushed new clip(s), cursor at $cursor"
