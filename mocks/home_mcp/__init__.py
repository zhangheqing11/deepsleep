"""MCP 智能家居：真协议 + 模拟设备总线。

- envelope.py  L1 安全包络（冻结，不进 playbook）
- bus.py       模拟设备总线（内存状态 + 事件历史）
- server.py    MCP server（需要 `mcp` 包；缺失时降级到直连）
- demo.py      演示用：按干预路径 P1–P5 生成环境计划并执行
"""
