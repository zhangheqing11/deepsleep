"""演示脚本：按干预路径生成环境计划并执行。

用法：
    python -m mocks.home_mcp.demo            # 跑全部 P1–P5
    python -m mocks.home_mcp.demo P5         # 只跑 P5
    python -m mocks.home_mcp.demo P5 --bad   # 额外跑一遍越界探测（不影响上面结果）

输出即演示时屏幕上的"设备调用 trace"。
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import sys
from typing import Any

from engine.home import make_port

PARAMS_PATH = pathlib.Path(__file__).resolve().parents[2] / "domain" / "home_params.yaml"

# PyYAML 不可用时的最小回退，保证演示脚本永远能跑
FALLBACK: dict[str, Any] = {
    "rooms": {
        "bedroom": {
            "light": {
                "wind_down": {"brightness_pct": 10, "kelvin": 2700, "transition_s": 900},
                "sleep": {"brightness_pct": 1, "kelvin": 2200, "transition_s": 300},
                "wake": {"brightness_pct": 70, "kelvin": 5000, "transition_s": 600},
            },
            "climate": {"sleep": {"target_c": 19, "mode": "cool"}},
            "curtain": {"sleep": {"position_pct": 0}, "wake": {"position_pct": 100}},
        }
    },
    "paths": {
        "P1": {"light": ["wind_down", "sleep", "wake"], "climate": ["sleep"], "curtain": ["sleep", "wake"]},
        "P2": {"light": ["sleep"], "climate": [], "curtain": []},
        "P3": {"light": ["wind_down", "sleep"], "climate": ["sleep"], "curtain": []},
        "P4": {"light": ["wind_down", "sleep", "wake"], "climate": [], "curtain": ["wake"]},
        "P5": {"light": ["wind_down", "sleep"], "climate": [], "curtain": []},
    },
}

RATIONALE = {
    "wind_down": "睡前逐步降亮、暖色，给'该收了'的身体信号",
    "sleep": "入睡后保持低照度与偏凉环境",
    "wake": "起床前缓亮 + 透光，配合相位前移",
}

# 越界探测：验证包络是 clamp 而不是崩溃，以及不存在的能力会被明确拒绝
BAD_ACTIONS: list[dict[str, Any]] = [
    {"tool": "set_light", "args": {"brightness_pct": 0, "kelvin": 9000},
     "rationale": "越界：亮度 0、色温 9000K"},
    {"tool": "set_climate", "args": {"target_c": 30, "mode": "cool"},
     "rationale": "越界：目标温度 30℃"},
    {"tool": "power_off", "args": {},
     "rationale": "这个能力根本不存在"},
]


def load_params() -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        with PARAMS_PATH.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except Exception:
        return FALLBACK


def _scene_rationale(scene: str) -> str:
    return RATIONALE.get(scene, scene)


def build_environment(path: str, params: dict[str, Any]) -> dict[str, Any]:
    """把一条干预路径翻译成设备动作序列。

    路径 → {设备类型: [场景名]}。不同路径动不同设备组合，这是"个性化"的落点。
    """
    spec = params.get("paths", {}).get(path) or {}
    if isinstance(spec, (list, tuple)):  # 兼容旧格式：一个列表套三类设备
        spec = {"light": list(spec), "climate": list(spec), "curtain": list(spec)}

    bedroom = params["rooms"]["bedroom"]
    actions: list[dict[str, Any]] = []

    for kind, tool in (
        ("light", "set_light"),
        ("climate", "set_climate"),
        ("curtain", "set_curtain"),
    ):
        for scene in spec.get(kind, []) or []:
            if scene not in bedroom.get(kind, {}):
                continue
            spec_args = dict(bedroom[kind][scene])
            spec_args.pop("verified", None)
            spec_args.pop("note", None)
            actions.append(
                {
                    "tool": tool,
                    "args": spec_args,
                    "rationale": _scene_rationale(scene),
                }
            )

    return {"room": "bedroom", "actions": actions}


def _print_state(tag: str, state: dict[str, Any]) -> None:
    light = state.get("light", {})
    climate = state.get("climate", {})
    curtain = state.get("curtain", {})
    print(
        f"{tag}: 亮度 {light.get('brightness_pct')}% / "
        f"{light.get('kelvin')}K | "
        f"温度 {climate.get('target_c')}C（{climate.get('mode')}） | "
        f"窗帘 {curtain.get('position_pct')}%"
    )


async def run_one(path: str, params: dict[str, Any]) -> None:
    env = build_environment(path, params)
    port = await make_port(prefer="auto")
    try:
        before = await port.get_state()
        result = await port.apply(env)
        after = result.state or {}
    finally:
        await port.close()

    print(f"\n=== {path} ===")
    print(f"后端        : {port.backend.name}"
          + (f"（降级：{port.degraded_reason}）" if port.degraded_reason else ""))
    print(f"规划动作    : {len(env['actions'])}  已执行 {result.ok_count}"
          f"  被拒 {len(result.rejected)}")

    print("调用 trace:")
    for i, item in enumerate(result.applied, 1):
        args = json.dumps(item["args"], ensure_ascii=False)
        flag = "  [clamped]" if item.get("clamped") else ""
        print(f"  {i}. {item['tool']:<12} {args}{flag}")
        if item.get("rationale"):
            print(f"        └ {item['rationale']}")
    for item in result.rejected:
        print(f"  ! 拒绝 {item.get('tool')} -> {item.get('reason')}")

    _print_state("前", before)
    _print_state("后", after)


async def run_envelope_probe() -> None:
    """独立的越界探测：用一条新总线，不污染上面的演示状态。"""
    port = await make_port(prefer="direct")
    try:
        result = await port.apply({"actions": BAD_ACTIONS})
    finally:
        await port.close()

    print("\n=== 安全包络探测（独立总线，不影响上面的结果）===")
    print(f"执行成功    : {result.ok_count} 条（且全部被 clamp 到合法范围）")
    for item in result.clamped:
        print(f"  ~ clamp {item['tool']} -> {item['args']}  {item['notes']}")
    print(f"被拒绝      : {len(result.rejected)} 条")
    for item in result.rejected:
        print(f"  ! {item.get('tool')} -> {item.get('reason')}")


async def main(argv: list[str]) -> int:
    params = load_params()
    want = [a for a in argv if a.upper() in params.get("paths", {})]
    for path in want or sorted(params.get("paths", {})):
        await run_one(path, params)
    if "--bad" in argv:
        await run_envelope_probe()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
