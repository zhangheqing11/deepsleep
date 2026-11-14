"""Playbook loading; sections are keyed by the contract's playbook_section enum."""
from dataclasses import dataclass
from pathlib import Path
import re

SECTIONS = ("communication_style", "questioning_strategy", "path_discrimination", "plan_rules", "referral_rules")
_HEADING = re.compile(r"^##\s+(\S+)\s*$", re.MULTILINE)
LOCK_MARK = "<!-- locked -->"
_LOCK = re.compile(r"\s*<!--\s*locked\s*-->")


@dataclass(frozen=True)
class Playbook:
    version: str
    text: str
    sections: dict[str, str]


def parse_sections(text: str) -> dict[str, str]:
    matches = list(_HEADING.finditer(text))
    names = [m.group(1) for m in matches]
    if names != list(SECTIONS):
        raise ValueError(f"playbook sections must be exactly {list(SECTIONS)} in order, got {names}")
    sections = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[match.group(1)] = text[match.end():end].strip()
    return sections


def load_playbook(path: Path | str, version: str = "v0") -> Playbook:
    text = Path(path).read_text(encoding="utf-8")
    return Playbook(version, text, parse_sections(text))


def locked_lines(text: str) -> list[str]:
    """Safety lines evolution must keep verbatim (S4 hard rule reads these)."""
    return [_LOCK.sub("", line).rstrip() for line in text.splitlines() if _LOCK.search(line)]


def strip_locks(text: str) -> str:
    return _LOCK.sub("", text)


def render_for_agent(playbook: Playbook) -> str:
    """Only the five sections reach the agent; the human preamble stays out."""
    return "\n\n".join(f"## {name}\n{strip_locks(playbook.sections[name])}" for name in SECTIONS)
