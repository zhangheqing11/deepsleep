"""冻结的规则状态模型：给定来访真值 + 会谈结果，算 4 周 ISI、依从、同盟（锁定决定第 7 条）。

不让 LLM 来访自我报告，全部确定性计算。参数见 sim/params.yaml（当前全是占位）。

接口（数据科学同学替换算法时保持不变）：
    simulate(visitor: dict, session: dict, params: dict | None = None) -> StateResult
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

import yaml

PARAMS_PATH = Path(__file__).resolve().parent / 'params.yaml'


@lru_cache(maxsize=1)
def _load_default() -> dict:
    return yaml.safe_load(PARAMS_PATH.read_text(encoding='utf-8'))


def load_params(path: Path | None = None) -> dict:
    if path is None:
        return _load_default()
    return yaml.safe_load(Path(path).read_text(encoding='utf-8'))


@dataclass
class StateResult:
    isi_week: list[int]       # 长度 5，第 0–4 周
    adherence: float          # 0–1
    alliance: float           # 0–1
    match: float              # 路径匹配度 0–1
    effect: float             # 第 4 周 ISI 降幅（未取整）
    params_version: str

    def to_dict(self) -> dict:
        return asdict(self)


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def alliance_score(session: dict, params: dict) -> float:
    cfg = params['alliance']
    behaviors = session.get('behaviors') or {}
    score = cfg['base']
    for name, weight in cfg['plus'].items():
        score += weight * min(behaviors.get(name, 0), cfg['cap'])
    for name, weight in cfg['minus'].items():
        score -= weight * min(behaviors.get(name, 0), cfg['cap'])
    plan = session.get('plan')
    if plan and plan.get('rationale_given'):
        score += cfg['rationale_given_bonus']
    return round(_clamp(score), 4)


def path_match(visitor: dict, plan: dict, params: dict) -> float:
    components = set(plan['components'])
    table = params['path_components']
    hit_main = bool(components & set(table[visitor['main_path']]))
    cfg = params['match']
    if visitor['secondary_path'] is None:
        weighted = float(hit_main)
    else:
        hit_secondary = bool(components & set(table[visitor['secondary_path']]))
        weighted = cfg['w_main'] * hit_main + cfg['w_secondary'] * hit_secondary
    return cfg['base'] + (1 - cfg['base']) * weighted


def final_referral(session: dict) -> str:
    rounds = session.get('rounds') or []
    return rounds[-1]['referral_pred'] if rounds else 'R0'


def simulate(visitor: dict, session: dict, params: dict | None = None) -> StateResult:
    params = params or load_params()
    isi0 = int(round(visitor['indices']['isi']))
    alliance = alliance_score(session, params)
    plan = session.get('plan')
    if plan is None:  # crisis_exit / error：没有处方，ISI 不变
        return StateResult([isi0] * 5, 0.0, alliance, 0.0, 0.0, params['version'])

    feasibility = 1.0
    if plan['tib_minutes'] < params['min_tib_minutes']:
        feasibility *= params['infeasible_adherence_factor']
    adh_cfg = params['adherence']
    adherence = _clamp(visitor['persona']['adherence_tendency']
                       * (adh_cfg['a'] + adh_cfg['b'] * alliance) * feasibility)

    match = path_match(visitor, plan, params)
    effect = params['effect_max'] * match * adherence
    if visitor['referral'] != 'R0' and final_referral(session) != visitor['referral']:
        effect *= params['referral_unaddressed_factor']
    if visitor['contraindications'] and 'sleep_restriction' in plan['components']:
        effect *= params['contraindication_effect_factor']

    isi_week = [max(0, int(round(isi0 - effect * f))) for f in params['week_curve']]
    isi_week[0] = isi0
    return StateResult(isi_week, round(adherence, 4), alliance, round(match, 4),
                       round(effect, 4), params['version'])
