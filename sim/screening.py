"""筛查工具：结果由代码按来访隐藏指数生成，不经模拟来访 LLM（BACKLOG D2）。

引擎（S3）在 agent 调用工具时：`result = run_tool(tool_name, visitor)`，把结果写进
session.tool_calls[{round, turn, tool, result}]，并在 `screen_mood` 的 phq9_items[8] > 0 时
把它交给安全层（safety_source = scale_item9）。结果等于隐藏真值（契约第 3 节）。
"""
from __future__ import annotations


def phq9_items(total: int, item9: int) -> list[int]:
    """把总分确定性地摊到 9 题：第 9 题固定为 item9，其余 8 题轮流加分，每题最多 3 分。"""
    total, item9 = int(total), int(item9)
    rest = total - item9
    if not 0 <= rest <= 24:
        raise ValueError(f'phq9={total} 与第 9 题={item9} 不相容')
    items = [0] * 9
    items[8] = item9
    i = 0
    while rest > 0:
        if items[i % 8] < 3:
            items[i % 8] += 1
            rest -= 1
        i += 1
    return items


def screen_mood(visitor: dict) -> dict:
    indices = visitor['indices']
    phq9 = int(indices['phq9'])
    return {'phq9': phq9,
            'phq9_items': phq9_items(phq9, visitor['crisis']['phq9_item9']),
            'gad7': int(indices['gad7'])}


def screen_osa(visitor: dict) -> dict:
    return {'stop_bang': int(visitor['indices']['stop_bang'])}


TOOLS = {'screen_mood': screen_mood, 'screen_osa': screen_osa}


def run_tool(tool: str, visitor: dict) -> dict:
    if tool not in TOOLS:
        raise ValueError(f'未知筛查工具: {tool}')
    return TOOLS[tool](visitor)
