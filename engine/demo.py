"""Two-run demo: A → learn on C → B and the original playbook on B.

Only runtime artifacts under var/ are mutated. Mock mode never constructs API clients.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from uuid import uuid4

from scoring.score import score_run
from safety.judges import MockJudge
from safety.layer import SafetyLayer
from .adapters_sim import S2OutcomeModel, S2RendererClient, S2Screening, S2VisitorSim
from .config import ROOT, load_config, load_dotenv
from .evolve.config import load_config as evolve_config
from .evolve.pipeline import evolve
from .evolve.reflector import load_sessions, load_traces
from .evolve.repo import PlaybookRepo
from .playbook import Playbook, parse_sections
from .run import build_deps, build_report, load_visitors
from .session import SessionRunner

VAR_DIR = ROOT / "var"
PLAYBOOK_REPO = VAR_DIR / "playbook-repo"
OPTIONS = ("visitors_dir", "dev", "mock", "n_a", "n_b", "n_c", "max_sessions")
METRICS = ("isi_response_rate", "path_acc_r2", "referral_recall", "referral_precision", "crisis_missed")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", value):
        raise ValueError("ID 只允许字母、数字、点、下划线和短横线（最多 101 字符）")
    return value


def config_for_repo():
    return evolve_config({"repo": {"path": str(PLAYBOOK_REPO)},
                          "review": {"run_dir": str(VAR_DIR / "evolve")}})


@contextmanager
def command_lock():
    """Avoid two operator commands racing the latest manifest or playbook repo."""
    directory = VAR_DIR / "demo"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("另一个 demo 命令正在运行") from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def save_manifest(manifest):
    manifest["updated_at"] = datetime.now().astimezone().isoformat()
    directory = VAR_DIR / "demo"
    atomic_json(directory / f"experiment.{manifest['experiment_id']}.json", manifest)
    atomic_json(directory / "experiment.json", manifest)


def reset():
    repo = PlaybookRepo(config_for_repo())
    repo.reset_to_initial()
    # Removing the pointer clears the active experiment; archived files stay intact.
    (VAR_DIR / "demo/experiment.json").unlink(missing_ok=True)
    print(f"已重置到 {repo.current_version()}；实验历史保留", flush=True)


def create_manifest(experiment_id):
    directory = VAR_DIR / "demo" / experiment_id
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {"experiment_id": experiment_id, "updated_at": None, "stage": "run1"}
    for key, split in (("run1", "A"), ("run2", "B"), ("control", "B")):
        manifest[key] = {"run_id": f"{experiment_id}-{key}", "playbook_version": None,
                         "split": split, "state": "pending"}
    manifest["evolution"] = {"evolution_id": f"{experiment_id}-learn", "state": "pending"}
    manifest["error"] = None
    save_manifest(manifest)
    return manifest


def cohorts(options):
    path = Path(options["visitors_dir"])
    path = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError("--visitors-dir 必须位于当前团队 worktree 内")
    hint = "；开发彩排请用 --visitors-dir sim/visitors --dev"
    if options["dev"]:
        visitors = load_visitors([path]) if path.is_dir() else []
        if not visitors:
            raise ValueError(f"开发来访目录不存在或无来访 JSON: {path}" + hint)
        groups = {split: visitors[i::3] for i, split in enumerate("ABC")}
    else:
        groups = {}
        for split in "ABC":
            folder = path / split
            if not folder.is_dir():
                raise ValueError(f"缺少来访分组目录: {folder}" + hint)
            groups[split] = load_visitors([folder])
    seen = set()
    for split, visitors in groups.items():
        if not visitors:
            raise ValueError(f"{split} 组没有可用来访" + hint)
        for visitor in visitors:
            vid = safe_id(visitor["id"])
            if vid in seen:
                raise ValueError(f"A/B/C 来访 ID 必须互不重复: {vid}")
            seen.add(vid)
            visitor["split"] = split
        cap = options[f"n_{split.lower()}"]
        groups[split] = visitors[:cap] if cap is not None else visitors
    return groups


class MockReflector:
    model = "mock-reflector"
    provider = "mock"

    async def complete(self, system, user):
        # Exercise three real candidate evaluations; never fabricate improved metrics.
        texts = ("先确认来访最希望改善的睡眠困扰。", "每次只问一个具体问题。", "用简短的复述确认已经听到的信息。")
        return json.dumps({"candidates": [
            {"summary": text, "changes": [{"op": "add", "section": "communication_style",
             "before": None, "after": text, "reason": "离线编排验证", "criticality_self": "low"}]}
            for text in texts]}, ensure_ascii=False)


def make_deps(options):
    mock = options["mock"]
    renderer = None
    if not mock:
        from sim.llm import DsConfig
        required = ("DS_BASE_URL", "DS_API_KEY", "DS_MODEL")
        if not all(os.getenv(k, "").strip() for k in required):
            raise ValueError("真实模式需要进程环境 DS_BASE_URL、DS_API_KEY、DS_MODEL；离线请用 --mock")
        # Deliberately avoid DsConfig.from_env(): it can read an external DS_ENV_FILE.
        renderer = S2RendererClient(DsConfig(*(os.environ[k] for k in required)))
    return build_deps(
        config={"agent_llm": {"provider": "mock"}, "path_classifier": {"provider": "mock"}} if mock else None,
        sim=S2VisitorSim(client=renderer), screening=S2Screening(), outcome=S2OutcomeModel(),
        safety=SafetyLayer(judge=MockJudge()) if mock else SafetyLayer())


async def close_deps(deps):
    renderer = getattr(deps.sim.client, "_client", None)
    classifier = deps.classifier if hasattr(deps.classifier, "aclose") else getattr(deps.classifier, "client", None)
    for obj in (deps.llm, classifier, renderer):
        close = getattr(obj, "aclose", None) or getattr(obj, "close", None)
        if close:
            await close()


async def batch(deps, visitors, text, version, run_id, role, split, limiter, mock):
    out = VAR_DIR / "runs" / run_id
    out.mkdir(parents=True, exist_ok=False)
    current = replace(deps, playbook=Playbook(version, text, parse_sections(text)))
    started = time.perf_counter()

    async def one(visitor):
        async with limiter:
            session, trace = await SessionRunner(current, visitor, run_id).run()
            atomic_json(out / "sessions" / f"{visitor['id']}.json", session)
            atomic_json(out / "trace" / f"{visitor['id']}.json", trace)
            return session, trace

    # Collect exceptions before raising so sibling sessions cannot outlive this stage.
    results = await asyncio.gather(*(one(v) for v in visitors), return_exceptions=True)
    errors = [r for r in results if isinstance(r, BaseException)]
    if errors:
        raise errors[0]
    report, summary = build_report(
        {v["id"]: v for v in visitors}, results, scorer=score_run, run_id=run_id,
        label={"run1": "运行 1", "run2": "运行 2", "control": "对照", "validation": "C 组验证"}[role],
        role=role, split=split, playbook_version=version,
        models={"agent": deps.llm.model_name, "visitor": deps.sim.model_name,
                "judge": getattr(deps.safety.judge, "provider", "unknown")},
        duration_s=time.perf_counter() - started,
        session_refs={v["id"]: f"sessions/{v['id']}.json" for v in visitors})
    summary["execution_mode"] = "mock" if mock else "real"
    atomic_json(out / "summary.json", summary)
    if report is not None:
        atomic_json(out / "run_report.json", report)
    if report is None or not summary["evaluation_complete"]:
        raise RuntimeError(f"{run_id}: 评估不完整，详见 summary.json")
    print(f"{run_id}: {len(results)} sessions -> {out}", flush=True)
    return {"metrics": report["metrics"], "per_visitor": report["per_visitor"],
            "sessions": {s["visitor_id"]: s for s, _ in results},
            "traces": {s["visitor_id"]: t for s, t in results}, "visitors": {v["id"]: v for v in visitors}}


def summary_text(manifest, options):
    lines = [f"实验 {manifest['experiment_id']}（{'mock' if options['mock'] else 'real'}；ISI 为规则模型模拟值）", "",
             "| 运行 | 版本 | " + " | ".join(METRICS) + " | veto.passed |",
             "|---|---|" + "---|" * (len(METRICS) + 1)]
    for key, name in (("run1", "运行 1"), ("control", "对照"), ("run2", "运行 2")):
        report = read_json(VAR_DIR / "runs" / manifest[key]["run_id"] / "run_report.json")
        values = [report["metrics"][k] for k in METRICS] + [report["veto"]["passed"]]
        lines.append("| " + " | ".join([name, report["playbook_version"]] +
                     ["N/A" if v is None else f"{v:.4f}" if isinstance(v, float) else str(v) for v in values]) + " |")
    evolution = read_json(VAR_DIR / "evolve" / manifest["evolution"]["evolution_id"] / "evolution.json")
    old, new = evolution["from_version"], evolution["to_version"] or evolution["from_version"]
    lines += ["", f"学习结果：{evolution['outcome']}；{old} → {new}；evolution_id={evolution['evolution_id']}"]
    chosen = next((c for c in evolution["candidates"] if c["id"] == evolution["chosen"]), None)
    if chosen:
        for change in chosen["changes"][:3]:
            detail = (change["after"] or change["before"] or change["reason"]).replace("\n", " ")
            lines.append(f"- {change['section']} / {change['op']}：{detail}")
    else:
        lines += ["未采纳候选；运行 2 与对照使用同一版本。"]
    lines += ["", f"回退命令：python -m engine.evolve rollback {old}"]
    return "\n".join(lines) + "\n"


class Experiment:
    def __init__(self, manifest, options):
        self.manifest, self.options = manifest, options
        self.directory = VAR_DIR / "demo" / manifest["experiment_id"]
        self.config = config_for_repo()
        self.repo = PlaybookRepo(self.config)
        self.deps = None
        self.limiter = asyncio.Semaphore(options["max_sessions"])

    def start(self, *keys):
        self.manifest["stage"] = "learning" if keys[0] == "evolution" else keys[0]
        for key in keys:
            self.manifest[key]["state"] = "running"
        save_manifest(self.manifest)

    def done(self, key):
        self.manifest[key]["state"] = "done"
        self.manifest["stage"] = next((stage for name, stage in (
            ("run1", "run1"), ("evolution", "learning"), ("run2", "run2"), ("control", "control"))
            if self.manifest[name]["state"] != "done"), "done")
        save_manifest(self.manifest)

    async def run_batch(self, visitors, text, version, run_id, role, split):
        if self.deps is None:
            self.deps = make_deps(self.options)
        return await batch(self.deps, visitors, text, version, run_id, role, split, self.limiter, self.options["mock"])

    async def run1(self):
        self.repo.init()
        version, text = self.repo.current_version(), self.repo.read()
        self.manifest["run1"]["playbook_version"] = self.manifest["control"]["playbook_version"] = version
        self.start("run1")
        groups = cohorts(self.options)
        atomic_json(self.directory / "cohorts.json", groups)
        (self.directory / "original.md").write_text(text, encoding="utf-8")
        atomic_json(self.directory / "options.json", self.options)
        await self.run_batch(groups["A"], text, version, self.manifest["run1"]["run_id"], "run1", "A")
        self.done("run1")

    async def learn(self):
        self.start("evolution")
        original = (self.directory / "original.md").read_text(encoding="utf-8")
        if self.repo.current_version() != self.manifest["run1"]["playbook_version"] or self.repo.read() != original:
            raise ValueError("运行 1 后 playbook 版本库已改变，不能对另一版本学习")
        groups = read_json(self.directory / "cohorts.json")
        run_dir = VAR_DIR / "runs" / self.manifest["run1"]["run_id"]
        report = read_json(run_dir / "run_report.json")
        evolution_id = self.manifest["evolution"]["evolution_id"]

        async def evaluator(playbook_text, *, label):
            return await self.run_batch(groups["C"], playbook_text, label,
                                        f"{evolution_id}-{label.replace('+', '_')}", "validation", "C")

        result = await evolve(run_report=report, sessions=load_sessions(report, run_dir),
                              traces=load_traces(report, run_dir), visitors={v["id"]: v for v in groups["A"]},
                              evaluator=evaluator, config=self.config, repo=self.repo, evolution_id=evolution_id,
                              primary=MockReflector() if self.options["mock"] else None,
                              use_default_clients=not self.options["mock"])
        self.manifest["run2"]["playbook_version"] = result["to_version"] or result["from_version"]
        (self.directory / "learned.md").write_text(self.repo.read(), encoding="utf-8")
        self.done("evolution")
        print(f"evolution_id={evolution_id}: {result['outcome']}", flush=True)

    async def run2(self):
        self.start("run2", "control")
        visitors = read_json(self.directory / "cohorts.json")["B"]

        async def run(key, filename):
            item = self.manifest[key]
            text = (self.directory / filename).read_text(encoding="utf-8")
            await self.run_batch(visitors, text, item["playbook_version"], item["run_id"], key, "B")
            self.done(key)

        results = await asyncio.gather(run("run2", "learned.md"), run("control", "original.md"), return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                raise result
        text = summary_text(self.manifest, self.options)
        (self.directory / "summary.md").write_text(text, encoding="utf-8")
        print(text, flush=True)

    async def execute(self, commands):
        try:
            try:
                for command in commands:
                    await getattr(self, command)()
            finally:
                if self.deps is not None:
                    await close_deps(self.deps)
        except BaseException as exc:
            self.manifest.update(stage="failed", error=f"{type(exc).__name__}: {exc}")
            for key in ("run1", "evolution", "run2", "control"):
                if self.manifest[key]["state"] == "running":
                    self.manifest[key]["state"] = "failed"
            save_manifest(self.manifest)
            raise


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("必须为正整数")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cmd", choices=("reset", "run1", "learn", "run2", "all"))
    parser.add_argument("--experiment", type=safe_id)
    parser.add_argument("--reset", action="store_true", help="仅 all：先重置 playbook")
    parser.add_argument("--visitors-dir")
    parser.add_argument("--dev", action="store_true", default=None)
    parser.add_argument("--mock", action="store_true", default=None)
    for flag in ("n-a", "n-b", "n-c", "max-sessions"):
        parser.add_argument(f"--{flag}", type=positive)
    args = parser.parse_args(argv)
    # Repo-root .env (gitignored), same as engine.run; existing env vars win. Harmless in mock mode
    # (no clients are built), and must happen before `learn` builds the reflector clients.
    load_dotenv()
    try:
        if args.reset and args.cmd != "all":
            raise ValueError("--reset 仅用于 all；也可单独执行 reset")
        with command_lock():
            if args.cmd == "reset":
                reset()
                return 0
            if args.cmd in ("run1", "all"):
                eid = args.experiment or f"exp-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}"
                if (VAR_DIR / "demo" / eid).exists():
                    raise ValueError(f"实验已存在: {eid}；请用新 ID，避免覆盖或重复计费")
                if args.reset:
                    reset()
                options = {key: getattr(args, key) for key in OPTIONS}
                options.update(visitors_dir=args.visitors_dir or "data/visitors", dev=bool(args.dev),
                               mock=bool(args.mock), max_sessions=args.max_sessions or load_config()["concurrency"]["max_sessions"])
                manifest = create_manifest(eid)
            else:
                filename = f"experiment.{args.experiment}.json" if args.experiment else "experiment.json"
                path = VAR_DIR / "demo" / filename
                if not path.exists():
                    raise ValueError("找不到实验清单；请先执行 run1 或用 --experiment 指定已有实验")
                manifest = read_json(path)
                options = read_json(VAR_DIR / "demo" / manifest["experiment_id"] / "options.json")
                for key in OPTIONS:
                    if getattr(args, key) is not None and getattr(args, key) != options[key]:
                        raise ValueError(f"实验配置已冻结，不能改变 --{key.replace('_', '-')}")
                required = "run1" if args.cmd == "learn" else "evolution"
                target = "evolution" if args.cmd == "learn" else "run2"
                if manifest["stage"] == "failed" or manifest[required]["state"] != "done" or manifest[target]["state"] != "pending":
                    raise ValueError(f"不能执行 {args.cmd}：前置阶段未完成、已失败或本阶段已执行")
            print(f"experiment_id={manifest['experiment_id']}", flush=True)
            commands = ("run1", "learn", "run2") if args.cmd == "all" else (args.cmd,)
            asyncio.run(Experiment(manifest, options).execute(commands))
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        print(f"demo failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
