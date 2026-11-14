"""Bounded real-agent regression, not an all-live performance benchmark."""
import asyncio
from collections import Counter
from contextvars import ContextVar
import hashlib
import json
from pathlib import Path
import sys
import time

# Reuse S2 read-only; engine/safety/contracts are from this worktree.
sys.path.append('/Users/zhangheqing/bohack/ds-integ')
from engine.config import load_dotenv
from engine.run import build_deps
from engine.session import SessionRunner
from engine.adapters_sim import S2VisitorSim, S2Screening, S2OutcomeModel
from engine.reporting import build_report
from engine.telemetry import CURRENT_CALL
from safety.layer import SafetyLayer
from safety.judges import MockJudge
from scoring.score import score_run
from contracts.validate import load_validators, validate_document

WHO = ContextVar('visitor', default='unknown')
OUT = Path('var/s3-fix1/live')


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str)+'\n')


async def main():
    OUT.mkdir(exist_ok=False)
    load_dotenv('/Users/zhangheqing/bohack/ds-safety/.env')
    visitors = [json.loads(Path(f'/Users/zhangheqing/bohack/ds-integ/sim/visitors/sample-{i:03}.json').read_text()) for i in [1, 2, 7]]
    config = {'round_turn_cap': {1:1,2:1}, 'pipeline': {'merge_strategy_response':True},
              'path_classifier': {'provider':'mock'}}
    deps = build_deps(config=config, sim=S2VisitorSim(), screening=S2Screening(), outcome=S2OutcomeModel(),
                      safety=SafetyLayer(judge=MockJudge()))
    assert deps.llm.model_name == 'deepseek-flash'
    requests = []
    original = deps.llm.client.chat.completions.create
    async def bounded(**kwargs):
        if len(requests) >= 28:
            raise RuntimeError('Task real-call budget exhausted')
        row = {'visitor_id': WHO.get(), 'task': CURRENT_CALL.get()['task'],
               'max_tokens': kwargs.get('max_tokens'), 'status':'started'}
        requests.append(row)
        write(OUT/'requests.json', requests)
        try:
            result = await original(**kwargs)
            row.update(status='ok', finish_reason=result.choices[0].finish_reason)
            return result
        except BaseException as exc:
            row.update(status='error', error_type=type(exc).__name__)
            raise
        finally:
            write(OUT/'requests.json', requests)
    deps.llm.client.chat.completions.create = bounded
    write(OUT/'manifest.json', {'scope':'real agent; S2 deterministic renderer, mock path classifier and safety judge; 1 action per round; merged',
        'config':deps.config, 'probe_calls_before_run':2, 'remaining_real_call_limit':28,
        'source_sha256': {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path('engine').rglob('*')) if p.is_file() and p.suffix in ('.py','.md','.yaml')}})
    async def one(visitor):
        token = WHO.set(visitor['id'])
        started = time.perf_counter()
        try:
            runner = SessionRunner(deps, visitor, 's3-fix1-live')
            session, trace = await runner.run()
            trace['wall_s'] = round(time.perf_counter()-started, 3)
            trace['s2_replies'] = runner.sim_memory.get('_s2_replies',[])
            write(OUT/'sessions'/f"{visitor['id']}.json",session)
            write(OUT/'trace'/f"{visitor['id']}.json",trace)
            print(visitor['id'],session['status'],trace['wall_s'], 'fallbacks', len(trace['fallbacks']), flush=True)
            return session,trace
        finally:
            WHO.reset(token)
    started = time.perf_counter()
    try:
        results = await asyncio.gather(*(one(v) for v in visitors))
    finally:
        await deps.llm.aclose()
    by_id = {v['id']:v for v in visitors}
    report, summary = build_report(by_id, results, scorer=score_run, run_id='s3-fix1-live',
        label='S3 真实 agent 短会谈回归', role='validation', split='sample', playbook_version='v0',
        models={'agent':deps.llm.model_name,'visitor':deps.sim.model_name,'judge':'mock'}, duration_s=time.perf_counter()-started)
    validators = load_validators()
    errors={}
    for session,_ in results:
        found=validate_document(session,'session',validators,by_id)
        if found: errors[session['visitor_id']]=found
    if report is not None:
        write(OUT/'run_report.json', report)
        found=validate_document(report,'run_report',validators,by_id)
        if found: errors['report']=found
    summary.update(real_requests=len(requests), task_real_requests=len(requests)+2,
        validation_errors=errors, real_finish_reasons=dict(Counter(r.get('finish_reason','unavailable') for r in requests)),
        sessions=[{'id':s['visitor_id'],'status':s['status'],'wall_s':t['wall_s'],
                   'fallbacks':t['fallbacks'],'finish_reasons':dict(Counter(r.get('finish_reason','unavailable') for r in requests if r['visitor_id']==s['visitor_id']))} for s,t in results])
    write(OUT/'summary.json', summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)

asyncio.run(main())
