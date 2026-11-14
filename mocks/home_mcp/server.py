"""MCP server：真协议，假设备。

启动：
    python -m mocks.home_mcp.server          # stdio（默认，给本机 client 用）

未安装 `mcp` 包时本模块仍可导入，只是 build_server() 会抛明确的错误；
engine.home.make_port() 捕获后自动降级为直连 DeviceBus。
"""

from __future__ import annotations

import sys
from typing import Any, Callable

from .bus import DeviceBus
from .envelope import check_one

try:  # 官方 Python SDK
    from mcp.server.fastmcp import FastMCP  # type: ignore

    _MCP_IMPORT_ERROR: Exception | None = None
except Exception as _exc1:  # 兼容独立发布的 fastmcp 包
    try:
        from fastmcp import FastMCP  # type: ignore

        _MCP_IMPORT_ERROR = None
    except Exception:
        FastMCP = None  # type: ignore[assignment]
        _MCP_IMPORT_ERROR = _exc1


SERVER_NAME = "deepsleep-home"


def _annotation(readonly: bool) -> dict[str, Any]:
    """尽力标注工具语义；SDK 版本不支持就返回空 dict。"""
    try:
        from mcp.types import ToolAnnotations  # type: ignore

        return {
            "annotations": ToolAnnotations(
                readOnlyHint=readonly,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            )
        }
    except Exception:
        return {}


def _register(mcp: Any, fn: Callable[..., Any], kwargs: dict[str, Any]) -> None:
    """注册工具，兼容不同版本的装饰器签名。"""
    try:
        mcp.tool(**kwargs)(fn)
    except TypeError:
        mcp.tool()(fn)


def _payload(verdict, state: dict[str, Any] | None = None) -> dict[str, Any]:
    if not verdict.ok:
        return {"ok": False, "reason": verdict.reason, "clamped": False, "notes": []}
    return {
        "ok": True,
        "clamped": verdict.clamped,
        "notes": verdict.notes,
        "state": state if state is not None else {},
    }


def build_server(bus: DeviceBus | None = None):
    """构造 MCP server。工具集固定为 4 个，没有 power/off 类能力。"""
    if FastMCP is None:
        raise RuntimeError(
            "MCP server 不可用：mcp 包未安装，或已安装但导入失败。"
            f"原始错误：{_MCP_IMPORT_ERROR}. "
            "修法：pip install \"mcp[cli]\"（若报缺依赖，按提示补齐 referencing / anyio / pydantic）。"
            "降级方式：engine.home.HomePort 使用 DirectBackend 直连 DeviceBus。"
        )

    bus = bus or DeviceBus()
    mcp = FastMCP(SERVER_NAME)

    # ---------------------------------------------------------- 读

    def get_home_state(room: str = "bedroom") -> dict[str, Any]:
        """读取房间当前设备状态（亮度/色温/目标温度/窗帘位置）。只读。"""
        verdict = check_one({"tool": "get_home_state", "args": {"room": room}})
        if not verdict.ok:
            return _payload(verdict)
        return _payload(verdict, bus.get_state(verdict.args["room"]))

    # ---------------------------------------------------------- 写

    def set_light(
        brightness_pct: float,
        kelvin: float = 2700.0,
        transition_s: float = 0.0,
    ) -> dict[str, Any]:
        """调整灯光。brightness_pct 1-100，kelvin 1800-6500，transition_s 0-3600。

        越界会被安全包络 clamp 到合法范围，并在返回的 clamped/notes 里说明。
        """
        verdict = check_one(
            {
                "tool": "set_light",
                "args": {
                    "brightness_pct": brightness_pct,
                    "kelvin": kelvin,
                    "transition_s": transition_s,
                },
            }
        )
        if not verdict.ok:
            return _payload(verdict)
        state = bus.set_light(
            brightness_pct=verdict.args["brightness_pct"],
            kelvin=verdict.args["kelvin"],
            transition_s=verdict.args["transition_s"],
        )
        return _payload(verdict, state)

    def set_climate(target_c: float, mode: str = "cool") -> dict[str, Any]:
        """设置空调目标温度（18-26 摄氏度）与模式（cool/heat/fan）。

        没有 power 参数：本工具不能关机或开机。
        """
        verdict = check_one(
            {"tool": "set_climate", "args": {"target_c": target_c, "mode": mode}}
        )
        if not verdict.ok:
            return _payload(verdict)
        state = bus.set_climate(
            target_c=verdict.args["target_c"], mode=verdict.args["mode"]
        )
        return _payload(verdict, state)

    def set_curtain(position_pct: float) -> dict[str, Any]:
        """设置窗帘开合百分比（0 全关，100 全开）。"""
        verdict = check_one(
            {"tool": "set_curtain", "args": {"position_pct": position_pct}}
        )
        if not verdict.ok:
            return _payload(verdict)
        state = bus.set_curtain(position_pct=verdict.args["position_pct"])
        return _payload(verdict, state)

    # 恰好 4 个工具：1 读 + 3 写。没有 power_off / power_on / lock。
    _register(mcp, get_home_state, _annotation(readonly=True))
    _register(mcp, set_light, _annotation(readonly=False))
    _register(mcp, set_climate, _annotation(readonly=False))
    _register(mcp, set_curtain, _annotation(readonly=False))

    return mcp


def main() -> int:
    if FastMCP is None:
        print(
            "MCP server 不可用：mcp 包未安装或导入失败。"
            f"（{_MCP_IMPORT_ERROR}）\n"
            "修法：pip install \"mcp[cli]\"；"
            "或使用 DirectBackend 直连 DeviceBus（engine.home.make_port(prefer=\"direct\")）。",
            file=sys.stderr,
        )
        return 2
    build_server().run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
