"""Frozen lexical routing; exclusions never override explicit risk evidence."""
from dataclasses import dataclass
import re
import unicodedata

import yaml

from .config import load_config

LEVEL_RANK = {"none": 0, "passive": 1, "active": 2}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\u200b-\u200d\ufeff]", "", text)
    text = re.sub(r"(?<=[\u3400-\u9fff])[^\S\n]+(?=[\u3400-\u9fff])", "", text)
    return text.translate(str.maketrans({",": "，", ".": "。", ";": "；", ":": "："}))


@dataclass(frozen=True)
class RuleHit:
    tier: str
    entry_ids: list[str]
    level: str
    matched: str = ""
    context_hint: str = ""
    past_time_ids: tuple[str, ...] = ()


class Rules:
    def __init__(self, path=None):
        path = path or load_config()["lexicon_path"]
        with open(path, encoding="utf-8") as stream:
            raw = yaml.safe_load(stream)
        self.entries = {}
        seen = set()
        for tier in ("explicit", "ambiguous", "exclude", "past_time"):
            entries = []
            for entry in raw.get(tier, []):
                if entry["id"] in seen:
                    raise ValueError(f"Duplicate lexicon id: {entry['id']}")
                seen.add(entry["id"])
                if tier == "explicit" and entry["level"] != "active":
                    raise ValueError("Explicit rules require active level")
                entries.append((entry, re.compile(entry["pattern"])))
            self.entries[tier] = entries

    def match(self, text: str) -> RuleHit:
        explicit, routed, ambiguous, past_ids, hints = [], [], [], [], []
        for sentence in re.split(r"[。！？!?；;\n]+", normalize(text)):
            past = [entry["id"] for entry, pattern in self.entries["past_time"] if pattern.search(sentence)]
            for entry, pattern in self.entries["explicit"]:
                for match in pattern.finditer(sentence):
                    (routed if past else explicit).append((entry["id"], match.group()))
                    if past:
                        past_ids.extend(past)
            exclusions = [match.span() for entry, pattern in self.entries["exclude"]
                          if not entry.get("context_hint") for match in pattern.finditer(sentence)]
            sentence_hits = []
            for entry, pattern in self.entries["ambiguous"]:
                for match in pattern.finditer(sentence):
                    if not any(start < match.end() and match.start() < end for start, end in exclusions):
                        sentence_hits.append((entry["id"], match.group()))
            if sentence_hits:
                ambiguous.extend(sentence_hits)
                hints.extend(entry["context_hint"] for entry, pattern in self.entries["exclude"]
                             if entry.get("context_hint") and pattern.search(sentence))
        # A current explicit hit in another sentence cannot be downgraded by past evidence.
        if explicit:
            return RuleHit("explicit", list(dict.fromkeys(e for e, _ in explicit)), "active",
                           " | ".join(m for _, m in explicit))
        hits = routed + ambiguous
        if hits:
            return RuleHit("ambiguous", list(dict.fromkeys(e for e, _ in hits)), "passive",
                           " | ".join(dict.fromkeys(m for _, m in hits)),
                           "；".join(dict.fromkeys(hints)), tuple(dict.fromkeys(past_ids)))
        return RuleHit("none", [], "none")


def match(text: str) -> RuleHit:
    """Convenience entry point; reuse Rules in a long-running session."""
    return Rules().match(text)
