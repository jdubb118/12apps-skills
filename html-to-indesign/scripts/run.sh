#!/bin/bash
# html-to-indesign: HTML print pages -> verified InDesign package (IDML + Links + Document fonts + Reference PDFs + README) -> archive.
# usage: run.sh <job.json> [--skip-visual]        (every step can also be run on its own; see SKILL.md)
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"; JOB="$1"; PY=${PYTHON:-python3}
echo "== 1/5 resolve job"; R=$($PY "$D/common.py" resolve "$JOB"); echo "   $R"
echo "== 2/5 extract (Chromium; ~10-40 s per page)"; node "$D/extract.mjs" "$R"
node "$D/reference_pdf.mjs" "$R"
echo "== 3/5 build IDML + package folder"; $PY "$D/build.py" "$JOB" --force
echo "== 4/5 gates"; $PY "$D/check.py" "$JOB"
if [[ "${2:-}" != "--skip-visual" ]]; then echo "== visual round-trip"; $PY "$D/visual.py" "$JOB"; fi
echo "== 5/5 archive + expanded-copy test"; $PY "$D/package.py" "$JOB"
