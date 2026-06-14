"""Command-line interface for the Ask Territory data agent.

Usage:
    python -m agent.cli "How much did each ward spend? Which spent most?"
    python -m agent.cli            # interactive REPL

Requires ANTHROPIC_API_KEY in the environment for the hosted "AI Powered" chat.
Questions are processed by a third-party AI service — don't include personal
information.
"""
from __future__ import annotations

import sys

from . import llm
from .agent import run
from .repository import Repository


def _preflight() -> bool:
    if not llm.server_up():
        print(
            "\n[!] AI chat is not configured.\n"
            "    Set ANTHROPIC_API_KEY in your environment, then re-run.\n"
            "    Note: questions are processed by a third-party AI service —\n"
            "    don't include personal information.\n",
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
        print("Ask Territory data agent (AI Powered). "
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
