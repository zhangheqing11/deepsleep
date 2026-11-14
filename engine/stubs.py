"""Offline stand-ins for sim/ (S2): index-based screening and a rule-based visitor.

Placeholders for development, tests and `make smoke`; S2's sim/ replaces them
through the same interfaces (engine/interfaces.py). Mock visitor wording is not
user-facing copy.
"""
from .interfaces import VisitorReply
from .topics import tag_topics


class IndexScreening:
    """Screening results straight from hidden indices (BACKLOG D2)."""

    def screen(self, visitor: dict, tool: str) -> dict:
        indices = visitor["indices"]
        if tool == "screen_osa":
            return {"stop_bang": indices["stop_bang"]}
        if tool == "screen_mood":
            return {"phq9": indices["phq9"], "phq9_items": phq9_items(indices["phq9"], visitor["crisis"]["phq9_item9"]),
                    "gad7": indices["gad7"]}
        raise ValueError(f"unknown tool {tool}")


def phq9_items(total: int, item9: int) -> list[int]:
    """Deterministic 9-item split with items[8] == item9 and sum == total."""
    if not 0 <= item9 <= 3 or not item9 <= total <= 24 + item9:
        raise ValueError("phq9 total incompatible with item 9")
    items = [0] * 8
    rest = total - item9
    index = 0
    while rest:
        if items[index] < 3:
            items[index] += 1
            rest -= 1
        index = (index + 1) % 8
    return items + [item9]


class MockVisitorSim:
    """Rule-based visitor: layered clues by topic, deny_first for mid/high defensiveness."""
    model_name = "mock-visitor"

    async def reply(self, visitor: dict, round: int, transcript: list[dict], memory: dict) -> VisitorReply:
        prompt = _since_last_visitor(transcript)
        if not prompt:
            return VisitorReply(visitor["opening_complaint"], [], [])
        agent_text = "".join(e["text"] for e in prompt if e["speaker"] == "agent")
        topics = tag_topics(agent_text)
        if any(e["speaker"] == "safety" for e in prompt) or "self_harm" in topics:
            text, ids = self._safety_answer(visitor, memory)
            return VisitorReply(text, ids, topics)
        revealed = {cid for e in transcript for cid in e.get("revealed_clue_ids", [])}
        denied = memory.setdefault("denied", set())
        defensive = visitor["persona"]["defensiveness"] in ("mid", "high")
        parts, ids = [], []
        for clue in visitor["clues"]:
            if clue["reveal_topic"] not in topics or clue["id"] in revealed or clue["supports"] == "crisis":
                continue
            if clue["deny_first"] and defensive and clue["id"] not in denied:
                denied.add(clue["id"])
                parts.append("没有吧，好像也还好。")
                continue
            parts.append(clue["content"])
            ids.append(clue["id"])
        text = "".join(dict.fromkeys(parts)) or "这方面好像没什么特别的。"
        return VisitorReply(text, ids, topics)

    @staticmethod
    def _safety_answer(visitor: dict, memory: dict) -> tuple[str, list[str]]:
        level = visitor["crisis"]["level"]
        crisis_clues = [c for c in visitor["clues"] if c["supports"] == "crisis"]
        if level == "active":
            return "其实我已经想好怎么结束生命了。", []
        if level == "passive":
            if crisis_clues and not memory.get("crisis_told"):
                memory["crisis_told"] = True
                return crisis_clues[0]["content"], [crisis_clues[0]["id"]]
            return "没有具体想过怎么做，也没有准备什么。", []
        if visitor["crisis"]["history"] and crisis_clues and not memory.get("crisis_told"):
            memory["crisis_told"] = True
            return crisis_clues[0]["content"], [crisis_clues[0]["id"]]
        return "现在没有，我挺安全的。", []


def _since_last_visitor(transcript: list[dict]) -> list[dict]:
    tail = []
    for entry in reversed(transcript):
        if entry["speaker"] == "visitor":
            break
        tail.append(entry)
    return list(reversed(tail))
