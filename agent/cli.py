"""Command-line interface for the self-hosted data agent.

Usage:
    python -m agent.cli "How much did each ward spend? Which spent most?"
    python -m agent.cli            # interactive REPL

Requires a local Ollama server running Qwen2.5-7B-Instruct (see agent/README.md).
Everything runs on your own machine — no external API.
"""
from __future__ import annotations

import sys

from . import llm
from .agent import run
from .repository import Repository


def _preflight() -> bool:
    if not llm.server_up():
        print(
            "\n[!] No local model server reachable at "
            f"{llm.OLLAMA_HOST}.\n"
            "    Start your self-hosted model first:\n"
            "      1. Install Ollama:        https://ollama.com/download\n"
            "      2. Pull the model:        ollama pull qwen2.5:7b-instruct\n"
            "      3. (Ollama serves automatically on localhost:11434)\n"
            "    Then re-run this command. Nothing leaves your machine.\n",
            file=sys.stderr,
        )
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not _preflight():
        return 1

    repo = Repository()
    try:
        if argv:
            question = " ".join(argv)
            print(f"\nQ: {question}\n")
            print(run(question, repo=repo))
            return 0
        # interactive
        print(f"Self-hosted Darwin data agent ({llm.DEFAULT_MODEL}). "
              "Ctrl-C or 'exit' to quit.\n")
        while True:
            try:
                q = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if q.lower() in {"exit", "quit"}:
                return 0
            if q:
                print(run(q, repo=repo), "\n")
    finally:
        repo.close()


if __name__ == "__main__":
    raise SystemExit(main())
