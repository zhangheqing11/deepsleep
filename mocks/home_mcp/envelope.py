"""L1 安全包络：设备动作的硬边界。

**本文件冻结，不进 playbook、不参与进化。**

进化层只能决定"什么时候调、调到包络内哪个值"（L2），
不能决定"范围是多少、能不能关设备"（L1）。

刻意设计：`ALLOWED_TOOLS` 里没有任何 power / off / disable 类能力。
产品边界写进代码，而不是写进文档。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------- 能力白名单

ALLOWED_TOOLS: tuple[str, ...] = (
    "get_home_state",
    "set_light",
    "set_climate",
    "set_curtain",
)

#: 会改变物理状态、受写入预算约束的工具
WRITE_TOOLS: tuple[str, ...] = ("set_light", "set_climate", "set_curtain")

#: 单次 session 最多写入次数（防 agent 反复试探）
MAX_WRITES_PER_SESSION: int = 8

#: 数值参数的允许范围（含端点）
RANGES: dict[str, tuple[float, float]] = {
    "brightness_pct": (1.0, 100.0),
    "kelvin": (1800.0, 6500.0),
    "transition_s": (0.0, 3600.0),
    "target_c": (18.0, 26.0),
    "position_pct": (0.0, 100.0),
}

#: 每个工具允许出现的参数（白名单）。出现别的键一律拒，防止 agent 发明
#: "power" / "duration" / "schedule" 之类不存在的控制面。
ALLOWED_ARGS: dict[str, tuple[str, ...]] = {
    "get_home_state": ("room",),
    "set_light": ("brightness_pct", "kelvin", "transition_s"),
    "set_climate": ("target_c", "mode"),
    "set_curtain": ("position_pct",),
}

#: 必填参数
REQUIRED: dict[str, tuple[str, ...]] = {
    "set_light": ("brightness_pct",),
    "set_climate": ("target_c",),
    "set_curtain": ("position_pct",),
}

#: 可选参数及其默认值
DEFAULTS: dict[str, dict[str, Any]] = {
    "get_home_state": {"room": "bedroom"},
    "set_light": {"kelvin": 2700.0, "transition_s": 0.0},
    "set_climate": {"mode": "cool"},
    "set_curtain": {},
}

CLIMATE_MODES: tuple[str, ...] = ("cool", "heat", "fan")


# ---------------------------------------------------------------- 结果结构


@dataclass
class Verdict:
    """一条动作经过包络校验后的结果。"""

    tool: str
    ok: bool
    args: dict[str, Any] = field(default_factory=dict)
    clamped: bool = False
    notes: list[str] = field(default_factory=list)
    reason: str | None = None
    #: agent 给出的理由，原样透传给看板与审计。包络不解释它，只负责搬运。
    rationale: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "ok": self.ok,
            "args": dict(self.args),
            "clamped": self.clamped,
            "notes": list(self.notes),
            "reason": self.reason,
            "rationale": self.rationale,
        }


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):  # bool 是 int 的子类，必须挡掉
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def check_one(action: dict[str, Any]) -> Verdict:
    """校验并归一化单条动作。越界就 clamp，不合法就拒。"""
    if not isinstance(action, dict):
        return Verdict(tool="", ok=False, reason="action_not_object")

    tool = str(action.get("tool", "")).strip()
    rationale = str(action.get("rationale", "") or "")
    raw = action.get("args") or {}

    def _rej(reason: str, args: dict[str, Any] | None = None) -> Verdict:
        return Verdict(
            tool=tool, ok=False, args=args or {}, reason=reason, rationale=rationale
        )

    if not isinstance(raw, dict):
        return _rej("args_not_object")

    if tool not in ALLOWED_TOOLS:
        return _rej("tool_not_allowed")

    allowed = set(ALLOWED_ARGS[tool])

    # 1) 未知参数直接拒
    unknown = set(raw) - allowed
    if unknown:
        return _rej(f"unknown_arg:{','.join(sorted(unknown))}")

    # 2) 必填检查
    for key in REQUIRED.get(tool, ()):
        if key not in raw:
            return _rej(f"missing_arg:{key}")

    args: dict[str, Any] = {}
    notes: list[str] = []
    clamped = False

    # 3) 数值参数 clamp（只处理本工具允许的参数）
    for key in ALLOWED_ARGS[tool]:
        if key not in RANGES or key not in raw:
            continue
        lo, hi = RANGES[key]
        num = _as_number(raw[key])
        if num is None:
            return _rej(f"not_a_number:{key}")
        if num < lo:
            notes.append(f"{key}:{num:g}->{lo:g}")
            num, clamped = lo, True
        elif num > hi:
            notes.append(f"{key}:{num:g}->{hi:g}")
            num, clamped = hi, True
        args[key] = round(num, 1)

    # 4) 枚举参数
    if tool == "set_climate":
        mode = str(raw.get("mode", DEFAULTS["set_climate"]["mode"])).strip().lower()
        if mode not in CLIMATE_MODES:
            return _rej(f"bad_mode:{mode}")
        args["mode"] = mode

    if tool == "get_home_state":
        args["room"] = str(raw.get("room", DEFAULTS["get_home_state"]["room"]))

    # 5) 可选参数补默认
    for key, default in DEFAULTS.get(tool, {}).items():
        args.setdefault(key, default)

    return Verdict(
        tool=tool,
        ok=True,
        args=args,
        clamped=clamped,
        notes=notes,
        rationale=rationale,
    )


def check_plan(
    actions: list[dict[str, Any]] | None,
    max_writes: int = MAX_WRITES_PER_SESSION,
) -> tuple[list[Verdict], list[Verdict]]:
    """校验一整份环境计划，返回 (accepted, rejected)。

    写入预算只约束 WRITE_TOOLS；读数不消耗预算。
    超预算的动作进 rejected，理由 `budget_exhausted`，不会静默丢弃。
    """
    accepted: list[Verdict] = []
    rejected: list[Verdict] = []
    writes = 0

    for action in actions or []:
        verdict = check_one(action)
        if not verdict.ok:
            rejected.append(verdict)
            continue
        if verdict.tool in WRITE_TOOLS:
            if writes >= max_writes:
                verdict.ok = False
                verdict.reason = "budget_exhausted"
                rejected.append(verdict)
                continue
            writes += 1
        accepted.append(verdict)

    return accepted, rejected


def envelope_snapshot() -> dict[str, Any]:
    """给看板/测试用的包络快照，方便审计"边界到底是什么"。"""
    return {
        "allowed_tools": list(ALLOWED_TOOLS),
        "write_tools": list(WRITE_TOOLS),
        "max_writes_per_session": MAX_WRITES_PER_SESSION,
        "ranges": {k: list(v) for k, v in RANGES.items()},
        "allowed_args": {k: list(v) for k, v in ALLOWED_ARGS.items()},
        "climate_modes": list(CLIMATE_MODES),
        "capabilities_excluded": ["power_off", "power_on", "lock", "alarm", "schedule_cron"],
    }
