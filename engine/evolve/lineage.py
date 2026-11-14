"""Multi-generation learning: chain ``pipeline.evolve`` generations on one source run.

Generation g reflects on the same source run (cohort A under the original playbook) but on top
of the current playbook text, with ``history`` = summaries of all earlier generations (what was
adopted / rejected and why, with paired deltas on C). From generation 2 on the previous
generation's adopted candidate evaluation is reused as the baseline instead of re-running it.
The chain stops early when a generation adopts nothing (which includes "no valid candidate").

Each generation writes its own contract ``evolution.json`` / ``insights.json`` / ``status.json``
under ``<run_dir>/<evolution_id>/``; ``<run_dir>/<prefix>/lineage.json`` summarises the chain.
With ``max_generations == 1`` the single generation keeps the id ``prefix`` exactly, so file
layout and callers are unchanged from the single-step pipeline.
"""
from __future__ import annotations

from datetime import datetime
import json
from typing import Iterable

from . import review
from .pipeline import Evaluator, evolve
from .repo import PlaybookRepo


def generation_id(prefix: str, generation: int, max_generations: int) -> str:
    return prefix if max_generations == 1 else f"{prefix}-g{generation}"


def _summary(generation: int, evolution: dict, insights: dict, primary_metric: str) -> dict:
    validation = insights.get("validation") or {}
    cands = {c["id"]: c for c in evolution["candidates"]}
    base = evolution["baseline_val_metrics"] or {}
    return {
        "generation": generation,
        "evolution_id": evolution["evolution_id"],
        "from_version": evolution["from_version"],
        "to_version": evolution["to_version"],
        "outcome": evolution["outcome"],
        "chosen": evolution["chosen"],
        "baseline_source": validation.get("baseline_source"),
        "primary_metric": {
            "name": primary_metric,
            "baseline": base.get(primary_metric),
            "candidates": {cid: (c["val_metrics"] or {}).get(primary_metric) for cid, c in cands.items()},
            "chosen": (cands[evolution["chosen"]]["val_metrics"] or {}).get(primary_metric)
            if evolution["chosen"] else None,
        },
        "paired": {cid: v.get("paired") for cid, v in (validation.get("candidates") or {}).items()},
        "candidates": [{"id": c["id"], "outcome": c["outcome"], "reasons": c["reasons"]}
                       for c in insights["history_item"]["candidates"]],
    }


async def evolve_lineage(*, run_report: dict, sessions: dict, traces: dict | None, visitors: dict | None,
                         evaluator: Evaluator, config: dict, repo: PlaybookRepo, max_generations: int = 1,
                         evolution_id_prefix: str, primary=None, fallback=None, use_default_clients: bool = True,
                         human_feedback: Iterable[dict] = (), review_timeout_s: float | None = None,
                         evolve_fn=None, source_runner=None, continue_after_reject: bool = False,
                         reuse_baseline: bool = True) -> list[dict]:
    """Run up to ``max_generations`` learning steps; returns the evolution dicts in order.

    ``evolve_fn`` defaults to ``pipeline.evolve`` (injectable so callers / tests can wrap it).
    ``source_runner(playbook_text, version)`` is optional self-practice: after a generation commits
    and another one follows, it re-runs the learning cohort under the new playbook and returns
    ``{"run_report", "sessions", "traces"}``, so the next generation reflects on what the new
    version actually did (not on the stale source run). Without it the source run is reused.
    `continue_after_reject`: a generation that adopts nothing does not end the chain (its baseline
    measurement is carried forward and the history tells the reflector what was rejected).
    euse_baseline=False: every generation measures its baseline afresh instead of reusing the
    previous generation's evaluation of the adopted candidate. That evaluation was the maximum of
    three noisy measurements, so it is biased upward and would raise the bar for the next generation.
    """
    if max_generations < 1:
        raise ValueError("max_generations 必须 ≥ 1")
    evolve_fn = evolve_fn or evolve
    feedback = list(human_feedback)
    primary_metric = config["gate"]["primary_metric"]
    history: list[dict] = []
    evolutions: list[dict] = []
    summaries: list[dict] = []
    carried: dict | None = None
    started = datetime.now().astimezone()
    lineage_dir = review.review_dir(config, evolution_id_prefix)

    def write_lineage(state: str) -> None:
        lineage = {
            "prefix": evolution_id_prefix,
            "created_at": started.isoformat(timespec="seconds"),
            "state": state,
            "max_generations": max_generations,
            "source_run_id": run_report["run_id"],
            "start_version": summaries[0]["from_version"] if summaries else repo.current_version(),
            "final_version": repo.current_version(),
            "generations": summaries,
        }
        lineage_dir.mkdir(parents=True, exist_ok=True)
        (lineage_dir / "lineage.json").write_text(json.dumps(lineage, ensure_ascii=False, indent=2),
                                                  encoding="utf-8")

    for generation in range(1, max_generations + 1):
        results: dict = {}
        out = await evolve_fn(
            run_report=run_report, sessions=sessions, traces=traces, visitors=visitors, evaluator=evaluator,
            config=config, repo=repo, primary=primary, fallback=fallback, use_default_clients=use_default_clients,
            human_feedback=feedback, review_timeout_s=review_timeout_s,
            evolution_id=generation_id(evolution_id_prefix, generation, max_generations),
            history=[dict(h) for h in history] or None,
            baseline_val_result=carried if reuse_baseline else None,
            val_results_out=results, return_insights=True)
        evolution, insights = out if isinstance(out, tuple) else (out, {})
        evolutions.append(evolution)
        item = dict(insights.get("history_item") or {"from_version": evolution["from_version"],
                                                    "to_version": evolution["to_version"], "candidates": []},
                    generation=generation)
        history.append(item)
        if insights.get("history_item"):
            summaries.append(_summary(generation, evolution, insights, primary_metric))
        else:  # an injected evolve_fn without insights still gets a minimal summary
            summaries.append({"generation": generation, "evolution_id": evolution["evolution_id"],
                              "from_version": evolution["from_version"], "to_version": evolution["to_version"],
                              "outcome": evolution["outcome"], "chosen": evolution["chosen"]})
        write_lineage("running" if evolution["chosen"] and generation < max_generations else "done")
        if not evolution["chosen"]:
            # A rejected generation is not proof that nothing more can be learned (the gate is noisy):
            # optionally keep going with the same baseline, as long as the reflector produced candidates.
            if not continue_after_reject or not any(c["changes"] for c in evolution["candidates"]):
                break
            carried = results.get("baseline") or carried
            continue
        carried = (results.get("candidates") or {}).get(evolution["chosen"])
        if source_runner is not None and generation < max_generations:
            try:
                fresh = await source_runner(repo.read(), repo.current_version())
            except Exception as exc:  # noqa: BLE001 - a failed practice run ends the chain, keeping what is committed
                summaries[-1]["practice_error"] = f"{type(exc).__name__}: {exc}"
                write_lineage("done")
                break
            run_report, sessions, traces = fresh["run_report"], fresh["sessions"], fresh.get("traces")
            summaries[-1]["next_source_run_id"] = run_report["run_id"]
            write_lineage("running")
    return evolutions
