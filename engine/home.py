"""HomePort：把 agent 产出的 `plan.environment` 执行到设备层。

运行时后端只有一个：`DirectBackend`（直连模拟总线）。

MCP 协议由 `mocks/home_mcp/server.py` 实现、由 `mocks/home_mcp/probe.py` 证明，
但**不接在运行时链路上**——原因见下方"后端：MCP（运行时未启用）"一节。

设计约束：
1. 设备计划**不进入**计分与 4 周状态模型——本模块不得 import `scoring`。
2. 安全包络在这里再校验一次（server 侧也校验一次，防御纵深）。
3. 任何失败都不许抛穿：整条 run 必须能跑完，只标 `degraded`。
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from mocks.home_mcp.envelope import MAX_WRITES_PER_SESSION, check_plan

RETRIES = 1  # 失败后再试一次；仍失败则跳过该动作


# ---------------------------------------------------------------- 结果结构


@dataclass
class ApplyResult:
    """一次环境计划执行的结果。"""

    applied: list[dict[str, Any]] = field(default_factory=list)
    clamped: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    degraded: bool = False
    error: str | None = None
    state: dict[str, Any] | None = None

    @property
    def ok_count(self) -> int:
        return len(self.applied)

    def as_dict(self) -> dict[str, Any]:
        return {
            "applied": self.applied,
            "clamped": self.clamped,
            "rejected": self.rejected,
            "degraded": self.degraded,
            "error": self.error,
            "state": self.state,
        }


@runtime_checkable
class Backend(Protocol):
    name: str

    async def start(self) -> None: ...

    async def call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]: ...

    async def get_state(self) -> dict[str, Any]: ...

    async def close(self) -> None: ...


# ---------------------------------------------------------------- 后端：直连


class DirectBackend:
    """直连模拟总线。不需要 mcp 包，永远可用。"""

    name = "direct"

    def __init__(self, bus: Any):
        self._bus = bus

    async def start(self) -> None:
        return None

    async def call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(self._bus.call, tool, dict(args))

    async def get_state(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._bus.get_state)

    async def close(self) -> None:
        return None


# ---------------------------------------------------------------- 后端：MCP（运行时未启用）
#
# 这里原本有一个 McpBackend（每次调用用嵌套 async with 起一个 stdio 会话）。
# 协议层验证通过，见 mocks/home_mcp/probe.py：4 个工具、clamp、真实握手都正常。
# 但它**状态不跨调用保持**——每次调用都是新的 server 进程 + 新的内存总线，
# 三条 set_* 落到三个独立总线上，设备面板会显示"什么都没变"。
#
# 要既走协议又保状态，必须把 server 起成长驻进程、用 streamable-http 连。
# 对 40–50 并发的现场运行这是额外风险，所以运行时只保留 DirectBackend；
# 接真设备时把 DirectBackend 换成 HTTP adapter，HomePort 与 agent 代码不用动。


# ---------------------------------------------------------------- 门面


class HomePort:
    """执行 `plan.environment` 的唯一入口。"""

    def __init__(self, backend: Backend, degraded_reason: str | None = None):
        self.backend = backend
        self.degraded_reason = degraded_reason
        self._started = False

    # ---------------------------------------------------------- 生命周期

    async def start(self) -> "HomePort":
        if not self._started:
            await self.backend.start()
            self._started = True
        return self

    async def close(self) -> None:
        try:
            await self.backend.close()
        except BaseException as exc:  # noqa: BLE001  关闭永远不该把调用方拖崩
            print(
                f"[warn] backend.close 失败（已忽略）：{type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
        finally:
            self._started = False

    async def __aenter__(self) -> "HomePort":
        return await self.start()

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    # ---------------------------------------------------------- 读

    async def get_state(self) -> dict[str, Any]:
        return await self.backend.get_state()

    # ---------------------------------------------------------- 写

    async def apply(
        self,
        environment: dict[str, Any] | None,
        max_writes: int = MAX_WRITES_PER_SESSION,
    ) -> ApplyResult:
        """执行一份环境计划。绝不抛穿。"""
        result = ApplyResult()
        if not environment:
            result.state = await self._safe_state()
            return result

        actions = environment.get("actions") or []
        accepted, rejected = check_plan(actions, max_writes=max_writes)
        result.rejected = [v.as_dict() for v in rejected]

        await self.start()

        for verdict in accepted:
            payload: dict[str, Any] | None = None
            last_error: str | None = None
            for attempt in range(RETRIES + 1):
                try:
                    payload = await self.backend.call(verdict.tool, dict(verdict.args))
                    break
                except Exception as exc:  # 超时 / 连接断 / 工具报错
                    last_error = f"{type(exc).__name__}: {exc}"
                    if attempt < RETRIES:
                        await asyncio.sleep(0.05)

            if payload is None:
                result.degraded = True
                result.error = result.error or last_error
                result.rejected.append(
                    {
                        "tool": verdict.tool,
                        "ok": False,
                        "args": dict(verdict.args),
                        "reason": f"call_failed:{last_error}",
                    }
                )
                continue

            if payload.get("clamped") or verdict.clamped:
                result.clamped.append(
                    {
                        "tool": verdict.tool,
                        "args": dict(verdict.args),
                        "notes": list(verdict.notes) or payload.get("notes", []),
                        "rationale": verdict.rationale,
                    }
                )
            result.applied.append(
                {
                    "tool": verdict.tool,
                    "args": dict(verdict.args),
                    "clamped": bool(payload.get("clamped") or verdict.clamped),
                    "rationale": verdict.rationale,
                }
            )

        result.state = await self._safe_state()
        return result

    # ---------------------------------------------------------- 内部

    async def _safe_state(self) -> dict[str, Any] | None:
        try:
            return await self.backend.get_state()
        except Exception:
            return None


# ---------------------------------------------------------------- 工厂


async def make_port(
    prefer: str = "auto",
    bus: Any | None = None,
) -> HomePort:
    """选后端。

    目前只有直连一种运行时后端，原因写在 `docs/demo-home.md` §9：

    - stdio MCP 的 client 每次调用都会新建一个 server 进程，三个写入落在三个
      独立的内存总线上 —— 状态不跨调用保持，设备面板会显示"什么都没变"。
    - 要既走协议又保状态，得把 server 起成长驻进程、用 streamable-http 连，
      这对 40–50 并发的现场运行是额外风险。

    所以：**MCP 协议由 `mocks/home_mcp/server.py` + `mocks/home_mcp/probe.py`
    证明（4 个工具、clamp、真实握手），运行时走直连。** 接真设备时把
    `DirectBackend` 换成 HTTP adapter 即可，HomePort 和 agent 代码不动。
    """
    if prefer == "mcp":
        raise NotImplementedError(
            "运行时暂不支持 MCP 后端（per-call 子进程不保状态）。"
            "协议验证请运行：python -m mocks.home_mcp.probe"
        )
    if prefer not in ("auto", "direct"):
        raise ValueError(f"unknown prefer: {prefer}")

    if bus is None:
        from mocks.home_mcp.bus import DeviceBus

        bus = DeviceBus()

    return HomePort(DirectBackend(bus))


def make_port_sync(prefer: str = "auto", bus: Any | None = None) -> HomePort:
    """同步包装，给脚本/演示用。"""
    return asyncio.run(make_port(prefer=prefer, bus=bus))
