"""One learning step between runs → contract ``evolution`` JSON.

reflect → apply check → hard rules → (validation on C ∥ veto-only human review) → choose
→ commit to var/playbook-repo. The only artefact that changes is the playbook repo.

Evaluator interface (implemented later by S2/S3; mocked in tests)::

    async def evaluator(playbook_text: str, *, label: str) -> dict  # run_report.metrics on split C
"""
from __future__ import annotations

import asyncio
from datetime import datetime
import json
from typing import Awaitable, Callable, Iterable

from . import gate, review
from .config import load_config
from .hard_rules import check_candidate, veto_from_violations
from .llm import LLMClient, default_clients
from .playbook import ApplyError, Playbook, unified_diff
from .reflector import reflect
from .repo import PlaybookRepo

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


async def _safe_eval(evaluator: Evaluator, text: str, label: str, errors: list[str]) -> dict | None:
    try:
        return await evaluator(text, label=label)
    except Exception as exc:  # noqa: BLE001 - a failed validation run just fails that candidate
        errors.append(f"{label} 验证失败: {type(exc).__name__}: {exc}")
        return None


async def evolve(*, run_report: dict, sessions: dict, evaluator: Evaluator,
                 human_feedback: Iterable[dict] = (), baseline_val_metrics: dict | None = None,
                 config: dict | None = None, repo: PlaybookRepo | None = None,
                 primary: LLMClient | None = None, fallback: LLMClient | None = None,
                 use_default_clients: bool = True, review_timeout_s: float | None = None,
                 evolution_id: str | None = None, write: bool = True) -> dict:
    config = config or load_config()
    repo = repo or PlaybookRepo(config)
    repo.init()
    created = _now()
    evolution_id = evolution_id or f"evolution-{created:%Y%m%d-%H%M%S}"
    feedback = list(human_feedback)  # C1: approved auto_critic entries arrive here too
    from_version, base_text = repo.current_version(), repo.read()

    primary_error = None
    if use_default_clients and primary is None and fallback is None:
        primary, fallback, primary_error = default_clients(config)
    reflection = await reflect(playbook_text=base_text, version=from_version, run_report=run_report,
                               sessions=sessions, feedback=feedback, config=config, primary=primary,
                               fallback=fallback, primary_error=primary_error)

    log: list[str] = list(reflection.dropped_changes)
    texts, violations = {}, {}
    for cand in reflection.candidates:
        texts[cand["id"]] = _applicable(cand, base_text, log)
        violations[cand["id"]] = check_candidate(cand["changes"], base_text, config) if cand["changes"] else []
    to_validate = [c for c in reflection.candidates if c["changes"] and not violations[c["id"]]]
    review_items = [{"candidate_id": c["id"], "change_id": ch["id"], "section": ch["section"], "op": ch["op"],
                     "before": ch["before"], "after": ch["after"], "reason": ch["reason"]}
                    for c in to_validate for ch in c["changes"] if ch["criticality"] == "high"]

    eval_errors: list[str] = []
    baseline_task = (evaluator(base_text, label=from_version) if baseline_val_metrics is None
                     else asyncio.sleep(0, result=baseline_val_metrics))
    results = await asyncio.gather(
        baseline_task,
        asyncio.gather(*(_safe_eval(evaluator, texts[c["id"]], f"{from_version}+{c['id']}", eval_errors)
                         for c in to_validate)),
        review.collect(config, evolution_id, review_items, review_timeout_s),
    )
    baseline, val_results, reviews = results
    val_by_id = {c["id"]: m for c, m in zip(to_validate, val_results)}
    blocked_changes = {r["change_id"] for r in reviews if review.blocks(r["decision"], config)}

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
    if write:
        out_dir = review.review_dir(config, evolution_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "evolution.json").write_text(json.dumps(evolution, ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / "log.json").write_text(json.dumps({"dropped_or_errors": log + eval_errors}, ensure_ascii=False,
                                                     indent=2), encoding="utf-8")
    return evolution
