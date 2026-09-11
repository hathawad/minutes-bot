#!/usr/bin/env bash
# Pull new transcript files into a meeting's transcripts/ folder.
#
#   ./ingest-transcripts.sh KCS/2026-09-10
#   ./ingest-transcripts.sh KCS/2026-09-10 --plaud    # the Plaud device export
#
# Sources scanned, newest first:
#   data/transcripts/   local recorder output  -> incremental/
#   ~/Downloads/        laptop chunks          -> incremental/
#
# Everything defaults to incremental/, since during the meeting every drop is
# a chunk. Pass --plaud for the device export at the end.
#
# Incremental chunks are renumbered in arrival order as they land:
#   01 - School Operations, Security, and Governance-transcript.txt
#   02 - Governance Review Standard, Financial Update...-transcript.txt
#
# Copies, never moves. Skips files already ingested (matched by content, so a
# rename won't cause a duplicate). Safe to run repeatedly mid-meeting.

set -euo pipefail

BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEETING="${1:-}"
FORCE="${2:-}"

if [[ -z "$MEETING" ]]; then
  echo "usage: $(basename "$0") <ORG/YYYY-MM-DD> [--plaud|--incremental]" >&2
  exit 2
fi

DEST="$BASE/$MEETING/transcripts"
if [[ ! -d "$DEST" ]]; then
  echo "no transcripts folder at $DEST" >&2
  echo "create the meeting folder first, or check the path" >&2
  exit 1
fi
mkdir -p "$DEST/incremental" "$DEST/plaud"

# Only pick up files touched since the meeting folder was created, so old
# Downloads clutter doesn't get swept in.
NEWER="$BASE/$MEETING"

ingested=0

classify() {
  # A local-recorder chunk looks like "2026-09-10 19_25_31-transcript.txt".
  # Anything else from Downloads is assumed to be a Plaud export.
  local name="$1" origin="$2"
  case "$FORCE" in
    --plaud)       echo plaud; return ;;
    --incremental) echo incremental; return ;;
  esac
  # Default to incremental: during the meeting every drop is a chunk. The
  # Plaud device export lands once, at the end, and gets --plaud.
  echo incremental
}

# Highest sequence number already used in a bucket, plus one.
next_seq() {
  local bucket="$1" hi=0 n
  for existing in "$DEST/$bucket"/[0-9][0-9]\ -\ *; do
    [[ -e "$existing" ]] || continue
    n=$(basename "$existing" | cut -c1-2)
    n=$((10#$n))
    (( n > hi )) && hi=$n
  done
  echo $((hi + 1))
}

# True if this exact content is already in the bucket, whatever it got named.
already_have() {
  local bucket="$1" src="$2"
  for existing in "$DEST/$bucket"/*; do
    [[ -f "$existing" ]] || continue
    cmp -s "$src" "$existing" && return 0
  done
  return 1
}

scan() {
  local dir="$1" origin="$2"
  [[ -d "$dir" ]] || return 0
  while IFS= read -r -d '' f; do
    local name bucket clean target
    name="$(basename "$f")"
    bucket="$(classify "$name" "$origin")"

    # Already ingested under any sequence number? Skip.
    if already_have "$bucket" "$f"; then
      continue
    fi

    if [[ "$bucket" == "incremental" ]]; then
      # Strip the recorder's date prefix, then number in arrival order:
      # "09-10 Meeting_ Finance Policy-transcript.txt" -> "03 - Finance Policy-transcript.txt"
      clean="$(printf '%s' "$name" | sed -E 's/^[0-9]{2}-[0-9]{2}( Meeting_)? *//; s/^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}_[0-9]{2}_[0-9]{2}-/session-/')"
      target="$DEST/$bucket/$(printf '%02d' "$(next_seq "$bucket")") - $clean"
    else
      target="$DEST/$bucket/$name"
    fi

    cp -p "$f" "$target"
    echo "  $bucket/$(basename "$target")"
    ingested=$((ingested + 1))
  done < <(find "$dir" -maxdepth 1 -type f \
             \( -name '*.txt' -o -name '*.md' -o -name '*.vtt' -o -name '*.srt' \) \
             -newer "$NEWER" -print0 2>/dev/null)
}

# Files dropped straight into incremental/ by hand arrive unnumbered. Number
# them in place before ingesting anything new, so the sequence stays correct.
normalize() {
  local clean
  for f in "$DEST/incremental"/*; do
    [[ -f "$f" ]] || continue
    local name; name="$(basename "$f")"
    [[ "$name" == .* || "$name" == README.md ]] && continue
    [[ "$name" =~ ^[0-9]{2}\ -\  ]] && continue
    clean="$(printf '%s' "$name" | sed -E 's/^[0-9]{2}-[0-9]{2}( Meeting_)? *//')"
    mv "$f" "$DEST/incremental/$(printf '%02d' "$(next_seq incremental)") - $clean"
    echo "  renumbered: $clean"
    ingested=$((ingested + 1))
  done
}

echo "ingesting into $MEETING/transcripts/"
normalize
scan "$BASE/data/transcripts" recorder
scan "$HOME/Downloads" downloads

if [[ $ingested -eq 0 ]]; then
  echo "  (nothing new)"
else
  echo "$ingested file(s) ingested"
fi

echo
echo "current contents:"
find "$DEST" -type f ! -name '.gitkeep' -exec basename {} \; | sort | sed 's/^/  /'
