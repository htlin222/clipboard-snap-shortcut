#!/bin/zsh
# Push new plain-text Maccy clips to the shared Turso clips table.
set -euo pipefail

DB="$HOME/Library/Containers/org.p0deje.Maccy/Data/Library/Application Support/Maccy/Storage.sqlite"
SOURCE="maccy-$(hostname -s)"
STATE="$HOME/.local/state/clipboard-snap/$SOURCE.cursor"
ENDPOINT=""
KEYCHAIN_SERVICE="clipboard-snap-$SOURCE"
CONFIG="${0:A:h:h}/config.toml"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --db) DB="$2"; shift 2 ;;
    --state) STATE="$2"; shift 2 ;;
    --endpoint) ENDPOINT="$2"; shift 2 ;;
    --keychain-service) KEYCHAIN_SERVICE="$2"; shift 2 ;;
    --source) SOURCE="$2"; shift 2 ;;
    --config) CONFIG="$2"; shift 2 ;;
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

# Load the [[patterns]] regex list from config.toml into two parallel
# arrays. Matching is done with `grep -Eiq` (see config.toml for why: no
# PCRE features, this has to run under whatever grep ships on each Mac).
pattern_names=()
pattern_regexes=()
if [[ -f "$CONFIG" ]]; then
  while IFS=$'\t' read -r pname pregex; do
    [[ -z "$pregex" ]] && continue
    pattern_names+=("$pname")
    pattern_regexes+=("$pregex")
  done < <(awk -f - "$CONFIG" <<'AWK_EOF'
BEGIN { name = "unnamed"; intable = 0 }
/^[[:space:]]*\[\[patterns\]\]/ { name = "unnamed"; intable = 1; next }
/^[[:space:]]*\[\[count_patterns\]\]/ { intable = 0; next }
!intable { next }
/^[[:space:]]*name[[:space:]]*=/ {
  line = $0
  sub(/^[^=]*=[[:space:]]*/, "", line)
  gsub(/^"/, "", line)
  gsub(/"[[:space:]]*$/, "", line)
  name = line
}
/^[[:space:]]*regex[[:space:]]*=/ {
  line = $0
  sub(/^[^=]*=[[:space:]]*/, "", line)
  gsub(/^'/, "", line)
  gsub(/'[[:space:]]*$/, "", line)
  print name "\t" line
}
AWK_EOF
  )
else
  print -u2 "warning: sensitive-pattern config not found at $CONFIG, pushing unfiltered"
fi

is_sensitive() {
  local text="$1" i
  for (( i = 1; i <= ${#pattern_regexes[@]}; i++ )); do
    if print -r -- "$text" | grep -Eiq -e "${pattern_regexes[$i]}"; then
      matched_pattern_name="${pattern_names[$i]}"
      return 0
    fi
  done
  return 1
}

# Load the [[count_patterns]] table into four parallel arrays.
count_names=()
count_token_regexes=()
count_match_regexes=()
count_min_counts=()
if [[ -f "$CONFIG" ]]; then
  while IFS=$'\t' read -r cname ctoken cmatch cmin; do
    [[ -z "$cname" ]] && continue
    count_names+=("$cname")
    count_token_regexes+=("$ctoken")
    count_match_regexes+=("$cmatch")
    count_min_counts+=("$cmin")
  done < <(awk -f - "$CONFIG" <<'AWK_EOF'
function flush() {
  if (name != "") print name "\t" token_regex "\t" match_regex "\t" min_count
  name = ""; token_regex = ""; match_regex = ""; min_count = ""
}
BEGIN { name = ""; intable = 0 }
/^[[:space:]]*\[\[count_patterns\]\]/ { flush(); intable = 1; next }
/^[[:space:]]*\[\[patterns\]\]/ { flush(); intable = 0; next }
!intable { next }
/^[[:space:]]*name[[:space:]]*=/ {
  line = $0
  sub(/^[^=]*=[[:space:]]*/, "", line)
  gsub(/^"/, "", line)
  gsub(/"[[:space:]]*$/, "", line)
  name = line
}
/^[[:space:]]*shell_token_regex[[:space:]]*=/ {
  line = $0
  sub(/^[^=]*=[[:space:]]*/, "", line)
  gsub(/^'/, "", line)
  gsub(/'[[:space:]]*$/, "", line)
  token_regex = line
}
/^[[:space:]]*shell_match_regex[[:space:]]*=/ {
  line = $0
  sub(/^[^=]*=[[:space:]]*/, "", line)
  gsub(/^'/, "", line)
  gsub(/'[[:space:]]*$/, "", line)
  match_regex = line
}
/^[[:space:]]*min_count[[:space:]]*=/ {
  line = $0
  sub(/^[^=]*=[[:space:]]*/, "", line)
  gsub(/[[:space:]]*$/, "", line)
  min_count = line
}
END { flush() }
AWK_EOF
  )
fi

is_bulk_sensitive() {
  local text="$1" i count
  for (( i = 1; i <= ${#count_names[@]}; i++ )); do
    count=$(print -r -- "$text" | grep -oE -- "${count_token_regexes[$i]}" | grep -cE -- "${count_match_regexes[$i]}" || true)
    if (( count >= count_min_counts[i] )); then
      matched_pattern_name="${count_names[$i]} (${count}x)"
      return 0
    fi
  done
  return 1
}

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
skipped=0
cursor=$since
while IFS='|' read -r pk hex_value; do
  [[ -z "$pk" ]] && continue

  if [[ -z "$hex_value" ]]; then
    cursor=$pk
    print "$cursor" > "$STATE"
    continue
  fi

  text=$(print -r -- "$hex_value" | xxd -r -p)
  if { (( ${#pattern_regexes[@]} > 0 )) && is_sensitive "$text"; } \
    || { (( ${#count_names[@]} > 0 )) && is_bulk_sensitive "$text"; }; then
    print "skipped item $pk: matched sensitive pattern '$matched_pattern_name'"
    skipped=$((skipped + 1))
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

print "pushed $pushed new clip(s), skipped $skipped sensitive item(s), cursor at $cursor"
