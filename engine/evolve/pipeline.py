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
sub-agent and dimension per change, per-dimension scorecards, classifier evidence, paired
per-visitor statistics (``validation.candidates[cid].paired``) and a ``history_item`` summary
that ``lineage.py`` feeds to later generations of the reflector.

Replicates (``gate.replicates`` > 1): baseline and each candidate are evaluated that many times,
sequentially, with labels ``<label>``, ``<label>#r2`` …. When every replicate returns per-visitor
rows, the rows are concatenated and the contract metrics are recomputed on them with
``contracts.validate.compute_metrics`` (the same function scoring uses), so rates are pooled
over visitor × replicate and counts (crisis_missed, contraindication_violations) are summed.
Otherwise rate metrics are averaged (ignoring None) and counts summed.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, is_dataclass
from datetime import datetime
import inspect
import json
from typing import Awaitable, Callable, Iterable

from contracts.validate import compute_metrics

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


COUNT_METRICS = ("crisis_missed", "contraindication_violations")


def replicate_labels(label: str, n: int) -> list[str]:
    return [label] + [f"{label}#r{i}" for i in range(2, n + 1)]


def _replicates(config: dict) -> int:
    return max(1, int(config["gate"].get("replicates", 1) or 1))


def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def average_metrics(items: list[dict]) -> dict:
    """Fallback pooling without per-visitor rows: average rates (ignoring None), sum counts."""
    out = {}
    for key, value in items[0].items():
        if key in COUNT_METRICS:
            out[key] = sum(m[key] for m in items)
        elif isinstance(value, dict):
            out[key] = {k: _mean([m[key][k] for m in items]) for k in value}
        else:
            out[key] = _mean([m[key] for m in items])
    if out.get("path_acc_r1") is not None and out.get("path_acc_r2") is not None:
        out["path_acc_gain"] = out["path_acc_r2"] - out["path_acc_r1"]
    return out


def pool(results: list[dict]) -> dict:
    """Pool replicate evaluator results (see module docstring). One result is returned unchanged."""
    if len(results) == 1:
        return results[0]
    unpacked = [_unpack(r) for r in results]
    riches = [rich for _, rich in unpacked]
    if all(rich and rich.get("per_visitor") for rich in riches):
        rows = [row for rich in riches for row in rich["per_visitor"]]
        return {**riches[0], "metrics": compute_metrics(rows), "per_visitor": rows,
                "replicates": riches, "pooling": "rows"}
    return average_metrics([m for m, _ in unpacked])


def _rows(rich: dict | None) -> list[dict] | None:
    return rich.get("per_visitor") if rich else None


def _val_insight(metrics: dict | None, rich: dict | None, config: dict) -> dict | None:
    if metrics is None:
        return None
    out = {"scorecard": None, "evidence": None}
    if rich and rich.get("per_visitor"):
        # Scorecard / evidence describe one replicate's sessions (pooled rows would double count);
        # the metric fields come from the pooled metrics.
        first = (rich.get("replicates") or [rich])[0]
        report = {"metrics": metrics, "per_visitor": first["per_visitor"]}
        out["scorecard"] = dims.scorecard(report, first.get("visitors"), config)
        out["evidence"] = ev.run_evidence(first["per_visitor"], first.get("sessions") or {},
                                          first.get("traces") or {}, first.get("visitors") or {})["summary"]
    return out


def _jsonable(value):
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except (TypeError, ValueError):
        return str(value)


def _reflect_kwargs(history: list[dict] | None) -> dict:
    """Pass ``history`` only if this reflector version accepts it."""
    try:
        params = inspect.signature(reflect).parameters
    except (TypeError, ValueError):
        return {}
    accepts = "history" in params or any(p.kind is p.VAR_KEYWORD for p in params.values())
    return {"history": history} if accepts else {}


def _metric_delta(m: dict, base: dict, key: str):
    if m.get(key) is None or base.get(key) is None:
        return None
    return round(m[key] - base[key], 4)


def candidate_delta(metrics: dict | None, baseline: dict | None, paired_stats: dict | None,
                    n_visitors: int | None) -> dict | None:
    """Candidate − baseline on C for the reflector history (None when not validated)."""
    if metrics is None or baseline is None:
        return None
    resp = (paired_stats or {}).get("responder")
    n = resp["n"] if resp else (n_visitors or 0)
    return {
        "n": n,
        "isi_responders": round((metrics["isi_response_rate"] - baseline["isi_response_rate"]) * n) if n else 0,
        "gained": len(resp["gained"]) if resp else 0,
        "lost": len(resp["lost"]) if resp else 0,
        **{k: _metric_delta(metrics, baseline, k)
           for k in ("referral_recall", "referral_precision", "path_acc_r2", "screening_coverage")},
    }


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
                 return_insights: bool = False, baseline_val_result: dict | None = None,
                 history: list[dict] | None = None, val_results_out: dict | None = None):
    """Run one learning step; returns the evolution dict, or (evolution, insights) if asked.

    With ``write=True`` it also keeps ``<run_dir>/<evolution_id>/status.json`` up to date
    (see ``status.py``) so the dashboard can show reflecting / validating / review / done live.

    ``baseline_val_result``: an already-computed evaluator result for the current playbook on C
    (metrics-only or rich); takes precedence over ``baseline_val_metrics`` and, when rich, keeps
    paired statistics available (lineage reuses the adopted candidate's evaluation this way).
    ``history``: summaries of earlier generations, forwarded to the reflector when it accepts them.
    ``val_results_out``: if a dict is given it is filled with the (pooled) evaluator results,
    ``{"baseline": ..., "candidates": {cid: ...}}``.
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
                             visitors=visitors, return_insights=return_insights,
                             baseline_val_result=baseline_val_result, history=history,
                             val_results_out=val_results_out)
    except BaseException as exc:  # noqa: BLE001 - record the failure for the dashboard, then re-raise
        tracker.fail(exc)
        raise


async def _evolve(tracker: StatusTracker, *, run_report: dict, sessions: dict, evaluator: Evaluator,
                  human_feedback: Iterable[dict], baseline_val_metrics: dict | None, config: dict,
                  repo: PlaybookRepo, primary: LLMClient | None, fallback: LLMClient | None,
                  use_default_clients: bool, review_timeout_s: float | None, evolution_id: str,
                  created: datetime, write: bool, traces: dict | None, visitors: dict | None,
                  return_insights: bool, baseline_val_result: dict | None, history: list[dict] | None,
                  val_results_out: dict | None):
    feedback = list(human_feedback)  # C1: approved auto_critic entries arrive here too
    from_version, base_text = repo.current_version(), repo.read()
    n_rep = _replicates(config)
    # The baseline may be measured more often than each candidate (it is shared by all three and can
    # run while the reflector thinks); never fewer times.
    base_rep = max(n_rep, int(config["gate"].get("baseline_replicates", 0) or 0))
    if baseline_val_result is not None:
        baseline_source, baseline_given = "reused", baseline_val_result
    elif baseline_val_metrics is not None:
        baseline_source, baseline_given = "metrics", baseline_val_metrics
    else:
        baseline_source, baseline_given = "evaluated", None

    primary_error = None
    if use_default_clients and primary is None and fallback is None:
        primary, fallback, primary_error = default_clients(config)

    # The baseline on C does not depend on the reflector's output: optionally run it while the
    # reflector thinks (gate.baseline_during_reflection), instead of after it.
    early_baseline = None
    if baseline_given is None and config["gate"].get("baseline_during_reflection", False):
        async def _early():
            labels = replicate_labels(from_version, base_rep)
            if config["gate"].get("parallel_candidates", False):  # replicates may overlap too
                return pool(list(await asyncio.gather(*(evaluator(base_text, label=label) for label in labels))))
            return pool([await evaluator(base_text, label=label) for label in labels])
        tracker.state["validation"]["baseline"] = "running"
        early_baseline = asyncio.create_task(_early())
    try:
        reflection = await reflect(playbook_text=base_text, version=from_version, run_report=run_report,
                                   sessions=sessions, feedback=feedback, config=config, primary=primary,
                                   fallback=fallback, primary_error=primary_error, traces=traces, visitors=visitors,
                                   **_reflect_kwargs(history))
    except BaseException:
        if early_baseline is not None:
            early_baseline.cancel()
            await asyncio.gather(early_baseline, return_exceptions=True)
        raise
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
    tracker.state["validation"]["baseline"] = "skipped" if baseline_given is not None else "pending"
    tracker.review(pending_changes=len(review_items))  # also flushes the states above
    tracker.set(phase="validating")

    async def _baseline():
        tracker.baseline("running")
        if early_baseline is not None:  # started while the reflector was thinking
            try:
                result = await early_baseline
            except BaseException:
                tracker.baseline("error")
                raise
            tracker.baseline("done")
            return result
        results = []
        try:
            for label in replicate_labels(from_version, base_rep):  # sequential, like today
                results.append(await evaluator(base_text, label=label))
        except BaseException:
            tracker.baseline("error")
            raise
        tracker.baseline("done")
        return pool(results)

    async def _candidate(cand: dict):
        tracker.candidate(cand["id"], "running")
        results = []
        for label in replicate_labels(f"{from_version}+{cand['id']}", n_rep):
            result = await _safe_eval(evaluator, texts[cand["id"]], label, eval_errors)
            if result is None:
                break
            results.append(result)
        ok = len(results) == n_rep
        tracker.candidate(cand["id"], "done" if ok else "error")
        return pool(results) if ok else None

    async def _review():
        reviews = await review.collect(config, evolution_id, review_items, review_timeout_s,
                                       on_open=tracker.review_open)
        if review_items:
            tracker.review(state="done")
        return reviews

    eval_errors: list[str] = []
    async def _validation():
        # Always finish the baseline before candidates; one version owns the
        # engine's session concurrency at a time. Review remains concurrent.
        baseline_raw = await _baseline() if baseline_given is None else baseline_given
        if config["gate"].get("parallel_candidates", False):
            # Opt-in: candidates share the provider concurrently (shorter learning step, more in-flight).
            values = list(await asyncio.gather(*(_candidate(candidate) for candidate in to_validate)))
        else:
            values = []
            for candidate in to_validate:
                values.append(await _candidate(candidate))
        return baseline_raw, values

    validation_task = asyncio.create_task(_validation())
    review_task = asyncio.create_task(_review())
    try:
        (baseline_raw, val_results), reviews = await asyncio.gather(validation_task, review_task)
    finally:
        for task in (validation_task, review_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(validation_task, review_task, return_exceptions=True)
    tracker.set(phase="committing")
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

    base_rows = _rows(baseline_rich)
    n_visitors = gate.n_visitors(base_rows)
    positives = gate.referral_positive_counts(base_rows)
    paired_by_id = {cid: gate.paired(base_rows, _rows(rich)) for cid, (_, rich) in unpacked.items()}

    candidates, reasons_by_id = [], {}
    for cand in reflection.candidates:
        hard = violations[cand["id"]]
        metrics = val_by_id.get(cand["id"])
        reasons: list[str] = []
        if hard:
            veto = veto_from_violations(hard, config)
        elif metrics is not None:
            veto = gate.val_veto(metrics, baseline, config, referral_positives=positives)
        else:
            veto = {"passed": True, "reasons": []}
        improves = metrics is not None and gate.improves_primary(metrics, baseline, config, n_visitors=n_visitors)
        reviewed_out = any(ch["id"] in blocked_changes for ch in cand["changes"])
        passed = not hard and metrics is not None and veto["passed"] and improves and not reviewed_out
        if not cand["changes"]:
            reasons.append("没有可用改动，未参与验证")
        elif hard:
            reasons += [v["message"] for v in hard]
        elif metrics is None:
            reasons.append("验证集评估失败")
        else:
            reasons += [r["message"] for r in veto["reasons"]]
            if not improves:
                reasons.append("主指标未严格提高" if not metrics[config["gate"]["primary_metric"]]
                               > baseline[config["gate"]["primary_metric"]]
                               else f"主指标提高不足 {gate.min_gain_visitors(config)} 名来访")
            if reviewed_out:
                reasons.append("高风险改动被人工否决（或审核超时按否决处理）")
        reasons_by_id[cand["id"]] = list(dict.fromkeys(reasons))
        candidates.append({**cand, "hard_rule_violations": hard, "val_metrics": metrics,
                           "veto": veto, "passed": passed})

    chosen = gate.choose(candidates)
    for cand in candidates:
        if cand["passed"] and cand["id"] != chosen:
            reasons_by_id[cand["id"]].append("通过但未被选中")
    if val_results_out is not None:
        val_results_out["baseline"] = baseline_raw
        val_results_out["candidates"] = dict(zip((c["id"] for c in to_validate), val_results))
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
    source_run = {"run_id": run_report["run_id"], "scorecard": reflection.scorecard,
                  "evidence": reflection.evidence["summary"]}
    if hasattr(reflection, "audit"):
        source_run["audit"] = _jsonable(reflection.audit)

    def _outcome(cand: dict) -> str:
        if cand["id"] == chosen:
            return "adopted"
        if not cand["changes"]:
            return "empty"
        return "blocked" if cand["hard_rule_violations"] else "rejected"

    history_item = {
        "generation": None,  # set by lineage.py
        "from_version": from_version,
        "to_version": to_version,
        "candidates": [{
            "id": c["id"], "summary": c["summary"], "outcome": _outcome(c), "reasons": reasons_by_id[c["id"]],
            "delta": candidate_delta(c["val_metrics"], baseline, paired_by_id.get(c["id"]), n_visitors),
            "changes": [{k: ch[k] for k in ("op", "section", "before", "after")} for ch in c["changes"]],
        } for c in candidates],
    }
    insights = {
        "evolution_id": evolution_id,
        "reflector": {**evolution["reflector"], "provider": reflection.provider,
                      "reasoning_effort": reflection.reasoning_effort, "attempts": reflection.attempts},
        "note": "环 3 跨来访进化的补充报告；契约 v0.1.1 前不进 evolution JSON。",
        "changes": change_meta,
        "failure_dimensions": reflection.failure_dimensions,
        "source_run": source_run,
        "validation": {
            "baseline": baseline_insight,
            "baseline_source": baseline_source,
            "replicates": n_rep,
            "gate_context": {
                "n_visitors": n_visitors,
                "referral_positives": positives,
                "referral_recall_tolerance_rate": gate.referral_tolerance(config, (positives or {}).get("all")),
                "min_primary_gain_visitors": gate.min_gain_visitors(config),
            },
            "candidates": {cid: {**(ins or {}), "scorecard_delta": _deltas((ins or {}).get("scorecard"),
                                                                          (baseline_insight or {}).get("scorecard")),
                                 "paired": paired_by_id.get(cid)}
                           for cid, ins in cand_insight.items() if ins is not None},
        },
        "history_item": history_item,
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
