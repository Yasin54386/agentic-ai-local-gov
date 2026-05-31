#!/usr/bin/env bash
# Set up the self-hosted LLM for the Darwin data agent.
# Installs Ollama (if missing) and pulls Qwen2.5-7B-Instruct.
# Everything runs locally on YOUR machine — no external API, no data leaves.
set -euo pipefail

MODEL="${MODEL:-qwen2.5:7b-instruct}"

echo "==> Self-hosted model setup for the Darwin data agent"
echo "    Model: ${MODEL}  (Apache-2.0, runs fully offline once downloaded)"
echo

# 1. Ensure Ollama is installed.
if ! command -v ollama >/dev/null 2>&1; then
  echo "==> Ollama not found. Installing (Linux/macOS)..."
  if [[ "$(uname)" == "Linux" ]]; then
    curl -fsSL https://ollama.com/install.sh | sh
  else
    echo "    Please install Ollama from https://ollama.com/download and re-run."
    exit 1
  fi
else
  echo "==> Ollama already installed: $(ollama --version 2>/dev/null || echo present)"
fi

# 2. Make sure the server is up (Ollama usually auto-starts a daemon).
if ! curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "==> Starting Ollama server in the background..."
  (ollama serve >/tmp/ollama.log 2>&1 &) || true
  sleep 3
fi

# 3. Pull the model (one-time download; cached locally afterwards).
echo "==> Pulling ${MODEL} (one-time download)..."
ollama pull "${MODEL}"

echo
echo "==> Done. Verify with:"
echo "      python -m agent.cli \"How much did each ward spend? Which ward spent the most?\""
echo
echo "    Hardware notes:"
echo "      - 7B model needs ~6-8 GB RAM (or a small GPU) to run comfortably."
echo "      - No GPU? It still runs on CPU, just slower."
echo "      - Bigger/sharper: set MODEL=qwen2.5:32b-instruct (needs a real GPU)."
