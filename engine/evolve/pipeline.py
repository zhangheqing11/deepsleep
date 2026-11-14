"""One learning step between runs → contract ``evolution`` JSON.

reflect → apply check → hard rules → (validation on C ∥ veto-only human review) → choose
→ commit to var/playbook-repo. The only artefact that changes is the playbook repo.

Evaluator interface (implemented later by S2/S3; mocked in tests)::

    async def evaluator(playbook_text: str, *, label: str) -> dict

returns either ``run_report.metrics`` on split C, or a rich result
``{"metrics": ..., "per_visitor": [...], "sessions": {id: session}, "traces": {id: trace},
"visitors": {id: visitor}}`` from which ring-3 evidence (per-turn true-path weight / entropy,
key-clue turn) is computed for the baseline and each candidate.

Besides the contract JSON, ``insights.json`` holds what the contract has no field for yet:
sub-agent and dimension per change, per-dimension scorecards, and classifier evidence.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
import json
from typing import Awaitable, Callable, Iterable

from . import dimensions as dims
from . import evidence as ev
from . import gate, review
from .config import load_config
from .hard_rules import check_candidate, veto_from_violations
from .llm import LLMClient, default_clients
from .playbook import ApplyError, Playbook, unified_diff
from .reflector import reflect
from .repo import PlaybookRepo
from .status import StatusTracker

Evaluator = Callable[..., Awaitable[dict]]
SCHEMA_VERSION = "0.1.0"
NO_APPLICABLE_SUMMARY = "候选改动无法对应到当前 playbook 原文（占位，不参与验证）。"


def _now() -> datetime:
    return datetime.now().astimezone()


def _applicable(candidate: dict, base_text: str, dropped: list[str]) -> str:
    """Drop changes that cannot be applied; return the candidate's playbook text."""
    playbook = Playbook.parse(base_text)
    kept = []
    for change in candidate["changes"]:
        try:
            playbook.apply(change)
            kept.append(change)
        except ApplyError as exc:
            dropped.append(f"{change['id']}: {exc}，已丢弃")
    if candidate["changes"] and not kept:
        candidate["summary"] = NO_APPLICABLE_SUMMARY
    candidate["changes"] = kept
    return playbook.render()


def _unpack(result) -> tuple[dict | None, dict | None]:
    """(metrics, rich-or-None) from either evaluator return shape."""
    if result is None:
        return None, None
    if isinstance(result.get("metrics"), dict):
        return result["metrics"], result
    return result, None


async def _safe_eval(evaluator: Evaluator, text: str, label: str, errors: list[str]):
    try:
        return await evaluator(text, label=label)
    except Exception as exc:  # noqa: BLE001 - a failed validation run just fails that candidate
        errors.append(f"{label} 验证失败: {type(exc).__name__}: {exc}")
        return None


def _val_insight(metrics: dict | None, rich: dict | None, config: dict) -> dict | None:
    if metrics is None:
        return None
    out = {"scorecard": None, "evidence": None}
    if rich and rich.get("per_visitor"):
        report = {"metrics": metrics, "per_visitor": rich["per_visitor"]}
        out["scorecard"] = dims.scorecard(report, rich.get("visitors"), config)
        out["evidence"] = ev.run_evidence(rich["per_visitor"], rich.get("sessions") or {},
                                          rich.get("traces") or {}, rich.get("visitors") or {})["summary"]
    return out


def _deltas(card: dict | None, base: dict | None) -> dict | None:
    """Numeric differences candidate − baseline per dimension (None where not comparable)."""
    if not card or not base:
        return None
    out = {}
    for d in dims.DIMENSIONS:
        out[d] = {k: (round(v - base[d][k], 4) if isinstance(v, (int, float)) and isinstance(base[d].get(k), (int, float))
                      and not isinstance(v, bool) else None)
                  for k, v in card[d].items() if not isinstance(v, dict)}
    return out


async def evolve(*, run_report: dict, sessions: dict, evaluator: Evaluator,
                 human_feedback: Iterable[dict] = (), baseline_val_metrics: dict | None = None,
                 config: dict | None = None, repo: PlaybookRepo | None = None,
                 primary: LLMClient | None = None, fallback: LLMClient | None = None,
                 use_default_clients: bool = True, review_timeout_s: float | None = None,
                 evolution_id: str | None = None, write: bool = True,
                 traces: dict | None = None, visitors: dict | None = None,
                 return_insights: bool = False):
    """Run one learning step; returns the evolution dict, or (evolution, insights) if asked.

    With ``write=True`` it also keeps ``<run_dir>/<evolution_id>/status.json`` up to date
    (see ``status.py``) so the dashboard can show reflecting / validating / review / done live.
    """
    config = config or load_config()
    repo = repo or PlaybookRepo(config)
    repo.init()
    created = _now()
    evolution_id = evolution_id or f"evolution-{created:%Y%m%d-%H%M%S}"
    tracker = StatusTracker(review.review_dir(config, evolution_id) if write else None,
                            evolution_id, repo.current_version())
    try:
        return await _evolve(tracker, run_report=run_report, sessions=sessions, evaluator=evaluator,
                             human_feedback=human_feedback, baseline_val_metrics=baseline_val_metrics,
                             config=config, repo=repo, primary=primary, fallback=fallback,
                             use_default_clients=use_default_clients, review_timeout_s=review_timeout_s,
                             evolution_id=evolution_id, created=created, write=write, traces=traces,
                             visitors=visitors, return_insights=return_insights)
    except BaseException as exc:  # noqa: BLE001 - record the failure for the dashboard, then re-raise
        tracker.fail(exc)
        raise


async def _evolve(tracker: StatusTracker, *, run_report: dict, sessions: dict, evaluator: Evaluator,
                  human_feedback: Iterable[dict], baseline_val_metrics: dict | None, config: dict,
                  repo: PlaybookRepo, primary: LLMClient | None, fallback: LLMClient | None,
                  use_default_clients: bool, review_timeout_s: float | None, evolution_id: str,
                  created: datetime, write: bool, traces: dict | None, visitors: dict | None,
                  return_insights: bool):
    feedback = list(human_feedback)  # C1: approved auto_critic entries arrive here too
    from_version, base_text = repo.current_version(), repo.read()

    primary_error = None
    if use_default_clients and primary is None and fallback is None:
        primary, fallback, primary_error = default_clients(config)
    reflection = await reflect(playbook_text=base_text, version=from_version, run_report=run_report,
                               sessions=sessions, feedback=feedback, config=config, primary=primary,
                               fallback=fallback, primary_error=primary_error, traces=traces, visitors=visitors)
    tracker.reflector(state="done", model=reflection.model, fell_back=reflection.fell_back)

    log: list[str] = list(reflection.dropped_changes)
    texts, violations = {}, {}
    for cand in reflection.candidates:
        texts[cand["id"]] = _applicable(cand, base_text, log)
        violations[cand["id"]] = check_candidate(cand["changes"], base_text, config) if cand["changes"] else []
    to_validate = [c for c in reflection.candidates if c["changes"] and not violations[c["id"]]]
    review_items = [{"candidate_id": c["id"], "change_id": ch["id"], "section": ch["section"], "op": ch["op"],
                     "before": ch["before"], "after": ch["after"], "reason": ch["reason"]}
                    for c in to_validate for ch in c["changes"] if ch["criticality"] == "high"]

    validating_ids = {c["id"] for c in to_validate}
    for cand in reflection.candidates:
        tracker.state["validation"]["candidates"][cand["id"]] = (
            "pending" if cand["id"] in validating_ids else ("blocked" if violations[cand["id"]] else "empty"))
    tracker.state["validation"]["baseline"] = "skipped" if baseline_val_metrics is not None else "pending"
    tracker.review(pending_changes=len(review_items))  # also flushes the states above
    tracker.set(phase="validating")

    async def _baseline():
        tracker.baseline("running")
        try:
            result = await evaluator(base_text, label=from_version)
        except BaseException:
            tracker.baseline("error")
            raise
        tracker.baseline("done")
        return result

    async def _candidate(cand: dict):
        tracker.candidate(cand["id"], "running")
        result = await _safe_eval(evaluator, texts[cand["id"]], f"{from_version}+{cand['id']}", eval_errors)
        tracker.candidate(cand["id"], "done" if result is not None else "error")
        return result

    async def _review():
        reviews = await review.collect(config, evolution_id, review_items, review_timeout_s,
                                       on_open=tracker.review_open)
        if review_items:
            tracker.review(state="done")
        return reviews

    eval_errors: list[str] = []
    baseline_task = _baseline() if baseline_val_metrics is None else asyncio.sleep(0, result=baseline_val_metrics)
    results = await asyncio.gather(
        baseline_task,
        asyncio.gather(*(_candidate(c) for c in to_validate)),
        _review(),
    )
    tracker.set(phase="committing")
    baseline_raw, val_results, reviews = results
    baseline, baseline_rich = _unpack(baseline_raw)
    unpacked = {c["id"]: _unpack(r) for c, r in zip(to_validate, val_results)}
    val_by_id = {cid: m for cid, (m, _) in unpacked.items()}
    blocked_changes = {r["change_id"] for r in reviews if review.blocks(r["decision"], config)}

    # Internal ring-3 fields stay out of the contract JSON (no schema field yet).
    change_meta = {}
    for cand in reflection.candidates:
        for ch in cand["changes"]:
            change_meta[ch["id"]] = {"section": ch["section"], "subagent": dims.SUBAGENT_BY_SECTION[ch["section"]],
                                     "dimension": ch.pop("dimension", dims.DEFAULT_DIMENSION_BY_SECTION[ch["section"]])}

    candidates = []
    for cand in reflection.candidates:
        hard = violations[cand["id"]]
        metrics = val_by_id.get(cand["id"])
        if hard:
            veto = veto_from_violations(hard, config)
        elif metrics is not None:
            veto = gate.val_veto(metrics, baseline, config)
        else:
            veto = {"passed": True, "reasons": []}
        passed = (not hard and metrics is not None and veto["passed"]
                  and gate.improves_primary(metrics, baseline, config)
                  and not any(ch["id"] in blocked_changes for ch in cand["changes"]))
        candidates.append({**cand, "hard_rule_violations": hard, "val_metrics": metrics,
                           "veto": veto, "passed": passed})

    chosen = gate.choose(candidates)
    to_version = commit = diff = None
    if chosen:
        cand = next(c for c in candidates if c["id"] == chosen)
        new_text = texts[chosen]
        diff = unified_diff(base_text, new_text, config["repo"]["file_name"])
        to_version, sha = repo.commit_version(new_text, cand["summary"])
        commit = {"repo": "var/playbook-repo", "sha": sha, "author": config["repo"]["agent_name"],
                  "message": f"{to_version}: {cand['summary']}"}

    tracker.set(outcome="committed" if chosen else "kept_previous", chosen=chosen, to_version=to_version)
    evolution = {
        "schema_version": SCHEMA_VERSION,
        "evolution_id": evolution_id,
        "created_at": created.isoformat(timespec="seconds"),
        "from_version": from_version,
        "to_version": to_version,
        "outcome": "committed" if chosen else "kept_previous",
        "source_run_id": run_report["run_id"],
        "val_split": "C",
        "baseline_val_metrics": baseline,
        "reflector": {"model": reflection.model, "fell_back": reflection.fell_back,
                      "fallback_reason": reflection.fallback_reason},
        "failures_used": reflection.failures_used,
        "human_feedback": feedback,
        "candidates": candidates,
        "human_review": reviews,
        "chosen": chosen,
        "commit": commit,
        "diff": diff,
    }
    baseline_insight = _val_insight(baseline, baseline_rich or {}, config) if baseline_rich else None
    cand_insight = {cid: _val_insight(m, rich, config) for cid, (m, rich) in unpacked.items()}
    insights = {
        "evolution_id": evolution_id,
        "note": "环 3 跨来访进化的补充报告；契约 v0.1.1 前不进 evolution JSON。",
        "changes": change_meta,
        "failure_dimensions": reflection.failure_dimensions,
        "source_run": {"run_id": run_report["run_id"], "scorecard": reflection.scorecard,
                       "evidence": reflection.evidence["summary"]},
        "validation": {
            "baseline": baseline_insight,
            "candidates": {cid: {**(ins or {}), "scorecard_delta": _deltas((ins or {}).get("scorecard"),
                                                                          (baseline_insight or {}).get("scorecard"))}
                           for cid, ins in cand_insight.items() if ins is not None},
        },
    }
    if write:
        out_dir = review.review_dir(config, evolution_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "insights.json").write_text(json.dumps(insights, ensure_ascii=False, indent=2), encoding="utf-8")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "evolution.json").write_text(json.dumps(evolution, ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / "log.json").write_text(json.dumps({"dropped_or_errors": log + eval_errors}, ensure_ascii=False,
                                                     indent=2), encoding="utf-8")
    tracker.set(phase="done")  # after evolution.json is on disk: "done" means the result is readable
    return (evolution, insights) if return_insights else evolution
