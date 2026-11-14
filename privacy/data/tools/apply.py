"""Reference extract postprocessor. No networking or model dependency."""
import copy
import json
import logging
from .rules import LABELS, occurrences, replacement_for, replay
LOG=logging.getLogger(__name__)

def apply(text,output,mapping=None,*,errors=None,warnings=None):
    """Return (deidentified_text, new_mapping), preserving all unselected characters.

    output: JSON string or {"entities": [{"text", "label", "replacement"?,
    "occ"?: [1-based indices], "same_as"?: "[人名1]"}]}.
    All labels use numbered tokens. Model replacement fields are ignored with a warning.
    same_as can reuse an existing token of the same label (including earlier
    entities in this turn). Unknown/cross-label targets warn and allocate anew.

    Invalid JSON/entities/occ/overlap are skipped and logged (no raw text in
    logs); optional errors list receives diagnostics. Skipping is NOT a privacy
    guarantee: the caller must block cloud upload or request review on errors.
    """
    current=copy.deepcopy(mapping) if mapping is not None else {}
    def report(msg):
        LOG.warning('deid: %s',msg)
        if errors is not None: errors.append(msg)
    try:
        obj=json.loads(output) if isinstance(output,str) else output
        if not isinstance(obj,dict) or not isinstance(obj.get('entities'),list): raise ValueError('缺少 entities 数组')
    except (ValueError,TypeError):
        report('模型输出不是有效实体 JSON'); return text,current
    candidates=[]
    for i,e in enumerate(obj['entities']):
        if isinstance(e,dict) and isinstance(e.get('label'),str) and e['label'] not in LABELS:
            report(f'实体 {i}: 未知标签，跳过'); continue
        try:
            if not isinstance(e,dict) or e.get('label') not in LABELS: raise ValueError('非法标签或结构')
            if 'replacement' in e:
                msg=f'实体 {i}: replacement 字段已忽略，由代码分配占位符'
                LOG.warning('deid: %s',msg)
                if warnings is not None: warnings.append(msg)
            starts=occurrences(text,e.get('text'))
            if not starts: raise ValueError('实体未出现在原文')
            occ=e.get('occ',list(range(1,len(starts)+1)))
            if not isinstance(occ,list) or not occ or any(type(n)!=int or not 1<=n<=len(starts) for n in occ) or len(set(occ))!=len(occ): raise ValueError('occ 非法')
            for n in occ:
                candidates.append(dict(start=starts[n-1],end=starts[n-1]+len(e['text']),text=e['text'],label=e['label'],replacement=None,same_as=e.get('same_as')))
        except (ValueError,TypeError): report(f'实体 {i}: 结构/文本/occ 无效，跳过')
    accepted=[]; end=0
    for e in sorted(candidates,key=lambda e:(e['start'],-e['end'])):
        if e['start']<end:
            report('重叠实体跳过'); continue
        alias=e.get('same_as')
        if alias is not None:
            if alias in current.get(e['label'],{}).values():
                e['replacement']=alias
            else:
                msg='same_as 目标不存在或类型不匹配，按新实体处理'
                LOG.warning('deid: %s',msg)
                if warnings is not None: warnings.append(msg)
                e['replacement']=None
        try: e['replacement']=replacement_for(e['label'],e['text'],e['replacement'],current)
        except (ValueError,TypeError):
            report('替换不符合规范，跳过'); continue
        accepted.append(e); end=e['end']
    return replay(text,accepted),current
