"""MCP 协议探针：不经过 HomePort，直接用 SDK 标准写法跑一次工具调用。

用途有两个：
1. 现场自证"协议是真的"——比开 Inspector 更快，一条命令出结果。
2. 判断 HomePort 的 MCP 后端出问题，是我们的封装问题还是环境问题。

用法：
    python -m mocks.home_mcp.probe
"""

from __future__ import annotations

import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mocks.home_mcp.server"],
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print(f"tools/list -> {len(names)} 个: {names}")

            state = await session.call_tool("get_home_state", {})
            print(f"get_home_state -> {state.content[0].text if state.content else state}")

            lit = await session.call_tool(
                "set_light", {"brightness_pct": 10, "kelvin": 2700, "transition_s": 900}
            )
            print(f"set_light     -> {lit.content[0].text if lit.content else lit}")

            bad = await session.call_tool("set_light", {"brightness_pct": 0})
            print(f"set_light(0)  -> {bad.content[0].text if bad.content else bad}")

    print("probe: OK（协议链路完整）")
    return 0


if __name__ == "__main__":
    raise SystemExit(anyio.run(main))
