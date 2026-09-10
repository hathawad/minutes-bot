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
# Copies, never moves. Skips files already ingested. Safe to run repeatedly
# mid-meeting.

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

scan() {
  local dir="$1" origin="$2"
  [[ -d "$dir" ]] || return 0
  while IFS= read -r -d '' f; do
    local name bucket target
    name="$(basename "$f")"
    bucket="$(classify "$name" "$origin")"
    target="$DEST/$bucket/$name"
    if [[ -e "$target" ]] && cmp -s "$f" "$target"; then
      continue
    fi
    cp -p "$f" "$target"
    echo "  $bucket/$name"
    ingested=$((ingested + 1))
  done < <(find "$dir" -maxdepth 1 -type f \
             \( -name '*.txt' -o -name '*.md' -o -name '*.vtt' -o -name '*.srt' \) \
             -newer "$NEWER" -print0 2>/dev/null)
}

echo "ingesting into $MEETING/transcripts/"
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
