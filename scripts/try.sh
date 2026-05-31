#!/usr/bin/env bash
# Try Ask Territory locally. No pip, no venv — pure Python standard library.
# Usage:  bash scripts/try.sh
set -euo pipefail

cd "$(dirname "$0")/.."

# 1. Check Python.
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 not found. Install it (macOS: 'brew install python3') and retry."
  exit 1
fi
echo "==> Using $(python3 --version)"

# 2. Make sure the data is present (it ships with the repo; rebuild if missing).
if [ ! -f data/unified.db ]; then
  echo "==> Unified data not found — building it (one-time, ~1 min)…"
  python3 -m ingestion.harvest --report
  python3 -m ingestion.fetch_data --api-sources
  python3 -m ingestion.unify
fi

# 3. Note about the chat tab.
if ! curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "==> Note: local model not running, so the 'Ask' chat tab will be disabled."
  echo "    The Neighbourhood / Live / Transparency / Repository tabs work now."
  echo "    To enable chat later: bash scripts/setup_local_model.sh"
fi

# 4. Open the browser (best-effort) and start the server.
PORT="${PORT:-8000}"
URL="http://localhost:${PORT}"
( sleep 2
  if command -v open >/dev/null 2>&1; then open "$URL"          # macOS
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" # Linux
  fi ) >/dev/null 2>&1 &

echo "==> Starting Ask Territory at ${URL}  (Ctrl-C to stop)"
PORT="$PORT" python3 -m webapp.server
