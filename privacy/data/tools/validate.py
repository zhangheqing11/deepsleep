"""Strict compiled-data integrity checks and reproducible corpus statistics."""
import argparse
import json
import re
from collections import Counter,defaultdict
from .build import ROOT,read_jsonl
from .rules import LABELS,PREFIX,replay,occurrences

TAGS=set('adversarial long no_clinical birth_date hard_negative time_keep drug_keep device_keep app_keep city_keep metric_keep symptom_keep substance_keep relation_keep shift_keep generic_place cbti_keep crisis ambiguous public_figure person phone id_num account plate address org school hospital date_keep date_birthday age_keep'.split())|{f'path_P{i}' for i in range(1,6)}|{f'ref_R{i}' for i in range(1,4)}

def compiled_paths(root=ROOT):
    return sorted(p for folder in ['gold','synth'] for p in (root/folder).glob('*.jsonl') if not p.name.endswith('.src.jsonl'))

def validate_rows(rows,*,seen=None,sessions=None):
    seen=seen if seen is not None else set();sessions=sessions if sessions is not None else {}
    errors=[]
    for r in rows:
        rid=r.get('id','<missing>') if isinstance(r,dict) else '<non-object>'
        def fail(msg):errors.append(f'{rid}: {msg}')
        try:
            if not isinstance(rid,str) or not rid or rid=='<missing>':fail('id 必须非空')
            if rid in seen:fail('id 全局重复')
            seen.add(rid)
            text=r['text'];deid=r['deid'];ents=r['entities'];keep=r['keep'];tags=r['tags']
            if not all(isinstance(x,str) for x in [text,deid]) or not isinstance(ents,list):raise ValueError('text/deid/entities 类型错误')
            if not isinstance(keep,list) or any(not isinstance(k,str) or not k for k in keep):raise ValueError('keep 必须为非空字符串列表')
            if not isinstance(tags,list) or any(t not in TAGS for t in tags):raise ValueError('非法 tag')
            if any(k not in text or k not in deid for k in keep):fail('keep 未原样出现在 text/deid')
            if 'hard_negative' in tags and (ents or deid!=text):fail('hard_negative 不得改文或含实体')
            if not keep and not ('no_clinical' in tags and isinstance(r.get('note'),str) and r['note'].strip()):
                fail('keep 不能为空，除非 no_clinical 且有 note')
            if len(keep)>6:fail('keep 个数必须为1–6（no_clinical 可为0）')
            limit=50 if 'crisis' in tags else 30
            if any(len(k)>limit for k in keep):fail(f'每个 keep 长度不得超过{limit}字')
            if 'crisis' in tags and not any(len(k)>=6 and re.search(r'我|他|她|想|过|以前|现在|有时候|不会|最近|已经|希望',k) for k in keep):
                fail('crisis keep 缺完整分句（长度>=6且含主语或意图/时态词）')
            if 'long' in tags and not 60<=len(text)<=200:fail('long 长度必须为60–200字')
            sid=r.get('session_id')
            state=sessions.setdefault(sid,{'map':{},'max':{},'turn':0}) if sid else {'map':{},'max':{},'turn':0}
            if sid:
                if type(r.get('turn'))!=int or r['turn']<=state['turn']:fail('会话 turn 未严格递增')
                state['turn']=r['turn']
            previous=0
            for e in ents:
                a,b=e['start'],e['end'];surface=e['text'];label=e['label'];replacement=e['replacement']
                if type(a)!=int or type(b)!=int or not 0<=a<b<=len(text) or text[a:b]!=surface:fail('offset 与 text 不对应')
                if a<previous:fail('entities 未排序或重叠')
                previous=b
                if label not in LABELS:fail(f'非法 label {label}');continue
                if not isinstance(replacement,str) or not replacement:fail('replacement 缺失');continue
                m=re.fullmatch(r'\['+PREFIX[label]+r'([1-9]\d*)\]',replacement)
                if not m:fail(f'{label} 占位符非法');continue
                key=(label,surface);number=int(m[1]);maximum=state['max'].get(PREFIX[label],0)
                if key in state['map'] and state['map'][key]!=replacement:fail('会话同一实体编号不一致')
                if key not in state['map'] and number>maximum+1:fail('首次出现编号跳号')
                # An already allocated token may be an explicitly declared alias.
                state['map'][key]=replacement;state['max'][PREFIX[label]]=max(maximum,number)
                if len(surface)>=2 and surface in deid and not any(surface in k for k in keep):fail(f'实体原文残留: {surface!r}')
            for k in keep:
                # A homonym may also occur inside an entity, but at least one
                # original occurrence must lie wholly outside every entity.
                if not any(all(a+len(k)<=e['start'] or a>=e['end'] for e in ents) for a in occurrences(text,k)):
                    fail('keep 必须有不跨实体的原文连续片段')
            non_entity_length=len(text)-sum(e['end']-e['start'] for e in ents)
            if len(text)>60 and 5*sum(map(len,keep))>3*non_entity_length:
                fail('文本>60字时 keep 总长不得超过非实体文本长度的60%')
            if replay(text,ents)!=deid:fail('重放替换不等于 deid')
        except (KeyError,ValueError,TypeError,IndexError) as exc:fail(f'结构或规则错误: {exc}')
    return errors

def stats(rows):
    tags=Counter(t for r in rows for t in r['tags']); labels=Counter(e['label'] for r in rows for e in r['entities'])
    ratios=[sum(map(len,r['keep']))/(len(r['text'])-sum(e['end']-e['start'] for e in r['entities'])) for r in rows if len(r['text'])>60 and len(r['text'])>sum(e['end']-e['start'] for e in r['entities'])]
    return dict(n=len(rows),hard_negative=tags['hard_negative'],hard_negative_ratio=tags['hard_negative']/len(rows) if rows else 0,labels=dict(sorted(labels.items())),tags=dict(sorted(tags.items())),entities=sum(labels.values()),empty_keep=sum(not r['keep'] for r in rows),sessions=len({r['session_id'] for r in rows if r.get('session_id')}),no_entity_turns=sum(not r['entities'] for r in rows),long=sum('long' in r['tags'] for r in rows),keep_fragments=sum(len(r['keep']) for r in rows),max_keep_count=max((len(r['keep']) for r in rows),default=0),max_keep_length=max((len(k) for r in rows for k in r['keep']),default=0),max_keep_ratio_over_40=max(ratios,default=None))

def validate_all(root=ROOT):
    errors=[];seen=set();sessions={};gold={};synth={};datasets={}
    for p in compiled_paths(root):
        try:rows=read_jsonl(p)
        except ValueError as exc:errors.append(str(exc));continue
        datasets[p]=rows
        errors.extend(f'{p.relative_to(root)}: {e}' for e in validate_rows(rows,seen=seen,sessions=sessions))
        target=gold if p.parent.name=='gold' else synth
        for r in rows:
            if isinstance(r,dict) and isinstance(r.get('text'),str):
                if r['text'] in target and p.parent.name=='synth' and not r.get('session_id'):errors.append(f'{r["id"]}: synth 文本内部重复')
                target[r['text']]=r.get('id')
    for t in gold.keys()&synth.keys():errors.append(f'训练/金标文本泄漏: {gold[t]} / {synth[t]}')
    # Dev and test themselves must be disjoint, including seed.
    heldout={}
    for split in ['seed','dev','test']:
        p=root/f'gold/{split}.jsonl'
        if p in datasets:
            for r in datasets[p]:
                if not isinstance(r,dict) or not isinstance(r.get('text'),str):continue
                if r['text'] in heldout:errors.append(f'金标 split 文本重复: {r["id"]} / {heldout[r["text"]]}')
                heldout[r['text']]=r['id']
    return errors

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--json',type=str);args=parser.parse_args()
    errors=validate_all()
    if errors:
        print('\n'.join(errors));raise SystemExit(1)
    summary={str(p.relative_to(ROOT)):stats(read_jsonl(p)) for p in compiled_paths()}
    for name,s in summary.items():
        print(f'{name}: n={s["n"]}, hard_negative={s["hard_negative"]} ({s["hard_negative_ratio"]:.1%})')
        print('  labels:',json.dumps(s['labels'],ensure_ascii=False));print('  tags:',json.dumps(s['tags'],ensure_ascii=False))
    if args.json: __import__('pathlib').Path(args.json).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('校验通过')
if __name__=='__main__':main()
