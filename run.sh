#!/usr/bin/env bash
# Craftag — launch script
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate venv if present
if [ -d "venv" ]; then
  source venv/bin/activate
fi

python -m craftag_py.main "$@"
