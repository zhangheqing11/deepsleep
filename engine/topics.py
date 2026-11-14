"""Frozen keyword tagger: which contract topics an agent utterance asks about.

Used by the mock visitor for layered clue reveal and as the engine's fallback for
rounds[].asked_topics when the visitor simulator does not report topics itself.
"""
import re

TOPIC_PATTERNS: dict[str, str] = {
    "schedule_regularity": r"几点(?:上床|睡|起)|作息|上床时间|起床时间|规律",
    "weekend_catchup": r"周末|假期补觉|补觉|休息日",
    "caffeine_alcohol": r"咖啡|茶|奶茶|酒|饮料|可乐",
    "bed_wakefulness": r"躺(?:在床上|下|着)|床上.{0,6}(?:清醒|精神|醒着|做什么)|翻来覆去|在床上",
    "sleep_elsewhere": r"沙发|出差|酒店|换(?:个)?地方|别的地方|外地",
    "worry_rumination": r"想(?:什么|事)|脑子|担心|思绪|反复想|复盘",
    "fear_of_sleeplessness": r"睡不着.{0,6}(?:后果|怎么办|担心)|看时间|看表|害怕睡不着|睡眠分数",
    "chronotype": r"自然(?:犯困|醒|困)|放假.{0,8}(?:几点|睡)|夜猫子|几点会困|几点才困|生物钟",
    "shift_work": r"轮班|倒班|夜班|三班|班次",
    "screen_in_bed": r"手机|刷|视频|屏幕|平板|游戏|追剧",
    "revenge_bedtime": r"舍不得睡|自己的时间|报复性|拖着不睡",
    "snoring_breathing": r"打鼾|打呼|呼吸|憋醒|喘不上气|口干",
    "daytime_sleepiness": r"白天.{0,6}(?:困|犯困|打瞌睡|嗜睡|精神)|午睡|打盹",
    "leg_discomfort": r"腿|小腿|下肢",
    "mood": r"心情|情绪|低落|提不起(?:劲|兴趣)|兴趣|开心",
    "anxiety": r"紧张|焦虑|心慌|不安|放松不下来",
    "self_harm": r"伤害自己|自伤|轻生|不想活|不再醒来|这种念头|这些念头",
    "medication": r"药|褪黑素",
    "life_constraints": r"工作.{0,6}(?:时间|安排)|上班|孩子|通勤|家里.{0,6}安排|几点到岗",
    "health_conditions": r"身体(?:状况|情况)|疾病|高血压|怀孕|癫痫|双相|看过医生|健康",
}
_COMPILED = {topic: re.compile(pattern) for topic, pattern in TOPIC_PATTERNS.items()}


def tag_topics(text: str) -> list[str]:
    return [topic for topic, pattern in _COMPILED.items() if pattern.search(text)]
