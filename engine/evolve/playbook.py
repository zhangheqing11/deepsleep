"""Playbook markdown format shared with the session loop (S3).

Format: free preamble, then one ``## <playbook_section>`` heading per contract section
(text after the key on the heading line is allowed, e.g. ``## plan_rules 处方规则``).
Each non-empty line of a section body is one rule. Lines carrying the locked marker
cannot be modified or deleted by the agent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import difflib
import re

from .config import SECTIONS

_HEADING = re.compile(r"^##\s+([a-z_]+)\b")


class ApplyError(ValueError):
    """A change cannot be applied to the playbook (e.g. ``before`` text not found)."""


@dataclass
class Section:
    key: str
    heading: str
    lines: list[str] = field(default_factory=list)


@dataclass
class Playbook:
    preamble: list[str]
    sections: dict[str, Section]

    @classmethod
    def parse(cls, text: str) -> "Playbook":
        preamble: list[str] = []
        sections: dict[str, Section] = {}
        current: Section | None = None
        for line in text.splitlines():
            match = _HEADING.match(line)
            if match and match.group(1) in SECTIONS:
                key = match.group(1)
                if key in sections:
                    raise ValueError(f"playbook 章节重复: {key}")
                current = sections[key] = Section(key, line)
            elif current is None:
                preamble.append(line)
            else:
                current.lines.append(line)
        missing = [key for key in SECTIONS if key not in sections]
        if missing:
            raise ValueError(f"playbook 缺少章节: {', '.join(missing)}")
        return cls(preamble, sections)

    def render(self) -> str:
        out = list(self.preamble)
        for key in SECTIONS:
            section = self.sections[key]
            out.append(section.heading)
            out.extend(section.lines)
        return "\n".join(out).rstrip("\n") + "\n"

    def section_text(self, key: str) -> str:
        return "\n".join(self.sections[key].lines).strip()

    def find_line(self, key: str, text: str) -> int | None:
        """Index of the first line in ``key`` that contains ``text`` (whitespace-trimmed)."""
        needle = text.strip()
        for index, line in enumerate(self.sections[key].lines):
            if needle and needle in line:
                return index
        return None

    def apply(self, change: dict) -> None:
        op, key = change["op"], change["section"]
        if key not in self.sections:
            raise ApplyError(f"未知章节: {key}")
        lines = self.sections[key].lines
        if op == "add":
            insert_at = len(lines)
            while insert_at > 0 and not lines[insert_at - 1].strip():
                insert_at -= 1
            lines.insert(insert_at, change["after"].strip())
            return
        index = self.find_line(key, change["before"] or "")
        if index is None:
            raise ApplyError(f"{key} 中找不到要{'修改' if op == 'modify' else '删除'}的原文")
        before = change["before"].strip()
        line = lines[index]
        if op == "modify":
            lines[index] = line.replace(before, change["after"].strip(), 1)
        elif op == "delete":
            remainder = line.replace(before, "", 1).strip()
            if remainder:
                lines[index] = remainder
            else:
                del lines[index]
        else:
            raise ApplyError(f"未知 op: {op}")


def apply_changes(text: str, changes: list[dict]) -> str:
    playbook = Playbook.parse(text)
    for change in changes:
        playbook.apply(change)
    return playbook.render()


def unified_diff(before: str, after: str, name: str = "playbook.md") -> str:
    return "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile=f"a/{name}", tofile=f"b/{name}",
    ))
