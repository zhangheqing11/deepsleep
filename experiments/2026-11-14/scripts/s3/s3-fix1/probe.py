import asyncio, json, time
from pathlib import Path
from engine.config import load_dotenv
from engine.run import build_deps, load_visitors
from engine.session import SessionRunner, _Round
from engine.llm import parse_json_object
from engine.classifier import make_state
from safety.layer import SafetyLayer

async def main():
    load_dotenv('/Users/zhangheqing/bohack/ds-safety/.env')
    deps = build_deps(safety=SafetyLayer({'judge_provider': 'mock'}))
    visitor = json.loads(Path('/Users/zhangheqing/bohack/ds-integ/sim/visitors/sample-001.json').read_text())
    runner = SessionRunner(deps, visitor, 'root-cause')
    runner.rounds.append(_Round(1))
    runner._add('visitor', visitor['opening_complaint'])
    runner.current.path_state = make_state(dict.fromkeys(('P1','P2','P3','P4','P5'), 1), 'cooperative', 'ok', 'probe', 0)
    runner.current.referral = 'R0'
    messages = runner._messages('plan', runner._snapshot(0))
    start = time.perf_counter()
    response = await deps.llm.client.chat.completions.create(model=deps.llm.model, messages=messages, temperature=0, top_p=1, max_tokens=800, response_format={'type':'json_object'})
    choice = response.choices[0]
    content = choice.message.content or ''
    try:
        parse_json_object(content)
        parsed = True
    except Exception:
        parsed = False
    result = {'calls': 1, 'model': deps.llm.model, 'wall_s': round(time.perf_counter()-start, 3), 'max_tokens':800, 'json_mode':True, 'finish_reason': choice.finish_reason, 'content_chars':len(content), 'reasoning_chars':len(getattr(choice.message,'reasoning_content','') or ''), 'parsed':parsed, 'usage': response.usage.model_dump() if response.usage else None, 'content': content}
    Path('var/s3-fix1/probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='content'},ensure_ascii=False))
    await deps.llm.aclose()
    await deps.classifier.client.close()

asyncio.run(main())
