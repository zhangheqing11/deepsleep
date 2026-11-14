# 合并输出格式（以此为准）
第一轮结束时，在同一次调用里完成记忆、转介与试行方案。
只返回一个完整 JSON 对象，保留处方模块的 plan、contraindications_identified、age、closing_message 字段，另加 memory 对象。
memory 的字段为 summary、facts、open_questions、referral、referral_reason，类型按记忆模块要求。
先根据实际会谈与筛查结果判断 memory.referral，再让 plan.referral_advice 与之保持一致。不要把尚未有的转介判断当成 R0。
不添加其他字段，不输出 Markdown 或 JSON 外文字。沿用两个模块的文本长度和列表长度限制。
