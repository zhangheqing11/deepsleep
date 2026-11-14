"""Offline acceptance checks for the sleep de-identification corpus."""
import json
from collections import Counter
import pytest
from privacy.data.tools.rules import id_checksum, luhn_valid
from privacy.data.tools.build import compile_rows, read_jsonl, ROOT
from privacy.data.tools.apply import apply
from privacy.data.tools.validate import validate_all
from privacy.data.tools.generate import generate, make_id, make_bank
from privacy.data.tools.evaluate import score

def test_checksums():
    import random
    rng = random.Random(44)
    assert id_checksum('11010519491231002') == 'X'
    assert luhn_valid('79927398713')
    assert not luhn_valid('79927398714')
    for _ in range(100):
        ident = make_id(rng)
        assert ident[-1] == id_checksum(ident[:17])
        assert luhn_valid(make_bank(rng))

def test_compile_order_occ_and_session():
    src = [dict(id='a',session_id='s',turn=1,text='王涛和小米戴小米手环，王涛失眠',ents=[['小米','PERSON',None,[1]],['王涛','PERSON']],keep=['小米手环'],tags=[]),dict(id='b',session_id='s',turn=2,text='小米又找李河',ents=[['小米','PERSON'],['李河','PERSON']],keep=[],tags=[])]
    rows = compile_rows(src)
    assert rows[0]['deid'] == '[人名1]和[人名2]戴小米手环，[人名1]失眠'
    assert rows[1]['deid'] == '[人名2]又找[人名3]'
    with pytest.raises(ValueError): compile_rows([dict(src[0],ents=[['小米','PERSON'],['小米手环','ORG']])])

def test_apply_robust_and_session():
    mapping = {}
    out,mapping = apply('王涛失眠', {'entities':[{'text':'王涛','label':'PERSON'}]},mapping)
    assert out == '[人名1]失眠'
    out,mapping = apply('李河问王涛', {'entities':[{'text':'王涛','label':'PERSON'},{'text':'李河','label':'PERSON'}]},mapping)
    assert out == '[人名2]问[人名1]'
    errors=[]
    assert apply('睡了两小时','invalid',mapping,errors=errors)[0] == '睡了两小时'
    assert errors
    for bad in [None,[],{'entities':[None, {'text':'不存在','label':'PERSON'}, {'text':'睡','label':'BOGUS'}, {'text':'睡','label':'AGE','replacement':'[年龄1]'}]}]:
        assert apply('睡了两小时',bad,errors=[])[0] == '睡了两小时'

def test_corpus_valid():
    assert validate_all() == []
    for path in sorted((ROOT/'gold').glob('*.src.jsonl')):
        from privacy.data.tools.build import compile_source
        assert compile_source(path) == read_jsonl(path.with_name(path.name.replace('.src','')))

def test_gold_requirements():
    for split in ['dev','test']:
        rows=read_jsonl(ROOT/f'gold/{split}.jsonl')
        assert len(rows)==(153 if split=='dev' else 150)
        tags=Counter(t for r in rows for t in r['tags'])
        labels=Counter(e['label'] for r in rows for e in {e['label']:e for e in r['entities']}.values())
        assert tags['hard_negative'] >=42 and tags['ambiguous']>=15 and tags['crisis']>=8
        assert sum('crisis' in r['tags'] and bool(r['entities']) for r in rows)>=3
        assert all(labels[l]>=5 for l in ['PERSON','PHONE','ID_NUM','ACCOUNT','PLATE','ADDRESS','ORG','SCHOOL','HOSPITAL','BIRTH_DATE'])
        assert all(tags[t]>=4 for t in ['date_keep','date_birthday','age_keep'])
        assert sum(any(e['label']=='PERSON' and len(e['text'])==1 for e in r['entities']) for r in rows)>=4

def test_generate_reproducible():
    assert generate(100,77) == generate(100,77)
    rows=generate(3000,20261114)
    tags=Counter(t for r in rows for t in r['tags'])
    assert len(rows)==len({r['text'] for r in rows})==3000
    assert 1050<=tags['hard_negative']<=1500 and tags['ambiguous']>=240
    assert sum('crisis' in r['tags'] and bool(r['ents']) for r in rows)>=90

def test_gold_prediction_metrics():
    rows=read_jsonl(ROOT/'gold/test.jsonl')
    metrics=score(rows,{r['id']:r['deid'] for r in rows})
    assert metrics['leakage_rate']==0
    assert metrics['keep_rate']==metrics['crisis_keep_rate']==metrics['exact_match']==1
    assert metrics['hard_negative_overredaction']==0


def test_validation_rejects_corruption():
    from copy import deepcopy
    from privacy.data.tools.validate import validate_rows
    base=read_jsonl(ROOT/'gold/dev.jsonl')[45]
    mutations=[lambda r:r['entities'][0].update(start=-1),lambda r:r.update(deid=r['text']),lambda r:r['entities'][0].update(label='UNKNOWN'),lambda r:r['entities'][0].update(replacement='[人名9]'),lambda r:r.update(keep=['不存在']),lambda r:r.update(tags=['hard_negative']),lambda r:r.update(tags=['crisis'],keep=[]),lambda r:r.update(entities=r['entities']*2)]
    for mutate in mutations:
        row=deepcopy(base);mutate(row)
        assert validate_rows([row])
    assert validate_rows([base,base])


def test_apply_occ_overlap_unknown_label_and_alias():
    errors=[]
    out,m=apply('小米和小米手环',{'entities':[{'text':'小米','label':'PERSON','occ':[1]}]},errors=errors)
    assert out=='[人名1]和小米手环' and not errors
    for occ in [[0],[3],[1,1],'1',[True]]:
        assert apply('小米',{'entities':[{'text':'小米','label':'PERSON','occ':occ}]},errors=[])[0]=='小米'
    assert apply('我19岁',{'entities':[{'text':'19岁','label':'AGE','replacement':'二十多岁'}]},errors=[])[0]=='我19岁'
    out,m=apply('王涛和涛哥',{'entities':[{'text':'王涛','label':'PERSON'},{'text':'涛哥','label':'PERSON'}]}, {'PERSON':{'王涛':'[人名1]','涛哥':'[人名1]'}})
    assert out=='[人名1]和[人名1]'
    errors=[]
    assert apply('云禾小区12栋',{'entities':[{'text':'云禾小区12栋','label':'ADDRESS'},{'text':'云禾','label':'PERSON'}]},errors=errors)[0]=='[地址1]'
    assert errors


def test_exports_roundtrip_and_no_test_leak():
    from privacy.data.tools.build_sft import extract_target,bio
    from privacy.data.tools.prompts import EXTRACT,REWRITE
    assert len(EXTRACT)<=700 and len(REWRITE)<=700
    for path in [ROOT/'gold/seed.jsonl',ROOT/'gold/dev.jsonl',ROOT/'gold/test.jsonl',ROOT/'synth/train.jsonl']:
        for r in read_jsonl(path):
            errors=[]
            assert apply(r['text'],extract_target(r),errors=errors)[0]==r['deid'],r['id']
            assert not errors
            b=bio(r)
            assert ''.join(b['chars'])==r['text'] and len(b['chars'])==len(b['tags'])
    exported=read_jsonl(ROOT/'sft/train_extract.jsonl')+read_jsonl(ROOT/'sft/dev_extract.jsonl')
    inputs={r['messages'][-2]['content'] for r in exported}
    assert not inputs & {r['text'] for r in read_jsonl(ROOT/'gold/test.jsonl')}


def test_evaluate_occ_aware_and_missing_predictions():
    from privacy.data.tools.evaluate import evaluate
    r=compile_rows([dict(id='x',text='小米和小米手环',ents=[['小米','PERSON',None,[1]]],keep=['小米手环'],tags=['ambiguous'])])[0]
    assert score([r],{'x':r['deid']})['leakage_rate']==0
    assert score([r],{'x':r['text']})['leakage_rate']==1
    missing=evaluate([r],{},mode='rewrite')
    assert missing['overall']['leakage_rate']==1 and missing['diagnostics']
    # Dropping the entire sentence must never look like useful de-identification.
    empty=score([r],{'x':''})
    assert empty['keep_rate']==0 and empty['exact_match']==0
    assert empty['crisis_keep_rate'] is None


def test_lexicon_and_session_requirements():
    import yaml
    from privacy.data.tools.generate import lexicon
    for path,n in [('keep/time_expressions.txt',250),('keep/drugs_substances.txt',80),('keep/symptoms.txt',120),('keep/apps_devices.txt',60),('keep/occupations_shift.txt',80),('keep/relations.txt',50),('keep/generic_places.txt',50),('keep/departments.txt',30),('keep/cities.txt',200),('redact/surnames.txt',150),('redact/given_names.txt',300),('redact/nicknames.txt',80)]:
        assert len(set(lexicon(path)))>=n,path
    assert len(lexicon('keep/crisis_phrases.txt'))==30
    orgs=yaml.safe_load((ROOT/'lexicons/redact/orgs.yaml').read_text())
    assert len(set(orgs['schools']))>=60 and len(set(orgs['hospitals']))>=60
    ambiguous=read_jsonl(ROOT/'lexicons/ambiguous.jsonl')
    assert len({r['surface'] for r in ambiguous})>=50
    templates=yaml.safe_load((ROOT/'tools/templates.yaml').read_text())
    assert len({''.join(s['text'] for s in r['sentences']) if r.get('long') else r['text'] for r in templates})>=80
    sessions=Counter(r['session_id'] for r in read_jsonl(ROOT/'gold/sessions.jsonl'))
    assert len(sessions)==12 and all(n==9 for n in sessions.values())


def test_identity_checksum_birthdates_are_valid():
    from datetime import datetime
    rows=read_jsonl(ROOT/'synth/train.jsonl')
    ids=[e['text'] for r in rows for e in r['entities'] if e['label']=='ID_NUM' and len(e['text'])==18]
    assert ids
    for value in ids:
        assert value[-1]==id_checksum(value[:17])
        datetime.strptime(value[6:14],'%Y%m%d')


def test_validator_handles_broken_json_and_detects_split_leaks(tmp_path):
    from privacy.data.tools.build import write_jsonl
    (tmp_path/'gold').mkdir();(tmp_path/'synth').mkdir()
    bad=tmp_path/'gold/test.jsonl';bad.write_text('{bad json}\n',encoding='utf-8')
    errors=validate_all(tmp_path)
    assert errors and 'test.jsonl:1' in errors[0]
    row=dict(id='test',text='夜里醒',entities=[],deid='夜里醒',keep=['夜里'],tags=['hard_negative'])
    write_jsonl(bad,[row])
    write_jsonl(tmp_path/'synth/train.jsonl',[dict(row,id='train')])
    assert any('训练/金标文本泄漏' in e for e in validate_all(tmp_path))


def test_compile_invalid_occ_and_unknown_labels():
    row=dict(id='x',text='小米小米',ents=[['小米','PERSON',None,[3]]],keep=[],tags=[])
    with pytest.raises(ValueError,match='occ'):compile_rows([row])
    row.update(text='34岁',ents=[['34岁','AGE']])
    with pytest.raises(ValueError,match='非法标签'):compile_rows([row])
    row.update(text='11月21日',ents=[['11月21日','DATE','11月上旬']])
    with pytest.raises(ValueError,match='非法标签'):compile_rows([row])


def gold_row(split, rid):
    return next(r for r in read_jsonl(ROOT/f'gold/{split}.jsonl') if r['id']==rid)


def test_audit_adversarial_positions():
    # P0: a copied device KEEP may not shelter the original leaked name.
    r=gold_row('seed','seed-027')
    out=r['text'].replace('闺蜜小米','闺蜜小米手环')
    assert score([r],{r['id']:out})['by_label']['PERSON']['leaked']==1
    # P1: 电话 inside the generated placeholder is not the original keep.
    r=gold_row('test','test-055')
    out=r['deid'].replace('我接电话','我接')
    assert '[电话1]' in out
    assert score([r],{r['id']:out})['keep_rate']<1
    # P0: removing intent changes the crisis meaning and must fail.
    r=gold_row('seed','seed-025')
    result=score([r],{r['id']:r['deid'].replace('想过','')})
    assert result['crisis_keep_rate']<1 and result['non_entity_exact_rate']==0


@pytest.mark.parametrize('output',[None,'not JSON',{'entities':[{'text':'不存在的人','label':'PERSON'}]}, {'entities':[{'text':'昨晚','label':'WRONG'}]}])
def test_invalid_extract_cannot_succeed_on_negative(output):
    from privacy.data.tools.evaluate import evaluate
    r=gold_row('seed','seed-001')
    m=evaluate([r],{r['id']:output},'extract')['overall']
    assert m['valid_output_rate']==0 and m['counts']['invalid']==1
    assert m['keep_rate']==m['non_entity_exact_rate']==m['exact_match']==0
    assert m['hard_negative_overredaction']==1


def test_alignment_repeated_keep_and_insertions():
    r=compile_rows([dict(id='p',text='我接电话，电话是13812345678，我接电话会醒。',ents=[['13812345678','PHONE']],keep=['我接电话'],tags=[])])[0]
    assert score([r],{'p':r['deid']})['keep_rate']==1
    assert score([r],{'p':r['deid'].replace('我接电话','我接',1)})['keep_rate']==0
    assert score([r],{'p':r['deid']+'多睡一点'})['non_entity_exact_rate']==0
    # KEEP containing a surface elsewhere never exempts an entity occurrence.
    r=gold_row('seed','seed-027')
    assert score([r],{r['id']:r['deid']})['leakage_rate']==0
    # All original KEEP occurrences inside a gold identity are excluded from
    # its KEEP denominator: 咨询 in the clinic name vs 咨询 elsewhere.
    r=gold_row('seed','seed-032')
    assert score([r],{r['id']:r['deid']})['keep_rate']==1


def test_birth_date_numbering_and_calendar_keep():
    from privacy.data.tools.rules import replacement_for
    out,m=apply('我生于1998年，姐姐生于1997年。',{'entities':[{'text':'1998年','label':'BIRTH_DATE'},{'text':'1997年','label':'BIRTH_DATE'}]})
    assert out=='我生于[日期1]，姐姐生于[日期2]。'
    assert replacement_for('BIRTH_DATE','六月',None,m)=='[日期3]'
    assert gold_row('seed','seed-015')['entities'][0]['label']=='BIRTH_DATE'
    assert gold_row('dev','dev-096')['entities']==[]


def test_alias_adoption_fallback_and_mapping_isolation(caplog):
    initial={'PERSON':{'王涛':'[人名1]'},'PHONE':{'123':'[电话1]'}}
    out,m=apply('涛子说昨晚没睡',{'entities':[{'text':'涛子','label':'PERSON','same_as':'[人名1]'}]},initial)
    assert out=='[人名1]说昨晚没睡' and '涛子' not in initial['PERSON']
    for alias in ['[人名9]','[电话1]']:
        warnings=[];errors=[]
        out,m=apply('小河醒了',{'entities':[{'text':'小河','label':'PERSON','same_as':alias}]},initial,warnings=warnings,errors=errors)
        assert out=='[人名2]醒了' and warnings and not errors
    assert 'same_as' in caplog.text


def test_keep_validation_and_crisis_full_clause():
    from privacy.data.tools.validate import validate_rows
    r=dict(id='v',text='我最近不想活了',entities=[],deid='我最近不想活了',keep=[],tags=[])
    assert validate_rows([r])
    assert validate_rows([dict(r,tags=['no_clinical'])])
    assert not validate_rows([dict(r,text='已登记',deid='已登记',tags=['no_clinical'],note='仅登记，无临床信息')])
    assert validate_rows([dict(r,tags=['crisis'],keep=['不想活了'])])
    assert not validate_rows([dict(r,tags=['crisis'],keep=['我最近不想活了'])])


def test_long_and_sessions_roundtrip():
    from privacy.data.tools.build_sft import extract_target,session_messages
    from privacy.data.tools.evaluate import evaluate
    for split in ['dev','test']:
        long=[r for r in read_jsonl(ROOT/f'gold/{split}.jsonl') if 'long' in r['tags']]
        assert len(long)==30
        assert all(2<=len(r['keep'])<=6 for r in long)
        assert all(60<=len(r['text'])<=200 and (not r['entities'] or 1<=len(r['entities'])<=5) for r in long)
    train=read_jsonl(ROOT/'synth/train.jsonl')
    assert sum('long' in r['tags'] for r in train)==600
    assert all(60<=len(r['text'])<=200 for r in train if 'long' in r['tags'])
    for path in [ROOT/'gold/sessions.jsonl',ROOT/'synth/sessions_train.jsonl',ROOT/'synth/sessions_dev.jsonl']:
        rows=read_jsonl(path);groups=Counter(r['session_id'] for r in rows)
        assert sum(not r['entities'] for r in rows)/len(rows)>=.3
        if path.parent.name=='synth':assert all(4<=n<=8 for n in groups.values())
        if path.name=='sessions_train.jsonl':assert len(groups)>=200
        maps={};pred={}
        for r in rows:
            mapping=maps.get(r['session_id'],{})
            pred[r['id']]=extract_target(r,mapping)
            out,m=apply(r['text'],pred[r['id']],mapping)
            assert out==r['deid'],r['id']
            maps[r['session_id']]=m
        metrics=evaluate(list(reversed(rows)),pred,'extract',session_mode=True)
        assert metrics['overall']['exact_match']==1
        assert metrics['overall']['valid_output_rate']==1
        assert metrics['session_numbering']['accuracy']==1
        exported=session_messages(rows)
        assert all('本会话已有映射：' in r['messages'][1]['content'] and '\n当前发言：' in r['messages'][1]['content'] for r in exported)
        assert any('same_as' in r['messages'][2]['content'] for r in exported)
    # Gold sessions stay evaluation-only; dev synthetic sessions remain whole.
    ids=[]
    for split in ['train','dev']:
        ids.append({r['session_id'] for r in read_jsonl(ROOT/f'synth/sessions_{split}.jsonl')})
        rows=read_jsonl(ROOT/f'sft/{split}_session_extract.jsonl')
        assert len(rows)==len(read_jsonl(ROOT/f'synth/sessions_{split}.jsonl'))
        assert not {r['messages'][1]['content'].split('\n当前发言：')[1] for r in rows}&{r['text'] for r in read_jsonl(ROOT/'gold/sessions.jsonl')}
    assert ids[0].isdisjoint(ids[1])


def test_synthetic_semantic_constraints():
    import re
    rows=read_jsonl(ROOT/'synth/train.jsonl')
    for r in rows:
        text=r['text']
        assert not re.search(r'喝了(?:烟|香烟|电子烟|尼古丁|巧克力)',text)
        assert not re.search(r'拿Oura Ring看时间|(?:玩|刷)(?:拼多多|百度网盘|支付宝)|看(?:原神|和平精英)',text)
        for m in re.finditer(r'(?:昨晚|凌晨|半夜|夜里)(\d+)点',text):assert int(m[1])>=20 or int(m[1])<=6
        for e in r['entities']:
            if e['label']=='ID_NUM' and len(e['text'])==18:assert '身份证' in text
        if '医保卡' in text:assert any(e['text'].startswith('YB') for e in r['entities'])
        if '门诊号' in text:assert any(e['text'].startswith('MZ') for e in r['entities'])
        if '住院号' in text:assert any(e['text'].startswith('ZY') for e in r['entities'])
        if 'tpl-07' in r['note'] and 'ambiguous' in r['tags']:
            assert any(rel in text for rel in ['我闺蜜','我的对象','我的雇主','我的单位','我的工作单位'])
    assert all(any(term in r['text'] for r in rows) for term in ['王医生','欧阳老师','李姐','老张','小陈'])


def test_alignment_keeps_clinical_brackets_and_ignores_tokens_as_leaks():
    r=compile_rows([dict(id='b',text='我叫人名，量表[ISI 18分]。',ents=[['人名','PERSON']],keep=['[ISI 18分]'],tags=[])])[0]
    m=score([r],{'b':r['deid']})
    assert m['keep_rate']==1 and m['leakage_rate']==0


@pytest.mark.parametrize('tags',[[],['hard_negative']])
def test_keep_count_limits_apply_to_every_row(tags):
    from privacy.data.tools.validate import validate_rows
    text='早醒心慌打鼾困倦夜班午睡憋醒'
    row=dict(id='limits',text=text,deid=text,entities=[],tags=tags,
             keep=['早醒','心慌','打鼾','困倦','夜班','午睡'])
    assert validate_rows([row])==[]
    assert any('个数' in e for e in validate_rows([dict(row,keep=row['keep']+['憋醒'])]))
    assert validate_rows([dict(row,keep=[])])
    assert validate_rows([dict(row,keep=[],tags=tags+['no_clinical'],note='测试仅身份核对的显式豁免')])==[]
    assert validate_rows([dict(row,keep=row['keep']+['憋醒'],tags=['no_clinical'],note='不豁免上限')])


@pytest.mark.parametrize('crisis,limit',[(False,30),(True,50)])
def test_keep_fragment_length_boundary(crisis,limit):
    from privacy.data.tools.validate import validate_rows
    text='我'+''.join(chr(0x4e10+i) for i in range(120))
    row=dict(id='length',text=text,deid=text,entities=[],tags=['crisis'] if crisis else [],keep=[text[:limit]])
    assert validate_rows([row])==[]
    assert any('每个 keep 长度' in e for e in validate_rows([dict(row,keep=[text[:limit+1]])]))


@pytest.mark.parametrize('entity',[False,True])
def test_keep_density_boundary_uses_non_entity_length(entity):
    from privacy.data.tools.validate import validate_rows
    text=''.join(chr(0x4e10+i) for i in range(70))
    src=dict(id='density',text=('王涛'+text if entity else text),ents=[['王涛','PERSON']] if entity else [],
             tags=[] if entity else ['hard_negative'],keep=[text[:21],text[21:42]])
    row=compile_rows([src])[0]
    assert validate_rows([row])==[]  # Exactly 42 / 70 = 60%.
    row['keep']=[text[:21],text[21:43]]
    assert any('60%' in e for e in validate_rows([row]))
    # 60 characters is exempt (dense short sentences such as seed-014), 61 is not.
    for n,valid in [(60,True),(61,False)]:
        r=dict(id='threshold',text=text[:n],deid=text[:n],entities=[],tags=[],keep=[text[:20],text[20:40]])
        assert (validate_rows([r])==[])==valid


def test_keep_requires_an_original_occurrence_outside_entities():
    from privacy.data.tools.validate import validate_rows
    row=compile_rows([dict(id='overlap',text='我叫小米，用小米手环。',ents=[['小米','PERSON',None,[1]]],keep=['小米手环'],tags=[])])[0]
    assert validate_rows([row])==[]
    row['keep']=['我叫小米']
    assert any('不跨实体' in e for e in validate_rows([row]))


def test_long_keep_is_union_of_selected_sentence_annotations():
    from privacy.data.tools.generate import compose_long,render,load_yaml,distinct_keep
    assert distinct_keep(['早醒','五点早醒','早醒','夜班'])==['五点早醒','夜班']
    template=next(t for t in load_yaml('tools/templates.yaml') if t['id']=='tpl-114')
    for n in [2,3,4]:
        row=render(compose_long(template,n),{'time':'两点'}, {})
        expected=[k.format(time='两点') for s in template['sentences'][:n] for k in s['keep']]
        expected=list(dict.fromkeys(expected))
        assert set(row['keep'])=={k for k in expected if not any(k!=v and k in v for v in expected)}
        assert ('困了再回床上' in row['keep'])==(n==4)
        assert not any(k==row['text'].rstrip('。') for k in row['keep'])


def test_clinical_keep_and_non_entity_exact_measure_different_changes():
    row=gold_row('dev','dev-121')
    assert 2<=len(row['keep'])<=6
    output=row['deid'].replace('最近项目交完了','最近项目做完了')
    assert output!=row['deid']
    m=score([row],{row['id']:output})
    assert m['keep_rate']==1 and m['non_entity_exact_rate']==0
    output=row['deid'].replace('两点才睡','三点才睡')
    assert score([row],{row['id']:output})['keep_rate']<1


def test_long_crisis_keeps_retain_history_and_current_negation():
    for split,rid,terms in [('dev','dev-150',['以前','现在没有']),
                            ('test','test-127',['我曾经跟','现在已经没有','不是说']),
                            ('test','test-139',['以前','现在没有'])]:
        row=gold_row(split,rid)
        for term in terms:
            output=row['deid'].replace(term,'',1)
            assert score([row],{rid:output})['crisis_keep_rate']<1,(rid,term)


def test_audit2_crisis_subjects_and_session_keep():
    for split,rid,subject in [('sessions','session-10-05','我跟'),
                              ('sessions','session-10-01','我叫'),
                              ('dev','dev-111','我叫'),('seed','seed-026','我住在')]:
        row=gold_row(split,rid)
        for replacement in ['',subject.replace('我','他')]:
            assert score([row],{rid:row['deid'].replace(subject,replacement,1)})['crisis_keep_rate']<1
    for split,rid,before,after in [('sessions','session-11-06','比我精神','比我没精神'),
                                  ('sessions','session-08-01','白天别打','白天打'),
                                  ('test','test-054','白天别打','白天打')]:
        row=gold_row(split,rid)
        assert score([row],{rid:row['deid'].replace(before,after)})['keep_rate']<1
    row=gold_row('sessions','session-12-02')
    assert row['keep']==[] and 'no_clinical' in row['tags'] and row['note']


def test_audit2_near_name_rewrite_is_illegal():
    from privacy.data.tools.evaluate import evaluate
    row=gold_row('dev','dev-121')
    out=row['deid'].replace('[人名1]','林霜')
    metrics=evaluate([row],{row['id']:out},'rewrite')['overall']
    assert metrics['leakage_rate']==0 and metrics['keep_rate']==1
    assert metrics['entity_replacement_legal_rate']<1
    assert metrics['by_label']['PERSON']['replacement_legal']==0


@pytest.mark.parametrize('replacement,legal',[
    ('[人名7]',True),('林霜',False),('[电话1]',False),('[人名0]',False),
    ('[人名1]林霜',False),('',False),('林雪',False),('[已隐藏]',False)])
def test_replacement_legality_type_and_whole_region(replacement,legal):
    row=compile_rows([dict(id='legal',text='林雪昨晚早醒',ents=[['林雪','PERSON']],keep=['昨晚早醒'],tags=[])])[0]
    out=replacement+'昨晚早醒'
    assert score([row],{'legal':out})['entity_replacement_legal_rate']==int(legal)


def test_replacement_legality_adjacent_tokens_and_invalid():
    row=compile_rows([dict(id='adj',text='林雪13812345678，34岁，11月8号早醒',
        ents=[['林雪','PERSON'],['13812345678','PHONE']],
        keep=['34岁','11月8号早醒'],tags=[])])[0]
    assert score([row],{'adj':row['deid']})['entity_replacement_legal_rate']==1
    assert score([row],{'adj':row['deid'].replace('[电话1]','[日期1]')})['counts']['replacement_legal']==0
    assert score([row],{'adj':row['deid']},invalid={'adj'})['entity_replacement_legal_rate']==0
    negative=gold_row('seed','seed-001')
    assert score([negative],{negative['id']:negative['deid']})['entity_replacement_legal_rate'] is None


def test_replacement_legality_all_gold_and_extract():
    from privacy.data.tools.evaluate import evaluate
    from privacy.data.tools.build_sft import extract_target
    for split in ['seed','dev','test','sessions']:
        rows=read_jsonl(ROOT/f'gold/{split}.jsonl')
        assert score(rows,{r['id']:r['deid'] for r in rows})['entity_replacement_legal_rate']==1
    row=gold_row('dev','dev-121')
    assert evaluate([row],{row['id']:extract_target(row)},'extract')['overall']['entity_replacement_legal_rate']==1
    # apply emits legal tokens, but a missed gold entity still fails this metric.
    assert evaluate([row],{row['id']:{'entities':[]}},'extract')['overall']['entity_replacement_legal_rate']==0


def test_adversarial_tag_is_reported_separately():
    from privacy.data.tools.evaluate import evaluate
    rows=read_jsonl(ROOT/'gold/dev.jsonl')
    assert {'dev-143','dev-147','dev-150'}<={r['id'] for r in rows if 'adversarial' in r['tags']}
    result=evaluate(rows,{r['id']:r['deid'] for r in rows},'rewrite')
    assert result['by_tag']['adversarial']['n']==sum('adversarial' in r['tags'] for r in rows)


def test_audit2_generated_birthdays_addresses_and_repetitions():
    import re
    from privacy.data.tools.generate import DOMESTIC_ADDRESS_CITIES
    rows=read_jsonl(ROOT/'synth/train.jsonl')
    for row in rows:
        text=row['text']
        if 'tpl-035。' in row['note']:
            assert re.match(r'生日\d{1,2}月\d{1,2}号不想过',text)
            assert next(e for e in row['entities'] if e['label']=='BIRTH_DATE')['text'] in text
        if 'tpl-037。' in row['note']:
            assert any(text.startswith('我住'+city) for city in DOMESTIC_ADDRESS_CITIES)
        if any(e['label']=='BIRTH_DATE' and re.fullmatch(r'\d{4}年',e['text']) for e in row['entities']):
            assert '我出生于' in text
        for m in re.finditer(r'(?=([\u4e00-\u9fff]{2,4})\1)',text):
            assert any(e['start']<=m.start() and e['end']>=m.start()+len(m[1])*2 for e in row['entities']),row['id']


def test_audit2_full_crisis_pronoun_scan_has_only_reviewed_gold_contexts():
    from privacy.data.tools.scan_audit2 import scan
    from privacy.data.tools.validate import compiled_paths
    result=scan()
    # These pronouns refer to metadata/clarification/contact, not an uncovered
    # risk subject. The actual risk clause's subject is covered where present.
    gold=[c for c in result['uncovered_crisis_pronouns'] if c['file'].startswith('gold/')]
    assert Counter(c['id'] for c in gold)==Counter({'dev-150':2,'test-111':1,'test-112':1,'test-113':1,'test-139':1})
    assert result['crisis_rows']==sum('crisis' in r['tags'] for p in compiled_paths() for r in read_jsonl(p))


@pytest.mark.parametrize('label,surface', [('DATE','10月8号'),('AGE','刚满61')])
def test_v03_rejects_legacy_labels(label,surface):
    from privacy.data.tools.validate import validate_rows
    from privacy.data.tools.evaluate import evaluate
    errors=[]
    text=surface+'，早醒'
    output={'entities':[{'text':surface,'label':label}]}
    out,mapping=apply(text,output,errors=errors)
    assert out==text and errors and mapping=={}
    row=compile_rows([dict(id='legacy',text=text,ents=[],keep=[surface,'早醒'],tags=['hard_negative'])])[0]
    assert evaluate([row],{'legacy':output},'extract')['overall']['valid_output_rate']==0
    row['entities']=[dict(text=surface,label=label,start=0,end=len(surface),replacement='[日期1]')]
    assert validate_rows([row])


@pytest.mark.parametrize('replacement',[None,'任意改写','[人名99]',{'bad':'structure'}])
def test_v03_model_replacement_is_ignored_with_warning(replacement):
    errors=[];warnings=[]
    out,mapping=apply('张涛早醒',{'entities':[{'text':'张涛','label':'PERSON','replacement':replacement}]},errors=errors,warnings=warnings)
    assert out=='[人名1]早醒' and not errors and len(warnings)==1
    assert mapping=={'PERSON':{'张涛':'[人名1]'}}
    from privacy.data.tools.evaluate import evaluate
    row=compile_rows([dict(id='warn',text='张涛早醒',ents=[['张涛','PERSON']],keep=['早醒'],tags=[])])[0]
    result=evaluate([row],{'warn':{'entities':[{'text':'张涛','label':'PERSON','replacement':replacement}]}},'extract')
    assert result['overall']['valid_output_rate']==1 and 'warning' in result['diagnostics'][0]


@pytest.mark.parametrize('text', ['我刚满61，10月8号开始失眠','我三十四了，十一月三号早醒','我16岁，2026-11-03开始换班'])
def test_v03_naive_masks_dates_ages_rules_preserves_them(text):
    from privacy.data.tools.evaluate import baseline
    assert baseline(text,'rules')==text
    assert baseline(text,'naive')!=text


def test_v03_birthday_calendar_age_contrast_occurrence():
    from privacy.data.tools.build_sft import extract_target,bio
    row=compile_rows([dict(id='contrast',text='我1990年出生，36岁，生日是5月17日，5月17日开始失眠。',
        ents=[['1990年','BIRTH_DATE'],['5月17日','BIRTH_DATE',None,[1]]],
        keep=['36岁','5月17日开始失眠'],tags=['age_keep','date_keep'])])[0]
    assert row['deid']=='我[日期1]出生，36岁，生日是[日期2]，5月17日开始失眠。'
    target=extract_target(row)
    assert target['entities'][1]['occ']==[1]
    assert all('replacement' not in e for e in target['entities'])
    assert apply(row['text'],target)[0]==row['deid']
    assert score([row],{row['id']:row['deid']})['keep_rate']==1
    assert set(bio(row)['tags'])=={'O','B-BIRTH_DATE','I-BIRTH_DATE'}


def test_v03_generated_keep_variants_and_contrasts():
    rows=read_jsonl(ROOT/'synth/train.jsonl')
    for value in ['刚满61','三十四了','十一月三号','六月二十一日']:
        assert any(any(value in k for k in r['keep']) for r in rows),value
    assert all(any(f'tpl-{i:03}。' in r['note'] for r in rows) for i in range(121,127))
    for row in rows:
        if 'date_keep' in row['tags'] or 'age_keep' in row['tags']:
            assert row['keep'] and all(k in row['deid'] for k in row['keep'])


def test_v03_full_compiled_and_sft_scan():
    from privacy.data.tools.scan_v03 import scan
    assert scan()['errors']==[]


@pytest.mark.parametrize('artifact', ['compiled_label','compiled_generalization','sft_label','sft_generalization','bio'])
def test_v03_scan_rejects_stale_artifacts(tmp_path,artifact):
    from privacy.data.tools.build import write_jsonl
    from privacy.data.tools.scan_v03 import scan
    text='我34岁，10月8号早醒'
    row=dict(id='x',text=text,deid=text,entities=[],keep=['34岁','10月8号早醒'],tags=['hard_negative'])
    if artifact=='compiled_label':row['entities']=[dict(label='AGE',text='34岁')]
    if artifact=='compiled_generalization':row['deid']='我三十多岁，10月上旬早醒'
    write_jsonl(tmp_path/'gold/seed.jsonl',[row])
    if artifact=='bio':
        write_jsonl(tmp_path/'sft/ner_bio_train.jsonl',[dict(chars=list(text),tags=['B-AGE']+['O']*(len(text)-1))])
    elif artifact.startswith('sft_'):
        mode='extract' if artifact=='sft_label' else 'rewrite'
        target=json.dumps({'entities':[{'text':'34岁','label':'AGE'}]},ensure_ascii=False) if mode=='extract' else '我三十多岁，10月上旬早醒'
        write_jsonl(tmp_path/f'sft/train_{mode}.jsonl',[{'messages':[dict(role='user',content=text),dict(role='assistant',content=target)]}])
    assert scan(tmp_path)['errors']


def test_v03_scan_allows_original_generalized_language(tmp_path):
    from privacy.data.tools.build import write_jsonl
    from privacy.data.tools.scan_v03 import scan
    text='我三十多岁，十月上旬早醒'
    write_jsonl(tmp_path/'gold/seed.jsonl',[dict(id='original',text=text,deid=text,entities=[],keep=['早醒'],tags=['hard_negative'])])
    write_jsonl(tmp_path/'sft/train_rewrite.jsonl',[{'messages':[dict(role='user',content=text),dict(role='assistant',content=text)]}])
    assert scan(tmp_path)['errors']==[]
