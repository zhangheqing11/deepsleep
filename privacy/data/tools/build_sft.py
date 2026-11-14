"""Export OpenAI messages and character BIO; held-out test is never exported."""
import argparse
import copy
import json
from .build import ROOT,read_jsonl,write_jsonl
from .rules import LABELS,occurrences
from .prompts import EXTRACT,REWRITE,FEW_SHOTS

def extract_target(row,mapping=None):
    current=copy.deepcopy(mapping or {})
    groups={}
    for e in row['entities']:
        if e['label'] not in LABELS:raise ValueError('未知实体标签')
        key=(e['text'],e['label'])
        alias=None
        bucket=current.setdefault(e['label'],{})
        if e['text'] not in bucket and e['replacement'] in bucket.values():alias=e['replacement']
        bucket[e['text']]=e['replacement']
        key=(*key,alias)
        groups.setdefault(key,[]).append(occurrences(row['text'],e['text']).index(e['start'])+1)
    entities=[]
    for (surface,label,alias),occ in groups.items():
        ent=dict(text=surface,label=label)
        if alias is not None:ent['same_as']=alias
        if len(occ)!=len(occurrences(row['text'],surface)):ent['occ']=occ
        entities.append(ent)
    return {'entities':entities}

def messages(row,mode,few_shot=False):
    out=[dict(role='system',content=EXTRACT if mode=='extract' else REWRITE)]
    if few_shot:
        for user,extract,rewrite in FEW_SHOTS:
            out.extend([dict(role='user',content=user),dict(role='assistant',content=json.dumps(extract,ensure_ascii=False,separators=(',',':')) if mode=='extract' else rewrite)])
    out.extend([dict(role='user',content=row['text']),dict(role='assistant',content=json.dumps(extract_target(row),ensure_ascii=False,separators=(',',':')) if mode=='extract' else row['deid'])])
    return {'messages':out}

def bio(row):
    tags=['O']*len(row['text'])
    for e in row['entities']:
        if e['label'] not in LABELS:raise ValueError('未知实体标签')
        tags[e['start']]='B-'+e['label']
        tags[e['start']+1:e['end']]=['I-'+e['label']]*(e['end']-e['start']-1)
    return dict(id=row['id'],chars=list(row['text']),tags=tags)

def session_messages(rows):
    """Teacher-forced existing mappings, reset only at a session boundary."""
    from .apply import apply
    mappings={};result=[]
    for row in sorted(rows,key=lambda r:(r['session_id'],r['turn'])):
        mapping=mappings.get(row['session_id'],{})
        target=extract_target(row,mapping)
        user='本会话已有映射：'+json.dumps(mapping,ensure_ascii=False,separators=(',',':'))+'\n当前发言：'+row['text']
        result.append({'messages':[dict(role='system',content=EXTRACT),dict(role='user',content=user),dict(role='assistant',content=json.dumps(target,ensure_ascii=False,separators=(',',':')))]})
        errors=[];warnings=[]
        output,mapping=apply(row['text'],target,mapping,errors=errors,warnings=warnings)
        if errors or warnings or output!=row['deid']:raise ValueError('会话导出回放不一致: '+row['id'])
        mappings[row['session_id']]=mapping
    return result


def build_sft(few_shot=False):
    splits=dict(train=read_jsonl(ROOT/'synth/train.jsonl')+read_jsonl(ROOT/'gold/seed.jsonl'),dev=read_jsonl(ROOT/'gold/dev.jsonl'))
    info={}
    for split,rows in splits.items():
        for mode in ['extract','rewrite']:
            name=f'{split}_{mode}';write_jsonl(ROOT/f'sft/{name}.jsonl',[messages(r,mode,few_shot) for r in rows])
            info[name]=dict(file_name=f'{name}.jsonl',formatting='sharegpt',columns={'messages':'messages'},tags=dict(role_tag='role',content_tag='content',user_tag='user',assistant_tag='assistant',system_tag='system'))
        write_jsonl(ROOT/f'sft/ner_bio_{split}.jsonl',[bio(r) for r in rows])
    for split in ['train','dev']:
        name=f'{split}_session_extract'
        rows=read_jsonl(ROOT/f'synth/sessions_{split}.jsonl')
        write_jsonl(ROOT/f'sft/{name}.jsonl',session_messages(rows))
        info[name]=dict(info['train_extract'],file_name=f'{name}.jsonl')
    (ROOT/'sft/dataset_info.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('SFT:',', '.join(f'{k}={len(v)}' for k,v in splits.items()))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--few-shot',action='store_true');args=p.parse_args();build_sft(args.few_shot)
