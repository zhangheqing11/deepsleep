"""Lab driver for evolution experiments (real API unless --mock). Not on the frozen demo path.

    python -m analysis.evo_lab batch --split A --run-id lab-v1-A --repeat 3 --max-sessions 16

Writes var/lab/<run-id>[-rK]/{sessions,trace,run_report.json,summary.json,http.json,meta.json}.
Every HTTP send is counted per host (no URL, key or body is logged) and bounded by --http-cap.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from contextlib import ExitStack
from dataclasses import replace
import json
import os
from pathlib import Path
import time
from unittest.mock import patch

from engine.adapters_sim import S2OutcomeModel, S2Screening, make_s2_sim
from engine.config import ROOT, load_config, load_dotenv
from engine.playbook import Playbook, parse_sections
from engine.reporting import build_report
from engine.run import build_deps, load_visitors
from engine.session import SessionRunner
from safety.judges import MockJudge
from safety.layer import SafetyLayer
from scoring.score import score_run

LAB = ROOT / "var" / "lab"
MAX_DEGRADED_SHARE = 0.10
SHOW = ("isi_response_rate", "mean_isi_change", "path_acc_r1", "path_acc_r2", "referral_recall",
        "referral_precision", "screening_coverage", "crisis_missed", "contraindication_violations")


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


class HttpLedger:
    """Global in-flight cap + per-host outcome counts for every httpx-based client."""

    def __init__(self, cap: int):
        self.cap = cap
        self.limiter = asyncio.Semaphore(cap)
        self.active = 0
        self.peak = 0
        self.rows: Counter = Counter()
        self.errors: Counter = Counter()
        self.ms: dict[str, list[float]] = {}

    def reset(self) -> None:
        self.peak = 0
        self.rows, self.errors, self.ms = Counter(), Counter(), {}

    def _wrap(self, client_type):
        original = client_type.send
        ledger = self

        async def send(client, request, *args, **kwargs):
            host = request.url.host
            async with ledger.limiter:
                ledger.active += 1
                ledger.peak = max(ledger.peak, ledger.active)
                started = time.perf_counter()
                try:
                    response = await original(client, request, *args, **kwargs)
                    ledger.rows[(host, "ok" if response.status_code < 400 else f"http_{response.status_code}")] += 1
                    return response
                except asyncio.CancelledError:
                    ledger.rows[(host, "cancelled")] += 1
                    raise
                except Exception as exc:  # noqa: BLE001 - count, then re-raise untouched
                    ledger.rows[(host, "error")] += 1
                    ledger.errors[(host, type(exc).__name__)] += 1
                    raise
                finally:
                    ledger.active -= 1
                    ledger.ms.setdefault(host, []).append((time.perf_counter() - started) * 1000)

        return patch.object(client_type, "send", send)

    def install(self, stack: ExitStack) -> None:
        import httpx
        stack.enter_context(self._wrap(httpx.AsyncClient))
        try:  # some SDK builds vendor a second transport package
            import httpx2
            stack.enter_context(self._wrap(httpx2.AsyncClient))
        except ImportError:
            pass

    def snapshot(self) -> dict:
        def pct(values, q):
            values = sorted(values)
            return round(values[min(len(values) - 1, int(q * len(values)))], 1) if values else None
        return {"cap": self.cap, "peak_inflight": self.peak,
                "by_host": {f"{h}|{s}": n for (h, s), n in sorted(self.rows.items())},
                "errors": {f"{h}|{e}": n for (h, e), n in sorted(self.errors.items())},
                "latency_ms": {h: {"n": len(v), "p50": pct(v, 0.5), "p90": pct(v, 0.9), "max": pct(v, 1.0)}
                               for h, v in self.ms.items()}}


def make_deps(*, mock: bool, renderer: str, classifier: str, max_sessions: int, max_inflight: int,
              overrides: dict | None = None):
    config = {"visitor_renderer": renderer, "concurrency": {"max_sessions": max_sessions},
              "agent_llm": {"max_inflight": max_inflight}, "path_classifier": {"provider": classifier}}
    for key, value in (overrides or {}).items():
        config.setdefault(key, {}).update(value) if isinstance(value, dict) else config.__setitem__(key, value)
    if mock:
        config["agent_llm"]["provider"] = "mock"
        config["path_classifier"]["provider"] = "mock"
    loaded = load_config(config)
    return build_deps(config=config, sim=make_s2_sim(loaded, mock=mock), screening=S2Screening(),
                      outcome=S2OutcomeModel(), safety=SafetyLayer(judge=MockJudge()) if mock else SafetyLayer())


async def close_deps(deps) -> None:
    renderer = getattr(deps.sim.client, "_client", None)
    classifier = deps.classifier if hasattr(deps.classifier, "aclose") else getattr(deps.classifier, "client", None)
    for obj in (deps.llm, classifier, renderer):
        close = getattr(obj, "aclose", None) or getattr(obj, "close", None)
        if close:
            await close()


async def run_batch(deps, visitors: list[dict], text: str, version: str, run_id: str, *, role: str, split: str,
                    max_sessions: int, ledger: HttpLedger | None = None, out_root: Path = LAB) -> dict:
    """One cohort under one playbook text → files + the rich evaluator result used by engine.evolve."""
    out = out_root / run_id
    if (out / "run_report.json").exists():
        raise ValueError(f"{run_id} already exists; use a new run id (no silent re-billing/overwrite)")
    current = replace(deps, playbook=Playbook(version, text, parse_sections(text)))
    limiter = asyncio.Semaphore(max_sessions)
    started = time.perf_counter()
    durations: dict[str, float] = {}

    async def one(visitor):
        async with limiter:
            t0 = time.perf_counter()
            runner = SessionRunner(current, visitor, run_id)
            session, trace = await runner.run()
            trace["s2_replies"] = runner.sim_memory.get("_s2_replies", [])  # reveal/deny log for the audit
            durations[visitor["id"]] = round(time.perf_counter() - t0, 2)
            write_json(out / "sessions" / f"{visitor['id']}.json", session)
            write_json(out / "trace" / f"{visitor['id']}.json", trace)
            return session, trace

    results = await asyncio.gather(*(one(v) for v in visitors))
    duration = time.perf_counter() - started
    report, summary = build_report(
        {v["id"]: v for v in visitors}, results, scorer=score_run, run_id=run_id, label=f"lab {run_id}",
        role=role, split=split, playbook_version=version,
        models={"agent": deps.llm.model_name, "visitor": deps.sim.model_name,
                "judge": getattr(deps.safety.judge, "provider", "unknown")},
        duration_s=duration, session_refs={v["id"]: f"sessions/{v['id']}.json" for v in visitors})
    ordered = sorted(durations.values())
    summary.update(duration_s=round(duration, 2), max_sessions=max_sessions,
                   classifier=deps.classifier.provider,
                   session_s={"p50": ordered[len(ordered) // 2], "max": ordered[-1]} if ordered else None)
    write_json(out / "summary.json", summary)
    (out / "playbook.md").write_text(text, encoding="utf-8")
    if ledger:
        write_json(out / "http.json", ledger.snapshot())
    if report is None:
        raise RuntimeError(f"{run_id}: no scoreable session; see summary.json")
    write_json(out / "run_report.json", report)
    # A batch with excluded or widely degraded sessions is not a measurement of the playbook.
    degraded_share = summary["degraded_sessions"] / max(1, summary["attempted"])
    if summary["excluded"] or degraded_share > MAX_DEGRADED_SHARE:
        print(json.dumps({"run_id": run_id, "INVALID": True, "excluded": len(summary["excluded"]),
                          "degraded": summary["degraded_sessions"], "attempted": summary["attempted"]}), flush=True)
        raise RuntimeError(f"{run_id}: invalid batch (excluded={len(summary['excluded'])}, "
                           f"degraded={summary['degraded_sessions']}/{summary['attempted']})")
    line = {"run_id": run_id, "version": version, "n": report["n_visitors"], "s": round(duration, 1),
            **{k: (round(report["metrics"][k], 4) if isinstance(report["metrics"].get(k), float)
                   else report["metrics"].get(k)) for k in SHOW},
            "excluded": len(summary["excluded"]), "degraded": summary["degraded_sessions"],
            "switches": summary["provider_switches"], "judge_fallbacks": summary["safety_summary"]["judge_fallbacks"],
            "crisis_exit": summary["crisis_exit_count"],
            "http_errors": sum(ledger.errors.values()) if ledger else None,
            "peak_inflight": ledger.peak if ledger else None}
    print(json.dumps(line, ensure_ascii=False), flush=True)
    return {"metrics": report["metrics"], "per_visitor": report["per_visitor"],
            "sessions": {s["visitor_id"]: s for s, _ in results},
            "traces": {s["visitor_id"]: t for s, t in results}, "visitors": {v["id"]: v for v in visitors},
            "summary": summary, "line": line}


def load_split(visitors_dir: str, split: str, n: int | None) -> list[dict]:
    folder = (ROOT / visitors_dir / split) if not Path(visitors_dir).is_absolute() else Path(visitors_dir) / split
    visitors = load_visitors([folder])
    if not visitors:
        raise ValueError(f"no visitors under {folder}")
    return visitors[:n] if n else visitors


async def cmd_batch(args) -> int:
    visitors = load_split(args.visitors_dir, args.split, args.n)
    text = Path(args.playbook).read_text(encoding="utf-8")
    ledger = HttpLedger(args.http_cap)
    with ExitStack() as stack:
        if not args.mock:
            ledger.install(stack)
        deps = make_deps(mock=args.mock, renderer=args.renderer, classifier=args.classifier,
                         max_sessions=args.max_sessions, max_inflight=args.max_inflight,
                         overrides={"prompts_dir": args.prompts_dir} if args.prompts_dir else None)
        write_json(LAB / f"{args.run_id}.meta.json", {**vars(args), "n_visitors": len(visitors),
                                                       "classifier": deps.classifier.provider})
        try:
            for k in range(1, args.repeat + 1):
                run_id = args.run_id if args.repeat == 1 else f"{args.run_id}-r{k}"
                await run_batch(deps, visitors, text, args.version, run_id, role=args.role, split=args.split,
                                max_sessions=args.max_sessions, ledger=None if args.mock else ledger)
        finally:
            await close_deps(deps)
    return 0


GATE_PROFILES = {
    # "default" = whatever engine/evolve/config.yaml freezes today.
    "default": {},
    # Proposed noise-aware settings (待统筹确认): one referral-positive visitor of slack, ≥2 responders gained.
    "robust": {"referral_recall_tolerance_visitors": 1, "min_primary_gain_visitors": 2},
    "robust2x": {"referral_recall_tolerance_visitors": 1, "min_primary_gain_visitors": 2, "replicates": 2},
    # Contract minimum on the primary metric (strictly higher) + one referral-positive visitor of slack.
    "tol1": {"referral_recall_tolerance_visitors": 1},
    "tol1x2": {"referral_recall_tolerance_visitors": 1, "replicates": 2},
    # Baseline measured 3x (free: runs while the reflector thinks), each candidate once / twice.
    "tol1b3": {"referral_recall_tolerance_visitors": 1, "baseline_replicates": 3},
    "tol1x2b3": {"referral_recall_tolerance_visitors": 1, "replicates": 2, "baseline_replicates": 3},
    # As above, but the pooled primary metric must gain at least two visitors' worth (noise margin).
    "m2x2b3": {"referral_recall_tolerance_visitors": 1, "min_primary_gain_visitors": 2, "replicates": 2,
               "baseline_replicates": 3},
}


class MockReflector:
    model, provider = "mock-reflector", "mock"

    async def complete(self, system, user):
        texts = ("先确认来访最希望改善的睡眠困扰。", "每次只问一个具体问题。", "用简短的复述确认已经听到的信息。")
        return json.dumps({"candidates": [
            {"summary": t, "changes": [{"op": "add", "section": "communication_style", "before": None,
                                        "after": t, "reason": "离线联调", "criticality_self": "low"}]}
            for t in texts]}, ensure_ascii=False)


async def cmd_evolve(args) -> int:
    """Multi-generation learning from an existing lab run on A, gated on C; nothing outside var/lab changes."""
    from engine.evolve.config import load_config as evolve_config
    from engine.evolve.lineage import evolve_lineage
    from engine.evolve.reflector import load_sessions, load_traces
    from engine.evolve.repo import PlaybookRepo

    exp = LAB / args.exp
    if (exp / "evolve").exists():
        raise ValueError(f"{args.exp} already has an evolve directory; use a new --exp")
    source = LAB / args.source_run
    report = json.loads((source / "run_report.json").read_text(encoding="utf-8"))
    learn_visitors = {v["id"]: v for v in load_split(args.visitors_dir, args.learn_split, None)}
    learn_visitors = {vid: learn_visitors[vid] for vid in (r["visitor_id"] for r in report["per_visitor"])}
    gate_visitors = load_split(args.visitors_dir, args.gate_split, args.n_gate)
    overrides = {"repo": {"path": str(exp / "playbook-repo")},
                 "review": {"run_dir": str(exp / "evolve")},
                 "gate": {**GATE_PROFILES[args.gate], "baseline_during_reflection": args.fast,
                          "parallel_candidates": args.parallel_candidates}}
    if args.skill:
        name = "reflector_skill_ladder.md" if args.skill == "ladder" else "reflector_skill.md"
        overrides["reflector"] = {"prompts": {**evolve_config()["reflector"]["prompts"],
                                              "skill": f"engine/prompts/{name}"}}
        if args.skill == "ladder":  # candidate 3 carries up to three targets x two rules
            overrides["reflector"]["max_changes_per_candidate"] = 6
    if args.reflector:
        os.environ["REFLECTOR_PROVIDER"] = args.reflector  # process-level; wins over .env
    if args.review_timeout is not None:
        overrides["review"]["timeout_s"] = args.review_timeout
    config = evolve_config(overrides)
    repo = PlaybookRepo(config)
    repo.init()
    if args.start_playbook:
        start = Path(args.start_playbook).read_text(encoding="utf-8")
        if start != repo.read():
            raise ValueError("--start-playbook differs from the repo's current text; the source run must match")
    ledger = HttpLedger(args.http_cap)
    with ExitStack() as stack:
        if not args.mock:
            ledger.install(stack)
        deps = make_deps(mock=args.mock, renderer=args.renderer, classifier=args.classifier,
                         max_sessions=args.max_sessions, max_inflight=args.max_inflight,
                         overrides={"prompts_dir": args.prompts_dir} if args.prompts_dir else None)
        write_json(exp / "meta.json", {**vars(args), "gate_overrides": overrides["gate"],
                                       "n_gate": len(gate_visitors), "source_metrics": report["metrics"]})

        async def evaluator(playbook_text, *, label):
            base = f"{args.exp}/C-{label.replace('+', '_').replace('#', '-')}"
            run_id, attempt = base, 1
            while (LAB / run_id).exists():  # same label can recur after a rejected generation
                attempt += 1
                run_id = f"{base}-t{attempt}"
            return await run_batch(deps, gate_visitors, playbook_text, label.split("#")[0], run_id,
                                   role="validation", split=args.gate_split, max_sessions=args.max_sessions,
                                   ledger=None if args.mock else ledger)

        async def source_runner(playbook_text, version):
            run_id = f"{args.exp}/A-{version}"
            rich = await run_batch(deps, list(learn_visitors.values()), playbook_text, version, run_id,
                                   role="run1", split=args.learn_split, max_sessions=args.max_sessions,
                                   ledger=None if args.mock else ledger)
            fresh = json.loads((LAB / run_id / "run_report.json").read_text(encoding="utf-8"))
            return {"run_report": fresh, "sessions": rich["sessions"], "traces": rich["traces"]}

        started = time.perf_counter()
        try:
            evolutions = await evolve_lineage(
                source_runner=source_runner if args.rerun_source else None,
                continue_after_reject=args.continue_after_reject,
                reuse_baseline=not args.fresh_baseline,
                run_report=report, sessions=load_sessions(report, source), traces=load_traces(report, source),
                visitors=learn_visitors, evaluator=evaluator, config=config, repo=repo,
                max_generations=args.generations, evolution_id_prefix="learn",
                primary=MockReflector() if args.mock else None, use_default_clients=not args.mock)
        finally:
            await close_deps(deps)
    (exp / "final.md").write_text(repo.read(), encoding="utf-8")
    for e in evolutions:
        chosen = next((c for c in e["candidates"] if c["id"] == e["chosen"]), None)
        print(json.dumps({"evolution": e["evolution_id"], "outcome": e["outcome"], "from": e["from_version"],
                          "to": e["to_version"], "reflector": e["reflector"]["model"],
                          "fell_back": e["reflector"]["fell_back"],
                          "baseline_isi": e["baseline_val_metrics"]["isi_response_rate"] if e["baseline_val_metrics"] else None,
                          "candidates": {c["id"]: {"isi": (c["val_metrics"] or {}).get("isi_response_rate"),
                                                   "passed": c["passed"],
                                                   "veto": [r["code"] for r in c["veto"]["reasons"]],
                                                   "hard": [v["code"] for v in c["hard_rule_violations"]]}
                                         for c in e["candidates"]},
                          "chosen_summary": chosen["summary"] if chosen else None}, ensure_ascii=False), flush=True)
    print(json.dumps({"exp": args.exp, "final_version": repo.current_version(),
                      "learn_s": round(time.perf_counter() - started, 1), "final_playbook": str(exp / "final.md")},
                     ensure_ascii=False), flush=True)
    return 0


def add_common(parser) -> None:
    parser.add_argument("--visitors-dir", default="data/visitors")
    parser.add_argument("--renderer", choices=("llm", "template"), default="template")
    parser.add_argument("--classifier", choices=("ds_flash", "jev"), default="ds_flash")
    parser.add_argument("--max-sessions", type=int, default=16)
    parser.add_argument("--max-inflight", type=int, default=32)
    parser.add_argument("--http-cap", type=int, default=64)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--prompts-dir", help="engine prompts directory override, relative to engine/ (lab only)")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    batch = sub.add_parser("batch", help="run one cohort under one playbook, optionally repeated")
    batch.add_argument("--split", required=True)
    batch.add_argument("--run-id", required=True)
    batch.add_argument("--playbook", default=str(ROOT / "engine" / "playbook_v1.md"))
    batch.add_argument("--version", default="v1")
    batch.add_argument("--role", default="validation", choices=("run1", "run2", "control", "validation"))
    batch.add_argument("--n", type=int)
    batch.add_argument("--repeat", type=int, default=1)
    add_common(batch)
    evo = sub.add_parser("evolve", help="multi-generation learning from a lab run, gated on a validation split")
    evo.add_argument("--exp", required=True)
    evo.add_argument("--source-run", required=True, help="var/lab/<run> produced by `batch` on the learn split")
    evo.add_argument("--learn-split", default="A")
    evo.add_argument("--gate-split", default="C")
    evo.add_argument("--n-gate", type=int)
    evo.add_argument("--generations", type=int, default=1)
    evo.add_argument("--gate", choices=tuple(GATE_PROFILES), default="default")
    evo.add_argument("--review-timeout", type=float)
    evo.add_argument("--start-playbook")
    evo.add_argument("--rerun-source", action="store_true",
                     help="after each adopted generation, re-run the learn split under the new playbook")
    evo.add_argument("--fresh-baseline", action="store_true",
                     help="re-measure the baseline every generation (no selection-biased reuse)")
    evo.add_argument("--reflector", choices=("openai", "deepseek", "anthropic"))
    evo.add_argument("--skill", nargs="?", const="plain", choices=("plain", "ladder"),
                     help="append a reflection skill to the reflector prompt (plain | ladder candidates)")
    evo.add_argument("--continue-after-reject", action="store_true",
                     help="a generation that adopts nothing does not end the chain")
    evo.add_argument("--fast", action="store_true",
                     help="run the baseline on the gate split while the reflector is thinking")
    evo.add_argument("--parallel-candidates", action="store_true",
                     help="evaluate candidates concurrently (provider rate limits permitting)")
    add_common(evo)
    args = parser.parse_args(argv)
    load_dotenv()
    return asyncio.run({"batch": cmd_batch, "evolve": cmd_evolve}[args.cmd](args))


if __name__ == "__main__":
    raise SystemExit(main())
