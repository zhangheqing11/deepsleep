"""确定性、离线的 150 人联合分层生成器（仅合成数据）。

python -m sim.generate --seed 20261115 --out data/visitors
阈值来自仓库审定规则；配额、指数分布、模板选择均为工程占位，并非流行率。
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import random

from sim.generate_templates import OPENINGS, PERSONAS, SHIFT_PERSONAS, TEMPLATES
from sim.samples import SCHEMA_VERSION, SPECS, build_diary, scale

PATHS = ('P1', 'P2', 'P3', 'P4', 'P5')
REFERRALS = ('R0', 'R1', 'R2', 'R3')
DEFENSES = ('low', 'mid', 'high')
SPLIT_SIZES = {'A': 45, 'B': 45, 'C': 30, 'offline': 30}
DEFAULT_SEED = 20261115
GENERATOR_VERSION = '1'
# PC-4：仅使用已列出的方向；所有来访均带一个次要路径。
SECONDARY = {'P1': ('P4',), 'P2': ('P3',), 'P3': ('P2',),
             'P4': ('P1',), 'P5': ('P1', 'P3', 'P4')}
MAIN_SLOTS = {'P1': ('irregular', 'coffee', 'nap'),
              'P2': ('bed_alert', 'sofa', 'stay_in_bed'),
              'P3': ('rumination', 'sleep_fear', 'catastrophe'),
              'P4': ('late_clock', 'late_morning'),
              'P5': ('screen', 'revenge', 'one_more')}
SECONDARY_SLOTS = {'P1': ('coffee', 'nap'), 'P2': ('secondary_bed',),
                   'P3': ('secondary_worry',), 'P4': ('secondary_clock',)}
# C7 审定原文：保持整个句子、否认资格与风险语义，不做新危机措辞。
CRISIS_TEXTS = {
    label: tuple(c for spec in SPECS
                 if (('history' if spec.get('crisis', {}).get('history') else
                      spec.get('crisis', {}).get('level')) == label)
                 for c in spec['clues'] if c['supports'] == 'crisis')
    for label in ('history', 'passive', 'active')
}


def allocate_strata(rng: random.Random) -> dict[str, list[dict]]:
    """先建 60 个 path×referral×defense 联合层，再作整数配额分配。

    每个 path×defense 单元 10 人：R0=6，三个阳性标签=2/1/1；重复标签
    随 defense 轮换。初分每单元 A/B/C/offline=3/3/2/2。随后在同单元内
    各交换三对 R0/阳性，使各组 R0=60%，三个阳性各占 2/15。
    交换不改变路径或防御性；每个联合层每组人数只取期望值的 floor/ceil。
    """
    cells = []
    for path in PATHS:
        labels = list(REFERRALS[1:])
        rng.shuffle(labels)
        for d, defense in enumerate(DEFENSES):
            positives = (labels[d], labels[(d + 1) % 3], labels[(d + 2) % 3], labels[d])
            cells.append({'path': path, 'defense': defense,
                          'groups': {split: ['R0'] * (2 if split in ('A', 'B') else 1) + [ref]
                                     for split, ref in zip(SPLIT_SIZES, positives)}})
    for large, small in (('A', 'C'), ('B', 'offline')):
        for ref in REFERRALS[1:]:
            # P4/R1 每组保留一人，供 sample-009 同型职业禁忌覆盖。
            cell = rng.choice([c for c in cells if ref in c['groups'][small]
                               and not (ref == 'R1' and c['path'] == 'P4')])
            cell['groups'][large].remove('R0')
            cell['groups'][large].append(ref)
            cell['groups'][small].remove(ref)
            cell['groups'][small].append('R0')
    groups = {split: [] for split in SPLIT_SIZES}
    for cell in cells:
        for split, labels in cell['groups'].items():
            groups[split].extend({'main_path': cell['path'], 'referral': ref,
                                  'defensiveness': cell['defense']} for ref in labels)
    for rows in groups.values():
        rng.shuffle(rows)
    return groups


def build_visitor(vid: str, split: str, seed: int, row: dict) -> dict:
    rng = random.Random(seed)
    path, ref, defense = row['main_path'], row['referral'], row['defensiveness']
    secondary = rng.choice(SECONDARY[path])
    shift = row.get('driving', False) or (path == 'P4' and rng.random() < 0.35)
    if row.get('driving'):
        job = SHIFT_PERSONAS[2]
    elif shift:
        job = rng.choice(SHIFT_PERSONAS[:2])
    elif path == 'P4':
        job = rng.choice([p for p in PERSONAS if p[0] in ('自由插画师', '研究生', '电商运营', '退休职员')])
    else:
        job = rng.choice(PERSONAS)
    occupation, age_min, age_max, task, constraint = job
    persona = dict(age=rng.randint(age_min, age_max), gender=rng.choice(('female', 'male', 'other')),
                   occupation=occupation, expressiveness=rng.choice(('brief', 'verbose')),
                   defensiveness=defense, emotionality=rng.choice(DEFENSES),
                   adherence_tendency=round(rng.uniform(0.35, 0.9), 2),
                   constraints=[constraint, rng.choice(('与家人同住', '住处空间有限', '周末常有家务安排'))])
    screen = rng.choice((90, 105, 120)) if path == 'P5' else rng.choice((10, 15, 20, 25))
    nap = rng.choice((60, 70, 80))
    variables = dict(occupation=occupation, task=task, screen=screen, nap=nap,
                     drink=rng.choice(('咖啡', '浓茶', '奶茶')),
                     hobby=rng.choice(('散步', '画画', '听音乐', '和朋友聊天', '打球')),
                     entertainment=rng.choice(('刷短视频', '追剧', '看直播', '打游戏')))
    crisis_label = row.get('crisis', 'none')
    crisis = dict(level=crisis_label if crisis_label in ('active', 'passive') else 'none',
                  phq9_item9={'passive': 1, 'active': 2}.get(crisis_label, 0),
                  history=crisis_label == 'history')
    # 数值区间参照样例量级作工程占位，不是研究估计的联合分布。
    indices = dict(isi=rng.randint(12, 22), phq9=rng.randint(3, 9), gad7=rng.randint(2, 9),
                   stop_bang=rng.randint(0, 2),
                   meq=None if shift else rng.randint(25, 35) if path == 'P4' else rng.randint(42, 60),
                   dbas16=round(rng.uniform(6.0, 8.0) if path == 'P3' else rng.uniform(3.0, 5.8), 1),
                   psas=rng.randint(40, 55) if path == 'P3' else rng.randint(20, 36),
                   screen_min_before_sleep=screen)
    mood_type = None
    if ref == 'R1':
        # 明示打鼾 + 观察到暂停，年龄/男性也不能让总分低于已知阳性项数。
        known_items = 2 + int(persona['age'] > 50) + int(persona['gender'] == 'male')
        indices['stop_bang'] = rng.randint(max(3, known_items), 6)
    elif ref == 'R3':
        mood_type = 'phq9' if crisis['level'] != 'none' or row.get('bipolar') else rng.choice(('phq9', 'gad7', 'both'))
        if mood_type in ('phq9', 'both'):
            indices['phq9'] = rng.randint(10, 20)
        if mood_type in ('gad7', 'both'):
            indices['gad7'] = rng.randint(10, 17)
    if ref != 'R1':
        # STOP-Bang 未逐题建模，但至少不违背已经披露的年龄/性别两项。
        indices['stop_bang'] = max(indices['stop_bang'], int(persona['age'] > 50) + int(persona['gender'] == 'male'))
    clues = []

    def add(slot: str, supports: str) -> None:
        topic, deny, texts = TEMPLATES[slot]
        clues.append(dict(reveal_topic=topic, supports=supports,
                          deny_first=deny, content=rng.choice(texts).format(**variables)))

    main_slots = ('shift', 'shift_sleep') if shift else MAIN_SLOTS[path]
    for slot in main_slots[:rng.choice((2, 3))]:
        add(slot, path)
    secondary_slots = SECONDARY_SLOTS[secondary]
    for slot in secondary_slots[:rng.randint(1, len(secondary_slots))]:
        add(slot, secondary)
    if ref == 'R1':
        add('snore', ref)
        add('osa_pending', ref)
    elif ref == 'R2':
        for slot in ('legs_rest', 'legs_move', 'legs_night'):
            add(slot, ref)
    elif ref == 'R3':
        if mood_type in ('phq9', 'both'):
            add('low_mood', ref)
        if mood_type in ('gad7', 'both'):
            add('day_anxiety', ref)
    elif row.get('near_miss'):
        # supports=R0，不能为了干扰而伪造阳性标签或混入第三条路径。
        add(rng.choice(('benign_snore', 'benign_legs', 'benign_mood')), 'R0')
    contraindications = []
    if ref == 'R1':
        contraindications.append('untreated_osa')
    if row.get('bipolar'):
        contraindications.append('bipolar')
        add('bipolar', ref)
    if row.get('driving'):
        contraindications.append('drowsy_driving_job')
        add('driving', ref)
    if crisis_label != 'none':
        clues.append(dict(rng.choice(CRISIS_TEXTS[crisis_label])))
    for i, clue in enumerate(clues, 1):
        clue['id'] = f'{vid}-c{i}'

    diary_args = dict(bed='23:00', rise='06:30', sol=35, waso=20, screen=screen,
                      delay=screen + 5, jitter=10)
    if path == 'P1':
        diary_args.update(sol=30, caffeine=True, nap=nap, jitter=30,
                          weekend=dict(bed_shift=60, rise_shift=180))
    elif path == 'P2':
        diary_args.update(bed='22:00', sol=70, waso=40)
    elif path == 'P3':
        diary_args.update(sol=60, waso=30)
    elif shift:
        diary_args.update(bed='08:30', rise='14:30', sol=25, waso=30)
    elif path == 'P4':
        diary_args.update(bed='01:00', rise='08:00', sol=85, waso=10, jitter=5,
                          weekend=dict(bed_shift=20, rise_shift=180))
    elif path == 'P5':
        diary_args.update(sol=25)
    # 日记与实际选出的次要咖啡/午睡线索同步。
    if any(c['reveal_topic'] == 'caffeine_alcohol' for c in clues):
        diary_args['caffeine'] = True
    if any(c['reveal_topic'] == 'daytime_sleepiness' and c['supports'] == 'P1' for c in clues):
        diary_args['nap'] = nap
    prefilled = []
    if row.get('prefilled'):
        names = ['isi']
        if ref == 'R1':
            names.append('stop_bang')
        elif ref == 'R3':
            names.append('gad7' if mood_type == 'gad7' else 'phq9')
        elif rng.random() < 0.5:
            names.append('phq9')
        for name in names:
            reported = indices[name]
            if defense != 'low':
                reported = max(0, reported - rng.randint(1, 2) if name == 'stop_bang'
                               else reported - rng.randint(2, 5))
            item9 = crisis['phq9_item9'] if defense == 'low' else 0
            prefilled.append(scale(name, reported, item9))
    opening = rng.choice(OPENINGS).format(impact=rng.choice(('没精神', '觉得累', '注意力不太集中', '提不起劲')))
    return dict(schema_version=SCHEMA_VERSION, id=vid, split=split, seed=seed,
                main_path=path, secondary_path=secondary, referral=ref, crisis=crisis,
                contraindications=contraindications, indices=indices,
                diary=build_diary(seed, diary_args), persona=persona,
                opening_complaint=opening, clues=clues, prefilled=prefilled)


def generate(seed: int = DEFAULT_SEED) -> list[dict]:
    rng = random.Random(seed)
    groups = allocate_strata(rng)
    visitor_seeds = iter(rng.sample(range(2**32), sum(SPLIT_SIZES.values())))
    visitors = []
    for split, rows in groups.items():
        r3 = [row for row in rows if row['referral'] == 'R3']
        passive, active, bipolar = rng.sample(r3, 3)
        passive['crisis'], active['crisis'], bipolar['bipolar'] = 'passive', 'active', True
        for row in rng.sample([r for r in rows if 'crisis' not in r], 3 if split in ('A', 'B') else 2):
            row['crisis'] = 'history'
        for defense in DEFENSES:
            for row in rng.sample([r for r in rows if r['defensiveness'] == defense], len(rows) * 2 // 15):
                row['prefilled'] = True
        # 每组一个 sample-009 同型的倒班/OSA/驾驶职业双禁忌难例。
        rng.choice([r for r in rows if r['main_path'] == 'P4' and r['referral'] == 'R1'])['driving'] = True
        r0 = [r for r in rows if r['referral'] == 'R0']
        for row in rng.sample(r0, len(r0) // 3):
            row['near_miss'] = True
        for i, row in enumerate(rows, 1):
            visitors.append(build_visitor(f'{split}-{i:03d}', split, next(visitor_seeds), row))
    return visitors


def distribution(visitors: list[dict]) -> dict:
    def counts(values):
        return dict(sorted(Counter(values).items()))

    return dict(count=len(visitors),
                main_path=counts(v['main_path'] for v in visitors),
                referral=counts(v['referral'] for v in visitors),
                defensiveness=counts(v['persona']['defensiveness'] for v in visitors),
                strata=counts('|'.join((v['main_path'], v['referral'], v['persona']['defensiveness'])) for v in visitors),
                prefilled=sum(bool(v['prefilled']) for v in visitors),
                prefilled_by_defensiveness=counts(v['persona']['defensiveness'] for v in visitors if v['prefilled']),
                underreported=sum(any(s['reported_score'] < v['indices'][s['scale']] for s in v['prefilled']) for v in visitors),
                history=sum(v['crisis']['history'] for v in visitors),
                crisis=counts(v['crisis']['level'] for v in visitors),
                contraindications=counts(c for v in visitors for c in v['contraindications']),
                near_miss=sum(any(c['supports'] == 'R0' for c in v['clues']) for v in visitors))


def manifest(seed: int, visitors: list[dict]) -> dict:
    return dict(generator_version=GENERATOR_VERSION, schema_version=SCHEMA_VERSION, seed=seed,
                total=len(visitors), counts=SPLIT_SIZES.copy(),
                sampling='path × referral × defensiveness joint strata; integer quotas; seeded within-stratum draws',
                sources=['domain/path_clues.md', 'domain/referral_cues.md', 'domain/plan_veto_rules.md',
                         'docs/review-decisions.md', 'docs/decision-queue-2.md', 'sim/samples.py'],
                limitations=['模板与指数联合分布为未有文献出处的工程占位，不代表真实人群发生率',
                             '四组共享模板库，不是独立语言来源的外部验证集',
                             '危机原文复用已审定样例；当前危机仅放在 R3，不代表危机只能出现在 R3',
                             'offline 本批为 30 个，尚非 AGENTS.md 所述 200+ 离线大样本'],
                templates=dict(semantic_slots=len(TEMPLATES),
                               clue_variants=sum(len(t[2]) for t in TEMPLATES.values()),
                               approved_crisis_variants=sum(map(len, CRISIS_TEXTS.values())),
                               opening_variants=len(OPENINGS), persona_profiles=len(PERSONAS) + len(SHIFT_PERSONAS)),
                overall=distribution(visitors),
                splits={s: distribution([v for v in visitors if v['split'] == s]) for s in SPLIT_SIZES})


def json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'


def write_dataset(seed: int, out: Path) -> dict:
    visitors = generate(seed)
    # 不把错误的生成结果落盘；复用契约的结构与业务校验，无网络请求。
    from contracts.validate import load_validators, validate_document
    validators = load_validators()
    for visitor in visitors:
        errors = validate_document(visitor, 'visitor', validators, {})
        if errors:
            raise ValueError(f'{visitor["id"]}: {errors}')
    expected = {out / v['split'] / f'{v["id"]}.json' for v in visitors}
    # 同目录重跑仅覆盖已知文件；发现旧批次/外来 JSON 时拒绝，而非留下混合数据或擅删。
    extras = set(out.glob('*/*.json')) - expected
    if extras:
        raise ValueError(f'输出目录有额外 JSON，请使用空目录：{sorted(map(str, extras))}')
    for visitor in visitors:
        path = out / visitor['split'] / f'{visitor["id"]}.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json_text(visitor), encoding='utf-8')
    report = manifest(seed, visitors)
    (out / 'MANIFEST.json').write_text(json_text(report), encoding='utf-8')
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=DEFAULT_SEED)
    parser.add_argument('--out', type=Path, default=Path('data/visitors'))
    args = parser.parse_args()
    report = write_dataset(args.seed, args.out)
    print(f'wrote {report["total"]} visitors (A=45, B=45, C=30, offline=30) + MANIFEST.json to {args.out}')


if __name__ == '__main__':
    main()
