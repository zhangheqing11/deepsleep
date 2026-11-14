"""Bounded real-API evolution experiment; all runtime evidence stays under var/.

Run as python -m analysis.evo_trial --id UNIQUE --repo-mode git|snapshot.
--baseline-only runs ds_thinking/r0 without any version-store mutation.
--resume reuses completed batches, never repeats an unfinished billed batch.
Git mode is solely for explicitly authorized independent runtime repositories.
"""
from __future__ import annotations
import argparse
import asyncio
from collections import Counter
from contextlib import ExitStack
from contextvars import ContextVar
from dataclasses import asdict, replace
from datetime import datetime
import difflib
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import time
from types import SimpleNamespace
from unittest.mock import patch

from contracts.validate import compute_metrics, load_validators, validate_document
from engine.config import load_dotenv
from engine.integ_trial import Meter, RequestBudget, RequestBudgetExceeded, VISITOR, COMPONENT, write_json
from engine.run import build_deps
from engine.session import SessionRunner
from engine.playbook import Playbook, parse_sections
from engine.reporting import build_report
from engine.adapters_sim import S2RendererClient, S2VisitorSim, S2Screening, S2OutcomeModel
from engine.evolve.config import load_config as evolve_config
from engine.evolve.pipeline import evolve
from engine.evolve.repo import PlaybookRepo
from engine.evolve.evidence import run_evidence
from engine.evolve.playbook import Playbook as EditablePlaybook
from scoring.score import score_run, veto as score_veto
from scoring.smoke import load_visitors
from sim.llm import DsConfig

ROOT = Path(__file__).resolve().parents[1]
STAGE = ContextVar('trial_stage', default='startup')
TRACKS = ('ds_thinking', 'ds_nothink', 'jev')
METRICS = ('isi_response_rate', 'mean_isi_change', 'path_acc_r1', 'path_acc_r2',
           'path_acc_gain', 'referral_recall', 'referral_precision', 'screening_coverage',
           'crisis_missed', 'crisis_recall', 'contraindication_violations', 'veto_passed')


def now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def read(path):
    return json.loads(Path(path).read_text())


def log(message):
    print(f'{now()} {message}', flush=True)


class TrialMeter(Meter):
    """Count every HTTP attempt before sending, with no URL, key or body logging."""
    def __init__(self, budget, out):
        super().__init__(budget)
        self.out = out

    def watch_http(self, client_type):
        original = client_type.send
        async def send(client, request, *args, **kwargs):
            try:
                self.budget.reserve()
            except RequestBudgetExceeded:
                self.budget_blocked += 1
                raise
            row = {'stage': STAGE.get(), 'visitor_id': VISITOR.get(),
                   'component': COMPONENT.get(), 'status': 'started', 'at': now()}
            self.http.append(row)
            with (self.out / 'http-starts.jsonl').open('a') as stream:
                stream.write(json.dumps(row) + '\n')
            started = time.perf_counter()
            try:
                response = await original(client, request, *args, **kwargs)
                row['http_status'] = response.status_code
                row['status'] = 'ok' if response.status_code < 400 else 'http_error'
                return response
            except asyncio.CancelledError:
                row['status'] = 'cancelled'
                raise
            except Exception as exc:
                row['status'] = 'error'
                row['error_type'] = type(exc).__name__
                raise
            finally:
                row['ms'] = round((time.perf_counter()-started)*1000, 3)
                with (self.out / 'http-results.jsonl').open('a') as stream:
                    stream.write(json.dumps(row) + '\n')
        return patch.object(client_type, 'send', send)


class EffortClient:
    """Only adds the unexposed classifier reasoning_effort constructor argument."""
    def __init__(self, client, effort):
        self.client, self.effort = client, effort
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        kwargs['reasoning_effort'] = self.effort
        return await self.client.chat.completions.create(**kwargs)

    async def close(self):
        await self.client.close()


class SnapshotRepo:
    """Optional no-git storage; SHA is a content digest, never a git commit."""
    def __init__(self, config):
        self.path = Path(config['repo']['path'])
        self.v0 = Path(config['repo']['v0_path'])

    def init(self):
        if not (self.path / 'VERSION').exists():
            self.path.mkdir(parents=True, exist_ok=True)
            self._save(self.v0.read_text(), 'v0')
        return hashlib.sha256(self.read().encode()).hexdigest()

    def _save(self, text, version):
        (self.path / f'{version}.md').write_text(text)
        (self.path / 'playbook.md').write_text(text)
        (self.path / 'VERSION').write_text(version)

    def current_version(self):
        return (self.path / 'VERSION').read_text().strip()

    def read(self):
        return (self.path / 'playbook.md').read_text()

    def commit_version(self, text, summary):
        version = f'v{int(self.current_version()[1:])+1}'
        self._save(text, version)
        return version, hashlib.sha256(text.encode()).hexdigest()


def deps_for(track, meter):
    override = {} if track == 'jev' else {'path_classifier': {
        'provider': 'ds_flash', 'thinking': 'enabled' if track == 'ds_thinking' else 'disabled'}}
    client = S2RendererClient(DsConfig(os.environ['DS_BASE_URL'], os.environ['DS_API_KEY'], os.environ['DS_MODEL']))
    deps = build_deps(config=override, sim=S2VisitorSim(client), screening=S2Screening(), outcome=S2OutcomeModel())
    if track == 'ds_thinking':
        deps.classifier.client = EffortClient(deps.classifier.client, 'high')
    assert deps.llm.model_name != 'mock' and 'mock' not in deps.classifier.provider
    assert [j.provider for j in deps.safety.judge.judges] == ['ds_flash', 'jev']
    meter.wrap(deps.llm, 'complete_json', 'agent')
    meter.wrap(deps.classifier, 'classify', 'classifier')
    if hasattr(deps.classifier, 'primary'):
        meter.wrap(deps.classifier.primary, 'classify', 'classifier.jev')
        meter.wrap(deps.classifier.fallback, 'classify', 'classifier.ds_flash')
    meter.wrap(client, 'complete', 'visitor')
    for judge in deps.safety.judge.judges:
        meter.wrap(judge, 'classify', f'judge.{judge.provider}')
    return deps


async def close_deps(deps):
    objects = [deps.llm, deps.sim.client._client]
    if hasattr(deps.classifier, 'aclose'):
        objects.append(deps.classifier)
    else:
        objects.append(deps.classifier.client)
    # The default safety judges manage their own per-request clients.
    for obj in objects:
        close = getattr(obj, 'aclose', None) or getattr(obj, 'close', None)
        if close:
            await close()


def rich_load(out, visitors):
    return {'metrics': read(out/'run_report.json')['metrics'],
            'per_visitor': read(out/'run_report.json')['per_visitor'],
            'sessions': {v['id']: read(out/'sessions'/f"{v['id']}.json") for v in visitors},
            'traces': {v['id']: read(out/'trace'/f"{v['id']}.json") for v in visitors},
            'visitors': {v['id']: v for v in visitors}}


async def batch(deps, visitors, text, version, out, stage, meter, sem, baseline=None):
    if (out/'done.json').exists():
        if not read(out/'summary.json')['accounting']['evaluation_complete']:
            raise RuntimeError('Cached incomplete evaluation')
        return rich_load(out, visitors)
    if out.exists():
        raise RuntimeError('Refusing to repeat an unfinished billed batch: '+str(out))
    out.mkdir(parents=True)
    (out/'playbook.md').write_text(text)
    write_json(out/'start.json', {'stage': stage, 'started_at': now(), 'version': version})
    current = replace(deps, playbook=Playbook(version, text, parse_sections(text)))
    token = STAGE.set(stage)
    started = time.perf_counter()
    async def one(v):
        async with sem:
            if meter.budget_blocked:
                raise RequestBudgetExceeded('Budget exhausted')
            vt = VISITOR.set(v['id'])
            t = time.perf_counter()
            try:
                runner = SessionRunner(current, v, stage)
                session, trace = await runner.run()
                trace['s2_replies'] = runner.sim_memory.get('_s2_replies', [])
                trace['all_judge_results'] = [asdict(r) for r in runner.safety_state.judge_results]
                trace['wall_s'] = time.perf_counter()-t
                write_json(out/'sessions'/f"{v['id']}.json", session)
                write_json(out/'trace'/f"{v['id']}.json", trace)
                return session, trace
            finally:
                VISITOR.reset(vt)
    try:
        results = await asyncio.gather(*(one(v) for v in visitors))
        wall = time.perf_counter()-started
        byid = {v['id']: v for v in visitors}
        report, accounting = build_report(byid, results, scorer=score_run, run_id=stage,
            label=stage, role='validation', split='sample', playbook_version=version,
            models={'agent': deps.llm.model_name, 'visitor': deps.sim.model_name, 'judge': deps.safety.judge.provider},
            duration_s=wall, session_refs={v['id']: f"sessions/{v['id']}.json" for v in visitors}, baseline=baseline)
        if meter.budget_blocked:
            accounting.update(evaluation_complete=False, incomplete_reason='request_budget_exhausted')
            if report:
                report['veto']['passed'] = False
        errors = {}
        validators = load_validators()
        for kind, docs in [('session', [s for s,t in results]), ('run_report', [report] if report else [])]:
            for i, doc in enumerate(docs):
                e = validate_document(doc, kind, validators, byid)
                if e:
                    errors[f'{kind}:{i}'] = e
        if report:
            write_json(out/'run_report.json', report)
        rows = [r for r in meter.http if r['stage'] == stage]
        summary = {'wall_s': wall, 'version': version, 'http_attempts': len(rows),
                   'http_statuses': dict(Counter(r['status'] for r in rows)),
                   'accounting': accounting, 'validation_errors': errors}
        write_json(out/'summary.json', summary)
        log(f'{stage}: {wall:.1f}s HTTP={len(rows)} scored={accounting["scored"]}/{len(visitors)} metrics={report["metrics"] if report else None}')
        if not report or not accounting['evaluation_complete'] or meter.budget_blocked:
            raise RuntimeError('Incomplete live evaluation: '+stage)
        rich = rich_load(out, visitors)
        write_json(out/'insights.json', run_evidence(rich['per_visitor'], rich['sessions'], rich['traces'], byid))
        write_json(out/'done.json', {'finished_at': now()})
        return rich
    finally:
        STAGE.reset(token)


async def experiment(args):
    load_dotenv('/Users/zhangheqing/bohack/ds-safety/.env')
    if not all(os.getenv(k, '').strip() for k in ('DS_API_KEY','DS_BASE_URL','DS_MODEL','TYPESAFE_API_KEY')):
        raise RuntimeError('Required live API configuration missing')
    out = ROOT/'var'/'evo-trial'/args.id
    if out.exists() and not args.resume:
        raise RuntimeError('Existing trial; use --resume, no automatic billed reruns')
    out.mkdir(parents=True, exist_ok=True)
    visitors = load_visitors(n=18)
    assert [v['id'] for v in visitors] == [f'sample-{i:03d}' for i in range(1,19)]
    manifest_path = out/'manifest.json'
    if not manifest_path.exists():
        source_paths = sorted(p for d in ('engine','sim','safety','contracts','scoring','domain')
                              for p in (ROOT/d).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
        write_json(manifest_path, {'started_at': now(), 'id': args.id, 'budget': args.budget,
            'head': subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip(),
            'source_sha256': hashlib.sha256(b''.join(str(p.relative_to(ROOT)).encode()+b'\0'+p.read_bytes() for p in source_paths)).hexdigest(),
            'anthropic_key_present': bool(os.getenv('ANTHROPIC_API_KEY','').strip()),
            'ds_model': os.environ['DS_MODEL'], 'A': [v['id'] for v in visitors[:10]],
            'C': [v['id'] for v in visitors[10:]], 'repo_mode': args.repo_mode,
            'same_A_reused': True, 'bootstrap_seed': 20261114, 'bootstrap_replicates': 10000})
    log('startup: '+json.dumps({k:v for k,v in read(manifest_path).items() if k in ('head','anthropic_key_present','ds_model','budget')},ensure_ascii=False))
    if read(manifest_path)['budget'] != args.budget:
        raise RuntimeError('Cannot change frozen budget')
    meter = TrialMeter(RequestBudget(out/'request-budget.log', args.budget), out)
    import httpx
    import httpx2
    try:
        with ExitStack() as stack:
            stack.enter_context(meter.watch_http(httpx.AsyncClient))
            stack.enter_context(meter.watch_http(httpx2.AsyncClient))
            for track in TRACKS:
                track_out = out/track
                if (track_out/'done.json').exists():
                    continue
                t = time.perf_counter()
                track_out.mkdir(exist_ok=True)
                deps = deps_for(track, meter)
                sem = asyncio.Semaphore(deps.config['concurrency']['max_sessions'])
                write_json(track_out/'config.json', {'engine': deps.config, 'safety': deps.safety.config,
                    'classifier_effort': 'high' if track == 'ds_thinking' else None})
                try:
                    v0 = (ROOT/'engine/playbook_v0.md').read_text()
                    await batch(deps, visitors[:10], v0, 'v0', track_out/'r0', f'{args.id}-{track}-r0', meter, sem)
                    if args.baseline_only:
                        return
                    config = evolve_config({'repo': {'path': str(track_out/'playbook-repo')},
                                            'review': {'run_dir': str(track_out/'evolve')}})
                    config['repo']['v0_path'] = str(ROOT/'engine/playbook_v0.md')
                    write_json(track_out/'evolve-config.json', config)
                    repo = PlaybookRepo(config) if args.repo_mode == 'git' else SnapshotRepo(config)
                    repo.init()
                    for generation in (1,2):
                        evo_id = f'g{generation}'
                        evo_dir = track_out/'evolve'/evo_id
                        previous = track_out/f'r{generation-1}'
                        source = rich_load(previous, visitors[:10])
                        if not (evo_dir/'evolution.json').exists():
                            before = repo.read()
                            version = repo.current_version()
                            async def evaluator(playbook_text, *, label):
                                return await batch(deps, visitors[10:], playbook_text, version,
                                    track_out/f'C-g{generation}'/label, f'{args.id}-{track}-g{generation}-C-{label}', meter, sem)
                            et = STAGE.set(f'{args.id}-{track}-g{generation}-reflect')
                            ct = COMPONENT.set('reflector')
                            e_start = time.perf_counter()
                            try:
                                evolution, insights = await evolve(run_report=read(previous/'run_report.json'),
                                    sessions=source['sessions'], traces=source['traces'], visitors=source['visitors'],
                                    evaluator=evaluator, config=config, repo=repo, evolution_id=evo_id, return_insights=True)
                            finally:
                                COMPONENT.reset(ct)
                                STAGE.reset(et)
                            if evolution['commit']:
                                write_json(evo_dir/'storage.json', {'actual_repo': str(repo.path.relative_to(ROOT)),
                                    'repo_mode': args.repo_mode, 'sha_kind': 'git_commit' if args.repo_mode == 'git' else 'content_sha256',
                                    'note': 'evolution.commit.repo is the frozen schema logical path, not this trial physical directory'})
                            write_json(evo_dir/'trial-metadata.json', {'wall_s': time.perf_counter()-e_start,
                                'repo_mode': args.repo_mode, 'actual_version': repo.current_version()})
                            for c in evolution['candidates']:
                                pb = EditablePlaybook.parse(before)
                                for change in c['changes']:
                                    pb.apply(change)
                                (evo_dir/f"{c['id']}.diff").write_text(''.join(difflib.unified_diff(
                                    before.splitlines(True),pb.render().splitlines(True),fromfile=version,tofile=c['id'])))
                            (evo_dir/'adopted.diff').write_text(evolution['diff'] or '')
                            log(f'{track} {evo_id}: outcome={evolution["outcome"]}, chosen={evolution["chosen"]}, reflector={evolution["reflector"]}')
                        await batch(deps, visitors[:10], repo.read(), repo.current_version(),
                                    track_out/f'r{generation}', f'{args.id}-{track}-r{generation}', meter, sem,
                                    baseline=read(previous/'run_report.json'))
                    write_json(track_out/'done.json', {'finished_at': now(), 'process_wall_s': time.perf_counter()-t})
                finally:
                    await close_deps(deps)
            write_json(out/'done.json', {'finished_at': now()})
    except Exception as exc:
        # Never serialize provider exception messages (could include credentials).
        write_json(out/'stopped.json', {'at': now(), 'error_type': type(exc).__name__,
                                      'budget_blocked': meter.budget_blocked})
        log('stopped: '+type(exc).__name__)
        raise
    finally:
        write_json(out/'calls-current-process.json', {'logical': meter.calls, 'http': meter.http})
        write_json(out/'accounting.json', {'attempts': len((out/'request-budget.log').read_text().splitlines())
                   if (out/'request-budget.log').exists() else 0, 'limit': args.budget, 'budget_blocked': meter.budget_blocked})


def scalar_metrics(rows, sessions, baseline=None):
    values = compute_metrics(rows)
    values['veto_passed'] = int(score_veto(values, sessions, {'metrics': baseline} if baseline else None)['passed'])
    return {k: values[k] for k in METRICS}


def derivative_statistics(track_out, replicates=10000, seed=20261114):
    reports = [read(track_out/f'r{i}'/'run_report.json') for i in range(3)]
    maps = [{r['visitor_id']: r for r in report['per_visitor']} for report in reports]
    ids = sorted(set.intersection(*(set(m) for m in maps)))
    sessions = [{vid: read(track_out/f'r{i}'/'sessions'/f'{vid}.json') for vid in ids} for i in range(3)]
    def calculate(sample):
        ms = []
        for i in range(3):
            ms.append(scalar_metrics([maps[i][vid] for vid in sample], [sessions[i][vid] for vid in sample], ms[-1] if ms else None))
        return {k: [None if ms[i][k] is None or ms[i+1][k] is None else ms[i+1][k]-ms[i][k] for i in range(2)]
                + [None if any(m[k] is None for m in ms) else ms[2][k]-2*ms[1][k]+ms[0][k]] for k in METRICS}
    point = calculate(ids)
    rng = random.Random(seed)
    draws = {k: [[],[],[]] for k in METRICS}
    for _ in range(replicates):
        values = calculate([rng.choice(ids) for _ in ids])
        for k, ds in values.items():
            for i, value in enumerate(ds):
                if value is not None:
                    draws[k][i].append(value)
    def quantile(values, p):
        values = sorted(values)
        if not values:
            return None
        x = (len(values)-1)*p
        lo = int(x)
        return values[lo]+(values[min(lo+1,len(values)-1)]-values[lo])*(x-lo)
    result = {'n_paired': len(ids), 'visitor_ids': ids, 'seed': seed, 'replicates': replicates,
              'metrics': {k: {name: {'estimate': point[k][i], 'ci95': [quantile(draws[k][i],.025),quantile(draws[k][i],.975)],
                                   'valid_replicates': len(draws[k][i])}
                              for i,name in enumerate(('d10','d21','d2'))} for k in METRICS}}
    write_json(track_out/'derivatives.json', result)
    return result


def fmt(value):
    if value is None:
        return 'NA'
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return '0' if abs(value)<0.00005 else f'{value:.4f}'.rstrip('0').rstrip('.')
    return str(value).replace('|',' / ').replace('\n',' ')


def table(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |', '| '+' | '.join(['---']*len(headers))+' |']+
                     ['| '+' | '.join(fmt(x) for x in row)+' |' for row in rows])+'\n'


def plot_trial(out):
    """Static export; optional plotting dependencies are isolated under ignored var/."""
    import sys
    sys.path.insert(0, str(ROOT/'var/evo-viz-deps'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font_path='/System/Library/Fonts/Supplemental/Arial Unicode.ttf'
    if Path(font_path).exists():
        font_manager.fontManager.addfont(font_path)
        plt.rcParams['font.family']=font_manager.FontProperties(fname=font_path).get_name()
    plt.rcParams['axes.unicode_minus']=False
    colors=('#0072B2','#D55E00','#009E73')
    target=out/'plots'
    target.mkdir(exist_ok=True)
    for track in TRACKS:
        fig, axes=plt.subplots(2,2,figsize=(12,8),sharex='col')
        for i in range(3):
            p=out/track/f'r{i}'/'insights.json'
            if not p.exists():
                continue
            ev=read(p)['summary']['by_step']
            ver=read(out/track/f'r{i}'/'summary.json')['version']
            for rnd in (1,2):
                points=[x for x in ev if x['round']==rnd]
                for j,(metric,title,limit) in enumerate((('mean_p_true','正确路径平均权重',1),('mean_entropy','平均熵（bits）',2.322))):
                    ax=axes[j,rnd-1]
                    xs=[p['step'] for p in points]
                    ys=[p[metric] for p in points]
                    ax.plot(xs,ys,marker=('o','s','^')[i],color=colors[i],label=f'r{i}（{ver}）',linewidth=1.8)
                    for x,y,pnt in zip(xs,ys,points):
                        ax.annotate(str(pnt['n']),(x,y),xytext=(3,(-10-i*9) if y>limit*.8 else (5+i*9)),textcoords='offset points',fontsize=7,color=colors[i])
                    ax.set_ylim(0,limit)
                    ax.set_xticks(range(1, max(xs,default=4)+1))
                    ax.set_title(f'会谈第 {rnd} 轮 · {title}')
                    ax.set_xlabel('本轮第 k 个有效分类步骤')
                    ax.spines[['top','right']].set_visible(False)
                    ax.grid(alpha=.2)
                    ax.legend(fontsize=8)
        fig.suptitle(f'{track}：三次运行的分类器证据',fontsize=16)
        fig.text(.5,.01,'点旁数字为来访数 n；仅采用 status=ok；缺失不补零；有效步骤不等于相同实际回合。',ha='center',fontsize=10)
        fig.tight_layout(rect=[0,.04,1,.95])
        fig.savefig(target/f'{track}-curves.png',dpi=160)
        fig.savefig(target/f'{track}-curves.svg')
        plt.close(fig)
    fig,ax=plt.subplots(figsize=(8,5))
    for i,track in enumerate(TRACKS):
        vals=[]
        for g in range(3):
            p=out/track/f'r{g}'/'run_report.json'
            vals.append(read(p)['metrics']['isi_response_rate']*100 if p.exists() else float('nan'))
        ax.plot(range(3),vals,color=colors[i],marker=('o','s','^')[i],label=track,linewidth=2)
    ax.set(xticks=range(3),xticklabels=['r0','r1','r2'],ylim=(0,100),ylabel='模拟 ISI 有效率（%）',title='三轨道：同一 A 组的三次运行')
    ax.spines[['top','right']].set_visible(False)
    ax.legend()
    ax.grid(alpha=.2)
    fig.tight_layout()
    fig.savefig(target/'isi-comparison.png',dpi=160)
    fig.savefig(target/'isi-comparison.svg')
    plt.close(fig)
    return target


def report_trial(trial_id, report_path):
    out = ROOT/'var'/'evo-trial'/trial_id
    manifest = read(out/'manifest.json')
    # Retain the frozen schema's logical repo constant; actual storage is a sidecar.
    # This also normalizes early trial output from the original orchestration revision.
    for ep in out.glob('*/evolve/*/evolution.json'):
        evo=read(ep)
        if evo['commit']:
            actual=ep.parents[2]/'playbook-repo'
            write_json(ep.parent/'storage.json', {'actual_repo': str(actual.relative_to(ROOT)),
                'repo_mode': manifest['repo_mode'], 'sha_kind': 'git_commit' if manifest['repo_mode']=='git' else 'content_sha256'})
            if evo['commit']['repo'] != 'var/playbook-repo':
                evo['commit']['repo']='var/playbook-repo'
                write_json(ep,evo)
    plot_dir = plot_trial(out)
    starts = [json.loads(s) for s in (out/'http-starts.jsonl').read_text().splitlines()]
    results = [json.loads(s) for s in (out/'http-results.jsonl').read_text().splitlines()]
    attempts = len((out/'request-budget.log').read_text().splitlines())
    lines = [f'# 真实 API 两代进化 × 三种路径分类器实测\n',
             f'实验 `{trial_id}`；开始 {manifest["started_at"]}；报告生成 {now()}。代码提交 `{manifest["head"]}`（detached）；来源 SHA256 `{manifest["source_sha256"]}`。',
             f'原始产物：[实验目录]({out})；脚本：[evo_trial.py]({ROOT/"analysis/evo_trial.py"})。HTTP 请求发送前计数 **{attempts}/15000**；账本、开始记录、完成记录分别为 {attempts}、{len(starts)}、{len(results)} 条。含失败、重试、超时和取消，不等于服务商账单。',
             'A=sample-001…010（10 人），C=sample-011…018（8 人）。三轨道顺序执行；每轨道共用引擎默认 50 场会谈、32 个 agent/DS 分类器在途上限；S4 的 C 基线与候选并行运行。A 在 r0/r1/r2 复用，C 每次门禁重新实跑。',
             '运行 JSON 保留入口的 role=validation、split=sample；本报告 A/C 指 manifest 中固定的 ID 分组，C 门禁实际使用 sample-011…018。',
             'A 的主路径 P1–P5 各 2 人；转介 R0/R1/R2/R3=4/2/1/3；危机 none/passive/active=8/1/1。C 的主路径 P1/P2/P3/P4/P5=2/2/2/1/1；转介 R0/R1/R2/R3=5/1/1/1；8 人均为 crisis=none。',
             'r0/r1/r2 是运行序号；实际 playbook 版本另列，未晋级时沿用上一版本。路径 path_acc_r1/r2 分别表示会谈第 1/2 轮，path_acc_gain 是两轮准确率之差。',
             'ds_thinking 发送 thinking.type=enabled 与 reasoning_effort=high；ds_nothink 发送 thinking.type=disabled；jev 使用 main 的 Jev→DS 回退链。各轨道分类器超时均为默认 6 秒。其余组件采用 main 默认配置（agent max_retries=2、动作上限 4/3、强制筛查与再核验不变）。',
             f'启动时 ANTHROPIC_API_KEY 是否非空：{manifest["anthropic_key_present"]}；DS_MODEL={manifest["ds_model"]}。逐代实际反思器及降级原因如下。审核只针对 high 改动，原配置等待 120 秒、timeout_policy=pass，无人工审核响应。',
             '指标比率均以 0–1 表示；差分为比率差（乘 100 得百分点），ISI 平均变化单位为分，crisis_missed/contraindication_violations 单位为例；veto_passed 编码 true=1、false=0。',
             '## 三轨道运行指标与资源\n', f'![三轨道 ISI 曲线]({plot_dir/"isi-comparison.png"})']
    metric_names = list(METRICS[:-1])
    overview, resources = [], []
    for track in TRACKS:
        td = out/track
        for i in range(3):
            rd = td/f'r{i}'
            if not (rd/'run_report.json').exists():
                continue
            r,s = read(rd/'run_report.json'),read(rd/'summary.json')
            overview.append([track,f'r{i}',r['playbook_version'],r['n_visitors']]+[r['metrics'][k] for k in metric_names]+[r['veto']['passed']])
        batches = list(td.glob('r*/summary.json'))+list(td.glob('C-g*/*/summary.json'))
        batch_seconds = sum(read(p)['wall_s'] for p in batches)
        calls = [r for r in starts if f'-{track}-' in r['stage']]
        finished = read(td/'done.json')['finished_at'] if (td/'done.json').exists() else None
        first = read(td/'r0'/'start.json')['started_at'] if (td/'r0'/'start.json').exists() else None
        elapsed = (datetime.fromisoformat(finished)-datetime.fromisoformat(first)).total_seconds() if finished and first else None
        resources.append([track, bool(finished), elapsed, batch_seconds, len(calls), len(batches),
                          sum(read(p)['accounting']['error_count'] for p in batches),
                          sum(read(p)['accounting']['degraded_sessions'] for p in batches)])
    lines += [table(['轨道','运行','实际版本','可评分 n']+metric_names+['veto'], overview),
              table(['轨道','完成','墙钟秒（含审核）','批次秒之和（并行有重叠）','HTTP次数','完成批次数','error会谈','agent降级会谈'],resources),
              '墙钟包含初次基线后可能的编排暂停；每批纯执行时间另列。未改变版本的重复运行差异包含模型/API/模拟来访的波动。',
              table(['轨道','阶段','HTTP次数','批次秒','可评分/尝试','完整评估','契约错误项'],
                    [[track,str(p.parent.relative_to(out/track)),read(p)['http_attempts'],read(p)['wall_s'],
                      f"{read(p)['accounting']['scored']}/{read(p)['accounting']['attempted']}",
                      read(p)['accounting']['evaluation_complete'],len(read(p)['validation_errors'])]
                     for track in TRACKS for p in sorted(list((out/track).glob('r*/summary.json'))+list((out/track).glob('C-g*/*/summary.json')))])]
    lines += ['HTTP 结果按轨道与组件汇总（包含门禁、反思和 A 组）：', table(['轨道','组件','HTTP次数','成功','连接/其他错误','取消','HTTP错误'], [[track,comp,len(rs),sum(r['status']=='ok' for r in rs),sum(r['status']=='error' for r in rs),sum(r['status']=='cancelled' for r in rs),sum(r['status']=='http_error' for r in rs)] for track in TRACKS for comp in sorted({r['component'] for r in results if f'-{track}-' in r['stage']}) for rs in [[r for r in results if f'-{track}-' in r['stage'] and r['component']==comp]]])]
    for track in TRACKS:
        td = out/track
        lines += [f'## {track}\n']
        if all((td/f'r{i}'/'done.json').exists() for i in range(3)):
            stats = derivative_statistics(td)
            lines += [f'按来访配对自助法：三次运行的共同可评分来访 n={stats["n_paired"]}，seed={stats["seed"]}，10,000 次有放回重采样；每次同一组来访索引同时用于三次运行并重算指标。95% 区间采用百分位法。转介/筛查分母为零的重复样本不定义比率，相应差分不计入区间；有效重复数单列。veto 每次按 scorer 重算，包括相对上一运行转介召回约束。区间仅反映该批来访重采样，不覆盖 API 重复运行或候选选择不确定性。',
                      table(['指标','r1−r0 [95%区间]','r2−r1 [95%区间]','二阶差分 [95%区间]','有效重复数 d10/d21/d2'],
                            [[k]+[f"{fmt(stats['metrics'][k][d]['estimate'])} [{fmt(stats['metrics'][k][d]['ci95'][0])}, {fmt(stats['metrics'][k][d]['ci95'][1])}]" for d in ('d10','d21','d2')]+
                             ['/'.join(str(stats['metrics'][k][d]['valid_replicates']) for d in ('d10','d21','d2'))] for k in METRICS])]
        for g in (1,2):
            ed = td/'evolve'/f'g{g}'
            if not (ed/'evolution.json').exists():
                lines += [f'第 {g} 次进化：无完成产物。']
                continue
            e,ins = read(ed/'evolution.json'), read(ed/'insights.json')
            evo_errors=validate_document(e,'evolution',load_validators(),{})
            evo_wall=read(ed/'trial-metadata.json')['wall_s'] if (ed/'trial-metadata.json').exists() else None
            write_json(ed/'validation.json',{'errors':evo_errors})
            lines += [f'### 第 {g} 次进化\n',
                f'来源 {e["source_run_id"]}；{e["from_version"]} → {e["to_version"] or e["from_version"]}；outcome={e["outcome"]}；采纳={e["chosen"] or "无"}。候选槽位 {len(e["candidates"])}，有改动候选 {sum(bool(c["changes"]) for c in e["candidates"])}，硬规则拦下 {sum(bool(c["hard_rule_violations"]) for c in e["candidates"])}。',
                f'本次进化墙钟（反思、C验证与审核）：{fmt(evo_wall)} 秒。',
                f'实际反思器：`{e["reflector"]["model"]}`；fell_back={e["reflector"]["fell_back"]}；原因：{e["reflector"]["fallback_reason"] or "无"}。',
                f'人类审核结果：{dict(Counter(r["decision"] for r in e["human_review"]))}；[完整 evolution]({ed/"evolution.json"})；[S4 insights]({ed/"insights.json"})。',
                table(['C基线/候选']+metric_names+['硬规则','门禁否决','主指标严格提高','最终passed'],
                      [['baseline']+[e['baseline_val_metrics'][k] for k in metric_names]+['—','—','—','—']]+
                      [[c['id']]+[(c['val_metrics'] or {}).get(k) for k in metric_names]+[
                          json.dumps(c['hard_rule_violations'],ensure_ascii=False),
                          json.dumps(c['veto'],ensure_ascii=False),
                          c['val_metrics']['isi_response_rate']>e['baseline_val_metrics']['isi_response_rate'] if c['val_metrics'] else None,
                          c['passed']] for c in e['candidates']]),
                table(['候选','改动','章节','S4子智能体','维度','关键度','理由'],
                      [[c['id'], ch['id'], ch['section'], ins['changes'][ch['id']]['subagent'], ins['changes'][ch['id']]['dimension'], ch['criticality'],ch['reason']]
                       for c in e['candidates'] for ch in c['changes']]),
                'evolution 契约校验：`'+json.dumps(evo_errors,ensure_ascii=False)+'`。旧校验器把 high 改动的 timeout 视为否决，与当前已审定 timeout_policy=pass 不一致时，原样记录此差异。',
                '丢弃/评估日志：`'+json.dumps(read(ed/'log.json'),ensure_ascii=False)+'`。']
        lines += ['### 分类器证据\n', f'![{track} 分类器曲线]({plot_dir/f"{track}-curves.png"})','以下由 S4 evidence.run_evidence 直接生成；熵单位 bits（0–log₂5），排除 status≠ok 的分类点。按每轮第 k 个有效分类步骤汇总，n 随提前退出/失败变化；不是等间隔时间导数。关键线索指 visitor.clues 中 supports=main_path 的首次 revealed_clue_ids，未出现记 NA。']
        evidences = {}
        for i in range(3):
            path = td/f'r{i}'/'insights.json'
            if path.exists():
                evidences[i] = read(path)
        lines += [table(['运行','会谈轮','有效步骤k','n','平均正确路径权重','平均熵bits'],
                        [[f'r{i}',s['round'],s['step'],s['n'],s['mean_p_true'],s['mean_entropy']]
                         for i,ev in evidences.items() for s in ev['summary']['by_step']]),
                  table(['运行','有权重来访','失败分类点','关键线索出现率','线索平均agent回合','首次判对平均agent回合','第1轮末正确路径权重','第2轮末正确路径权重'],
                        [[f'r{i}']+[ev['summary'][k] for k in ('n_with_path_probs','classifier_failures','key_clue_rate','mean_key_clue_agent_turn','mean_first_correct_agent_turn','r1_end_p_true','r2_end_p_true')] for i,ev in evidences.items()])]
        ids = sorted(set().union(*(set(ev['visitors']) for ev in evidences.values())))
        def clue(i,vid):
            return evidences.get(i,{}).get('visitors',{}).get(vid,{}).get('key_clue')
        def clue_str(c):
            return f"轮{c['round']}:t{c['turn']} / agent#{c['agent_turn']}" if c else '未出现'
        def compare(a,b):
            if not a and not b: return '均未出现'
            if not a: return '新出现'
            if not b: return '本次未出现'
            delta=b['agent_turn']-a['agent_turn']
            return f'提前{-delta}' if delta<0 else (f'推迟{delta}' if delta>0 else '相同')
        lines += [table(['来访','r0关键线索','r1关键线索','r2关键线索','r1对r0','r2对r1'],
                        [[vid]+[clue_str(clue(i,vid)) for i in range(3)]+[compare(clue(0,vid),clue(1,vid)),compare(clue(1,vid),clue(2,vid))] for vid in ids]),
                  '逐来访逐回合的完整权重/熵曲线：'+ '；'.join(f'[r{i} insights]({td/f"r{i}"/"insights.json"})' for i in evidences)+'。']
        # Align generation curves on valid-step index; missing steps are never filled with zero.
        aligned = {}
        for i,ev in evidences.items():
            for p in ev['summary']['by_step']:
                aligned.setdefault((p['round'],p['step']),{})[i]=p
        curve_rows=[]
        for (rnd,step), ps in sorted(aligned.items()):
            for metric in ('mean_p_true','mean_entropy'):
                vals=[ps.get(i,{}).get(metric) for i in range(3)]
                ds=[None if vals[i] is None or vals[i+1] is None else vals[i+1]-vals[i] for i in (0,1)]
                curve_rows.append([rnd,step,metric]+vals+ds+[None if None in ds else ds[1]-ds[0]])
        lines += [table(['轮','步骤','量','r0','r1','r2','Δ10','Δ21','Δ²'],curve_rows)]
    audit_path=out/'final-audit.json'
    if audit_path.exists():
        audit=read(audit_path)
        lines += ['## 最终核验\n',
            f'完成 9 次 A 组运行、6 次进化、{audit["batch_count"]-9} 次 C 组批次，共 {audit["session_count"]} 场模拟会谈。候选槽位 {audit["candidate_slots"]}，空候选 {audit["empty_candidates"]}，硬规则拦下 {audit["hard_blocked_candidates"]}，采纳 {audit["adopted_generations"]} 次。',
            f'预算账本、HTTP 开始及结果记录均为 {audit["http_attempts"]} 条，budget_blocked={audit["budget_blocked"]}。全部批次完成、指标重算及候选/实际 playbook 全文比对通过，受保护源码摘要与启动时相同。session/run_report 契约错误为 0。',
            f'evolution 校验记录为 {json.dumps(audit["evolution_validation_errors"],ensure_ascii=False)}。这 3 项均涉及 ds_nothink/g2 未被最终选择的 c2：旧校验器把 timeout 当作否决，现行审定配置 timeout_policy=pass；最终选择为 c3。未改契约或门禁。',
            f'产物中凭据原值匹配数为 {audit["secret_value_matches"]}；运行时快照目录内无 .git。[核验 JSON]({audit_path})。']
    lines += ['## 局限与口径\n',
        '- 同一 A 组反复用于学习与测量，未使用独立 B 组；这些差分不是泛化改善估计。C 也在两次候选选择中复用。',
        '- A 每轨道 10 人、C 每次 8 人，轨道只重复三个代际运行；bootstrap 区间离散且可能退化。轨道顺序固定，服务时段和生成波动未做随机化或重复控制。',
        '- ANTHROPIC_API_KEY 启动时为空，反思器按代码降级；未测 Opus 5.5 的实际效果。前两次日志为 Anthropic SDK 缺失，后续可出现认证缺失；实际降级原因逐代列出，未把不同初始化状态合并成一次成功的主反思器调用。',
        '- ISI 为冻结的简易规则状态模型输出，不是实际来访疗效；参数为占位模型，见 sim/params.yaml。',
        '- 已知模拟器问题：accept-report 第 2 条记录真实渲染偶尔编造本回合未授权的线索（sample-001 出现“脑子还转个不停”）。本实验保留该默认行为；基于 revealed_clue_ids 的线索回合证据无法覆盖这类额外措辞。来源：[accept-report.md](/Users/zhangheqing/bohack/research/codex-tasks/accept-report.md)。',
        '- crisis_exit 若第一轮退出，scorer 将第一轮路径沿用作第二轮指标；危机漏报指标仅统计非 none 真值被判 none，不等于 active/passive 分档准确率。',
        '- screening_coverage 使用契约 needed_screen 的适用子集，不能等同所有来访强制 screen_mood 的覆盖率。',
        '- C 组 8 人均无危机阳性，因此 crisis_recall=null；crisis_missed=0 不构成 C 组危机识别召回证据。C 组本次各批 screening_coverage 为 null，表示契约适用分母为零。',
        '- 主指标严格提高和门禁是不同条件：veto=true 不代表候选通过；ISI 未严格提高仍会保留上一代。未采纳改动时，一阶/二阶差分包含相同 playbook 的重复运行波动。',
        '- 绘图依赖 matplotlib 仅安装于 var/evo-viz-deps；未改变引擎运行环境或仓库依赖文件。',
        f'- 版本存储模式为 {manifest["repo_mode"]}。本次按不写任何 .git、不 commit 的限制使用独立文件快照；evolution 中 committed 表示 S4 已采纳并保存，SHA 为内容 SHA256，不是 Git 提交；未实测 Git 提交/回滚。evolution.commit.repo 保留 schema 固定逻辑路径 var/playbook-repo，实际独立存储路径在各代 storage.json。团队仓库未提交。全套 JSON 校验错误计数见上表与各 summary，不将契约通过等同模型全程成功。',
        '## 附录：全部候选与最终采纳的 playbook diff\n']
    for track in TRACKS:
        for g in (1,2):
            ed=out/track/'evolve'/f'g{g}'
            for path in sorted(ed.glob('*.diff')):
                lines += [f'### {track} / g{g} / {path.name}\n', '```diff\n'+(path.read_text() or '（无改动）\n')+'```']
    Path(report_path).write_text('\n\n'.join(lines)+'\n')
    write_json(out/'report-check.json', {'report': str(report_path), 'request_ledger': attempts,
               'http_starts': len(starts), 'http_results': len(results),
               'completed': (out/'done.json').exists()})
    log('report written: '+str(report_path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--id', required=True)
    parser.add_argument('--budget', type=int, default=15000, choices=range(1,15001))
    parser.add_argument('--repo-mode', choices=('git','snapshot'), default='snapshot')
    parser.add_argument('--baseline-only', action='store_true')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--report-only', action='store_true')
    args = parser.parse_args()
    if not args.report_only:
        asyncio.run(experiment(args))
    if args.report_only or not args.baseline_only:
        report_trial(args.id, '/Users/zhangheqing/bohack/research/codex-tasks/evo-trial.md')


if __name__ == '__main__':
    main()
