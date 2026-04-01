#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

export PYTHONPATH=src
export PYTHONDONTWRITEBYTECODE=1
export PYTHONHASHSEED=0

echo "[TEST] Running full Python test suite"
python3 -m unittest discover -s tests -p 'test_*.py' -v
