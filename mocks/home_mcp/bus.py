"""模拟设备总线：内存状态 + 事件历史。

替代真实硬件，保证：
- 零网络、零驱动、零配对，现场 100% 可复现
- 状态可读、可回放、可一键重置（演示中途翻车能救）
- 每次写入留一条带序号的审计事件

接真设备时只替换这一层（Home Assistant adapter / Hue Bridge adapter），
MCP 工具定义和 agent 侧代码不动。
"""

from __future__ import annotations

import copy
import threading
import time
from dataclasses import dataclass, field
from typing import Any

DEFAULT_STATE: dict[str, Any] = {
    "room": "bedroom",
    "light": {"brightness_pct": 80.0, "kelvin": 5000.0, "last_transition_s": 0.0},
    "climate": {"target_c": 26.0, "mode": "cool"},
    "curtain": {"position_pct": 0.0},
}


@dataclass
class Event:
    """一次设备写入的审计记录。"""

    seq: int
    ts: float
    tool: str
    args: dict[str, Any]
    state_after: dict[str, Any]
    source: str = "agent"

    def as_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "ts": round(self.ts, 3),
            "tool": self.tool,
            "args": dict(self.args),
            "state_after": copy.deepcopy(self.state_after),
            "source": self.source,
        }


class DeviceBus:
    """一个房间的设备状态机。线程安全，可重置。"""

    def __init__(self, initial: dict[str, Any] | None = None):
        # 必须用 RLock：reset() 在持锁状态下还会调用 get_state()。
        # 普通 Lock 会在这里自死锁。
        self._lock = threading.RLock()
        self._seq = 0
        self._state = copy.deepcopy(initial or DEFAULT_STATE)
        self._history: list[Event] = []
        self.rev = 0

    # ------------------------------------------------------------ 读

    def get_state(self, room: str = "bedroom") -> dict[str, Any]:
        with self._lock:
            state = copy.deepcopy(self._state)
            state["room"] = room
            state["rev"] = self.rev
            return state

    def history(self, limit: int | None = None) -> list[dict[str, Any]]:
        with self._lock:
            items = self._history[-limit:] if limit else list(self._history)
            return [e.as_dict() for e in items]

    # ------------------------------------------------------------ 写

    def set_light(
        self,
        brightness_pct: float,
        kelvin: float = 2700.0,
        transition_s: float = 0.0,
    ) -> dict[str, Any]:
        with self._lock:
            self._state["light"] = {
                "brightness_pct": float(brightness_pct),
                "kelvin": float(kelvin),
                "last_transition_s": float(transition_s),
            }
            return self._record(
                "set_light",
                {
                    "brightness_pct": brightness_pct,
                    "kelvin": kelvin,
                    "transition_s": transition_s,
                },
            )

    def set_climate(self, target_c: float, mode: str = "cool") -> dict[str, Any]:
        with self._lock:
            self._state["climate"] = {"target_c": float(target_c), "mode": mode}
            return self._record("set_climate", {"target_c": target_c, "mode": mode})

    def set_curtain(self, position_pct: float) -> dict[str, Any]:
        with self._lock:
            self._state["curtain"] = {"position_pct": float(position_pct)}
            return self._record("set_curtain", {"position_pct": position_pct})

    def reset(self) -> dict[str, Any]:
        """回到初始状态，并清空历史。演示中途翻车用。"""
        with self._lock:
            self._state = copy.deepcopy(DEFAULT_STATE)
            self._history.clear()
            self._seq = 0
            self.rev = 0
            return self.get_state()

    # ------------------------------------------------------------ 分发

    def call(self, tool: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        """按 MCP 工具名分发。给 DirectBackend 用。"""
        args = dict(args or {})
        if tool == "get_home_state":
            return self.get_state(**args)
        if tool == "set_light":
            return self.set_light(**args)
        if tool == "set_climate":
            return self.set_climate(**args)
        if tool == "set_curtain":
            return self.set_curtain(**args)
        raise KeyError(f"unknown tool: {tool}")

    # ------------------------------------------------------------ 内部

    def _record(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        """调用方必须已持锁。"""
        self._seq += 1
        self.rev += 1
        snapshot = copy.deepcopy(self._state)
        snapshot["rev"] = self.rev
        self._history.append(
            Event(
                seq=self._seq,
                ts=time.time(),
                tool=tool,
                args=dict(args),
                state_after=snapshot,
            )
        )
        out = copy.deepcopy(self._state)
        out["rev"] = self.rev
        return out
