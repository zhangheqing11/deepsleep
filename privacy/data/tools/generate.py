"""Seeded synthetic-only corpus generator; no network, real-person lookup or LLM."""
import argparse
import copy
import re
import random
import string
from functools import lru_cache
from datetime import date,timedelta
import yaml
from .build import ROOT,read_jsonl,write_jsonl,compile_rows
from .rules import id_checksum,luhn_valid,occurrences

def lexicon(name):
    return [line.split('\t')[0] for line in (ROOT/'lexicons'/name).read_text(encoding='utf-8').splitlines() if line and not line.startswith('#')]

@lru_cache(maxsize=None)
def load_yaml(name):return yaml.safe_load((ROOT/name).read_text(encoding='utf-8'))

def make_id(rng):
    regions=load_yaml('lexicons/redact/patterns.yaml')['id_region_codes']
    birthday=date(1950,1,1)+timedelta(days=rng.randrange(24000))
    first=rng.choice(regions)+birthday.strftime('%Y%m%d')+f'{rng.randint(1,999):03}'
    return first+id_checksum(first)

def make_bank(rng):
    first='622202'+''.join(str(rng.randrange(10)) for _ in range(12))
    return next(first+str(n) for n in range(10) if luhn_valid(first+str(n)))

def make_phone(rng):
    n=rng.choice(['138','139','150','156','158','159','176','187','189'])+''.join(str(rng.randrange(10)) for _ in range(8))
    style=rng.randrange(6)
    return [n,'+86 '+n[:3]+' '+n[3:7]+' '+n[7:],n[:3]+' '+n[3:7]+' '+n[7:],n[:3]+'-'+n[3:7]+'-'+n[7:],''.join('零一二三四五六七八九'[int(c)] for c in n),'022-'+str(rng.randint(60000000,89999999))][style]

ENTITY_LABELS=dict(person='PERSON',phone='PHONE',ident='ID_NUM',work_id='ID_NUM',medical_id='ID_NUM',email='ACCOUNT',account='ACCOUNT',bank='ACCOUNT',plate='PLATE',address='ADDRESS',org='ORG',school='SCHOOL',hospital='HOSPITAL',birthyear='BIRTH_DATE',birthday='BIRTH_DATE',birthday_md='BIRTH_DATE',surname='PERSON',insurance_id='ID_NUM',outpatient_id='ID_NUM',inpatient_id='ID_NUM',record_id='ID_NUM')

def compose_long(template, count):
    """Only selected sentences contribute text and manually annotated KEEP."""
    sentences=template['sentences'][:count]
    return dict(template,text=''.join(s['text'] for s in sentences),
                keep=[k for s in sentences for k in s['keep']],
                tags=list(dict.fromkeys(template['tags']+[tag for s in sentences for tag in s.get('tags',[])])))

def distinct_keep(fragments):
    """Stable union; a containing phrase already protects its shorter fragment."""
    unique=list(dict.fromkeys(fragments))
    return [k for k in unique if not any(k!=other and k in other for other in unique)]

def render(template,values,labels):
    text='';spans=[]
    for literal,field,fmt,conversion in string.Formatter().parse(template['text']):
        text+=literal
        if field:
            value=values[field];start=len(text);text+=value
            if field in labels:
                label=labels[field]
                spans.append((start,value,label,None))
    groups={}
    for start,surface,label,repl in spans:
        occ=occurrences(text,surface).index(start)+1
        groups.setdefault((surface,label,repl),[]).append(occ)
    ents=[];tags=list(template['tags'])
    for (surface,label,repl),occ in groups.items():
        ent=[surface,label]
        if repl is not None or len(occ)!=len(occurrences(text,surface)):ent.append(repl)
        if len(occ)!=len(occurrences(text,surface)):ent.append(occ)
        ents.append(ent)
        tags.append('date_birthday' if label=='BIRTH_DATE' else label.lower())
    fields={field for _,field,_,_ in string.Formatter().parse(template['text']) if field}
    for field in ['age','day']:
        if field in fields:tags.append('age_keep' if field=='age' else 'date_keep')
    if not ents:tags.append('hard_negative')
    keep=distinct_keep([k.format(**values) for k in template['keep']])
    return dict(text=text,ents=ents,keep=keep,tags=list(dict.fromkeys(tags)),note=f'虚构模板合成；{template["id"]}。号码仅格式有效，禁止拨打或查询。')

DOMESTIC_ADDRESS_CITIES=('北京','天津','上海','重庆','南京','苏州','杭州','成都','武汉','广州','深圳')


def generate(n=3000,seed=20261114):
    if n<0:raise ValueError('n 不能为负数')
    rng=random.Random(seed)
    vocabulary={key:lexicon(path) for key,path in dict(person_surname='redact/surnames.txt',person_given='redact/given_names.txt',symptom='keep/symptoms.txt',city='keep/cities.txt',relation='keep/relations.txt').items()}
    typed=lambda name: [line.split('\t') for line in (ROOT/'lexicons/keep'/name).read_text(encoding='utf-8').splitlines() if line and not line.startswith('#')]
    drug_terms=typed('drugs_substances.txt'); app_terms=typed('apps_devices.txt')
    drugs=[w for w,c in drug_terms if c=='药物或补充剂']
    # Action/capability pools intentionally narrower than the recall lexicons.
    substances=['咖啡','浓茶','红茶','酒','红牛','能量饮料','热巧克力']
    substance_actions=[('喝了'+w,w) for w in substances]+[('抽了烟','烟'),('抽了香烟','香烟'),('抽了电子烟','电子烟')]
    app_actions=[('刷抖音','抖音'),('刷快手','快手'),('刷小红书','小红书'),('玩王者荣耀','王者荣耀'),('玩和平精英','和平精英'),('玩原神','原神'),('玩梦幻西游','梦幻西游'),('玩崩坏星穹铁道','崩坏星穹铁道'),('在七猫小说看小说','七猫小说'),('在番茄小说看小说','番茄小说'),('逛拼多多','拼多多'),('逛京东','京东'),('在百度网盘看视频','百度网盘'),('看腾讯视频','腾讯视频')]
    screen_devices=['Apple Watch','华为手表','小米手环','手机']
    monitor_devices=['Apple Watch','华为手环','小米手环','Oura Ring']
    apps=[w for w,c in app_terms if c in ['app','game']]
    devices=[w for w,c in app_terms if c=='device']
    occupations=lexicon('keep/occupations_shift.txt')
    occupations=['客服','保安','运维人员','仓库管理员','护士']
    orgs=load_yaml('lexicons/redact/orgs.yaml');addresses=load_yaml('lexicons/redact/address_parts.yaml')
    templates=load_yaml('tools/templates.yaml');by_kind={(kind,long):[t for t in templates if t['kind']==kind and bool(t.get('long'))==long] for kind in ['negative','normal','ambiguous','crisis'] for long in [False,True]}
    seen={r['text'] for p in (ROOT/'gold').glob('*.src.jsonl') for r in read_jsonl(p)}
    result=[];attempts=0
    while len(result)<n:
        attempts+=1
        if attempts>max(10000,n*100):raise RuntimeError('模板空间不足以生成不重复文本')
        index=len(result);bucket=index%100
        kind='negative' if bucket<38 else 'ambiguous' if bucket<50 else 'crisis' if bucket<55 else 'normal'
        is_long=index%5==0
        t=copy.deepcopy(rng.choice(by_kind[kind,is_long]))
        if is_long:t=compose_long(t,rng.randint(2,4))
        values={key:rng.choice(pool) for key,pool in vocabulary.items()}
        values['person']=values['person_surname']+values['person_given']
        values.update(time=rng.choice([f'{h}点{suffix}' for h in [20,21,22,23,0,1,2,3,4,5,6] for suffix in ['','半','多']]),drug=rng.choice(drugs),substance=rng.choice(substances),app=rng.choice(apps),device=rng.choice(devices),occupation=rng.choice(occupations),shift=rng.choice(['三班倒','大小夜','固定夜班','早班','晚班','大夜','两班倒']),metric=rng.choice(['AHI 32','血氧最低84%','ISI 18分','PSQI 12分','ESS 16分','睡眠效率70%']))
        components={k:rng.choice(addresses[v]) for k,v in dict(district='districts',road='roads',number='numbers',estate='estates',unit='units',village='villages').items()}
        values['address']=rng.choice(addresses['templates']).format(**components)
        values['org']=rng.choice(orgs['companies']+[p.format(stem=rng.choice(orgs['fictional_stems'])) for p in orgs['company_templates']+orgs['public_templates']])
        values['school']=rng.choice(orgs['schools']);values['hospital']=rng.choice(orgs['hospitals']+[p.format(stem=rng.choice(orgs['fictional_stems'])) for p in orgs['psych_templates']])
        d=date(2026,1,1)+timedelta(days=rng.randrange(334));birth=date(1960,1,1)+timedelta(days=rng.randrange(19000))
        values.update(day=rng.choice([f'{d.month}月{d.day}号',d.strftime('%Y-%m-%d'),f'{d.year}年{d.month}月{d.day}日','十一月三号','六月二十一日']),birthday=rng.choice([birth.strftime('%Y/%m/%d'),f'{birth.year}年',f'{birth.month}月{birth.day}号']),age=rng.choice([f'{rng.randint(5,99)}岁','十六岁','三十四岁','刚满61','三十四了']),birthyear=f'{birth.year}年',phone=make_phone(rng),ident=make_id(rng),work_id='GH'+str(rng.randint(1000000,9999999)),insurance_id='YB'+str(rng.randint(100000000,999999999)),outpatient_id='MZ'+str(rng.randint(100000000,999999999)),inpatient_id='ZY'+str(rng.randint(100000000,999999999)),record_id='BL'+str(rng.randint(100000000,999999999)),account='sleep_'+str(rng.randint(100000,999999)),email=''.join(rng.choices(string.ascii_lowercase,k=9))+'@example.invalid',bank=make_bank(rng),plate=rng.choice(['津A·','京B','沪AD','粤BF'])+str(rng.randint(10000,99999)))
        values['substance_action'],values['substance']=rng.choice(substance_actions)
        values['app_action'],values['app']=rng.choice(app_actions)
        values['device']=rng.choice(monitor_devices)
        values['daytime']=rng.choice([f'{h}点{suffix}' for h in range(8,18) for suffix in ['','半']])
        values['game_device']=rng.choice(['Switch','PS5'])
        values['oral_drug']=rng.choice(['褪黑素','佐匹克隆','安眠药'])
        values['symptom']=rng.choice(['睡不踏实','入睡很慢','夜里反复醒','睡得断断续续'])
        tid=t['id']
        values['birthday_md']=f'{birth.month}月{birth.day}号'
        if tid=='tpl-124':
            years,values['age']=rng.choice([(16,'十六岁'),(34,'三十四了'),(61,'刚满61'),(36,'36岁')])
            values['birthyear']=f'{2026-years}年'
        if tid=='tpl-069':values['age']=f'{rng.randint(5,99)}岁'
        if tid=='tpl-037':values['city']=rng.choice(DOMESTIC_ADDRESS_CITIES)
        if tid in ['tpl-017','tpl-069']:values['symptom']=values['symptom'].removeprefix('夜里')
        if t.get('long') and tid=='tpl-115':values['shift']=rng.choice(['夜班','大夜'])
        if tid=='tpl-016':values['device']=rng.choice(screen_devices)
        if tid=='tpl-010':values['metric']=rng.choice(['总睡眠时长5小时','夜里醒了4次','睡眠效率70%'])
        if tid in ['tpl-006','tpl-014','tpl-028']:values['relation']=rng.choice(['老公','对象','室友'])
        if tid in ['tpl-012','tpl-052','tpl-055']:values['occupation']=rng.choice(['客服','保安','运维人员'])
        if tid in ['tpl-002','tpl-003']:values['symptom']=rng.choice(['脑子停不下来','心里发慌','忍不住想工作','清醒得很'])
        if tid=='tpl-020':values['symptom']=rng.choice(['没困意','觉得累','担心睡着后呼吸暂停'])
        if tid in ['tpl-035','tpl-038','tpl-029']:values['symptom']=rng.choice(['心慌','紧张','担心第二天没精神'])
        if tid=='tpl-050':values['time']=rng.choice(['3点','4点半','5点'])
        if 'surname' in t:values['surname']=t['surname']
        # Risk statements are reused verbatim from the existing safety lexicon excerpt.
        values['crisis']=rng.choice(lexicon('keep/crisis_phrases.txt')[:19])
        if not values['crisis'].startswith('我'):values['crisis']='我'+values['crisis']
        labels=dict(ENTITY_LABELS)
        if kind=='ambiguous':
            amb=rng.choice([('小米','PERSON','我闺蜜','我戴着小米手环','小米手环'),('华为','ORG','我的工作单位','华为手环显示我没睡好','华为手环'),('美团','ORG','我的雇主','我还用美团订早餐','用美团订早餐'),('静静','PERSON','我的对象','我想静静地躺会儿','静静地躺会儿'),('苹果','ORG','我的雇主','晚上还吃了个苹果','吃了个苹果'),('腾讯','ORG','我的单位','我睡前刷腾讯视频','腾讯视频')])
            values.update(amb_red=amb[0],amb_role=amb[2],amb_clause=amb[3],amb_keep=amb[4]);labels['amb_red']=amb[1]
        row=render(t,values,labels)
        if is_long and not 60<=len(row['text'])<=200:continue
        if row['text'] in seen:continue
        seen.add(row['text']);row['id']=f'synth-{len(result)+1:05}';result.append(row)
    return result


def generate_sessions(n=200,seed=20261115,split='train'):
    """Whole synthetic conversations; distinct people, explicit alias, stable context.

    Each has 4–8 turns, >= 2 entity-free followups. Train/dev use separate seeds
    and IDs; no gold session is ever consumed here or by session SFT export.
    """
    rng=random.Random(seed);rows=[];seen=set()
    for i in range(n):
        sid=f'synth-{split}-session-{i+1:04}'
        while True:
            name=rng.choice(lexicon('redact/surnames.txt'))+rng.choice(lexicon('redact/given_names.txt'))
            if name not in seen:seen.add(name);break
        alias=name[-1]+'仔'
        address=f'{rng.choice(["禾月路","晴杉街","岚泉路","青露巷"])}{rng.randint(10,999)}号'
        stage=rng.choice(['最近两周','这一个月','这阵子'])
        # Alias is established in the same turn, then referred to across turns.
        opening=f'我叫{name}，家里也叫我{alias}，{stage}躺下后老想工作，关了屏幕也不困。'
        plans=[
            (opening,[[name,'PERSON'],[alias,'PERSON','[人名1]']],['躺下后老想工作','关了屏幕也不困']),
            rng.choice([
                ('昨天关了手机还是没困意，脑子还在转。',[],['关了手机还是没困意','脑子还在转']),
                ('夜里醒来又想到工作，躺了一阵才有困意。',[],['夜里醒来又想到工作','躺了一阵才有困意']),
                ('不看屏幕的时候也会想明天的任务。',[],['不看屏幕','也会想明天的任务']),
            ]),
            (f'今天同事又喊我{alias}，说我白天走神，我也觉得没睡够。',[[alias,'PERSON']],['白天走神','觉得没睡够']),
            rng.choice([
                ('后来我没有回消息，只是闭着眼躺了一阵。',[],['没有回消息','闭着眼躺了一阵']),
                ('今晚先把手机放远一点，免得又摸出来。',[],['把手机放远一点']),
                ('我想先记一下晚上清醒的时间。',[],['晚上清醒的时间']),
            ]),
            (f'我住{address}，屋子挺安静的，可还是会想工作。',[[address,'ADDRESS']],['屋子挺安静的','还是会想工作']),
            (f'说回{name}这个名字，是登记用的，我更想把睡眠记录说清楚。',[[name,'PERSON']],['把睡眠记录说清楚']),
            ('我没有午睡，傍晚有点困，躺回床上又清醒。',[],['我没有午睡','傍晚有点困','躺回床上又清醒']),
            (f'在{address}住了一阵子了，最近没有装修声，我想先从睡前的活动记起。',[[address,'ADDRESS']],['最近没有装修声','从睡前的活动记起'])]
        for turn,(text,ents,keep) in enumerate(plans[:rng.randint(4,8)],1):
            rows.append(dict(id=f'{sid}-{turn:02}',session_id=sid,turn=turn,text=text,ents=ents,keep=keep,tags=['person','time_keep'] if ents else ['hard_negative','time_keep'],note='独立合成会话；别名在首轮明确声明，编号连续；仅模拟数据。'))
    return rows

def main():
    p=argparse.ArgumentParser();p.add_argument('--n',type=int,default=3000);p.add_argument('--seed',type=int,default=20261114);args=p.parse_args()
    rows=generate(args.n,args.seed)
    write_jsonl(ROOT/'synth/train.src.jsonl',rows);write_jsonl(ROOT/'synth/train.jsonl',compile_rows(rows))
    for split,n_sessions,s_seed in [('train',200,args.seed+1),('dev',40,args.seed+2)]:
        session_rows=generate_sessions(n_sessions,s_seed,split)
        write_jsonl(ROOT/f'synth/sessions_{split}.src.jsonl',session_rows)
        write_jsonl(ROOT/f'synth/sessions_{split}.jsonl',compile_rows(session_rows))
    print(f'合成完成: {len(rows)} 条，seed={args.seed}')
if __name__=='__main__':main()
