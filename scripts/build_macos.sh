#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Kem Timelapse Studio packaging requires macOS." >&2
  exit 1
fi
if [[ "$(uname -m)" != "arm64" ]]; then
  echo "Kem Timelapse Studio packaging requires Apple Silicon (arm64)." >&2
  exit 1
fi

.venv/bin/pytest -m 'not e2e' -q
.venv/bin/ruff check src tests tools
.venv/bin/mypy src/kem_timelapse

rm -rf build "dist/Kem Timelapse Studio.app"
export PYINSTALLER_CONFIG_DIR="$PWD/.pyinstaller"
.venv/bin/pyinstaller packaging/kem-timelapse.spec --noconfirm --log-level WARN
QT_QPA_PLATFORM=offscreen "dist/Kem Timelapse Studio.app/Contents/MacOS/Kem Timelapse Studio" --smoke-test
