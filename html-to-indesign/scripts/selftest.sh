#!/bin/bash
# html-to-indesign self-test: rebuild the sample line sheet (non-facing pages, TrueType, transparency over a photo,
# rounded corners, native SVG paths, SVG arc raster fallback, rotated text) and require every gate to pass.
# After changing the builder, also rebuild a real job you have delivered and diff it: compare_idml.py OLD.idml NEW.idml
set -uo pipefail
D="$(cd "$(dirname "$0")" && pwd)"; S="$(dirname "$D")"; PY=${PYTHON:-python3}
fail=0
out=$(bash "$D/run.sh" "$S/examples/sample-linesheet/linesheet.job.json" 2>&1); echo "$out" | grep -E 'PASS|FAIL|RESULT|LOOK|expanded|WARN'
echo "$out" | grep -q 'RESULT: ALL GATES PASS' || fail=1
echo "$out" | grep -q 'links + references OK' || fail=1
echo "SELFTEST: $([ $fail -eq 0 ] && echo PASS || echo FAIL)"; exit $fail
