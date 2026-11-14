"""模拟来访：分层线索 + deny_first，LLM 只负责措辞。

**透露什么由代码决定，怎么说才交给 LLM。** 每回合：
1. 拿到 agent 本句问到的 topic（引擎传 `asked_topics`；没传就用 `sim.topics` 关键词兜底）。
2. 对每条 `reveal_topic` 被问到、尚未透露的线索：
   - `deny_first` 且 `persona.defensiveness` 为 mid/high（PC-2 A）且还没否认过 → 本回合否认，记下；
   - 否则 → 本回合透露。
3. 把"要透露的线索原文 + 要否认的话题"交给 ds flash（temperature 0）改写成符合人格卡的口语；
   没有 key 或调用失败 → 确定性 mock 直接拼接线索原文。
4. `revealed_clue_ids` 由第 2 步给出，**不看 LLM 输出**，保证计分可复现。

模拟来访看得到的只有 persona、opening_complaint、clues、diary（AGENTS/contract 第 2 节）；
indices 里的量表分不自述，筛查结果由 `sim.screening` 代码生成（D2）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sim.llm import DsClient
from sim.topics import classify_topics

DEFENSIVE_LEVELS = ('mid', 'high')

# mock 否认话术（模拟来访的台词，不是 app 文案）
DENIAL_TEXT = {
    'screen_in_bed': '就看一会儿，没多久。',
    'revenge_bedtime': '也没有故意熬吧。',
    'caffeine_alcohol': '没有啊，就偶尔喝一点。',
    'mood': '还好，就是有点累。',
    'anxiety': '也还好吧，谁没点压力。',
    'self_harm': '没有，没有这种想法。',
    'snoring_breathing': '没人说过吧。',
    'leg_discomfort': '没有，就是有点酸。',
    'sleep_elsewhere': '好像没有，在哪儿都差不多。',
    'bed_wakefulness': '没有，床就是用来睡觉的。',
    'fear_of_sleeplessness': '也没有那么夸张。',
}
DEFAULT_DENIAL = '没有吧。'
SCHEDULE_TOPICS = ('schedule_regularity', 'weekend_catchup', 'chronotype')
FOLLOWUP_AFTER_SELF_HARM = {
    'passive': '没有具体的打算，也没想过怎么做，就是累的时候会这么想。',
    'none': '现在没有了，已经过去了。',
}


@dataclass
class VisitorReply:
    text: str
    revealed_clue_ids: list[str] = field(default_factory=list)
    denied_clue_ids: list[str] = field(default_factory=list)
    asked_topics: list[str] = field(default_factory=list)
    renderer: str = 'mock'          # 'mock' | DS_MODEL 名
    fallback_reason: str | None = None


class SimVisitor:
    """一个来访的一次会谈。引擎每轮/每回合调用 respond()；状态（已透露、已否认）跨两轮保留。"""

    def __init__(self, visitor: dict, client: DsClient | None = None):
        self.visitor = visitor
        self.client = client
        self.persona = visitor['persona']
        self.revealed: set[str] = set()
        self.denied: set[str] = set()

    # ---------- 确定性部分 ----------

    @property
    def model_name(self) -> str:
        return self.client.model if self.client else 'mock'

    def opening(self) -> VisitorReply:
        return VisitorReply(text=self.visitor['opening_complaint'], renderer='fixed')

    def decide(self, asked_topics: list[str]) -> tuple[list[dict], list[dict]]:
        """返回 (本回合透露的线索, 本回合否认的线索)，并更新状态。"""
        defensive = self.persona['defensiveness'] in DEFENSIVE_LEVELS
        reveal, deny = [], []
        for clue in self.visitor['clues']:
            if clue['reveal_topic'] not in asked_topics or clue['id'] in self.revealed:
                continue
            if clue['deny_first'] and defensive and clue['id'] not in self.denied:
                self.denied.add(clue['id'])
                deny.append(clue)
            else:
                self.revealed.add(clue['id'])
                reveal.append(clue)
        return reveal, deny

    def _diary_summary(self) -> str:
        weekdays = self.visitor['diary'][:5]
        bed = sorted(d['bedtime'] for d in weekdays)[2]
        rise = sorted(d['risetime'] for d in weekdays)[2]
        return f'平时大概{bed}上床，{rise}起床。'

    def _extras(self, asked_topics: list[str], reveal: list[dict], deny: list[dict]) -> list[str]:
        """不属于线索、但来访自然会说的话：作息自述、对危机核验的回答。"""
        extras = []
        covered = {c['reveal_topic'] for c in reveal + deny}
        if any(t in asked_topics and t not in covered for t in SCHEDULE_TOPICS):
            extras.append(self._diary_summary())
        crisis_clues = [c for c in self.visitor['clues'] if c['supports'] == 'crisis']
        if ('self_harm' in asked_topics and 'self_harm' not in covered
                and any(c['id'] in self.revealed for c in crisis_clues)):
            level = self.visitor['crisis']['level']
            if level == 'active':
                extras.extend(c['content'] for c in crisis_clues)
            else:
                extras.append(FOLLOWUP_AFTER_SELF_HARM[level])
        return extras

    def mock_text(self, reveal: list[dict], deny: list[dict], extras: list[str]) -> str:
        parts = [DENIAL_TEXT.get(c['reveal_topic'], DEFAULT_DENIAL) for c in deny]
        parts += [c['content'] for c in reveal]
        parts += extras
        if not parts:
            parts = ['其他好像也没什么特别的。' if self.persona['expressiveness'] == 'brief'
                     else '嗯……这个我倒没太注意，其他好像也没什么特别的。']
        # 去重并保持顺序（同一话题的否认句可能重复）
        return ''.join(dict.fromkeys(parts))

    # ---------- LLM 措辞 ----------

    def _system_prompt(self) -> str:
        p = self.persona
        return (
            '你在扮演一位来做睡眠咨询的来访者，只用中文口语回答，不要使用任何格式符号。\n'
            f'人设：{p["age"]}岁，{p["occupation"]}，生活约束：{"、".join(p["constraints"]) or "无"}。\n'
            f'说话风格：{"简短，一两句话" if p["expressiveness"] == "brief" else "话比较多，两三句话"}；'
            f'情绪外露程度：{p["emotionality"]}。\n'
            '规则：只能表达"本回合要说的内容"里列出的信息，可以换成自己的说法，但不得增加、推测或透露任何其他'
            '睡眠、健康、情绪相关的信息；"要否认的话题"就用轻描淡写的方式否认；不要提问，不要给建议。'
        )

    def _user_prompt(self, agent_text: str, reveal: list[dict], deny: list[dict], extras: list[str]) -> str:
        say = [c['content'] for c in reveal] + extras
        lines = [f'咨询师刚才说：{agent_text}', '本回合要说的内容：' + ('；'.join(say) if say else '（无新信息，礼貌地说没什么特别的）')]
        if deny:
            lines.append('要否认的话题：' + '、'.join(sorted({c['reveal_topic'] for c in deny})))
        return '\n'.join(lines)

    async def respond(self, agent_text: str, asked_topics: list[str] | None = None) -> VisitorReply:
        topics = list(asked_topics) if asked_topics is not None else classify_topics(agent_text)
        reveal, deny = self.decide(topics)
        extras = self._extras(topics, reveal, deny)
        reply = VisitorReply(text='', revealed_clue_ids=[c['id'] for c in reveal],
                             denied_clue_ids=[c['id'] for c in deny], asked_topics=topics)
        if self.client is not None:
            text = await self.client.complete(self._system_prompt(),
                                              self._user_prompt(agent_text, reveal, deny, extras))
            if text:
                reply.text, reply.renderer = text, self.client.model
                return reply
            reply.fallback_reason = self.client.last_error
        reply.text = self.mock_text(reveal, deny, extras)
        return reply
