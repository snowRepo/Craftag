#!/usr/bin/env bash
# Craftag — launch script
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Prefer the venv Python explicitly so PySide6 is always on sys.path,
# regardless of which shell Python is active when this script is invoked.
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python3"

if [ -x "$VENV_PYTHON" ]; then
  exec "$VENV_PYTHON" -m craftag_py.main "$@"
elif [ -d "venv" ]; then
  # Fallback: activate and hope the venv python is first on PATH
  source venv/bin/activate
  exec python -m craftag_py.main "$@"
else
  echo "ERROR: No venv found at '$SCRIPT_DIR/venv'." >&2
  echo "Run: python3 -m venv venv && venv/bin/pip install -r craftag_py/requirements.txt" >&2
  exit 1
fi
