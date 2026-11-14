"""CLI for the evolve engine.

  python -m engine.evolve reset                 # 一键重置 var/playbook-repo 到 v0
  python -m engine.evolve status                # 当前版本、版本列表、提交历史
  python -m engine.evolve rollback v1           # 以新提交回到 v1（保留历史）
  python -m engine.evolve review-list <evolution_id>
  python -m engine.evolve veto <evolution_id> <change_id> [--comment ...] [--scores 1,2,3]
  python -m engine.evolve run --run-report R.json --evaluator pkg.mod:func [--feedback F.json]
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
from pathlib import Path

from . import review
from .config import load_config
from .pipeline import evolve
from .reflector import load_sessions, load_traces
from .repo import PlaybookRepo


def _load_evaluator(spec: str):
    module, _, attr = spec.partition(":")
    return getattr(importlib.import_module(module), attr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m engine.evolve")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("reset")
    sub.add_parser("status")
    p = sub.add_parser("rollback"); p.add_argument("version")
    p = sub.add_parser("review-list"); p.add_argument("evolution_id")
    p = sub.add_parser("veto"); p.add_argument("evolution_id"); p.add_argument("change_id")
    p.add_argument("--comment"); p.add_argument("--scores", help="safety,clinical,feasibility，各 1–5")
    p = sub.add_parser("run")
    p.add_argument("--run-report", type=Path, required=True)
    p.add_argument("--evaluator", required=True, help="module:function，签名 async (playbook_text, *, label) -> metrics")
    p.add_argument("--feedback", type=Path)
    p.add_argument("--baseline", type=Path, help="baseline_val_metrics JSON；缺省时现场评估上一代")
    p.add_argument("--visitors", type=Path, help="来访 JSON 目录（用于关键线索与防御型判定，可选）")
    args = parser.parse_args(argv)

    config = load_config()
    repo = PlaybookRepo(config)
    if args.cmd == "reset":
        print(f"已重置到 v0: {repo.reset_to_v0()}")
    elif args.cmd == "status":
        repo.init()
        print(json.dumps({"current": repo.current_version(), "versions": repo.versions(), "log": repo.log()},
                         ensure_ascii=False, indent=2))
    elif args.cmd == "rollback":
        print(f"已回到 {args.version}: {repo.rollback(args.version)}")
    elif args.cmd == "review-list":
        print((review.review_dir(config, args.evolution_id) / "review_request.json").read_text(encoding="utf-8"))
    elif args.cmd == "veto":
        scores = None
        if args.scores:
            s, c, f = (float(x) for x in args.scores.split(","))
            scores = {"safety": s, "clinical": c, "feasibility": f}
        print(review.submit(config, args.evolution_id, args.change_id, "reject", scores, args.comment))
    elif args.cmd == "run":
        report = json.loads(args.run_report.read_text(encoding="utf-8"))
        feedback = json.loads(args.feedback.read_text(encoding="utf-8")) if args.feedback else []
        baseline = json.loads(args.baseline.read_text(encoding="utf-8")) if args.baseline else None
        visitors = {}
        if args.visitors:
            for f in sorted(args.visitors.glob("*.json")):
                v = json.loads(f.read_text(encoding="utf-8"))
                visitors[v["id"]] = v
        base = args.run_report.parent
        result = asyncio.run(evolve(run_report=report, sessions=load_sessions(report, base),
                                    traces=load_traces(report, base), visitors=visitors,
                                    evaluator=_load_evaluator(args.evaluator), human_feedback=feedback,
                                    baseline_val_metrics=baseline, config=config, repo=repo))
        print(json.dumps({k: result[k] for k in ("evolution_id", "outcome", "from_version", "to_version", "chosen")},
                         ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
