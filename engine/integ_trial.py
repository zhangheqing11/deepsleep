"""Bounded local trial: S2 visitors/state model + S3 + the default safety chain.

One invocation runs exactly one bounded sample batch (default 10 visitors). It never loads a repository-local
.env. Raw outputs stay under ignored var/. No request headers/bodies are recorded.
"""
import argparse
import asyncio
from collections import Counter, defaultdict
from contextlib import ExitStack
from contextvars import ContextVar
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import time
from unittest.mock import patch

from contracts.validate import load_validators, validate_document
from scoring.score import score_run
from scoring.smoke import load_visitors
from sim.llm import DsConfig
from .adapters_sim import S2RendererClient
from safety.judges import MockJudge
from safety.layer import SafetyLayer

from .adapters_sim import S2OutcomeModel, S2Screening, S2VisitorSim
from .config import load_dotenv
from .run import build_deps
from .session import SessionRunner
from .reporting import build_report
from .file_lock import file_lock

VISITOR = ContextVar("integ_visitor", default="unknown")
COMPONENT = ContextVar("integ_component", default="unknown")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def distribution(values):
    if not values:
        return {"n": 0, "total": 0, "mean": None, "p50": None, "p95": None, "max": None}
    ordered = sorted(values)
    return {"n": len(values), "total": round(sum(values), 3),
            "mean": round(sum(values) / len(values), 3),
            **{key: round(ordered[max(0, math.ceil(p * len(values)) - 1)], 3)
               for key, p in (("p50", .5), ("p95", .95), ("max", 1))}}


class RequestBudgetExceeded(RuntimeError):
    pass


def mark_budget_incomplete(report, accounting, blocked):
    """A successful deterministic fallback is not a completed live-API evaluation."""
    if blocked:
        accounting["evaluation_complete"] = False
        accounting["real_api_validation_complete"] = False
        accounting["incomplete_reason"] = "request_budget_exhausted"
        if report is not None:
            report["veto"]["passed"] = False  # no budget reason enum exists in the contract


class RequestBudget:
    """Durable, process-safe count of attempted HTTP requests, including retries/cancellations."""
    def __init__(self, path, limit=450):
        self.path, self.limit = Path(path), limit
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def reserve(self):
        # Lock a sidecar file.  Locking the append-only budget file itself
        # would require a sentinel byte on Windows and would corrupt its line
        # count when the file starts empty.
        with file_lock(self.path.with_name(self.path.name + ".lock")):
            with self.path.open("a+") as stream:
                stream.seek(0)
                count = len(stream.readlines())
                if count >= self.limit:
                    raise RequestBudgetExceeded("Global real-request budget exhausted")
                stream.write("attempt\n")
                stream.flush()


class Meter:
    def __init__(self, budget=None):
        self.budget = budget
        self.budget_blocked = 0
        self.calls = []
        self.http = []

    def wrap(self, obj, method, component):
        original = getattr(obj, method)

        async def measured(*args, **kwargs):
            name = kwargs.get("task", component) if component == "agent" else component
            token = COMPONENT.set(name)
            row = {"visitor_id": VISITOR.get(), "component": name, "status": "started"}
            self.calls.append(row)
            started = time.perf_counter()
            try:
                result = await original(*args, **kwargs)
                row["status"] = getattr(result, "status", "ok")
                if component == "visitor" and result is None:
                    row["status"] = "fallback"
                    # Exception class only; API errors can contain sensitive request details.
                    row["error_type"] = (obj.last_error or "unknown").split(":", 1)[0]
                return result
            except asyncio.CancelledError:
                row["status"] = "cancelled"
                raise
            except Exception as exc:
                row["status"] = "timeout" if "timeout" in type(exc).__name__.lower() else "error"
                row["error_type"] = type(exc).__name__
                raise
            finally:
                row["ms"] = round((time.perf_counter() - started) * 1000, 3)
                COMPONENT.reset(token)
        setattr(obj, method, measured)

    def watch_http(self, client_type):
        original = client_type.send
        rows = self.http

        async def send(client, request, *args, **kwargs):
            if self.budget is not None:
                try:
                    self.budget.reserve()
                except RequestBudgetExceeded:
                    self.budget_blocked += 1
                    raise
            row = {"visitor_id": VISITOR.get(), "component": COMPONENT.get(),
                   "status": "started"}
            rows.append(row)
            started = time.perf_counter()
            try:
                response = await original(client, request, *args, **kwargs)
                row["http_status"] = response.status_code
                row["status"] = "ok" if response.status_code < 400 else "http_error"
                return response
            except asyncio.CancelledError:
                row["status"] = "cancelled"
                raise
            except Exception as exc:
                row["status"] = "timeout" if "timeout" in type(exc).__name__.lower() else "error"
                row["error_type"] = type(exc).__name__
                raise
            finally:
                row["ms"] = round((time.perf_counter() - started) * 1000, 3)
        return patch.object(client_type, "send", send)

    def summary(self):
        groups = defaultdict(list)
        for row in self.calls:
            groups[row["component"]].append(row)
        return {
            "components": {key: {**distribution([r["ms"] for r in rows]),
                                 "statuses": dict(Counter(r["status"] for r in rows)),
                                 "http_attempts": sum(r["component"] == key for r in self.http)}
                           for key, rows in sorted(groups.items())},
            "http_attempts": len(self.http),
            "budget_blocked": self.budget_blocked,
            "http_statuses": dict(Counter(r["status"] for r in self.http)),
            "logical_calls": len(self.calls),
            "logical_statuses": dict(Counter(r["status"] for r in self.calls)),
        }


async def trial(args):
    if not args.mock:
        load_dotenv(args.env_file)
        required = ("DS_API_KEY", "DS_BASE_URL", "DS_MODEL", "TYPESAFE_API_KEY")
        if not all(os.getenv(key, "").strip() for key in required):
            raise RuntimeError("Required DS/Jev configuration is missing; refusing mock fallback")
    out = Path("var/integ") / args.run_id
    out.mkdir(parents=True, exist_ok=False)  # refuse accidental billed reruns
    visitors = load_visitors(n=args.n)
    meter = Meter(None if args.mock else RequestBudget(args.budget_file, args.budget))
    config = {"agent_llm": {"max_retries": 1},
              "pipeline": {"merge_strategy_response": args.merged}}
    if args.config:
        import yaml
        from .config import _merge
        _merge(config, yaml.safe_load(args.config.read_text()))
    if args.mock:
        config["agent_llm"]["provider"] = "mock"
        config["path_classifier"] = {"provider": "mock"}
    sim_client = None if args.mock else S2RendererClient(DsConfig(
        os.environ["DS_BASE_URL"], os.environ["DS_API_KEY"], os.environ["DS_MODEL"]))
    if not args.mock and sim_client is None:
        raise RuntimeError("Visitor client missing")
    safety = SafetyLayer(judge=MockJudge()) if args.mock else SafetyLayer()
    deps = build_deps(config=config, sim=S2VisitorSim(sim_client), screening=S2Screening(),
                      outcome=S2OutcomeModel(), safety=safety)
    resources = []
    if not args.mock:
        if safety.judge.provider != "chain" or [j.provider for j in safety.judge.judges] != ["ds_flash", "jev"]:
            raise RuntimeError("Expected default ds_flash -> Jev chain")
        # Preserve safety thresholds/timeouts. Bound the optional SDK's retry policy.
        from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy
        jev = safety.judge.judges[1]
        jev.client = AsyncTypeSafeClient(api_key=jev.api_key, timeout=jev.timeout,
                                         retry=RetryPolicy(max_retries=1))
        resources.append(jev.client)
        resources.append(deps.llm)
        if hasattr(deps.classifier, "aclose"):
            resources.append(deps.classifier)
        elif getattr(deps.classifier, "client", None) is not None:
            resources.append(deps.classifier.client)
        sim_client._get_client()
        resources.append(sim_client._client)
    meter.wrap(deps.llm, "complete_json", "agent")
    meter.wrap(deps.classifier, "classify", "classifier")
    if hasattr(deps.classifier, "primary"):
        meter.wrap(deps.classifier.primary, "classify", "classifier.jev")
        meter.wrap(deps.classifier.fallback, "classify", "classifier.ds_flash")
    if sim_client:
        meter.wrap(sim_client, "complete", "visitor")
    for judge in getattr(safety.judge, "judges", (safety.judge,)):
        meter.wrap(judge, "classify", f"judge.{judge.provider}")

    manifest = {"run_id": args.run_id, "mode": "merged" if args.merged else "split",
                "mock": args.mock, "n": args.n, "max_concurrent_sessions": args.n,
                "models": {"agent": deps.llm.model_name, "visitor": deps.sim.model_name,
                           "judge": safety.judge.provider},
                "config": deps.config, "safety_config": safety.config,
                "params_sha256": hashlib.sha256(Path("sim/params.yaml").read_bytes()).hexdigest(),
                "git_commit": __import__("subprocess").check_output(
                    ["git", "rev-parse", "HEAD"], text=True).strip(),
                "note": "Worktree files may be uncommitted; source digest identifies tested code."}
    paths = sorted(p for directory in ("engine", "sim", "scoring", "safety", "domain", "contracts")
                   for p in Path(directory).rglob("*")
                   if p.is_file() and "__pycache__" not in p.parts
                   and p.suffix in (".py", ".yaml", ".md", ".json"))
    manifest["source_sha256"] = hashlib.sha256(
        b"".join(str(p).encode() + b"\0" + p.read_bytes() for p in paths)).hexdigest()
    write_json(out / "manifest.json", manifest)

    async def one(visitor):
        token = VISITOR.set(visitor["id"])
        started = time.perf_counter()
        runner = SessionRunner(deps, visitor, args.run_id)
        try:
            session, trace = await runner.run()
            trace["s2_replies"] = runner.sim_memory.get("_s2_replies", [])
            trace["all_judge_results"] = [asdict(r) for r in runner.safety_state.judge_results]
            trace["wall_s"] = time.perf_counter() - started
            write_json(out / "sessions" / f'{visitor["id"]}.json', session)
            write_json(out / "trace" / f'{visitor["id"]}.json', trace)
            print(f'{visitor["id"]}: {session["status"]}, {trace["wall_s"]:.2f}s', flush=True)
            return session, trace
        finally:
            VISITOR.reset(token)

    import httpx
    try:
        import httpx2  # installed transitively by typesafe-sdk
    except ImportError:
        httpx2 = None
    started = time.perf_counter()
    try:
        with ExitStack() as stack:
            stack.enter_context(meter.watch_http(httpx.AsyncClient))
            if httpx2 is not None:
                stack.enter_context(meter.watch_http(httpx2.AsyncClient))
            results = await asyncio.gather(*(one(v) for v in visitors))
            wall_s = time.perf_counter() - started
    finally:
        for client in resources:
            close = getattr(client, "aclose", None) or getattr(client, "close", None)
            if close:
                await close()
        write_json(out / "calls.json", {"logical": meter.calls, "http": meter.http})

    sessions = [s for s, _ in results]
    by_id = {v["id"]: v for v in visitors}
    report, accounting = build_report(by_id, results, scorer=score_run, run_id=args.run_id, label="本地联调",
                       role="validation", split="sample", playbook_version="v1",
                       models=manifest["models"], duration_s=wall_s,
                       session_refs={v["id"]: f'sessions/{v["id"]}.json' for v in visitors})
    mark_budget_incomplete(report, accounting, meter.budget_blocked)
    if report is not None:
        write_json(out / "run_report.json", report)
    validators = load_validators()
    errors = {}
    for kind, documents in (("visitor", visitors), ("session", sessions), ("run_report", [report] if report else [])):
        for i, doc in enumerate(documents):
            found = validate_document(doc, kind, validators, by_id)
            if found:
                errors[f"{kind}:{i}"] = found
    summary = {"wall_s": wall_s, "session_s": distribution([t["wall_s"] for _, t in results]),
               "statuses": dict(Counter(s["status"] for s in sessions)),
               "validation_errors": errors, "metrics": report["metrics"] if report else None,
               "veto": report["veto"] if report else None, "accounting": accounting,
               **meter.summary()}
    write_json(out / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return int(bool(errors) or bool(meter.budget_blocked) or any(s["status"] == "error" for s in sessions))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--merged", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--n", type=int, choices=range(1, 19), default=10)
    parser.add_argument("--config", type=Path, help="Frozen override YAML for staged measurements")
    parser.add_argument("--budget", type=int, default=450)
    parser.add_argument("--budget-file", type=Path, default=Path("var/s3-phase2/request-budget.log"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--env-file", type=Path,
                        default=Path("/Users/zhangheqing/bohack/ds-safety/.env"))
    return asyncio.run(trial(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
