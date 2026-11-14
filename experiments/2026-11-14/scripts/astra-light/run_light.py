"""One generation, existing r0, current frozen engine, snapshot storage only."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from analysis.evo_trial import *
import engine.evolve.pipeline as pipeline
from engine.evolve.llm import default_clients, primary_settings

OUT = ROOT/'var/astra-light/astra-20261114'
OLD = ROOT/'var/evo-trial/evo-20261114/jev'

def hashes(paths):
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}

def tracked():
    return [ROOT/p for p in subprocess.check_output(['git','ls-files','-z']).decode().split('\0') if p]

async def main():
    if OUT.exists():
        raise RuntimeError('Refusing billed rerun')
    OUT.mkdir()
    # Read credential values directly into process memory; never persist them.
    envpath = Path('/Users/zhangheqing/bohack/ds-safety/.env')
    for line in envpath.read_text().splitlines():
        line=line.strip()
        if line and not line.startswith('#') and '=' in line:
            k,v=line.split('=',1); k=k.strip(); v=v.strip().strip('"').strip("'")
            if k and v: os.environ[k]=v
    os.environ.update(REFLECTOR_PROVIDER='openai', REFLECTOR_MODEL='gpt-6-astra', REFLECTOR_REASONING_EFFORT='xhigh')
    assert all(os.getenv(k,'').strip() for k in ('OPENAI_API_KEY','DS_API_KEY','DS_BASE_URL','DS_MODEL','TYPESAFE_API_KEY'))
    visitors=load_visitors(n=18)
    assert [v['id'] for v in visitors]==[f'sample-{i:03d}' for i in range(1,19)]
    source=rich_load(OLD/'r0', visitors[:10])
    before=(OLD/'r0/playbook.md').read_text()
    config=evolve_config({'repo': {'path':str(OUT/'playbook-snapshots'), 'v0_path':str(OLD/'r0/playbook.md')},
                          'review': {'run_dir': str(OUT/'evolve')}})
    primary,fallback,error=default_clients(config)
    assert error is None and primary.provider=='openai' and primary.model=='gpt-6-astra' and primary.effort=='xhigh'
    assert primary._client.base_url.host=='api.openai.com'
    repo=SnapshotRepo(config); repo.init()
    initial=hashes(tracked())
    prior=hashes(sorted(OLD.rglob('*')))
    write_json(OUT/'manifest.json', {'started_at':now(),'budget':1500,'head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'reflector_settings':primary_settings(config),'endpoint_host':primary._client.base_url.host,'A':[v['id'] for v in visitors[:10]],'C':[v['id'] for v in visitors[10:]],
        'r0_source':str(OLD/'r0'),'r0_reused':True,'repo_mode':'snapshot','sha_kind':'content_sha256','seed':20261114,'tracked_hashes':initial,'prior_hashes':prior})
    write_json(OUT/'evolve-config.json',config)
    random.seed(20261114)
    meter=TrialMeter(RequestBudget(OUT/'request-budget.log',1500),OUT)
    original=pipeline.reflect
    async def recorded_reflect(**kw):
        result=await original(**kw)
        write_json(OUT/'reflection.json',asdict(result))
        log('reflection: '+json.dumps({'model':result.model,'provider':result.provider,'effort':result.reasoning_effort,'fallback':result.fell_back,'attempts':result.attempts},ensure_ascii=False))
        return result
    import httpx, httpx2
    deps=None
    started=time.perf_counter()
    try:
        with ExitStack() as stack:
            stack.enter_context(meter.watch_http(httpx.AsyncClient))
            stack.enter_context(meter.watch_http(httpx2.AsyncClient))
            stack.enter_context(patch.object(pipeline,'reflect',recorded_reflect))
            deps=deps_for('jev',meter)
            write_json(OUT/'engine-config.json',{'engine':deps.config,'safety':deps.safety.config})
            sem=asyncio.Semaphore(deps.config['concurrency']['max_sessions'])
            async def evaluator(text, *, label):
                return await batch(deps, visitors[10:], text, 'v0', OUT/'C-g1'/label, 'astra-g1-C-'+label, meter, sem)
            st=STAGE.set('astra-g1-reflect'); ct=COMPONENT.set('reflector')
            try:
                evolution,insights=await evolve(run_report=read(OLD/'r0/run_report.json'), sessions=source['sessions'],traces=source['traces'],visitors=source['visitors'],
                    evaluator=evaluator,config=config,repo=repo,primary=primary,fallback=fallback,use_default_clients=False,evolution_id='g1',return_insights=True)
            finally:
                STAGE.reset(st); COMPONENT.reset(ct)
            for c in evolution['candidates']:
                pb=EditablePlaybook.parse(before)
                for change in c['changes']: pb.apply(change)
                (OUT/'evolve/g1'/f"{c['id']}.diff").write_text(''.join(difflib.unified_diff(before.splitlines(True),pb.render().splitlines(True),fromfile='v0',tofile=c['id'])))
            (OUT/'evolve/g1/adopted.diff').write_text(evolution['diff'] or '')
            errors=validate_document(evolution,'evolution',load_validators(),{v['id']:v for v in visitors})
            write_json(OUT/'evolution-validation.json',errors)
            log('gate: '+json.dumps({'outcome':evolution['outcome'],'chosen':evolution['chosen'],'budget_used':len(meter.http)},ensure_ascii=False))
            if evolution['chosen']:
                await batch(deps,visitors[:10],repo.read(),repo.current_version(),OUT/'r1','astra-r1',meter,sem,baseline=read(OLD/'r0/run_report.json'))
            write_json(OUT/'done.json',{'finished_at':now(),'wall_s':time.perf_counter()-started,'r1_run':bool(evolution['chosen'])})
    except Exception as exc:
        write_json(OUT/'stopped.json',{'at':now(),'error_type':type(exc).__name__,'budget_blocked':meter.budget_blocked})
        log('stopped: '+type(exc).__name__)
    finally:
        if deps: await close_deps(deps)
        for client in (primary,fallback):
            if client: await client._client.close()
        write_json(OUT/'calls.json',{'logical':meter.calls,'http':meter.http})
        write_json(OUT/'accounting.json',{'attempts':len(meter.http),'limit':1500,'budget_blocked':meter.budget_blocked})
        write_json(OUT/'integrity.json',{'tracked_unchanged':hashes(tracked())==initial,'prior_outputs_unchanged':hashes(sorted(OLD.rglob('*')))==prior,'runtime_git_dirs':list(map(str,OUT.rglob('.git')))})
        log('finished accounting: '+json.dumps(read(OUT/'accounting.json')))

if __name__=='__main__': asyncio.run(main())
