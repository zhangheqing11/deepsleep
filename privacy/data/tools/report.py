"""Regenerate measured baseline tables and content checksums, entirely offline."""
import hashlib
import json
import re
from pathlib import Path
from .build import ROOT,read_jsonl
from .build_sft import extract_target
from .apply import apply
from .evaluate import evaluate,pct
from .validate import validate_all, stats, compiled_paths
from .scan_audit2 import scan


def refresh_review_tables():
    """Refresh values from compiled gold while retaining the reviewer's row IDs."""
    path=ROOT/'HUMAN_REVIEW.md';text=path.read_text()
    rows={r['id']:r for p in (ROOT/'gold').glob('*.jsonl') if not p.name.endswith('.src.jsonl') for r in read_jsonl(p)}
    def replace_section(match):
        section=match[0]
        ids=re.findall(r'^\| ((?:seed|dev|test|session)-[0-9-]+) \|',section,re.M)
        def replace_row(row_match):
            row=rows[row_match[1]]
            escape=lambda value:value.replace('|','\\|')
            return '| '+' | '.join(escape(v) for v in [row['id'],row['text'],row['deid'],'、'.join(row['keep'])])+' |'
        updated=re.sub(r'^\| ((?:seed|dev|test|session)-[0-9-]+) \|.*$',replace_row,section,flags=re.M)
        assert ids==re.findall(r'^\| ((?:seed|dev|test|session)-[0-9-]+) \|',updated,re.M)
        return updated
    text=re.sub(r'## [23]\..*?(?=\n## |\Z)',replace_section,text,flags=re.S)
    path.write_text(text,encoding='utf-8')


def refresh_readme_tables(results):
    path=ROOT/'README.md';text=path.read_text()
    table=['| 文件 | 条数/轮数 | 会话数 | 实体数 | hard negative | 比例 | KEEP片段 |',
           '|---|---:|---:|---:|---:|---:|---:|']
    for p in compiled_paths():
        st=stats(read_jsonl(p))
        table.append('| '+' | '.join(map(str,[p.relative_to(ROOT),st['n'],st['sessions'],st['entities'],st['hard_negative'],pct(st['hard_negative_ratio']),st['keep_fragments']]))+' |')
    text=re.sub(r'\| 文件 \|.*?(?=\n\n)',lambda _: '\n'.join(table),text,count=1,flags=re.S)
    table=['| split | 基线 | n | 泄露率↓ | 实体替换合法↑ | KEEP↑ | 危机KEEP↑ | 非实体一致↑ | 有效输出↑ | HN过脱敏↓ | 整句匹配↑ |',
           '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    keys=['leakage_rate','entity_replacement_legal_rate','keep_rate','crisis_keep_rate','non_entity_exact_rate','valid_output_rate','hard_negative_overredaction','exact_match']
    for (split,mode),result in results.items():
        st=result['overall'];table.append('| '+' | '.join([split,mode,str(st['n'])]+[pct(st[k]) for k in keys])+' |')
    text=re.sub(r'\| split \| 基线 \|.*?(?=\n\n)',lambda _: '\n'.join(table),text,count=1,flags=re.S)
    path.write_text(text,encoding='utf-8')


def report():
    results={}
    for split in ['dev','test','sessions']:
        for mode in (['rules'] if split=='sessions' else ['rules','naive']):
            results[split,mode]=json.loads((ROOT/f'baselines/{split}_{mode}.json').read_text())
    lines=['# 离线基线结果（SPEC v0.3）','',
        '本文件由 `make deid-data` 的 `tools/report.py` 从本次 JSON 结果重建。旧 v0.1/v0.2 数字作废，不能与新分母/新口径直接比较。未联网、未训练模型。',
        '',
        'v0.3 核心思想：移除所有可识别个人的信息，其余一律保留。日历日期、精确年龄和城市原样保留；任何精度的生日/出生年月仍使用 BIRTH_DATE 替换。日期/年龄改为 KEEP，实体和负例分母随之变化；泄露/KEEP 使用 difflib 原文位置对齐，输出占位符不充当 KEEP。新增非实体区逐字一致率与有效输出率。缺失、解析失败、非法实体/occ/重叠输出单列无效：保留/一致/精确匹配记失败，身份实体保守记泄露，负例记失败。模型 replacement 字段忽略并记 warning；unknown same_as 仅 warning，按新实体分配，不算格式无效。',
        '',
        '第二轮修订将 long KEEP 改为人工选取的关键临床片段；合成长句取各组成句的 KEEP 并集，去重及去掉被包含片段。KEEP 分母已变化，本表与上一轮 KEEP 数字不能直接比较；预测器未改变，指标变化不代表模型进步。',
        '',
        '第三轮（回应 AUDIT2）新增实体替换合法率：以金标实体出现次数为分母，对齐实体两侧非实体边界后，整个输出区域必须为对应标签的正整数编号占位符。近似假名、漏抽、错类型、删除和多余文本均失败；无效输出全部失败。相邻实体作为一组按顺序完整匹配，组内无法合法拆分则整组失败；边界无法对齐时保守失败。编号是否与金标一致另看会话编号/整句匹配。extract 经过 apply 产生合法格式，但仍会漏抽或抽错类型，所以同样计算。',
        '',
        'rules 仍为号码正则及机构/地址后缀基线，不读金标 entities/keep/tags 来预测；不理解任职关系、不识别人名、不处理普通日期和年龄，不能当生产脱敏器。naive 在其基础上继续粗暴抹去日期、年龄、数字、时间、药物和品牌，不代表任何实际产品。',
        '',
        '| split | 基线 | n | 泄露率↓ | 实体替换合法↑ | KEEP↑ | 危机KEEP↑ | 非实体一致↑ | 有效输出↑ | HN过脱敏↓ | 整句匹配↑ |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    keys=['leakage_rate','entity_replacement_legal_rate','keep_rate','crisis_keep_rate','non_entity_exact_rate','valid_output_rate','hard_negative_overredaction','exact_match']
    for (split,mode),r in results.items():
        m=r['overall'];lines.append('| '+' | '.join([split,mode,str(m['n'])]+[pct(m[k]) for k in keys])+' |')
    errors=validate_all()
    lines+=['','## 数据校验状态','',
            ('当前全量数据校验通过。' if not errors else '当前全量数据校验未通过；本表是已重算的评测结果，不表示 make 或 pytest 全绿。')]
    if errors:lines+=['']+['- '+e for e in errors]
    lines+=['','## 标签泄露（出现次数）','','| 标签 | dev rules | dev naive | test rules | test naive | test实体数 |','|---|---:|---:|---:|---:|---:|']
    for label,v in results['test','rules']['overall']['by_label'].items():
        lines.append('| '+' | '.join([label]+[pct(results[s,m]['overall']['by_label'][label]['leakage_rate']) for s,m in [('dev','rules'),('dev','naive'),('test','rules'),('test','naive')]]+[str(v['total'])])+' |')
    lines+=['','## 分母与无效输出','','| split / 基线 | 泄露/实体 | 合法替换/实体 | 保留/KEEP | 危机保留/KEEP | 非实体一致/n | 无效/n |','|---|---:|---:|---:|---:|---:|---:|']
    for (split,mode),r in results.items():
        c=r['overall']['counts'];n=r['overall']['n']
        lines.append(f'| {split} / {mode} | {c["leaked"]}/{c["entities"]} | {c["replacement_legal"]}/{c["entities"]} | {c["kept"]}/{c["keep"]} | {c["crisis_kept"]}/{c["crisis_keep"]} | {c["non_entity_exact"]}/{n} | {c["invalid"]}/{n} |')
    lines+=['','## 对抗子集（adversarial）','',
            '自述脱敏规则的长句单独分组；这是有意构造的对抗材料，不代表自然会谈分布。其余 tag 可以与 adversarial 重叠，不能将各组相加。',
            '', '| split / 基线 | n | 实体替换合法↑ | KEEP↑ | 非实体一致↑ |',
            '|---|---:|---:|---:|---:|']
    for (split,mode),result in results.items():
        group=result['by_tag'].get('adversarial')
        if group:
            lines.append('| '+' | '.join([split+' / '+mode,str(group['n'])]+[pct(group[k]) for k in ['entity_replacement_legal_rate','keep_rate','non_entity_exact_rate']])+' |')
    rows=read_jsonl(ROOT/'gold/sessions.jsonl');maps={};pred={}
    for row in rows:
        mapping=maps.get(row['session_id'],{});target=extract_target(row,mapping)
        pred[row['id']]=target;_,maps[row['session_id']]=apply(row['text'],target,mapping)
    oracle=evaluate(rows,pred,'extract',session_mode=True)
    (ROOT/'baselines/sessions_oracle.json').write_text(json.dumps(oracle,ensure_ascii=False,indent=2)+'\n')
    num=oracle['session_numbering']
    lines+=['','## 会话协议回放','',
        f'gold/sessions 的 extract 金标目标逐轮回放：{oracle["overall"]["counts"]["exact"]}/{len(rows)} 整句匹配；编号 {num["correct"]}/{num["total"]} 正确；无效输出 {oracle["overall"]["counts"]["invalid"]}。这是协议和导出正确性检查，不是模型准确率。',
        '',
        '完整 by_tag（包含 long、adversarial）、by_label 和诊断见 baselines/*.json。空 KEEP 的 no_clinical 行不贡献保留率分母，但仍纳入有效输出/非实体一致/精确匹配。危机率按带 crisis 标签行的全部 KEEP 计算，不等于危机识别召回。',
        '',
        'difflib 在重复文本上存在启发式对齐限制；泄露只测完整原文 surface 在对应实体区域的残留，不能证明部分号码、同音/转写或跨位置复制安全。需联合看实体替换合法、非实体逐字一致与有效输出。两种基线均不满足隐私和临床双重目标，也没有本地 Qwen 实测结果。','']
    (ROOT/'BASELINES.md').write_text('\n'.join(lines))
    (ROOT/'SCAN_AUDIT2.json').write_text(json.dumps(scan(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    refresh_review_tables()
    refresh_readme_tables(results)
    # Includes generated outputs for local reproduction even when gitignored;
    # excludes caches and itself. Paths are relative to the repository root.
    repo=ROOT.parents[1]
    paths=[p for p in (repo/'privacy').rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='MANIFEST.sha256']
    paths += [repo/'tests/test_privacy_data.py',repo/'Makefile']
    manifest=''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(repo)}\n' for p in sorted(paths))
    (ROOT/'MANIFEST.sha256').write_text(manifest)
    print(f'基线表和 manifest 已更新（{len(paths)} 文件）')

if __name__=='__main__':report()
