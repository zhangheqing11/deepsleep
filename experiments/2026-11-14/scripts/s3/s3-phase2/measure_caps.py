import asyncio,json
from collections import Counter
from pathlib import Path
from engine.run import build_deps,run_batch
from engine.adapters_sim import S2Screening,S2VisitorSim,S2OutcomeModel
from safety.layer import SafetyLayer
from safety.judges import MockJudge
from scoring.smoke import load_visitors
async def main():
    rows=[]
    for label,caps,merged in [('3a',{1:5,2:4},False),('3b',{1:4,2:3},False),('3c',{1:4,2:3},True)]:
        deps=build_deps(config={'agent_llm':{'provider':'mock'},'path_classifier':{'provider':'mock'},'round_turn_cap':caps,'pipeline':{'merge_strategy_response':True,'merge_memory_plan':merged}},sim=S2VisitorSim(),screening=S2Screening(),outcome=S2OutcomeModel(),safety=SafetyLayer(judge=MockJudge()))
        results=await run_batch(load_visitors(n=10),deps,'measure-'+label)
        rows.append({'stage':label,'n':10,'statuses':dict(Counter(s['status'] for s,t in results)), 'calls':dict(Counter(c['agent'] for s,t in results for c in t['llm_calls'])),'forced_screens':sum(len(t['forced_tool_calls']) for s,t in results),'actions':sum(len(t['strategies']) for s,t in results),'safety_events':sum(len(s['safety_events']) for s,t in results)})
    Path('var/s3-phase2/cap_measurement.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows,indent=2))
asyncio.run(main())
