"""Single-pair real API microbenchmarks, not independent full-batch ablations."""
import asyncio,json,time
from contextlib import ExitStack
from pathlib import Path
from engine.config import load_dotenv,load_config
from engine.integ_trial import Meter,RequestBudget,write_json
from engine.run import build_deps
from engine.llm import DsFlashClient
from engine.classifier import DsFlashPathClassifier,JevPathClassifier,make_state
from engine.session import SessionRunner,_Round,_valid_memory,_valid_plan,_valid_memory_plan,_valid_strategy,_valid_response,_valid_turn
from engine.adapters_sim import S2Screening
from scoring.smoke import load_visitors
from safety.layer import SafetyLayer
from safety.judges import MockJudge

async def main():
    out=Path('var/s3-phase2/component_bench.json')
    if out.exists(): raise RuntimeError('Refuse billed rerun')
    write_json(out,{'started':True})
    load_dotenv('/Users/zhangheqing/bohack/ds-safety/.env')
    deps=build_deps(config={'agent_llm':{'provider':'mock'},'path_classifier':{'provider':'mock'}},safety=SafetyLayer(judge=MockJudge()))
    runner=SessionRunner(deps,load_visitors(n=1)[0],'bench')
    runner.rounds.append(_Round(1))
    for speaker,text in [('visitor','最近睡不好，躺下后清醒着。'),('agent','躺下时脑中有担心的事情吗？'),('visitor','没什么特别的想法，只是清醒。换到沙发反而很快睡着。'),('agent','平时身体状况怎么样，有没有在看医生的情况？'),('visitor','没有。')]:
        runner._add(speaker,text)
    runner.current.topics=['bed_wakefulness','sleep_elsewhere','health_conditions']
    runner.current.path_state=make_state({'P1':.1,'P2':.6,'P3':.1,'P4':.1,'P5':.1},'cooperative','ok','fixture',0)
    runner.current.path_pred='P2'
    runner.tool_calls=[{'round':1,'turn':6,'tool':'screen_mood','result':S2Screening().screen(runner.visitor,'screen_mood')}]
    snap=runner._snapshot(2);cls=runner.current.path_state
    llm=DsFlashClient(load_config()['agent_llm'])
    ds=DsFlashPathClassifier(6,thinking='disabled');jev=JevPathClassifier(6)
    meter=Meter(RequestBudget('var/s3-phase2/request-budget.log',450))
    rows=[]
    import httpx,httpx2
    async def ask(task,valid,strategy=None):
        start=time.perf_counter();row={'task':task}
        try:
            result=await llm.complete_json(runner._messages(task,snap,cls,strategy=strategy),task=task,state=runner._state(task,snap,cls,strategy=strategy))
            valid(result);row['valid']=True
        except Exception as e:
            row.update(valid=False,error_type=type(e).__name__);result=None
        row['seconds']=time.perf_counter()-start;rows.append(row);return result
    with ExitStack() as stack:
        stack.enter_context(meter.watch_http(httpx.AsyncClient));stack.enter_context(meter.watch_http(httpx2.AsyncClient))
        memory=await ask('memory',_valid_memory)
        if memory: runner._save_memory(memory)
        await ask('plan',_valid_plan)
        runner.current.referral=None
        await ask('memory_plan',_valid_memory_plan)
        for name,client in [('ds_classifier',ds),('jev_classifier',jev)]:
            start=time.perf_counter();result=await client.classify(runner.entries)
            rows.append({'task':name,'seconds':time.perf_counter()-start,'status':result.status,'top':result.top})
        strategy=await ask('strategy',_valid_strategy)
        if strategy: await ask('response',_valid_response,strategy['strategy'])
        await ask('turn',_valid_turn)
    for client in (llm,ds.client,jev.client):
        close=getattr(client,'aclose',None) or getattr(client,'close',None)
        if close: await close()
    write_json(out,{'rows':rows,'http_attempts':len(meter.http),'http':meter.http})
    print(json.dumps(rows,indent=2))
asyncio.run(main())
