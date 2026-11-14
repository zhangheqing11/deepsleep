"""Veto-only human review (C5), file/CLI interface; the web UI can write the same files.

Request:  <run_dir>/<evolution_id>/review_request.json  — high-criticality changes awaiting review.
Response: <run_dir>/<evolution_id>/review_response.json — ``{"decisions": [{change_id, decision,
          scores, comment}]}`` with decision ``reject`` or ``approve``.

Rules: only high changes are reviewable; a change blocked by a hard rule stays blocked
whatever the decision; a missing decision becomes ``timeout`` when the window closes.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import time

from .config import resolve


def review_dir(config: dict, evolution_id: str) -> Path:
    return resolve(config["review"]["run_dir"]) / evolution_id


def write_request(config: dict, evolution_id: str, items: list[dict], deadline: float) -> Path:
    path = review_dir(config, evolution_id)
    path.mkdir(parents=True, exist_ok=True)
    request = {"evolution_id": evolution_id, "deadline_epoch": deadline,
               "timeout_policy": config["review"]["timeout_policy"], "changes": items}
    target = path / "review_request.json"
    target.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _read_decisions(config: dict, evolution_id: str, allowed: set[str]) -> dict[str, dict]:
    target = review_dir(config, evolution_id) / "review_response.json"
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}  # half-written file: try again on the next poll
    out = {}
    for item in data.get("decisions", []):
        change_id = item.get("change_id")
        if change_id in allowed and item.get("decision") in ("approve", "reject"):
            out[change_id] = {
                "change_id": change_id,
                "decision": item["decision"],
                "scores": _scores(item.get("scores")),
                "comment": item.get("comment"),
            }
    return out


def _scores(scores):
    if not isinstance(scores, dict):
        return None
    try:
        values = {k: float(scores[k]) for k in ("safety", "clinical", "feasibility")}
    except (KeyError, TypeError, ValueError):
        return None
    if not all(1 <= v <= 5 for v in values.values()):
        return None
    return {k: (int(v) if v.is_integer() else v) for k, v in values.items()}


def submit(config: dict, evolution_id: str, change_id: str, decision: str,
           scores: dict | None = None, comment: str | None = None) -> Path:
    """CLI helper: append/overwrite one decision in review_response.json."""
    if decision not in ("approve", "reject"):
        raise ValueError("decision 只能是 approve 或 reject")
    path = review_dir(config, evolution_id)
    path.mkdir(parents=True, exist_ok=True)
    target = path / "review_response.json"
    data = {"decisions": []}
    if target.exists():
        data = json.loads(target.read_text(encoding="utf-8"))
    data["decisions"] = [d for d in data["decisions"] if d.get("change_id") != change_id]
    data["decisions"].append({"change_id": change_id, "decision": decision, "scores": scores, "comment": comment})
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)
    return target


async def collect(config: dict, evolution_id: str, items: list[dict], timeout_s: float | None = None) -> list[dict]:
    """Wait until every item has a decision or the window closes; missing ones become timeout."""
    if not items:
        return []
    timeout_s = config["review"]["timeout_s"] if timeout_s is None else timeout_s
    deadline = time.time() + timeout_s
    write_request(config, evolution_id, items, deadline)
    allowed = {item["change_id"] for item in items}
    decisions = _read_decisions(config, evolution_id, allowed)
    while len(decisions) < len(allowed) and time.time() < deadline:
        await asyncio.sleep(min(config["review"]["poll_interval_s"], max(0.0, deadline - time.time())))
        decisions = _read_decisions(config, evolution_id, allowed)
    return [decisions.get(item["change_id"]) or
            {"change_id": item["change_id"], "decision": "timeout", "scores": None, "comment": None}
            for item in items]


def blocks(decision: str, config: dict) -> bool:
    """Whether a review decision blocks its candidate. approve never unblocks anything."""
    if decision == "reject":
        return True
    if decision == "timeout":
        return config["review"]["timeout_policy"] == "veto"
    return False
