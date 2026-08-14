"""Prompts live as versioned markdown beside their agents (AGENTS.md)."""

from functools import cache
from pathlib import Path

PROMPT_DIR = Path(__file__).parent


@cache
def load(name: str) -> str:
    """Read ``<name>.md`` from this directory."""
    path = PROMPT_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"no prompt named {name!r} in {PROMPT_DIR}")
    return path.read_text(encoding="utf-8").strip()


def built_in_guideline() -> str:
    """The always-on AI-slop ruleset."""
    return load("built_in_guideline")
