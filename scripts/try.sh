#!/usr/bin/env bash
# Try Ask Territory locally. The data panels are pure Python standard library;
# the AI chat needs `pip install -r requirements.txt` and ANTHROPIC_API_KEY.
# Usage:  bash scripts/try.sh
set -euo pipefail

cd "$(dirname "$0")/.."

# 1. Check Python.
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 not found. Install it (macOS: 'brew install python3') and retry."
  exit 1
fi
echo "==> Using $(python3 --version)"

# 2. Build the local database if it doesn't exist (migrate + load).
#    The source artifacts (catalog.db, unified.db, column_catalog.json) ship with
#    the repo, so this just creates data/askterritory.db from them.
if [ ! -f data/askterritory.db ]; then
  echo "==> Local database not found — creating it (migrate + load)…"
  python3 -m db.migrate
  python3 -m db.load
fi

# 3. Note about the chat tab.
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "==> Note: ANTHROPIC_API_KEY not set, so the 'Ask' chat tab will be disabled."
  echo "    The Neighbourhood / Live / Transparency / Repository tabs work now."
  echo "    To enable chat: pip install -r requirements.txt && export ANTHROPIC_API_KEY=sk-..."
  echo "    (Chat questions are processed by a third-party AI service.)"
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
