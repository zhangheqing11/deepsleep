"""Compiled regex rules. Exclusions never override an explicit match."""
from dataclasses import dataclass
import re

import yaml

from .config import load_config

LEVEL_RANK = {"none": 0, "passive": 1, "active": 2}


@dataclass(frozen=True)
class RuleHit:
    tier: str
    entry_ids: list[str]
    level: str
    matched: str = ""


class Rules:
    def __init__(self, path=None):
        path = path or load_config()["lexicon_path"]
        with open(path, encoding="utf-8") as stream:
            raw = yaml.safe_load(stream)
        self.entries = {}
        seen = set()
        for tier in ("explicit", "ambiguous", "exclude"):
            entries = []
            for entry in raw[tier]:
                if entry["id"] in seen:
                    raise ValueError(f"Duplicate lexicon id: {entry['id']}")
                seen.add(entry["id"])
                if tier == "explicit" and entry["level"] not in ("passive", "active"):
                    raise ValueError("Explicit rules require passive or active level")
                entries.append((entry, re.compile(entry["pattern"])))
            self.entries[tier] = entries

    def match(self, text: str) -> RuleHit:
        for tier in ("explicit", "ambiguous"):
            hits = [(entry, match) for entry, pattern in self.entries[tier] if (match := pattern.search(text))]
            if not hits:
                continue
            if tier == "ambiguous" and any(pattern.search(text) for _, pattern in self.entries["exclude"]):
                break
            level = max((e["level"] for e, _ in hits), key=LEVEL_RANK.__getitem__) if tier == "explicit" else "passive"
            return RuleHit(tier, [e["id"] for e, _ in hits], level, " | ".join(m.group(0) for _, m in hits))
        return RuleHit("none", [], "none")


def match(text: str) -> RuleHit:
    """Convenience entry point; reuse Rules in a long-running session."""
    return Rules().match(text)
