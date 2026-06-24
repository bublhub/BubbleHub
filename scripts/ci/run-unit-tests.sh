#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PYTHON_COVERAGE_THRESHOLD="${PYTHON_COVERAGE_THRESHOLD:-85}"
C_COVERAGE_THRESHOLD="${C_COVERAGE_THRESHOLD:-85}"

find libageos/build -name '*.gcda' -delete
meson test -C libageos/build --print-errorlogs
GCOVR_JSON="$(mktemp)"
gcovr \
  --root "$ROOT/libageos" \
  --exclude-directories 'build' \
  --json "$GCOVR_JSON"
python3 - "$GCOVR_JSON" "$C_COVERAGE_THRESHOLD" <<'PY'
import json
import pathlib
import sys

report_path = pathlib.Path(sys.argv[1])
threshold = float(sys.argv[2])
target_files = {"hw_detect.c", "log.c"}
report = json.loads(report_path.read_text())
rows = []
covered = 0
total = 0
for entry in report["files"]:
    filename = pathlib.Path(entry["file"]).name
    if filename not in target_files:
        continue
    line_total = len(entry["lines"])
    line_covered = sum(1 for line in entry["lines"] if line["count"] > 0)
    rows.append((filename, line_covered, line_total))
    covered += line_covered
    total += line_total

if not rows or total == 0:
    raise SystemExit("No C coverage data found for hw_detect.c/log.c")

print("Native unit coverage:")
for filename, line_covered, line_total in sorted(rows):
    pct = (line_covered / line_total) * 100
    print(f"  {filename}: {line_covered}/{line_total} ({pct:.1f}%)")

overall = (covered / total) * 100
print(f"  total: {covered}/{total} ({overall:.1f}%)")
if overall < threshold:
    raise SystemExit(f"C unit coverage {overall:.1f}% is below threshold {threshold:.1f}%")
PY

find libageos/build -name '*.gcda' -delete
pytest \
  --cov=ageos.engine \
  --cov=ageos.http_api \
  --cov=ageos.inference \
  --cov=ageos.integrations \
  --cov=ageos.log \
  --cov=ageos.node.client \
  --cov-report=term \
  --cov-fail-under="$PYTHON_COVERAGE_THRESHOLD" \
  -m "not integration" \
  "$@"
