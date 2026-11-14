"""SPEC v0.3 deterministic transformations; Python character offsets, not bytes."""
import re

PREFIX = dict(PERSON='人名', PHONE='电话', ID_NUM='证件号', ACCOUNT='账号', PLATE='车牌', ADDRESS='地址', ORG='单位', SCHOOL='学校', HOSPITAL='医院', BIRTH_DATE='日期')
LABELS = set(PREFIX)
PLACEHOLDER = re.compile(r'^\[[^\[\]]+\d+\]$')
def id_checksum(first17):
    if not re.fullmatch(r'\d{17}',first17): raise ValueError('身份证前17位必须为数字')
    return '10X98765432'[sum(int(a)*b for a,b in zip(first17,[7,9,10,5,8,4,2,1,6,3,7,9,10,5,8,4,2]))%11]

def luhn_valid(value):
    if not isinstance(value,str) or not value.isascii() or not value.isdigit(): return False
    digits=list(map(int,value[::-1]))
    return sum(d if i%2==0 else (2*d-9 if d>4 else 2*d) for i,d in enumerate(digits))%10==0

def occurrences(text,surface):
    if not isinstance(surface,str) or not surface: raise ValueError('实体文本必须是非空字符串')
    # Include overlapping occurrences so ambiguous spans are rejected explicitly.
    return [m.start() for m in re.finditer('(?='+re.escape(surface)+')',text)]

def replacement_for(label,surface,replacement,mapping):
    if label not in LABELS: raise ValueError(f'非法标签 {label!r}')
    prefix=PREFIX[label]
    if replacement is not None and not re.fullmatch(r'\['+prefix+r'[1-9]\d*\]',str(replacement)):
        raise ValueError(f'{label} 替换只能使用 [{prefix}N]')
    bucket=mapping.setdefault(label,{})
    if surface in bucket:
        if replacement is not None and bucket[surface]!=replacement: raise ValueError('会话映射冲突')
        return bucket[surface]
    used=[int(re.search(r'(\d+)\]$',v)[1])
          for kind, entries in mapping.items() if PREFIX.get(kind)==prefix
          for v in entries.values() if re.fullmatch(r'\['+prefix+r'[1-9]\d*\]',v)]
    result=replacement or f'[{prefix}{max(used,default=0)+1}]'
    bucket[surface]=result
    return result

def replay(text,entities):
    out=[]; end=0
    for e in entities:
        if e['start']<end: raise ValueError('实体重叠')
        out.extend([text[end:e['start']], e['replacement']]); end=e['end']
    return ''.join(out)+text[end:]
