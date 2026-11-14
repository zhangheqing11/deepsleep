"""SPEC §6 metrics. Baselines never read gold entities, keep, or tags to predict."""
import argparse
import difflib
import json
import re
from collections import Counter,defaultdict
from pathlib import Path
import yaml
from .build import ROOT,read_jsonl
from .apply import apply
from .rules import occurrences, PREFIX


TOKEN = re.compile(r'\[(?:(?:人名|电话|证件号|账号|车牌|地址|单位|学校|医院|日期)[1-9]\d*|已隐藏)\]')


def alignment(text, output):
    """Map original positions to surviving output characters, never into tokens.

    Masking keeps output indices stable while preventing 电话 in [电话1] from
    becoming an equal block. autojunk=False matters for repeated Chinese text.
    """
    masked=list(output)
    for m in TOKEN.finditer(output):
        masked[m.start():m.end()]=['\uffff']*(m.end()-m.start())
    matcher=difflib.SequenceMatcher(None,text,''.join(masked),autojunk=False)
    positions={}
    ops=matcher.get_opcodes()
    for op,a,b,c,d in ops:
        if op=='equal':positions.update((i,c+i-a) for i in range(a,b))
    return positions,ops


def survives(start,end,positions):
    first=positions.get(start)
    return first is not None and all(positions.get(i)==first+i-start for i in range(start,end))


def entity_replacement_legality(row, output):
    """Check complete entity regions anchored by neighboring non-entity text.

    Mask source entities so partial fake names cannot anchor
    alignment. Adjacent entities share a region and must match their ordered
    type patterns in full. Missing boundary anchors fail conservatively. This
    checks legal types, not gold numbering (session_numbering checks that).
    """
    entities=row['entities']
    masked=list(row['text'])
    groups=[]
    for index,e in enumerate(entities):
        masked[e['start']:e['end']]=['\ufffe']*(e['end']-e['start'])
        if groups and entities[groups[-1][-1]]['end']==e['start']:
            groups[-1].append(index)
        else:groups.append([index])
    positions,_=alignment(''.join(masked),output)
    result=[False]*len(entities)
    for group in groups:
        a=entities[group[0]]['start'];b=entities[group[-1]]['end']
        left=0 if a==0 else positions.get(a-1)
        right=len(output) if b==len(masked) else positions.get(b)
        if left is None or right is None:continue
        if a:left+=1
        patterns=[]
        for index in group:
            e=entities[index]
            patterns.append(r'\['+PREFIX[e['label']]+r'[1-9]\d*\]')
        legal=left<=right and re.fullmatch(''.join(patterns),output[left:right]) is not None
        for index in group:result[index]=legal
    return result


def score(rows,outputs,invalid=None):
    invalid=set(invalid or ())
    labels=defaultdict(lambda:dict(total=0,leaked=0,replacement_legal=0))
    kept=keep_total=crisis_kept=crisis_total=hn=over=exact=unchanged=valid=0
    for r in rows:
        output=outputs.get(r['id'])
        ok=r['id'] not in invalid and isinstance(output,str)
        valid+=ok
        positions,ops=alignment(r['text'],output) if ok else ({},[])
        exact+=ok and output==r['deid']
        # All source occurrences of each keep must survive at their own position.
        preserved=[]
        for k in r['keep']:
            starts=[a for a in occurrences(r['text'],k) if not any(a<e['end'] and a+len(k)>e['start'] for e in r['entities'])]
            preserved.append(ok and bool(starts) and all(survives(a,a+len(k),positions) for a in starts))
        kept+=sum(preserved);keep_total+=len(preserved)
        if 'crisis' in r['tags']:
            crisis_total+=len(preserved);crisis_kept+=sum(preserved)
        if 'hard_negative' in r['tags']:
            hn+=1;over+=not ok or output!=r['text']
        entity_positions={i for e in r['entities'] for i in range(e['start'],e['end'])}
        intact=ok and all(i in positions for i in range(len(r['text'])) if i not in entity_positions)
        # Inserting text into a non-entity area also breaks exact preservation.
        for op,a,b,c,d in ops:
            if op=='insert' and not any(e['start']<=a<=e['end'] for e in r['entities']):intact=False
        unchanged+=intact
        legality=entity_replacement_legality(r,output) if ok else [False]*len(r['entities'])
        for e,legal in zip(r['entities'],legality):
            labels[e['label']]['replacement_legal']+=legal
            labels[e['label']]['total']+=1
            if not ok:
                leaked=True  # fail closed; expose invalid count separately
            else:
                a,b=e['start'],e['end']
                # Equal characters and overlapping replacement blocks define the
                # output region belonging to this ORIGINAL entity occurrence.
                regions=[]
                for op,i,j,k,l in ops:
                    if i<b and j>a:
                        if op=='equal':regions.append((k+max(i,a)-i,k+min(j,b)-i))
                        elif op=='replace':regions.append((k,l))
                leaked=any(e['text'] in TOKEN.sub('',output[k:l]) for k,l in regions)
            labels[e['label']]['leaked']+=leaked
    def rate(a,b):return a/b if b else None
    total=sum(v['total'] for v in labels.values());leaks=sum(v['leaked'] for v in labels.values())
    legal_total=sum(v['replacement_legal'] for v in labels.values())
    return dict(n=len(rows),entity_replacement_legal_rate=rate(legal_total,total),leakage_rate=rate(leaks,total),keep_rate=rate(kept,keep_total),crisis_keep_rate=rate(crisis_kept,crisis_total),non_entity_exact_rate=rate(unchanged,len(rows)),valid_output_rate=rate(valid,len(rows)),hard_negative_overredaction=rate(over,hn),exact_match=rate(exact,len(rows)),counts=dict(entities=total,replacement_legal=legal_total,leaked=leaks,keep=keep_total,kept=kept,crisis_keep=crisis_total,crisis_kept=crisis_kept,hard_negative=hn,overredacted=over,exact=exact,non_entity_exact=unchanged,valid=valid,invalid=len(rows)-valid),by_label={l:dict(**v,leakage_rate=rate(v['leaked'],v['total']),entity_replacement_legal_rate=rate(v['replacement_legal'],v['total'])) for l,v in sorted(labels.items())})


def grouped_score(rows,outputs,invalid=None):
    return {tag:score([r for r in rows if tag in r['tags']],outputs,invalid) for tag in sorted({t for r in rows for t in r['tags']})}


def rules_entities(text):
    """Pattern-only baseline: identifier regexes plus contextual suffix heuristics."""
    patterns=yaml.safe_load((ROOT/'lexicons/redact/patterns.yaml').read_text(encoding='utf-8'))['regex']
    suffix_rules=[
        ('ADDRESS',r'(?:住在|住|家在|搬到|搬来|在)(?:天津市?|北京市?|上海市?|成都市?|重庆市?)?(?P<entity>[\u4e00-\u9fffA-Za-z0-9]{2,24}(?:区|县|街|路|巷|村|花园|小区|公寓|家园|苑)(?:[\u4e00-\u9fffA-Za-z0-9]{0,16}?(?:号|栋|室|单元))?)(?=[，。、的]|$)'),
        ('HOSPITAL',r'(?P<entity>[\u4e00-\u9fff]{2,22}(?:医院|心理咨询中心|心理诊所))'),
        ('SCHOOL',r'(?P<entity>[\u4e00-\u9fff]{2,18}(?:大学|中学|附中))'),
        ('ORG',r'(?P<entity>[\u4e00-\u9fff]{2,18}(?:有限公司|事业服务中心|街道办事处|公益协会))'),
    ]
    found=[]
    for item in patterns+[dict(label=l,pattern=p) for l,p in suffix_rules]:
        for m in re.finditer(item['pattern'],text):
            if 'entity' in m.re.groupindex:surface=m['entity'];start=m.start('entity')
            else:surface=m[0];start=m.start()
            found.append(dict(text=surface,label=item['label'],occ=[occurrences(text,surface).index(start)+1]))
    return {'entities':found}

def baseline(text,mode):
    if mode=='rules':return apply(text,rules_entities(text),errors=[])[0]
    if mode!='naive':raise ValueError(mode)
    # Deliberately destructive caricature of generic masking, not an actual vendor.
    patterns=[r'[0-9零〇一二两三四五六七八九十百千万]+(?:[:：点时分秒年月日号周天岁小时分钟]*)',r'(?:凌晨|半夜|晚上|早上|昨天|前天|今天|明天|上周|本周|周末|快天亮|睡前)']
    words=[]
    for name in ['cities.txt','drugs_substances.txt','apps_devices.txt','time_expressions.txt']:
        words.extend(line.split('\t')[0] for line in (ROOT/'lexicons/keep'/name).read_text(encoding='utf-8').splitlines() if line and not line.startswith('#'))
    patterns.append('|'.join(re.escape(w) for w in sorted(set(words),key=lambda w:(-len(w),w))))
    spans=[]
    for p in patterns:spans.extend((m.start(),m.end()) for m in re.finditer(p,text))
    for e in rules_entities(text)['entities']:
        starts=occurrences(text,e['text']);spans.extend((starts[n-1],starts[n-1]+len(e['text'])) for n in e['occ'])
    merged=[]
    for a,b in sorted(spans):
        if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else:merged.append((a,b))
    out=[];end=0
    for a,b in merged:out.extend([text[end:a],'[已隐藏]']);end=b
    return ''.join(out)+text[end:]

def evaluate(rows,predictions=None,mode='rewrite',baseline_name=None,session_mode=False):
    outputs={};diagnostics=[];sessions={};invalid=set();numbered=consistent=0
    predictions=predictions or {}
    if session_mode:
        if any(not r.get('session_id') or type(r.get('turn'))!=int for r in rows):
            raise ValueError('--sessions 要求每行有 session_id 和整数 turn')
        keys=[(r['session_id'],r['turn']) for r in rows]
        if len(keys)!=len(set(keys)):raise ValueError('重复会话 turn')
        rows=sorted(rows,key=lambda r:(r['session_id'],r['turn']))
    for r in rows:
        sid=r.get('session_id');mapping=sessions.get(sid,{}) if sid else {}
        if baseline_name=='naive':outputs[r['id']]=baseline(r['text'],'naive');continue
        raw=rules_entities(r['text']) if baseline_name=='rules' else predictions.get(r['id'])
        if baseline_name=='rules' or mode=='extract':
            errors=[];warnings=[]
            out,new_mapping=apply(r['text'],raw,mapping,errors=errors,warnings=warnings)
            diagnostics.extend(f'{r["id"]}: {e}' for e in errors)
            diagnostics.extend(f'{r["id"]}: warning: {w}' for w in warnings)
            if errors:invalid.add(r['id'])
            elif sid:sessions[sid]=new_mapping
            if session_mode:
                for e in r['entities']:
                    if TOKEN.fullmatch(e['replacement']):
                        numbered+=1
                        consistent+=not errors and new_mapping.get(e['label'],{}).get(e['text'])==e['replacement']
            outputs[r['id']]=out
        elif isinstance(raw,str):outputs[r['id']]=raw
        else:
            diagnostics.append(f'{r["id"]}: 缺少预测或 rewrite output 非字符串')
            invalid.add(r['id'])
    result=dict(overall=score(rows,outputs,invalid),by_tag=grouped_score(rows,outputs,invalid),diagnostics=diagnostics)
    if session_mode:
        result['session_numbering']=dict(total=numbered,correct=consistent,accuracy=consistent/numbered if numbered else None,
            note='extract 映射与会话金标编号逐实体比较，包含新实体、别名及复现；rewrite/naive 不适用')
    return result

def pct(v):return 'N/A' if v is None else f'{100*v:.2f}%'

def print_report(result):
    print('分组 | n | 泄露率 | 实体替换合法 | 临床保留 | 危机保留 | 非实体一致 | 有效输出 | 负例过脱敏 | 整句匹配')
    for key,s in [('ALL',result['overall'])]+list(result['by_tag'].items()):
        print(' | '.join([key,str(s['n'])]+[pct(s[k]) for k in ['leakage_rate','entity_replacement_legal_rate','keep_rate','crisis_keep_rate','non_entity_exact_rate','valid_output_rate','hard_negative_overredaction','exact_match']]))
    print('\n标签 | 实体数 | 泄露数 | 泄露率')
    for l,s in result['overall']['by_label'].items():print(f'{l} | {s["total"]} | {s["leaked"]} | {pct(s["leakage_rate"])}')
    if result['diagnostics']:print('\n预测问题:\n'+'\n'.join(result['diagnostics']))

def main():
    p=argparse.ArgumentParser();p.add_argument('--gold',type=Path);p.add_argument('--sessions',action='store_true');p.add_argument('--pred',type=Path);p.add_argument('--mode',choices=['extract','rewrite'],default='extract');p.add_argument('--baseline',choices=['rules','naive']);p.add_argument('--json',type=Path);args=p.parse_args()
    if bool(args.pred)==bool(args.baseline):p.error('必须且只能提供 --pred 或 --baseline')
    gold=args.gold or ROOT/('gold/sessions.jsonl' if args.sessions else 'gold/test.jsonl')
    gold=gold if gold.exists() else ROOT/gold;rows=read_jsonl(gold);pred={}
    if args.pred:
        for r in read_jsonl(args.pred):
            if not isinstance(r,dict) or not isinstance(r.get('id'),str) or 'output' not in r:p.error('pred 每行必须有 id 和 output')
            if r['id'] in pred:p.error(f'重复预测 id: {r["id"]}')
            pred[r['id']]=r['output']
        extra=set(pred)-{r['id'] for r in rows}
        if extra:p.error(f'未知预测 id: {sorted(extra)}')
    result=evaluate(rows,pred,args.mode,args.baseline,args.sessions);print_report(result)
    if args.json:args.json.parent.mkdir(parents=True,exist_ok=True);args.json.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
