#!/usr/bin/env bash
# ==============================================================================
# ABCI-MI Backend Development Server Launcher
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"

cd "$BACKEND_DIR"

echo "=== ABCI-MI Backend Development Server ==="
echo "Working directory: $BACKEND_DIR"

# Export PYTHONPATH to include backend root
export PYTHONPATH="$BACKEND_DIR:$PYTHONPATH"

# Run Uvicorn development server
python3 -m uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" --reload
