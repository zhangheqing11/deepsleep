"""Run one batch of sessions concurrently and write contract session JSON.

    python -m engine.run --visitors contracts/examples --run-id dev-001
    python -m engine.run --visitors data/visitors/A --sim sim.visitor:make_sim --screening sim.screening:make_screening

Without DS_* keys the agent falls back to the mock LLM; without --sim the rule-based
mock visitor is used. Outputs: <out>/sessions/<visitor_id>.json (contract) and
<out>/trace/<visitor_id>.json (debug only, not a contract).
"""
import argparse
import asyncio
import importlib
import json
from pathlib import Path
import time

from safety.layer import SafetyLayer

from .classifier import make_classifier
from .config import ROOT, load_config, load_dotenv
from .llm import make_agent_llm
from .playbook import load_playbook
from .session import EngineDeps, SessionRunner
from .stubs import IndexScreening, MockVisitorSim, StubOutcomeModel

PROMPTS = ("boundaries", "strategy", "response", "turn_merged", "memory", "plan", "select")


def build_deps(*, config=None, llm=None, classifier=None, sim=None, screening=None, outcome=None, safety=None,
               playbook=None, playbook_version="v0") -> EngineDeps:
    config = load_config(config)
    # One limiter for every ds flash request the engine itself makes (agent sub-agents + path classifier).
    limiter = asyncio.Semaphore(config["agent_llm"]["max_inflight"])
    prompts_dir = Path(config["prompts_dir"])
    return EngineDeps(
        llm=llm or make_agent_llm(config["agent_llm"], limiter=limiter),
        classifier=classifier or make_classifier(config["path_classifier"], limiter=limiter),
        sim=sim or MockVisitorSim(),
        screening=screening or IndexScreening(),
        outcome=outcome or StubOutcomeModel(),
        safety=safety or SafetyLayer(),
        playbook=playbook or load_playbook(config["playbook_path"], playbook_version),
        config=config,
        prompts={name: (prompts_dir / f"{name}.md").read_text(encoding="utf-8") for name in PROMPTS},
    )


async def run_batch(visitors: list[dict], deps: EngineDeps, run_id: str, *,
                    max_sessions: int | None = None) -> list[tuple[dict, dict]]:
    """All sessions concurrently, bounded by concurrency.max_sessions; order follows `visitors`."""
    limit = asyncio.Semaphore(max_sessions or deps.config["concurrency"]["max_sessions"])

    async def one(visitor):
        async with limit:
            return await SessionRunner(deps, visitor, run_id).run()

    return list(await asyncio.gather(*(one(v) for v in visitors)))


def load_visitors(paths: list[Path]) -> list[dict]:
    files = []
    for path in paths:
        files += sorted(path.glob("*.json")) if path.is_dir() else [path]
    visitors = []
    for file in files:
        data = json.loads(file.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "clues" in data and "opening_complaint" in data:  # visitor documents only
            visitors.append(data)
    return visitors


def _factory(spec: str):
    module, _, name = spec.partition(":")
    return getattr(importlib.import_module(module), name)()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--visitors", nargs="+", type=Path, default=[ROOT / "contracts/examples"])
    parser.add_argument("--run-id", default=time.strftime("dev-%Y%m%d-%H%M%S"))
    parser.add_argument("--out", type=Path, help="default var/runs/<run-id>")
    parser.add_argument("--playbook", type=Path, help="default engine/playbook_v0.md")
    parser.add_argument("--playbook-version", default="v0")
    parser.add_argument("--sim", help="module:factory returning a VisitorSim (default: engine.stubs mock)")
    parser.add_argument("--screening", help="module:factory returning a ScreeningProvider")
    parser.add_argument("--outcome", help="module:factory returning a PlanOutcomeModel (4-week model)")
    parser.add_argument("--mock", action="store_true", help="force the mock agent LLM and mock path classifier")
    parser.add_argument("--merged", action="store_true", help="merge strategy + response into one call")
    args = parser.parse_args(argv)
    load_dotenv()
    overrides = {}
    if args.mock:
        overrides.update(agent_llm={"provider": "mock"}, path_classifier={"provider": "mock"})
    if args.merged:
        overrides["pipeline"] = {"merge_strategy_response": True}
    playbook = load_playbook(args.playbook, args.playbook_version) if args.playbook else None
    deps = build_deps(config=overrides, sim=_factory(args.sim) if args.sim else None,
                      screening=_factory(args.screening) if args.screening else None,
                      outcome=_factory(args.outcome) if args.outcome else None,
                      playbook=playbook, playbook_version=args.playbook_version)
    visitors = load_visitors(args.visitors)
    started = time.perf_counter()
    results = asyncio.run(run_batch(visitors, deps, args.run_id))
    out = args.out or ROOT / "var/runs" / args.run_id
    (out / "sessions").mkdir(parents=True, exist_ok=True)
    (out / "trace").mkdir(parents=True, exist_ok=True)
    for session, trace in results:
        name = f"{session['visitor_id']}.json"
        (out / "sessions" / name).write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "trace" / name).write_text(json.dumps(trace, ensure_ascii=False, indent=2, default=str),
                                          encoding="utf-8")
    statuses = {}
    for session, _ in results:
        statuses[session["status"]] = statuses.get(session["status"], 0) + 1
    print(f"{len(results)} sessions in {time.perf_counter() - started:.1f}s -> {out}  {statuses}  "
          f"agent={deps.llm.model_name} classifier={deps.classifier.provider} "
          f"judge={getattr(deps.safety.judge, 'provider', '?')}")
    return int(any(s["status"] == "error" for s, _ in results))


if __name__ == "__main__":
    raise SystemExit(main())
