#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

export PYTHONPATH=src

echo "[E2E] Running PR-blocking CLI/API end-to-end suite"
python3 -m unittest -v \
  tests.test_cli_smoke \
  tests.test_console_api

