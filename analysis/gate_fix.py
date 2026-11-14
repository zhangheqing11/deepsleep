"""40-person repeated template baseline and one evolution; no git writes.
Run: python -m analysis.gate_fix --run. Report: python -m analysis.gate_report.
Existing incomplete billed batches are never restarted automatically.
"""
from analysis.gate_support import *
from engine.run import load_visitors as load_files
from engine.evolve import pipeline
from engine.evolve.llm import default_clients, primary_settings

OUT = ROOT/'var/gate-fix/gate-fix-20261114-r2'
PRIOR = ROOT/'var/gate-fix/gate-fix-20261114'
BUDGET = ROOT/'var/gate-fix/request-budget.log'
REPORT = Path('/Users/zhangheqing/bohack/research/codex-tasks/gate-fix.md')

def hashes():
    names = subprocess.check_output(['git', 'ls-files', '-z']).decode().split('\0')
    return {n: hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names if n and (ROOT/n).is_file()}

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
            label=stage, role='validation', split=visitors[0]['split'], playbook_version=version,
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

async def experiment40():
    load_dotenv('/Users/zhangheqing/bohack/ds-safety/.env')
    for k,v in {'REFLECTOR_PROVIDER':'openai','REFLECTOR_MODEL':'gpt-6-astra',
                'REFLECTOR_REASONING_EFFORT':'xhigh'}.items():
        os.environ[k]=v
    for k in ('DS_API_KEY','DS_BASE_URL','DS_MODEL','TYPESAFE_API_KEY','OPENAI_API_KEY'):
        if not os.getenv(k, '').strip():
            raise RuntimeError('Required credential/config missing: '+k)
    OUT.mkdir(parents=True, exist_ok=True)
    A=load_files([ROOT/'data/visitors/interim/A'])
    C=load_files([ROOT/'data/visitors/interim/C'])
    assert len(A)==40 and len(C)==32
    assert {v['split'] for v in A}=={'A'} and {v['split'] for v in C}=={'C'}
    initial=ROOT/'engine/playbook_v1.md'
    config=evolve_config({'repo':{'path':str(OUT/'playbook-snapshots')},
                          'review':{'run_dir':str(OUT/'evolve')}})
    config['repo']['v0_path']=str(initial) # compatibility adapter for snapshot-only store
    manifest={'started_at':now(),'head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
              'prior_attempt_dir':str(PRIOR),'prior_attempt_requests':len((PRIOR/'request-budget.log').read_text().splitlines()),'tracked_hashes':hashes(),'source_hashes':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in list((ROOT/'engine').rglob('*.py'))+list((ROOT/'analysis').glob('gate*.py'))},'budget':12000,'A':[v['id'] for v in A], 'C':[v['id'] for v in C],
              'initial_sha256':hashlib.sha256(initial.read_bytes()).hexdigest(),
              'reflector_settings':primary_settings(config),'bootstrap_seed':20261114,'bootstrap_replicates':10000,
              'C_scheduling':'baseline first; sequential versions; 8 sessions; 16 HTTP requests', 'repo_mode':'snapshot'}
    if (OUT/'manifest.json').exists():
        assert read(OUT/'manifest.json')['tracked_hashes']==manifest['tracked_hashes']
    else: write_json(OUT/'manifest.json',manifest)
    meter=TrialMeter(RequestBudget(BUDGET,12000),OUT)
    import httpx, httpx2
    started=time.perf_counter()
    try:
        with ExitStack() as stack:
            stack.enter_context(meter.watch_http(httpx.AsyncClient))
            stack.enter_context(meter.watch_http(httpx2.AsyncClient))
            deps=deps_for('jev',meter)
            write_json(OUT/'config.json',{'engine':deps.config,'safety':deps.safety.config,'evolve':config})
            sem=asyncio.Semaphore(deps.config['concurrency']['max_sessions'])
            try:
                v0=initial.read_text()
                for label in ('r0a','r0b'):
                    log('starting '+label)
                    await batch(deps,A,v0,'v0',OUT/label,label,meter,sem)
                repo=SnapshotRepo(config)
                repo.init()
                source=rich_load(OUT/'r0a',A)
                lock=asyncio.Lock()
                async def evaluator(text, *, label):
                    async with lock:
                        log('starting C/'+label)
                        return await batch(deps,C,text,'v0',OUT/'C'/label,'C-'+label,meter,sem)
                evofile=OUT/'evolve/g1/evolution.json'
                if not evofile.exists():
                    primary,fallback,error=default_clients(config)
                    assert error is None and primary is not None
                    assert primary.model=='gpt-6-astra' and primary.effort=='xhigh'
                    original_create=primary._client.responses.create
                    async def capture_usage(**kwargs):
                        response=await original_create(**kwargs)
                        write_json(OUT/'reflector-usage.json',{'model':response.model,'status':response.status,
                            'usage':response.usage.model_dump() if response.usage else None})
                        return response
                    primary._client.responses.create=capture_usage
                    original_reflect=pipeline.reflect
                    async def captured_reflect(**kwargs):
                        if (OUT/'reflection.json').exists():
                            raise RuntimeError('Refusing to repeat existing reflection')
                        log('starting reflector gpt-6-astra/xhigh')
                        t=time.perf_counter()
                        result=await original_reflect(**kwargs)
                        write_json(OUT/'reflection.json',{'wall_s':time.perf_counter()-t,**asdict(result)})
                        log('reflection done: '+result.model+' fallback='+str(result.fell_back))
                        if result.fell_back or result.model!='gpt-6-astra':
                            raise RuntimeError('Reflector did not complete as requested; stopped before C')
                        return result
                    token=STAGE.set('reflector'); ct=COMPONENT.set('reflector')
                    try:
                        with patch.object(pipeline,'reflect',captured_reflect):
                            evolution,insights=await evolve(run_report=read(OUT/'r0a/run_report.json'),
                                sessions=source['sessions'],traces=source['traces'],visitors=source['visitors'],
                                evaluator=evaluator,config=config,repo=repo,primary=primary,fallback=fallback,
                                use_default_clients=False,evolution_id='g1',return_insights=True)
                    finally:
                        COMPONENT.reset(ct); STAGE.reset(token)
                        await primary._client.close()
                        if fallback: await fallback._client.close()
                evolution=read(evofile)
                for cand in evolution['candidates']:
                    pb=EditablePlaybook.parse(v0)
                    for change in cand['changes']: pb.apply(change)
                    (evofile.parent/(cand['id']+'.diff')).write_text(''.join(difflib.unified_diff(
                        v0.splitlines(True),pb.render().splitlines(True),fromfile='v0',tofile=cand['id'])))
                write_json(OUT/'evolution-validation.json',validate_document(evolution,'evolution',load_validators(),{v['id']:v for v in A+C}))
                if evolution['chosen']:
                    await batch(deps,A,repo.read(),repo.current_version(),OUT/'r1','r1',meter,sem,
                                baseline=read(OUT/'r0a/run_report.json'))
                write_json(OUT/'done.json',{'finished_at':now(),'wall_s':time.perf_counter()-started,
                           'chosen':evolution['chosen'],'outcome':evolution['outcome']})
                log('done: '+evolution['outcome'])
            finally: await close_deps(deps)
    except Exception as exc:
        write_json(OUT/'stopped.json',{'at':now(),'error_type':type(exc).__name__,'budget_blocked':meter.budget_blocked})
        log('stopped: '+type(exc).__name__)
        raise
    finally:
        write_json(OUT/'calls-current-process.json',{'logical':meter.calls,'http':meter.http})
        write_json(OUT/'network-retries.json', deps.llm.network_stats if 'deps' in locals() else {})
        write_json(OUT/'accounting.json',{'attempts':len(BUDGET.read_text().splitlines())
            if BUDGET.exists() else 0,'limit':12000,'budget_blocked':meter.budget_blocked})
        write_json(OUT/'integrity.json',{'tracked_unchanged':hashes()==read(OUT/'manifest.json')['tracked_hashes'],
            'runtime_git_dirs':[str(p) for p in OUT.rglob('.git')]})

def fmt(v):
    if v is None: return 'NA'
    if isinstance(v,bool): return str(v).lower()
    if isinstance(v,float): return f'{v:.4f}'
    return str(v)


def table(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+
                     ['| '+' | '.join(fmt(v).replace('\n',' ').replace('|','/') for v in row)+' |' for row in rows])+'\n'


def paired_stats(left, right, reps=10000):
    """right-left; resample visitor IDs jointly, recompute ratio denominators."""
    def quantiles(values):
        values=sorted(values)
        def q(p):
            x=(len(values)-1)*p; i=int(x); j=min(i+1,len(values)-1)
            return values[i]+(values[j]-values[i])*(x-i)
        return [q(.025),q(.975)]
    a={r['visitor_id']:r for r in left['per_visitor']}
    b={r['visitor_id']:r for r in right['per_visitor']}
    assert set(a)==set(b)
    ids=sorted(a)
    keys=[k for k in METRICS if k!='veto_passed']+['referral_recall_R1','referral_recall_R2','referral_recall_R3']
    def calc(rows):
        m=compute_metrics(rows)
        m.update({'referral_recall_'+k:v for k,v in m['referral_recall_by_label'].items()})
        return m
    ma,mb=calc(list(a.values())),calc(list(b.values()))
    point={k:None if ma[k] is None or mb[k] is None else mb[k]-ma[k] for k in keys}
    draws={k:[] for k in keys}; rng=random.Random(20261114)
    for _ in range(reps):
        sample=[rng.choice(ids) for _ in ids]
        x,y=calc([a[i] for i in sample]),calc([b[i] for i in sample])
        for k in keys:
            if x[k] is not None and y[k] is not None: draws[k].append(y[k]-x[k])
    metrics={k:{'baseline':ma[k],'comparison':mb[k],'delta':point[k],
                 'ci95':quantiles(draws[k]) if draws[k] else [None,None],
                 'valid_bootstrap':len(draws[k])} for k in keys}
    flags={'有效':lambda r:r['isi_week'][4]-r['isi_week'][0]<-7,
           '路径第1轮正确':lambda r:r['path_pred_r1']==r['main_path'],
           '路径第2轮正确':lambda r:r['path_pred_r2']==r['main_path'],
           '转介标签正确':lambda r:r['referral_pred']==r['referral_true']}
    paired=[]; agreement={}
    for name,fn in flags.items():
        cells=Counter((bool(fn(a[i])),bool(fn(b[i]))) for i in ids)
        agreement[name]={'n':len(ids),'both_yes':cells[True,True],'both_no':cells[False,False],
                         'lost':cells[True,False],'gained':cells[False,True],
                         'agreement':(cells[True,True]+cells[False,False])/len(ids)}
    for i in ids:
        paired.append({'visitor_id':i,**{name:[bool(fn(a[i])),bool(fn(b[i]))] for name,fn in flags.items()}})
    return {'metrics':metrics,'agreement':agreement,'paired':paired}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if args.run:
        asyncio.run(experiment40())
