"""Offline AUDIT2 review inventory; candidates need human semantic judgment.

Scans every compiled crisis row, every gold KEEP <=2 characters, and every
adjacent repeated 2–4 character sequence (including identifier digits). Never
repairs model output: natural repetitions and identifier substrings are valid.
"""
import argparse
import json
import re
from .build import ROOT, read_jsonl
from .rules import occurrences
from .validate import compiled_paths

MODIFIERS=re.compile(r'不|没|别|无|比|更|最|越|很|太|挺|特别|反而|总|老是|一直|才|只|一般|却|还')


def scan(root=ROOT):
    result=dict(rows=0,crisis_rows=0,gold_short_keep=0,
                uncovered_crisis_pronouns=[],short_keep_candidates=[],repetitions=[])
    for path in compiled_paths(root):
        for row in read_jsonl(path):
            text=row['text'];entities=row['entities']
            result['rows']+=1
            covered={i for k in row['keep'] for a in occurrences(text,k)
                     if not any(a<e['end'] and a+len(k)>e['start'] for e in entities)
                     for i in range(a,a+len(k))}
            common=dict(file=str(path.relative_to(root)),id=row['id'])
            if 'crisis' in row['tags']:
                result['crisis_rows']+=1
                for m in re.finditer(r'本人|我',text):
                    if m.start() in covered or any(e['start']<=m.start()<e['end'] for e in entities):continue
                    result['uncovered_crisis_pronouns'].append(dict(common,start=m.start(),
                        context=text[max(0,m.start()-12):m.end()+24],note=row.get('note','')))
            if path.parent.name=='gold':
                for k in row['keep']:
                    if len(k)>2:continue
                    result['gold_short_keep']+=1
                    for a in occurrences(text,k):
                        b=a+len(k)
                        if any(a<e['end'] and b>e['start'] for e in entities):continue
                        lo=max([0]+[e['end'] for e in entities if e['end']<=a])
                        hi=min([len(text)]+[e['start'] for e in entities if e['start']>=b])
                        context=text[max(lo,a-5):min(hi,b+5)]
                        if MODIFIERS.search(context):
                            result['short_keep_candidates'].append(dict(common,keep=k,context=context))
            # Lookahead deliberately includes overlapping candidate fragments.
            for size in range(2,5):
                for m in re.finditer(r'(?=([^\s，。！？；、：]{'+str(size)+r'})\1)',text):
                    a=m.start();b=a+2*size
                    result['repetitions'].append(dict(common,start=a,text=text[a:b],
                        in_entity=any(e['start']<=a and e['end']>=b for e in entities)))
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--json',type=str)
    args=parser.parse_args();result=scan()
    if args.json:
        from pathlib import Path
        Path(args.json).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:len(v) if isinstance(v,list) else v for k,v in result.items()},ensure_ascii=False))


if __name__=='__main__':main()
