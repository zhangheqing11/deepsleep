"""Perception-layer evidence for ring 3: the frozen PathClassifier's per-turn ``path_probs``.

Because the classifier is frozen, a better playbook can only show up as the agent eliciting
key clues earlier, so the weight on the true path rises sooner and entropy falls faster.
This module turns traces into those curves (plus first/second differences of the mean
curve, the basis for later "derivative" analyses).

Trace format is not a contract yet (v0.1.1 will add it). Accepted shapes, first match wins:
  trace["path_probs" | "classifier" | "path_classifier"] = [{round, turn, probs|path_probs|weights: {P1..P5}}]
  session.rounds[].transcript[].path_probs = {P1..P5}
"""
from __future__ import annotations

import math
from statistics import mean

PATHS = ("P1", "P2", "P3", "P4", "P5")
_SERIES_KEYS = ("path_probs", "classifier", "path_classifier")
_PROB_KEYS = ("probs", "path_probs", "weights")


def _normalize(probs) -> dict | None:
    if not isinstance(probs, dict):
        return None
    values = {p: float(probs.get(p) or 0.0) for p in PATHS}
    total = sum(values.values())
    if total <= 0 or any(v < 0 for v in values.values()):
        return None
    return {p: v / total for p, v in values.items()}


def classifier_series(session: dict | None, trace: dict | None) -> list[dict]:
    """[{round, turn, probs}] in conversation order."""
    out = []
    for key in _SERIES_KEYS:
        entries = (trace or {}).get(key)
        if isinstance(entries, list) and entries:
            for e in entries:
                if not isinstance(e, dict):
                    continue
                raw = next((e[k] for k in _PROB_KEYS if isinstance(e.get(k), dict)), e)
                probs = _normalize(raw)
                if probs and "round" in e and "turn" in e:
                    out.append({"round": int(e["round"]), "turn": int(e["turn"]), "probs": probs})
            if out:
                return sorted(out, key=lambda x: (x["round"], x["turn"]))
    for rnd in (session or {}).get("rounds", []):
        for t in rnd.get("transcript", []):
            probs = _normalize(t.get("path_probs"))
            if probs:
                out.append({"round": rnd["round"], "turn": t["turn"], "probs": probs})
    return out


def entropy_bits(probs: dict) -> float:
    return -sum(p * math.log2(p) for p in probs.values() if p > 0)


def _agent_index(session: dict | None):
    """(round, turn) → number of agent turns up to and including that point."""
    marks = []
    for rnd in (session or {}).get("rounds", []):
        for t in rnd.get("transcript", []):
            if t["speaker"] == "agent":
                marks.append((rnd["round"], t["turn"]))

    def index(rnd: int, turn: int) -> int:
        return sum(1 for m in marks if m <= (rnd, turn))
    return index


def visitor_evidence(visitor_id: str, main_path: str, session: dict | None, trace: dict | None,
                     visitor: dict | None) -> dict:
    index = _agent_index(session)
    curve = []
    for point in classifier_series(session, trace):
        probs = point["probs"]
        curve.append({"round": point["round"], "turn": point["turn"], "agent_turn": index(point["round"], point["turn"]),
                      "p_true": round(probs[main_path], 4), "entropy": round(entropy_bits(probs), 4),
                      "correct": max(probs, key=probs.get) == main_path})
    key_ids = {c["id"] for c in (visitor or {}).get("clues", []) if c.get("supports") == main_path}
    key_clue = None
    for rnd in (session or {}).get("rounds", []):
        for t in rnd.get("transcript", []):
            if key_clue is None and key_ids & set(t.get("revealed_clue_ids") or []):
                key_clue = {"round": rnd["round"], "turn": t["turn"], "agent_turn": index(rnd["round"], t["turn"])}
    first_correct = next(({k: p[k] for k in ("round", "turn", "agent_turn")} for p in curve if p["correct"]), None)
    return {"visitor_id": visitor_id, "main_path": main_path, "curve": curve,
            "key_clue": key_clue, "key_clue_known": bool(key_ids), "first_correct": first_correct}


def _avg(values):
    values = [v for v in values if v is not None]
    return round(mean(values), 4) if values else None


def _diff(values: list) -> list:
    return [None if a is None or b is None else round(b - a, 4) for a, b in zip(values, values[1:])]


def aggregate(items: list[dict]) -> dict:
    """Mean curves by (round, k-th classifier step), with first and second differences."""
    steps: dict[tuple[int, int], list[dict]] = {}
    for item in items:
        per_round: dict[int, int] = {}
        for point in item["curve"]:
            k = per_round[point["round"]] = per_round.get(point["round"], 0) + 1
            steps.setdefault((point["round"], k), []).append(point)
    by_step = [{"round": r, "step": k, "n": len(pts), "mean_p_true": _avg(p["p_true"] for p in pts),
                "mean_entropy": _avg(p["entropy"] for p in pts)} for (r, k), pts in sorted(steps.items())]
    p_curve = [s["mean_p_true"] for s in by_step]
    h_curve = [s["mean_entropy"] for s in by_step]
    d1_p = _diff(p_curve)
    known = [i for i in items if i["key_clue_known"]]

    def round_end(rnd):
        ends = [[p for p in i["curve"] if p["round"] == rnd][-1]["p_true"] for i in items
                if any(p["round"] == rnd for p in i["curve"])]
        return _avg(ends)

    return {
        "n_visitors": len(items),
        "n_with_path_probs": sum(1 for i in items if i["curve"]),
        "by_step": by_step,
        "d1_p_true": d1_p, "d2_p_true": _diff(d1_p),
        "d1_entropy": _diff(h_curve),
        "r1_end_p_true": round_end(1), "r2_end_p_true": round_end(2),
        "key_clue_rate": round(sum(1 for i in known if i["key_clue"]) / len(known), 4) if known else None,
        "mean_key_clue_agent_turn": _avg(i["key_clue"]["agent_turn"] for i in known if i["key_clue"]),
        "mean_first_correct_agent_turn": _avg(i["first_correct"]["agent_turn"] for i in items if i["first_correct"]),
    }


def run_evidence(per_visitor: list[dict], sessions: dict, traces: dict, visitors: dict) -> dict:
    items = [visitor_evidence(r["visitor_id"], r["main_path"], sessions.get(r["visitor_id"]),
                              traces.get(r["visitor_id"]), visitors.get(r["visitor_id"])) for r in per_visitor]
    return {"summary": aggregate(items), "visitors": {i["visitor_id"]: i for i in items}}


def describe(item: dict) -> str:
    """One prompt line for the reflector."""
    parts = []
    if item["curve"]:
        p = "→".join(f"{x['p_true']:.2f}" for x in item["curve"])
        h = "→".join(f"{x['entropy']:.1f}" for x in item["curve"])
        parts.append(f"正确路径权重 {p}；熵 {h} bits")
    else:
        parts.append("无分类器权重记录")
    if item["key_clue_known"]:
        parts.append(f"关键线索第 {item['key_clue']['agent_turn']} 个 agent 回合出现" if item["key_clue"] else "关键线索始终未问出")
    if item["curve"]:
        parts.append(f"第 {item['first_correct']['agent_turn']} 个 agent 回合起判对" if item["first_correct"] else "分类器始终未判对")
    return "；".join(parts)
