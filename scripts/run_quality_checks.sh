#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[1/3] Python compile checks"
python3 -m py_compile main.py webapp.py app_store.py manuscript_service.py journal_recommender.py document_processor.py chicago_editor.py job_queue.py routes/*.py scripts/check_dependency_lock.py scripts/check_version_consistency.py
python3 scripts/check_version_consistency.py
python3 scripts/check_dependency_lock.py

echo "[2/3] Frontend syntax checks"
# Check every shipped JS file, not a hand-maintained list.
JS_FILES="$(find web -name '*.js' -type f | sort)"
if [ -z "$JS_FILES" ]; then
  echo "No frontend JavaScript files found under web/" >&2
  exit 1
fi
echo "$JS_FILES" | while IFS= read -r js_file; do
  node --check "$js_file"
done

echo "[3/3] Regression tests"
python3 -m unittest discover -s tests -p "test_*.py" -v

echo "All quality checks passed."
