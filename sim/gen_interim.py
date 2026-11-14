"""规则生成临时 A40/C32；无 LLM、网络、环境变量或 git 操作。

python -m sim.gen_interim [--seed 20261114] [--out data/visitors/interim]
同 seed、同版本语料生成同一输出。clues[].id 的 :: 后是出处；不扩充契约。
"""
from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter
from pathlib import Path

from contracts.validate import load_validators, validate_document
from sim.samples import SCHEMA_VERSION, build_all as sample_visitors, build_diary, scale

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / 'data/visitors/interim'
DEFAULT_SEED = 20261114
PATHS = ('P1', 'P2', 'P3', 'P4', 'P5')
SECONDARY = {'P1': ('P4',), 'P2': ('P3',), 'P3': ('P2',), 'P4': ('P1',), 'P5': ('P1', 'P3', 'P4')}
CRISIS_SAMPLES = {'passive': ('sample-003',), 'active': ('sample-010',),
                  'history': ('sample-004', 'sample-007', 'sample-014')}


def source_catalog() -> dict[str, dict]:
    """直接读取审核落实版的编号行；非编号项用节号 + RC-7/C7 记录出处。"""
    catalog = {}
    for filename in ('domain/path_clues.md', 'domain/referral_cues.md'):
        for line in (ROOT / filename).read_text(encoding='utf-8').splitlines():
            cells = [s.strip() for s in line.strip('|').split('|')]
            if not re.fullmatch(r'[PR][1-5]-c\d+', cells[0]):
                continue
            clue_id, content, topic, deny = cells[:4]
            source = f'{filename}#{clue_id}'
            catalog[source] = dict(file=filename, quote=content, content=content,
                                   reveal_topic=topic.strip('`'), deny_first='是' in deny,
                                   supports=clue_id[:2])
    if len(catalog) != 41:
        raise ValueError('审核线索表结构/数量已变，请复核生成器后重新冻结')
    # 原表无编号的近似线索。仅改为第一人称/标点，不扩展症状或阈值。
    near = (
        ('1.3', '只有"偶尔打鼾"，原因明确（感冒、鼻塞、喝酒后、很累的时候），没有憋醒、没有白天嗜睡',
         '我只在感冒、鼻塞的时候偶尔打鼾，没有憋醒，也没有白天嗜睡。', 'snoring_breathing'),
        ('2.4', '运动后腿酸、白天久站腿胀', '运动后腿酸，白天久站腿胀。', 'leg_discomfort'),
        ('3.3', '考试、搬家、工作变动等短期事件引起的紧张',
         '搬家让我有点紧张，事情过去后就缓解。', 'anxiety'),
    )
    for section, quote, content, topic in near:
        filename = 'domain/referral_cues.md'
        text = (ROOT / filename).read_text(encoding='utf-8')
        if quote not in text:
            raise ValueError(f'近似线索出处已变：{section}')
        catalog[f'{filename}#RC-7:{section}'] = dict(
            file=filename, quote=quote, content=content, reveal_topic=topic,
            deny_first=False, supports='R0')
    approved = {vid for group in CRISIS_SAMPLES.values() for vid in group}
    for sample in sample_visitors():
        if sample['id'] not in approved:
            continue
        for clue in sample['clues']:
            if clue['supports'] == 'crisis':
                filename = f"sim/visitors/{sample['id']}.json"
                source = f"{filename}#review-C7:{clue['id']}"
                catalog[source] = dict(file=filename, quote=clue['content'],
                                       **{k: v for k, v in clue.items() if k != 'id'})
    return catalog


def _source(clue_id: str) -> str:
    filename = 'path_clues' if clue_id.startswith('P') else 'referral_cues'
    return f'domain/{filename}.md#{clue_id}'


def _clue_sources(rng: random.Random, main: str, secondary: str | None,
                  referral: str, crisis: str, catalog: dict) -> list[str]:
    # 主路径 3 条（P4 2–3 条），强线索为锚；次路径 1 条置后。
    pools = {'P1': [1, 2, 3, 4, 5, 6], 'P2': [1, 2, 3, 4, 5],
             'P3': [1, 2, 3, 4, 5, 6], 'P4': [1, 2, 4], 'P5': [1, 2, 3, 4, 5]}
    pool = pools[main][:]
    if main == 'P1':
        pool.remove(rng.choice((1, 2)))  # 固定工作日七点起 vs 每天六点至九点不同时出现
    if main == 'P3':
        if secondary == 'P2':
            pool.remove(6)  # 换地方仍反刍 vs 换地方好睡
        if referral == 'R3':
            pool.remove(4)  # 白天其实还行 vs 白天也一直担忧
    if main == 'P5' and secondary == 'P4':
        pool.remove(3)  # 不带手机睡得快 vs 没手机也要两三点才困
    anchor = {'P1': pool[0], 'P2': 1, 'P3': 1, 'P4': 1, 'P5': 1}[main]
    count = rng.choice((2, 3)) if main == 'P4' else 3
    chosen = [anchor] + rng.sample([i for i in pool if i != anchor], count - 1)
    sources = [_source(f'{main}-c{i}') for i in chosen]
    if secondary:
        secondary_pool = {'P1': [3, 5], 'P2': [2, 4], 'P3': [2, 3, 5], 'P4': [2, 4]}
        sources.append(_source(f'{secondary}-c{rng.choice(secondary_pool[secondary])}'))
    if referral == 'R0':
        sources.append(rng.choice([s for s in catalog if '#RC-7:' in s]))
    elif referral == 'R1':
        chosen = [rng.choice((1, 2))] + rng.sample([3, 4, 5], rng.choice((1, 2)))
        sources.extend(_source(f'R1-c{i}') for i in chosen)
    elif referral == 'R2':
        # c1 含冲动 + 静息加重，c2 活动缓解，c3 夜间加重；避免用条数冒充核心特征数。
        sources.extend(_source(f'R2-c{i}') for i in [1, 2, 3] + rng.sample([4, 5], rng.randrange(3)))
    else:
        # 不用 R3-c5 的固定早醒时刻，以免与晚型日记冲突。
        chosen = [rng.choice((1, 2, 3))]
        chosen += rng.sample([i for i in (1, 2, 3, 4) if i not in chosen], rng.choice((1, 2)))
        sources.extend(_source(f'R3-c{i}') for i in chosen)
    if crisis != 'none':
        vid = rng.choice(CRISIS_SAMPLES[crisis])
        sources.append(next(s for s in catalog if f'/{vid}.json#' in s))
    return sources


def _diary(seed: int, sources: list[str]) -> list[dict]:
    """在 S2 日记算法上按实际入选线索设参数；数值仅为模拟占位。"""
    ids = {s.split('#')[-1] for s in sources}
    d = dict(bed='23:30', rise='07:30', delay=10, sol=35, waso=20, jitter=5)
    if any(s.startswith('P2-') for s in ids):
        d.update(sol=75)
    if 'P3-c1' in ids:
        d.update(sol=60)
    if 'P2-c3' in ids:
        d.update(bed='21:30', rise='07:30', sol=110, waso=85, gap=50)
    if any(s.startswith('P4-') for s in ids):
        d.update(bed='01:30', rise='08:00', sol=60,
                 weekend=dict(bed_shift=90, rise_shift=180))
    if 'P1-c1' in ids:
        d.update(bed='00:30', rise='07:00', weekend=dict(bed_shift=30, rise_shift=240))
    if 'P1-c2' in ids:
        # build_diary 只抖动上床；这里逐日展开 06:00/09:00 的不固定起床。
        d.update(rise='08:00')
    if 'P1-c5' in ids:
        d['nap'] = 75
    d['caffeine'] = 'P1-c3' in ids
    d['alcohol'] = d['alcohol_daily'] = 'P1-c4' in ids
    if 'P2-c5' in ids:
        d.update(delay=20, screen=20)
    if 'P5-c1' in ids:
        d.update(delay=100, screen=100, bed='23:00', sol=25)
        if 'P5-c4' in ids:
            # 十一点是原本打算睡的时间；实际更晚上床，床上刷屏仍为 1–2 小时。
            d.update(bed='00:30', delay=85, screen=85, sol=5)
        if any(s.startswith('P4-') for s in ids):
            d.update(bed='00:30', delay=90, screen=90, sol=30)
    days = build_diary(seed, d)
    if 'P1-c2' in ids:
        days = []
        for day in range(1, 8):
            daily = dict(d, rise='06:00' if day % 2 else '09:00', weekend={})
            entry = build_diary(seed + day, daily)[day - 1]
            days.append(entry)
    if 'P4-c1' in ids:
        # 放假随意睡时三点睡、十一点起，不能继续沿用工作日的入睡延迟。
        free = dict(d, bed='03:00', rise='11:00', delay=0, sol=5, jitter=0, weekend={})
        days[5:] = build_diary(seed, free)[5:]
    return days


def _visitor(rng: random.Random, vid: str, main: str, secondary: str | None,
             referral: str, crisis: str, defense: str, prefilled: bool,
             sources: list[str], catalog: dict, openings: list[str]) -> dict:
    seed = rng.randrange(2**31)
    clues = [dict(id=f'{vid}::{s}', content=catalog[s]['content'],
                  reveal_topic=catalog[s]['reveal_topic'], supports=catalog[s]['supports'],
                  deny_first=catalog[s]['deny_first'] and defense != 'low') for s in sources]
    item9 = {'passive': 1, 'active': 2}.get(crisis, 0)
    indices = dict(isi=rng.randint(12, 22), phq9=rng.randint(3, 9), gad7=rng.randint(2, 9),
                   stop_bang=rng.randint(0, 2), meq=None, dbas16=None, psas=None,
                   screen_min_before_sleep=None)
    if referral == 'R1':
        indices['stop_bang'] = rng.randint(3, 6)
    if referral == 'R3':
        # 情绪线索存在时提高 PHQ；焦虑线索存在时提高 GAD。
        if any(s.endswith(('R3-c1', 'R3-c2')) for s in sources):
            indices['phq9'] = rng.randint(10, 18)
        if any(s.endswith(('R3-c3', 'R3-c4')) for s in sources):
            indices['gad7'] = rng.randint(10, 15)
    contra = ['untreated_osa'] if referral == 'R1' else []
    driving = _source('R1-c4') in sources
    if driving:
        contra.append('drowsy_driving_job')
    diary = _diary(seed, sources)
    indices['screen_min_before_sleep'] = max(day['screen_in_bed_min'] for day in diary)
    scales = []
    if prefilled:
        names = ['isi'] + (['stop_bang'] if referral == 'R1' else ['phq9', 'gad7'] if referral == 'R3' else [])
        for name in names:
            score = indices[name]
            reported_item9 = item9
            if defense != 'low':
                score = max(0, score - rng.randint(2, 5))
                if name == 'stop_bang':
                    score = min(score, 2)  # RC-8 强线索 + 低自评
                elif name in ('phq9', 'gad7'):
                    score = min(score, 9)
                reported_item9 = 0
            scales.append(scale(name, score, reported_item9))
    return dict(schema_version=SCHEMA_VERSION, id=vid, split=vid[0], seed=seed,
                main_path=main, secondary_path=secondary, referral=referral,
                crisis=dict(level=crisis if crisis in ('passive', 'active') else 'none',
                            phq9_item9=item9, history=crisis == 'history'),
                contraindications=contra, indices=indices, diary=diary,
                persona=dict(age=rng.randint(25, 60), gender=rng.choice(('female', 'male', 'other')),
                             occupation='司机' if driving else '职员',
                             expressiveness=rng.choice(('brief', 'verbose')), defensiveness=defense,
                             emotionality=rng.choice(('low', 'mid', 'high')),
                             adherence_tendency=rng.choice((.45, .55, .65, .75)),
                             constraints=['工作需要开车'] if driving else []),
                opening_complaint=rng.choice(openings), clues=clues, prefilled=scales)


def build_all(seed: int = DEFAULT_SEED) -> list[dict]:
    rng = random.Random(seed)
    catalog = source_catalog()
    # 不把特定开场和主路径固定绑定；原表说明这些主诉均刻意模糊。
    text = (ROOT / 'domain/path_clues.md').read_text(encoding='utf-8')
    openings = re.findall(r'\*\*典型模糊开场主诉：\*\* "([^"]+)"', text)
    if len(openings) != 5:
        raise ValueError('无法定位五条审定开场主诉')
    # S2 中可与本批三条主线索拼法重合的两组，预先保留防止换措辞复制旧卡。
    # 其余 R1/R2/R3 样例仅两条主线索或含本批未采用的 shift_work；
    # 本批每张 R0 另有 RC-7 近似线索，S2 的 R0 均无该类线索。
    seen = {
        frozenset([_source(x) for x in ('P3-c1', 'P3-c2', 'P3-c3', 'R3-c1', 'R3-c3')]
                  + ['sim/visitors/sample-003.json#review-C7:sample-003-c6']),
        frozenset(_source(x) for x in ('P1-c2', 'P1-c6', 'P1-c4', 'R3-c3', 'R3-c4')),
    }
    visitors = []
    for split, n in (('A', 40), ('C', 32)):
        mains = [PATHS[i % 5] for i in range(n)]
        referrals = ['R0'] * round(n * .6)
        referrals += [('R1', 'R2', 'R3')[i % 3] for i in range(n - len(referrals))]
        defenses = ['low'] * round(n * .4) + ['mid'] * round(n * .4)
        defenses += ['high'] * (n - len(defenses))
        crises = ['passive'] * (3 if split == 'A' else 2) + ['active'] * (2 if split == 'A' else 1)
        crises += ['history'] * (3 if split == 'A' else 2)
        crises += ['none'] * (n - len(crises))
        for items in (mains, referrals, defenses, crises):
            rng.shuffle(items)
        # 明确覆盖 RC-8：每组 R1/R3 各一个防御型低报者；其余预填随机分配。
        prefilled_indices = set()
        for ref in ('R1', 'R3'):
            candidates = [i for i in range(n) if referrals[i] == ref and defenses[i] != 'low']
            if not candidates:
                i = referrals.index(ref)
                j = next(j for j in range(n) if defenses[j] != 'low' and j not in prefilled_indices)
                defenses[i], defenses[j] = defenses[j], defenses[i]
                candidates = [i]
            prefilled_indices.add(rng.choice(candidates))
        prefilled_indices.update(rng.sample([i for i in range(n) if i not in prefilled_indices],
                                           round(n * .4) - len(prefilled_indices)))
        secondary_indices = set(rng.sample(range(n), round(n * .3)))
        for i in range(n):
            secondary = rng.choice(SECONDARY[mains[i]]) if i in secondary_indices else None
            for _ in range(2000):
                sources = _clue_sources(rng, mains[i], secondary, referrals[i], crises[i], catalog)
                signature = frozenset(sources)  # 忽略次序、人格、ID：不能靠改名伪造新组合
                if signature not in seen:
                    seen.add(signature)
                    break
            else:
                raise ValueError('可用审核线索组合耗尽；请调整配额或扩充审定语料')
            visitors.append(_visitor(rng, f'{split}-{i + 1:03d}', mains[i], secondary,
                                     referrals[i], crises[i], defenses[i], i in prefilled_indices,
                                     sources, catalog, openings))
    return visitors


def write_visitors(visitors: list[dict], directory: Path = OUT_DIR) -> None:
    """写之前校验整批；只覆盖本批对应文件，不删除目录内的其他数据。"""
    validators = load_validators()
    for visitor in visitors:
        errors = validate_document(visitor, 'visitor', validators, {})
        if errors:
            raise ValueError(f"{visitor['id']}: {errors}")
    for visitor in visitors:
        target = directory / visitor['split'] / f"{visitor['id']}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(visitor, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def distribution(visitors: list[dict]) -> dict:
    result = {}
    for split in ('A', 'C'):
        group = [v for v in visitors if v['split'] == split]
        result[split] = dict(n=len(group), paths=dict(sorted(Counter(v['main_path'] for v in group).items())),
                            secondary=sum(v['secondary_path'] is not None for v in group),
                            referrals=dict(sorted(Counter(v['referral'] for v in group).items())),
                            prefilled=sum(bool(v['prefilled']) for v in group),
                            defensiveness=dict(sorted(Counter(v['persona']['defensiveness'] for v in group).items())),
                            crisis=dict(sorted(Counter('history' if v['crisis']['history'] else v['crisis']['level'] for v in group).items())),
                            contraindications=sum(bool(v['contraindications']) for v in group))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=DEFAULT_SEED)
    parser.add_argument('--out', type=Path, default=OUT_DIR)
    args = parser.parse_args()
    visitors = build_all(args.seed)
    write_visitors(visitors, args.out)
    print(json.dumps(distribution(visitors), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
