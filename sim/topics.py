"""agent 发言 → 问到的 topic（关键词兜底）。

首选做法是引擎让 agent 以结构化输出声明本句问了哪些 topic（session.rounds[].asked_topics
本来就要记录），直接传给 SimVisitor.respond(asked_topics=...)。这里的关键词表只是 agent
没有声明时的兜底，召回有限；数据科学同学可以替换成更好的分类器（接口不变）。
"""
from __future__ import annotations

TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    'schedule_regularity': ('几点睡', '几点起', '作息', '规律', '固定时间', '起床时间', '上床时间'),
    'weekend_catchup': ('周末', '假期补觉', '补觉', '休息日'),
    'caffeine_alcohol': ('咖啡', '茶', '酒', '咖啡因', '饮料'),
    'bed_wakefulness': ('躺在床上', '床上醒着', '翻来覆去', '在床上做', '床上待'),
    'sleep_elsewhere': ('沙发', '出差', '酒店', '换个地方', '别的地方'),
    'worry_rumination': ('想什么', '脑子', '担心', '反复想', '思绪'),
    'fear_of_sleeplessness': ('睡不着会', '看时间', '害怕睡不着', '后果', '睡眠分数'),
    'chronotype': ('自然犯困', '自然醒', '夜猫子', '几点会困', '放假的时候'),
    'shift_work': ('倒班', '轮班', '夜班', '班次'),
    'screen_in_bed': ('手机', '刷', '屏幕', '游戏', '追剧', '视频'),
    'revenge_bedtime': ('舍不得睡', '自己的时间', '熬夜'),
    'snoring_breathing': ('打鼾', '打呼', '憋醒', '呼吸'),
    'daytime_sleepiness': ('白天困', '打盹', '午睡', '犯困', '嗜睡'),
    'leg_discomfort': ('腿',),
    'mood': ('心情', '情绪', '兴趣', '低落'),
    'anxiety': ('紧张', '焦虑', '心慌', '坐立不安'),
    'self_harm': ('伤害自己', '不想活', '轻生', '结束生命', '想过死'),
    'medication': ('药',),
    'life_constraints': ('工作安排', '时间安排', '家里', '孩子', '上班时间'),
    'health_conditions': ('身体', '血压', '疾病', '体检'),
}


def classify_topics(text: str) -> list[str]:
    return [topic for topic, words in TOPIC_KEYWORDS.items() if any(w in text for w in words)]
