#!/bin/bash
# new.sh <piece-dir> [--from <existing-piece-dir>] — scaffold a motion-kit piece.
# Default = the skeleton template (studio headline → line wipe → end card; renders + passes QA as-is).
# --from copies another piece's SOURCE (index/BRIEF/COPY/prep/brand), never its assets or renders: run ./prep.sh.
set -euo pipefail
DST="${1:?usage: new.sh <piece-dir> [--from <existing-piece-dir>]}"
SK="$(cd "$(dirname "$0")/.." && pwd -P)"
[ -e "$DST" ] && { echo "exists: $DST"; exit 1; }
mkdir -p "$DST"
if [ "${2:-}" = "--from" ]; then
  SRC="${3:?--from needs a piece dir}"
  for f in index.html BRIEF.md COPY.md prep.sh brand.json hyperframes.json package.json; do
    [ -f "$SRC/$f" ] && cp "$SRC/$f" "$DST/"
  done
  echo "copied source from $SRC — run $DST/prep.sh to rebuild its assets"
else
  cp "$SK"/templates/piece/* "$DST/"
  cp "$SK"/brand.json "$DST/"
fi
SLUG="$(basename "$DST")"
sed -i.bak "s/\"name\": *\"[^\"]*\"/\"name\": \"$SLUG\"/" "$DST/package.json" && rm -f "$DST/package.json.bak"
echo "$DST"
echo "next: BRIEF.md → COPY.md → brand.json → prep.sh → index.html → $SK/scripts/render.sh $DST draft"
