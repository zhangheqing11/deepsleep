"""最简 stub 会谈 agent —— 只为 `make smoke` 在引擎（S3, zhq/engine-session）落地前跑通端到端。

⚠️ 这不是会谈 agent，也不是安全层：
- 不调 LLM，按固定话题顺序提问；路径用关键词投票，转介靠筛查工具结果。
- 安全判定是几条关键词规则的占位，真实实现是 safety/layer.py（PR #6）。
- agent / safety 发言都是 `[stub]` 占位串，不是任何用户可见文案。
- 它**看不到来访的隐藏标签**：只读来访说出的话、自评表（context_scales）和工具结果。

**给 S3 的接入接口**（smoke 用 `--agent module:function` 切换）：

    async def run_session(visitor: dict, sim: SimVisitor, *, run_id: str,
                          playbook_version: str) -> dict   # 返回契约 session 对象

    - 用 `sim.opening()` 拿第 1 轮开场，用 `await sim.respond(agent_text, asked_topics)` 拿每句回答；
      回答里的 `revealed_clue_ids` 直接写进 transcript。
    - 筛查工具用 `sim.screening.run_tool(tool, visitor)`（代码按真值生成，D2）。
    - `models.visitor` 填 `sim.model_name`。
"""
from __future__ import annotations

from sim.screening import run_tool
from sim.visitor_sim import SimVisitor

ROUND_TOPICS = {
    1: [['schedule_regularity', 'weekend_catchup'],
        ['bed_wakefulness', 'worry_rumination'],
        ['mood', 'snoring_breathing']],
    2: [['chronotype', 'screen_in_bed', 'shift_work'],
        ['sleep_elsewhere', 'caffeine_alcohol', 'fear_of_sleeplessness'],
        ['leg_discomfort', 'anxiety', 'daytime_sleepiness'],
        ['revenge_bedtime', 'health_conditions', 'self_harm']],
}

PATH_KEYWORDS = {
    'P1': ('周末', '咖啡', '浓茶', '喝两口', '中午', '午', '没有固定', '看行程', '开会', '眯'),
    'P2': ('越来越精神', '沙发', '酒店', '硬躺', '办公桌', '没在想', '不想什么', '地垫', '躺着等'),
    'P3': ('脑子', '复盘', '算账', '看表', '时间', '睡不着了', '垮', '紧张', '面试', '分数'),
    'P4': ('两三点才困', '夜猫子', '三班倒', '夜班', '闹钟', '天都亮'),
    'P5': ('刷', '短视频', '游戏', '追剧', '舍不得睡', '手机', '充电器'),
}
OSA_TRIGGERS = ('打鼾', '打呼', '憋醒', '停一下')
MOOD_TRIGGERS = ('兴趣', '心情', '一直在担心', '提心吊胆', '绷', '最坏')
# 不宁腿核心特征的粗糙关键词（冲动/不适、活动缓解、静息或夜间加重）；满足 ≥3 个特征转 R2（RC-2）
LEG_FEATURES = (('想动', '动一动', '虫子'), ('走几步', '走一走'), ('躺下', '躺回去', '坐久了', '坐长途'),
                ('晚上', '夜里'))

# 安全占位规则（真实规则见 safety/lexicon.yaml）
ACTIVE_PATTERNS = (('不想活', '怎么做'), ('结束生命',))
PASSIVE_PATTERNS = (('不再醒',), ('不想醒',), ('别醒',))
HISTORY_PAST = ('以前', '大学的时候', '高中', '年前', '早就', '好多年', '五年')
HISTORY_RISK = ('死', '划', '药', '住院')

STUB_SAFETY_CHECK = '[stub 安全确认占位]'
STUB_CRISIS = '[stub 危机流程占位]'
LEVEL_RANK = {'none': 0, 'passive': 1, 'active': 2}


def _has(text: str, words) -> bool:
    return any(w in text for w in words)


def _classify_safety(text: str) -> str | None:
    if any(all(w in text for w in pat) for pat in ACTIVE_PATTERNS):
        return 'active'
    if any(all(w in text for w in pat) for pat in PASSIVE_PATTERNS):
        return 'passive'
    if _has(text, HISTORY_PAST) and _has(text, HISTORY_RISK):
        return 'history'
    return None


def _vote_path(texts: list[str]) -> tuple[str, float]:
    joined = ''.join(texts)
    votes = {p: sum(joined.count(w) for w in words) for p, words in PATH_KEYWORDS.items()}
    total = sum(votes.values())
    best = max(votes, key=lambda p: (votes[p], p == 'P1'))  # 平票偏 P1（"普通咨询师"默认）
    return best, round(votes[best] / total, 2) if total else 0.2


class _Session:
    def __init__(self, visitor: dict, sim: SimVisitor, run_id: str, playbook_version: str):
        self.visitor, self.sim = visitor, sim
        self.data = {
            'schema_version': '0.1.0',
            'session_id': f'{run_id}/{visitor["id"]}',
            'run_id': run_id,
            'visitor_id': visitor['id'],
            'playbook_version': playbook_version,
            'models': {'agent': 'stub-agent', 'visitor': sim.model_name},
            'status': 'completed',
            'error': None,
            'context_scales': visitor['prefilled'],
            'tool_calls': [],
            'rounds': [],
            'plan': None,
            'behaviors': {'goal_setting': 1, 'reflection': 1, 'emotion_response': 1,
                          'rationale_explained': 1, 'lecturing': 0, 'premature_advice': 0},
            'safety_events': [],
        }
        self.visitor_texts: list[str] = []
        self.tool_results: dict[str, dict] = {}
        self.exited = False
        self.safety_checked = False

    # ----- 小工具 -----
    def event(self, rnd, turn, level, source, action, matched):
        self.data['safety_events'].append({
            'round': rnd, 'turn': turn, 'level': level, 'source': source, 'action': action,
            'judge_status': 'skipped', 'judge_provider': 'stub-rules', 'judge_probs': None,
            'matched': matched})

    def has_active(self) -> bool:
        return any(e['level'] == 'active' for e in self.data['safety_events'])

    async def visitor_turn(self, rd, agent_text, topics):
        reply = await self.sim.respond(agent_text, topics)
        rd['next'] += 1
        turn = rd['next']
        rd['transcript'].append({'turn': turn, 'speaker': 'visitor', 'text': reply.text,
                                 'revealed_clue_ids': reply.revealed_clue_ids})
        self.visitor_texts.append(reply.text)
        await self.after_visitor(rd, turn, reply.text)

    def say(self, rd, speaker, text):
        rd['next'] += 1
        rd['transcript'].append({'turn': rd['next'], 'speaker': speaker, 'text': text,
                                 'revealed_clue_ids': []})

    async def after_visitor(self, rd, turn, text):
        level = _classify_safety(text)
        rnd = rd['round']
        if level == 'active':
            self.event(rnd, turn, 'active', 'rule_explicit', 'crisis_protocol', text[:20])
            rd['crisis_level'] = 'active'
            self.say(rd, 'safety', STUB_CRISIS)
            self.exited = True
            return
        if level == 'passive':
            self.event(rnd, turn, 'passive', 'rule_ambiguous', 'safety_check', text[:20])
            rd['crisis_level'] = max(rd['crisis_level'], 'passive', key=LEVEL_RANK.get)
            self.say(rd, 'safety', STUB_SAFETY_CHECK)
            self.safety_checked = True
            await self.visitor_turn(rd, STUB_SAFETY_CHECK, ['self_harm'])
            return
        if level == 'history':
            self.event(rnd, turn, 'none', 'rule_ambiguous', 'history_check', text[:20])
            text = '[stub] 核验：现在是否还有这种念头'
            rd['asked'].add('self_harm')
            self.say(rd, 'agent', text)
            await self.visitor_turn(rd, text, ['self_harm'])
            return
        # 筛查工具（每个最多调一次）
        if 'screen_osa' not in self.tool_results and _has(text, OSA_TRIGGERS):
            self.call_tool(rd, 'screen_osa')
        if 'screen_mood' not in self.tool_results and _has(text, MOOD_TRIGGERS):
            self.call_tool(rd, 'screen_mood')
            await self.check_item9(rd)

    def call_tool(self, rd, tool):
        rd['next'] += 1
        result = run_tool(tool, self.visitor)
        self.tool_results[tool] = result
        self.data['tool_calls'].append({'round': rd['round'], 'turn': rd['next'],
                                        'tool': tool, 'result': result})

    async def check_item9(self, rd):
        item9 = self.tool_results['screen_mood']['phq9_items'][8]
        if item9 > 0 and not self.has_active():
            self.event(rd['round'], rd['next'], 'passive', 'scale_item9', 'safety_check',
                       f'PHQ-9 第 9 题 = {item9}')
            rd['crisis_level'] = max(rd['crisis_level'], 'passive', key=LEVEL_RANK.get)
            if not self.safety_checked:
                self.safety_checked = True
                self.say(rd, 'safety', STUB_SAFETY_CHECK)
                await self.visitor_turn(rd, STUB_SAFETY_CHECK, ['self_harm'])

    def referral(self) -> str:
        osa, mood = self.tool_results.get('screen_osa'), self.tool_results.get('screen_mood')
        scales = {s['scale']: s['reported_score'] for s in self.data['context_scales']}
        if osa and osa['stop_bang'] >= 3:
            return 'R1'
        if (mood and (mood['phq9'] >= 10 or mood['gad7'] >= 10)) or \
                scales.get('phq9', 0) >= 10 or scales.get('gad7', 0) >= 10:
            return 'R3'
        leg_text = ''.join(t for t in self.visitor_texts if '腿' in t or '走几步' in t or '走一走' in t)
        if leg_text and sum(_has(leg_text, words) for words in LEG_FEATURES) >= 3:
            return 'R2'
        return 'R0'

    async def run(self) -> dict:
        # 会谈前自评表的第 9 题
        for s in self.data['context_scales']:
            if s['scale'] == 'phq9' and s['items'][8] > 0:
                self.event(1, 0, 'passive', 'scale_item9', 'safety_check',
                           f'PHQ-9 第 9 题 = {s["items"][8]}')
        for rnd in (1, 2):
            rd = {'round': rnd, 'transcript': [], 'next': 0, 'asked': set(), 'crisis_level': 'none'}
            if rnd == 1:
                opening = self.sim.opening()
                self.say(rd, 'visitor', opening.text)
                self.visitor_texts.append(opening.text)
            for topics in ROUND_TOPICS[rnd]:
                if self.exited:
                    break
                text = '[stub] 问题话题：' + '、'.join(topics)
                rd['asked'].update(topics)
                self.say(rd, 'agent', text)
                await self.visitor_turn(rd, text, topics)
            path, conf = _vote_path(self.visitor_texts)
            self.data['rounds'].append({
                'round': rnd, 'transcript': rd['transcript'],
                'asked_topics': sorted(rd['asked']), 'path_pred': path, 'path_confidence': conf,
                'referral_pred': self.referral(), 'crisis_level': rd['crisis_level']})
            if self.exited:
                self.data['status'] = 'crisis_exit'
                return self.data
        self.data['plan'] = self.plan()
        return self.data

    def plan(self) -> dict:
        path = self.data['rounds'][-1]['path_pred']
        referral = self.data['rounds'][-1]['referral_pred']
        components = {
            'P1': ['sleep_hygiene', 'fixed_risetime'],
            'P2': ['stimulus_control', 'fixed_risetime'],
            'P3': ['worry_time', 'relaxation'],
            'P4': ['light_timing', 'schedule_shift'],
            'P5': ['digital_curfew', 'fixed_risetime'],
        }[path]
        if referral != 'R0':
            components = components + ['referral_advice']
        return {'bedtime': '00:00', 'risetime': '07:00', 'tib_minutes': 420,
                'components': components, 'rationale_given': True,
                'contraindications_checked': False,
                'referral_advice': '[stub 转介建议占位]' if referral != 'R0' else None,
                'cards': []}


async def run_session(visitor: dict, sim: SimVisitor, *, run_id: str, playbook_version: str) -> dict:
    return await _Session(visitor, sim, run_id, playbook_version).run()
