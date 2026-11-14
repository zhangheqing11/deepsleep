"""Compile source annotations; source files and SPEC are never rewritten."""
import argparse
import json
from pathlib import Path
from .rules import occurrences, replacement_for, replay
ROOT=Path(__file__).resolve().parents[1]

def read_jsonl(path):
    rows=[]
    with Path(path).open(encoding='utf-8') as f:
        for line_no,line in enumerate(f,1):
            if not line.strip(): continue
            try: rows.append(json.loads(line))
            except ValueError as exc: raise ValueError(f'{path}:{line_no}: {exc}') from exc
    return rows

def write_jsonl(path,rows):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(''.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n' for r in rows),encoding='utf-8')

def compile_rows(rows):
    sessions={}; turns={}; result=[]
    for row in rows:
        try:
            sid=row.get('session_id'); mapping=sessions.setdefault(sid,{}) if sid else {}
            if sid:
                if not isinstance(row.get('turn'),int) or row['turn']<=turns.get(sid,0): raise ValueError('turn 必须按会话严格递增')
                turns[sid]=row['turn']
            spans=[]
            for ent in row['ents']:
                if not isinstance(ent,list) or not 2<=len(ent)<=4: raise ValueError('ents 元素应有2–4项')
                surface,label=ent[:2]; repl=ent[2] if len(ent)>2 else None
                starts=occurrences(row['text'],surface)
                if not starts: raise ValueError(f'实体未出现: {surface!r}')
                occ=ent[3] if len(ent)>3 else list(range(1,len(starts)+1))
                if not isinstance(occ,list) or not occ or len(set(occ))!=len(occ) or any(type(i)!=int or not 1<=i<=len(starts) for i in occ): raise ValueError(f'occ 非法: {occ!r}')
                spans.extend(dict(start=starts[i-1],end=starts[i-1]+len(surface),text=surface,label=label,replacement=repl) for i in occ)
            spans.sort(key=lambda e:(e['start'],e['end']))
            previous=0
            for e in spans:
                if e['start']<previous: raise ValueError('实体重叠')
                previous=e['end']
                e['replacement']=replacement_for(e['label'],e['text'],e['replacement'],mapping)
            out={k:row[k] for k in ('id','text','keep','tags')}
            out.update(entities=spans,deid=replay(row['text'],spans),note=row.get('note',''))
            if sid: out.update(session_id=sid,turn=row['turn'])
            result.append(out)
        except (ValueError,KeyError,TypeError) as exc: raise ValueError(f'{row.get("id","<missing id>")}: {exc}') from exc
    return result

def compile_source(path):
    return compile_rows(read_jsonl(Path(path)))


def build(root=ROOT):
    count=0
    for folder in ['gold','synth']:
        for path in sorted((root/folder).glob('*.src.jsonl')):
            rows=compile_source(path); write_jsonl(path.with_name(path.name.replace('.src','')),rows); count+=len(rows)
    return count

if __name__=='__main__':
    print(f'编译完成: {build()} 条')
