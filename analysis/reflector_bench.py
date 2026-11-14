"""Screen reflector models on one fixed source run (real API calls to the reflector only).

    python -m analysis.reflector_bench reflect --source-run X-v1-A2 --out bench1 --only a,b
    python -m analysis.reflector_bench gate --bench bench1 --names a,b --baseline E11/C-v1,E11/C-v1-r2 ...

``reflect`` sends the same reflection prompt to every candidate model concurrently and stores the
normalised candidates with timing and validity; it never touches the session agent's provider
budget beyond one call per DeepSeek model. ``gate`` then evaluates stored candidates on the gate
split with the same evaluator the lab driver uses.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import time

from engine.config import ROOT, load_dotenv
from engine.evolve.config import load_config as evolve_config
from engine.evolve.hard_rules import check_candidate
from engine.evolve.llm import LLMError, OpenAIClient, OpenAICompatClient
from engine.evolve.pipeline import _applicable
from engine.evolve.reflector import load_sessions, load_traces, reflect
from engine.run import load_visitors

LAB = ROOT / "var" / "lab"

# name -> (kind, model, effort). kind: openai (Responses API) | deepseek | compat:<base-url-env>|<key-env>
MODELS = {
    "astra-high": ("openai", "gpt-6-astra", "high"),
    "astra-medium": ("openai", "gpt-6-astra", "medium"),
    "astra-low": ("openai", "gpt-6-astra", "low"),
    "luna-medium": ("openai", "gpt-6-luna", "medium"),
    "sol-medium": ("openai", "gpt-6-sol", "medium"),
    "sol61-medium": ("openai", "gpt-6.1-sol", "medium"),
    "terra61-medium": ("openai", "gpt-6.1-terra", "medium"),
    "terra61-low": ("openai", "gpt-6.1-terra", "low"),
    "dspro-high": ("deepseek", "deepseek-v4-pro", "high"),
    "dspro-low": ("deepseek", "deepseek-v4-pro", "low"),
    "dsflash-high": ("deepseek", "deepseek-flash", "high"),
    "gemini4-carbon": ("gemini", "gemini-4-carbon", "medium"),
    "gemini4-argon": ("gemini", "gemini-4-argon", "medium"),
    "gemini38-flash": ("gemini", "gemini-3.8-flash", "medium"),
}
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"


class CompatClient:
    """Generic OpenAI-compatible chat client (used for Gemini's compatibility endpoint)."""

    def __init__(self, provider: str, model: str, *, base_url: str, api_key: str, timeout_s: float,
                 max_tokens: int, effort: str | None):
        from openai import AsyncOpenAI
        self.provider, self.model, self.effort, self.timeout_s = provider, model, effort, timeout_s
        self.max_tokens = max_tokens
        self.last_response_metadata: dict = {}
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=timeout_s, max_retries=0)

    async def complete(self, system: str, user: str) -> str:
        extra = {"reasoning_effort": self.effort} if self.effort else {}
        response = await self._client.chat.completions.create(
            model=self.model, max_tokens=self.max_tokens, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], **extra)
        usage = getattr(response, "usage", None)
        details = getattr(usage, "completion_tokens_details", None)
        self.last_response_metadata = {"model": response.model,
                                       "reasoning_tokens": getattr(details, "reasoning_tokens", None)}
        if response.choices[0].finish_reason != "stop":
            raise LLMError(f"输出未完成（{response.choices[0].finish_reason}）")
        text = (response.choices[0].message.content or "").strip()
        if not text:
            raise LLMError("返回空文本")
        return text


def make_client(name: str, config: dict, timeout_s: float):
    kind, model, effort = MODELS[name]
    max_tokens = config["reflector"]["max_tokens"]
    if kind == "openai":
        return OpenAIClient(model, timeout_s=timeout_s, max_tokens=max_tokens, effort=effort)
    if kind == "deepseek":
        return OpenAICompatClient(model, timeout_s=timeout_s, max_tokens=max_tokens, effort=effort, json_mode=True)
    if kind == "gemini":
        return CompatClient("gemini", model, base_url=GEMINI_BASE, api_key=os.environ["GEMINI_API_KEY"],
                            timeout_s=timeout_s, max_tokens=max_tokens, effort=effort)
    raise ValueError(kind)


def load_source(source_run: str, split: str):
    source = LAB / source_run
    report = json.loads((source / "run_report.json").read_text(encoding="utf-8"))
    visitors = {v["id"]: v for v in load_visitors([ROOT / "data" / "visitors" / split])}
    visitors = {r["visitor_id"]: visitors[r["visitor_id"]] for r in report["per_visitor"]}
    playbook = (source / "playbook.md").read_text(encoding="utf-8")
    return report, load_sessions(report, source), load_traces(report, source), visitors, playbook


async def cmd_reflect(args) -> int:
    config = evolve_config()
    report, sessions, traces, visitors, playbook = load_source(args.source_run, args.split)
    out = LAB / args.out
    out.mkdir(parents=True, exist_ok=True)
    names = [n for n in (args.only.split(",") if args.only else MODELS) if n]

    async def one(name: str) -> dict:
        row = {"name": name, "kind": MODELS[name][0], "model": MODELS[name][1], "effort": MODELS[name][2]}
        started = time.perf_counter()
        try:
            client = make_client(name, config, args.timeout)
            result = await reflect(playbook_text=playbook, version="v1", run_report=report, sessions=sessions,
                                   feedback=[], config=config, primary=client, fallback=None, traces=traces,
                                   visitors=visitors, history=None)
            attempt = result.attempts[-1] if result.attempts else {}
            log: list[str] = list(result.dropped_changes)
            texts, hard = {}, {}
            for cand in result.candidates:
                texts[cand["id"]] = _applicable(cand, playbook, log)
                hard[cand["id"]] = [v.get("code") for v in check_candidate(cand["changes"], playbook, config)] \
                    if cand["changes"] else []
            row.update(ok=bool(attempt.get("success")), error=attempt.get("error"),
                       reasoning_tokens=attempt.get("reasoning_tokens"), actual_model=result.model,
                       n_valid=sum(bool(c["changes"]) and not hard[c["id"]] for c in result.candidates),
                       n_changes=[len(c["changes"]) for c in result.candidates], hard=hard, dropped=log,
                       candidates=result.candidates, texts=texts)
        except Exception as exc:  # noqa: BLE001 - a model that cannot be called is a result, not a crash
            row.update(ok=False, error=f"{type(exc).__name__}: {str(exc)[:200]}", n_valid=0)
        row["seconds"] = round(time.perf_counter() - started, 1)
        (out / f"{name}.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({k: row.get(k) for k in ("name", "model", "effort", "ok", "seconds", "reasoning_tokens",
                                                   "n_valid", "n_changes", "error")}, ensure_ascii=False), flush=True)
        return row

    await asyncio.gather(*(one(n) for n in names))
    return 0


async def cmd_gate(args) -> int:
    """Evaluate stored candidates on the gate split (replicated) against existing baseline runs."""
    from contextlib import ExitStack
    from analysis.evo_lab import HttpLedger, close_deps, load_split, make_deps, run_batch

    bench = LAB / args.bench
    gate_visitors = load_split("data/visitors", args.gate_split, None)
    ledger = HttpLedger(args.http_cap)
    with ExitStack() as stack:
        ledger.install(stack)
        deps = make_deps(mock=False, renderer="template", classifier="ds_flash", max_sessions=45,
                         max_inflight=args.max_inflight)
        try:
            jobs = []
            for name in args.names.split(","):
                row = json.loads((bench / f"{name}.json").read_text(encoding="utf-8"))
                for cand in row["candidates"]:
                    if not cand["changes"] or row["hard"].get(cand["id"]):
                        continue
                    for rep in range(1, args.replicates + 1):
                        jobs.append((name, cand["id"], rep, row["texts"][cand["id"]]))
            limiter = asyncio.Semaphore(args.parallel)

            async def run(name, cid, rep, text):
                async with limiter:
                    run_id = f"{args.bench}/gate/{name}-{cid}-r{rep}"
                    if (LAB / run_id / "run_report.json").exists():
                        return
                    try:
                        await run_batch(deps, gate_visitors, text, f"v1+{name}-{cid}", run_id, role="validation",
                                        split=args.gate_split, max_sessions=45, ledger=ledger)
                    except Exception as exc:  # noqa: BLE001 - keep the other evaluations going
                        print(json.dumps({"run_id": run_id, "FAILED": f"{type(exc).__name__}: {exc}"[:200]}), flush=True)

            await asyncio.gather(*(run(*job) for job in jobs))
        finally:
            await close_deps(deps)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("reflect")
    r.add_argument("--source-run", required=True)
    r.add_argument("--split", default="A")
    r.add_argument("--out", required=True)
    r.add_argument("--only")
    r.add_argument("--timeout", type=float, default=420)
    g = sub.add_parser("gate")
    g.add_argument("--bench", required=True)
    g.add_argument("--names", required=True)
    g.add_argument("--gate-split", default="C")
    g.add_argument("--replicates", type=int, default=2)
    g.add_argument("--parallel", type=int, default=3)
    g.add_argument("--max-inflight", type=int, default=192)
    g.add_argument("--http-cap", type=int, default=384)
    args = parser.parse_args(argv)
    load_dotenv()
    return asyncio.run({"reflect": cmd_reflect, "gate": cmd_gate}[args.cmd](args))


if __name__ == "__main__":
    raise SystemExit(main())
