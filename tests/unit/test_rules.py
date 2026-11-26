import re
from pathlib import Path

from ctxbook.rules import MEMORY_RULE

CLAUDE_MD = Path(__file__).resolve().parents[2] / "CLAUDE.md"


def test_memory_rule_matches_claude_md_exactly() -> None:
    text = CLAUDE_MD.read_text(encoding="utf-8")
    match = re.search(r"The rule text \(same everywhere.*?\n```\n(.*?)```", text, re.S)
    assert match is not None, "rule block not found in CLAUDE.md section 10"
    assert match.group(1) == MEMORY_RULE
