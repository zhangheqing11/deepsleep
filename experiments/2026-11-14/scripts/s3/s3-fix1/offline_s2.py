import asyncio, copy, json, sys
from pathlib import Path
sys.path.append('/Users/zhangheqing/bohack/ds-integ')
from engine.run import build_deps, run_batch
from engine.adapters_sim import S2VisitorSim, S2Screening, S2OutcomeModel
from engine.reporting import build_report
from safety.layer import SafetyLayer
from safety.judges import MockJudge
from scoring.score import score_run
from contracts.validate import load_validators, validate_document
async def main():
    visitors=[json.loads(p.read_text()) for p in sorted(Path('/Users/zhangheqing/bohack/ds-integ/sim/visitors').glob('sample-*.json'))]
    deps=build_deps(config={'agent_llm':{'provider':'mock'},'path_classifier':{'provider':'mock'}},sim=S2VisitorSim(),screening=S2Screening(),outcome=S2OutcomeModel(),safety=SafetyLayer(judge=MockJudge()))
    results=await run_batch(visitors,deps,'s3-fix1-offline')
    by_id={v['id']:v for v in visitors}
    options=dict(scorer=score_run,run_id='s3-fix1-offline',label='S3 offline',role='validation',split='sample',playbook_version='v0',models={'agent':'mock','visitor':'mock','judge':'mock'},duration_s=0)
    report,summary=build_report(by_id,results,**options)
    validators=load_validators()
    errors=[(s['visitor_id'], validate_document(s,'session',validators,by_id)) for s,t in results]
    errors=[e for e in errors if e[1]]
    errors+=validate_document(report,'run_report',validators,by_id)
    mixed=copy.deepcopy(results)
    mixed[0][0]['status']='error';mixed[0][0]['error']='injected downstream error'
    mixed[1][1]['unknown_path_rounds']=[2];mixed[1][0]['rounds'][-1]['path_confidence']=None
    subset,subsummary=build_report(by_id,mixed,**options)
    subset_errors=validate_document(subset,'run_report',validators,by_id)
    assert subset['n_visitors']==len(visitors)-2 and not subset['veto']['passed']
    summary.update(validation_errors=errors,mixed_report_validation_errors=subset_errors,mixed_summary=subsummary)
    Path('var/s3-fix1/offline_s2.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    assert not errors and not subset_errors
asyncio.run(main())
