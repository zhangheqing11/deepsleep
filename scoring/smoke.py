"""端到端冒烟：N 个样例来访 → 模拟来访（默认强制 mock）→ 会谈 agent（默认 stub）→ 计分 → 契约校验。

    python -m scoring.smoke                 # 10 个来访 + mock LLM + stub agent（make smoke）
    python -m scoring.smoke --n 18 --llm    # 允许用 .env 里的 ds flash 给模拟来访措辞
    python -m scoring.smoke --agent engine.session:run_session   # S3 落地后接入真引擎

输出写到 var/smoke/<run_id>/（var/ 不入库）：visitor 不复制，session.<id>.json、run_report.json。
任何文件不过契约校验 → 退出码 1。
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import sys
import time
from pathlib import Path

from contracts.validate import load_validators, validate_document
from scoring.score import score_run
from sim.llm import client_from_env
from sim.visitor_sim import SimVisitor

REPO_ROOT = Path(__file__).resolve().parents[1]
VISITOR_DIR = REPO_ROOT / 'sim' / 'visitors'


def load_visitors(directory: Path = VISITOR_DIR, n: int | None = None) -> list[dict]:
    paths = sorted(directory.glob('*.json'))
    visitors = [json.loads(p.read_text(encoding='utf-8')) for p in paths]
    return visitors[:n] if n else visitors


def load_agent(spec: str):
    if spec == 'stub':
        spec = 'sim.stub_agent:run_session'
    module, _, func = spec.partition(':')
    return getattr(importlib.import_module(module), func)


async def run_all(visitors, agent, *, run_id, playbook_version, use_llm, concurrency=50):
    sem = asyncio.Semaphore(concurrency)

    async def one(visitor):
        async with sem:
            sim = SimVisitor(visitor, client_from_env(force_mock=not use_llm))
            return await agent(visitor, sim, run_id=run_id, playbook_version=playbook_version)

    return await asyncio.gather(*(one(v) for v in visitors))


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--n', type=int, default=10)
    parser.add_argument('--agent', default='stub')
    parser.add_argument('--llm', action='store_true', help='允许模拟来访调用 ds flash（缺 key 自动降级 mock）')
    parser.add_argument('--run-id', default='smoke-0001')
    parser.add_argument('--playbook-version', default='v0')
    parser.add_argument('--out', type=Path, default=REPO_ROOT / 'var' / 'smoke')
    args = parser.parse_args(argv)

    visitors = load_visitors(n=args.n)
    by_id = {v['id']: v for v in visitors}
    agent = load_agent(args.agent)
    started = time.monotonic()
    sessions = asyncio.run(run_all(visitors, agent, run_id=args.run_id,
                                   playbook_version=args.playbook_version, use_llm=args.llm))
    out = args.out / args.run_id
    out.mkdir(parents=True, exist_ok=True)
    refs = {}
    for s in sessions:
        name = f'session.{s["visitor_id"]}.json'
        write_json(out / name, s)
        refs[s['visitor_id']] = name
    report = score_run(
        by_id, sessions, run_id=args.run_id, label='冒烟测试', role='validation',
        split=visitors[0]['split'], playbook_version=args.playbook_version,
        models={'agent': sessions[0]['models']['agent'], 'visitor': sessions[0]['models']['visitor'],
                'judge': 'stub-rules'},
        duration_s=time.monotonic() - started, session_refs=refs)
    write_json(out / 'run_report.json', report)

    validators = load_validators()
    failed = 0
    docs = [('visitor', v['id'], v) for v in visitors]
    docs += [('session', s['visitor_id'], s) for s in sessions]
    docs += [('run_report', args.run_id, report)]
    for kind, ident, doc in docs:
        errors = validate_document(doc, kind, validators, by_id)
        if errors:
            failed += 1
            print(f'FAIL {kind} {ident}: {"; ".join(errors)}')
    m = report['metrics']
    print(f'smoke: {len(visitors)} visitors, {len(docs) - failed}/{len(docs)} docs valid, '
          f'out={out.relative_to(REPO_ROOT) if out.is_relative_to(REPO_ROOT) else out}')
    print(f'  isi_response_rate={m["isi_response_rate"]:.2f} path_acc r1/r2={m["path_acc_r1"]:.2f}/'
          f'{m["path_acc_r2"]:.2f} referral recall/precision={m["referral_recall"]}/'
          f'{m["referral_precision"]} screening_coverage={m["screening_coverage"]} '
          f'crisis_missed={m["crisis_missed"]} veto={report["veto"]["passed"]}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
