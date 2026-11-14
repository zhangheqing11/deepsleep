import asyncio, json, os, time
from pathlib import Path
from engine.config import load_dotenv
from openai import AsyncOpenAI
async def main():
    load_dotenv('/Users/zhangheqing/bohack/ds-safety/.env')
    out=Path('var/s3-phase2/probe.json')
    if out.exists(): raise RuntimeError('Refuse billed rerun')
    out.write_text('[]')
    rows=[]
    async with AsyncOpenAI(api_key=os.environ['DS_API_KEY'],base_url=os.environ['DS_BASE_URL'],max_retries=0,timeout=25) as client:
        for mode, options in [('default',{}),('disabled',{'extra_body':{'thinking':{'type':'disabled'}}}),('low',{'reasoning_effort':'low'})]:
            t=time.perf_counter()
            row={'mode':mode}
            try:
                r=await client.chat.completions.create(model=os.environ['DS_MODEL'],messages=[{'role':'system','content':Path('engine/prompts/response.md').read_text()},{'role':'user','content':'来访：最近睡不好，躺下后反复担心明天。策略：共情后询问担心的具体内容。仅输出 text、acts 的 JSON。'}],max_tokens=1200,temperature=0,response_format={'type':'json_object'},**options)
                row.update(finish_reason=r.choices[0].finish_reason,usage=r.usage.model_dump(),json_ok=isinstance(json.loads(r.choices[0].message.content),dict))
            except Exception as e: row['error_type']=type(e).__name__
            row['seconds']=time.perf_counter()-t
            rows.append(row);out.write_text(json.dumps(rows,indent=2));print(json.dumps(row),flush=True)
asyncio.run(main())
