"""Check every source/compiled/SFT artifact against the v0.3 label/KEEP policy."""
import json
import re
from collections import Counter
from .build import ROOT, read_jsonl
from .validate import compiled_paths

LEGACY={'DATE','AGE'}
GENERALIZED=re.compile(r'上旬|中旬|下旬|[零一二三四五六七八九两\d]十多岁|十几岁|不到十岁')


def scan(root=ROOT):
    errors=[];counts=dict(compiled_rows=0,source_rows=0,sft_rows=0)
    def check_output(source,output,where):
        added=Counter(GENERALIZED.findall(output))-Counter(GENERALIZED.findall(source))
        if added:errors.append(f'{where}: 新增泛化产物 {dict(added)}')
    def check_labels(value,where):
        if isinstance(value,dict):
            if value.get('label') in LEGACY:errors.append(f'{where}: 旧实体标签')
            if LEGACY.intersection(value):errors.append(f'{where}: 旧映射标签')
            for v in value.values():check_labels(v,where)
        elif isinstance(value,list):
            for v in value:check_labels(v,where)
    for path in compiled_paths(root):
        for row in read_jsonl(path):
            counts['compiled_rows']+=1;where=f'{path.relative_to(root)}:{row["id"]}'
            check_labels(row,where);check_output(row['text'],row['deid'],where)
            if {'age','date_generalize'}.intersection(row['tags']):errors.append(f'{where}: 旧 tag')
    for folder in ['gold','synth']:
        for path in sorted((root/folder).glob('*.src.jsonl')):
            for row in read_jsonl(path):
                counts['source_rows']+=1
                if any(e[1] in LEGACY for e in row['ents']):errors.append(f'{path.name}:{row["id"]}: 旧源标签')
    for path in sorted((root/'sft').glob('*.jsonl')):
        for i,row in enumerate(read_jsonl(path),1):
            counts['sft_rows']+=1;where=f'{path.relative_to(root)}:{i}'
            if 'chars' in row:
                if set(row['tags']) & {'B-DATE','I-DATE','B-AGE','I-AGE'}:errors.append(f'{where}: 旧 BIO 标签')
                continue
            source=''
            for message in row['messages']:
                content=message['content'];role=message['role']
                if role=='system':
                    if re.search(r'\b(?:DATE|AGE)\b',content) or GENERALIZED.search(content):errors.append(f'{where}: 旧 system prompt')
                elif role=='user':source=content
                elif role=='assistant':
                    check_output(source,content,where)
                    if 'extract' in path.stem:
                        target=json.loads(content);check_labels(target,where)
                        if any('replacement' in e for e in target['entities']):errors.append(f'{where}: extract 含 replacement')
    return dict(spec_version='0.3',**counts,errors=errors)


def main():
    result=scan()
    (ROOT/'SCAN_V03.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    if result['errors']:raise SystemExit(1)


if __name__=='__main__':main()
