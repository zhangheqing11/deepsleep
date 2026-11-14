"""MCP 智能家居层的测试。

不依赖 mcp 包、不依赖网络：全部跑在模拟总线上。
运行：`python -m pytest tests -q` 或 `python -m unittest discover -s tests`
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import unittest

from engine.home import ApplyResult, HomePort, make_port
from mocks.home_mcp import envelope
from mocks.home_mcp.bus import DeviceBus

ROOT = pathlib.Path(__file__).resolve().parents[1]


class FailingBackend:
    """模拟 MCP 子进程挂掉：所有调用都抛。"""

    name = "failing"

    async def start(self) -> None:
        return None

    async def call(self, tool, args):
        raise TimeoutError("simulated device timeout")

    async def get_state(self):
        return {"room": "bedroom", "light": {}, "climate": {}, "curtain": {}}

    async def close(self) -> None:
        return None


# --------------------------------------------------------------- 包络


class TestEnvelope(unittest.TestCase):
    def test_tool_count_is_four(self):
        self.assertEqual(len(envelope.ALLOWED_TOOLS), 4)

    def test_no_power_capability(self):
        joined = " ".join(envelope.ALLOWED_TOOLS).lower()
        for banned in ("power", "off", "lock", "alarm", "kill", "cron"):
            self.assertNotIn(banned, joined, f"工具集里不该出现 {banned}")

    def test_snapshot_lists_excluded_capabilities(self):
        snap = envelope.envelope_snapshot()
        self.assertIn("power_off", snap["capabilities_excluded"])
        self.assertEqual(snap["max_writes_per_session"], 8)

    def test_clamp_low_brightness(self):
        v = envelope.check_one({"tool": "set_light", "args": {"brightness_pct": 0}})
        self.assertTrue(v.ok)
        self.assertTrue(v.clamped)
        self.assertEqual(v.args["brightness_pct"], 1.0)
        self.assertTrue(any("brightness_pct" in n for n in v.notes))

    def test_clamp_high_temp(self):
        v = envelope.check_one({"tool": "set_climate", "args": {"target_c": 30}})
        self.assertTrue(v.ok)
        self.assertTrue(v.clamped)
        self.assertEqual(v.args["target_c"], 26.0)

    def test_clamp_low_temp(self):
        v = envelope.check_one({"tool": "set_climate", "args": {"target_c": 5}})
        self.assertEqual(v.args["target_c"], 18.0)

    def test_clamp_kelvin(self):
        v = envelope.check_one({"tool": "set_light", "args": {"brightness_pct": 50, "kelvin": 9000}})
        self.assertEqual(v.args["kelvin"], 6500.0)

    def test_reject_unknown_tool(self):
        v = envelope.check_one({"tool": "power_off", "args": {}})
        self.assertFalse(v.ok)
        self.assertEqual(v.reason, "tool_not_allowed")

    def test_reject_unknown_arg(self):
        v = envelope.check_one(
            {"tool": "set_light", "args": {"brightness_pct": 50, "power": True}}
        )
        self.assertFalse(v.ok)
        self.assertEqual(v.reason, "unknown_arg:power")

    def test_reject_cross_tool_arg(self):
        # target_c 是空调参数，不该被 set_light 接受
        v = envelope.check_one({"tool": "set_light", "args": {"target_c": 20}})
        self.assertFalse(v.ok)
        self.assertEqual(v.reason, "unknown_arg:target_c")

    def test_reject_missing_required(self):
        v = envelope.check_one({"tool": "set_light", "args": {"kelvin": 2700}})
        self.assertFalse(v.ok)
        self.assertEqual(v.reason, "missing_arg:brightness_pct")

    def test_reject_bad_mode(self):
        v = envelope.check_one({"tool": "set_climate", "args": {"target_c": 20, "mode": "turbo"}})
        self.assertFalse(v.ok)
        self.assertEqual(v.reason, "bad_mode:turbo")

    def test_reject_non_numeric(self):
        v = envelope.check_one({"tool": "set_light", "args": {"brightness_pct": "很暗"}})
        self.assertFalse(v.ok)
        self.assertTrue(v.reason.startswith("not_a_number"))

    def test_reject_bool_as_number(self):
        v = envelope.check_one({"tool": "set_light", "args": {"brightness_pct": True}})
        self.assertFalse(v.ok)

    def test_budget(self):
        actions = [
            {"tool": "set_light", "args": {"brightness_pct": 10 + i}} for i in range(10)
        ]
        accepted, rejected = envelope.check_plan(actions)
        self.assertEqual(len(accepted), envelope.MAX_WRITES_PER_SESSION)
        self.assertEqual(len(rejected), 2)
        self.assertTrue(all(r.reason == "budget_exhausted" for r in rejected))

    def test_reads_do_not_consume_budget(self):
        actions = [{"tool": "get_home_state", "args": {}}] * 20
        accepted, rejected = envelope.check_plan(actions)
        self.assertEqual(len(accepted), 20)
        self.assertEqual(len(rejected), 0)


# --------------------------------------------------------------- 总线


class TestBus(unittest.TestCase):
    def test_default_state(self):
        bus = DeviceBus()
        state = bus.get_state()
        self.assertEqual(state["light"]["brightness_pct"], 80.0)
        self.assertEqual(state["climate"]["target_c"], 26.0)

    def test_idempotent(self):
        bus = DeviceBus()
        bus.set_light(brightness_pct=10, kelvin=2700, transition_s=0)
        first = bus.get_state()
        bus.set_light(brightness_pct=10, kelvin=2700, transition_s=0)
        second = bus.get_state()
        self.assertEqual(first["light"], second["light"])

    def test_history_records_events(self):
        bus = DeviceBus()
        bus.set_light(brightness_pct=10)
        bus.set_climate(target_c=19)
        history = bus.history()
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["tool"], "set_light")
        self.assertEqual(history[1]["tool"], "set_climate")

    def test_reset(self):
        bus = DeviceBus()
        bus.set_light(brightness_pct=1)
        bus.reset()
        self.assertEqual(bus.get_state()["light"]["brightness_pct"], 80.0)
        self.assertEqual(bus.history(), [])

    def test_unknown_tool_raises(self):
        with self.assertRaises(KeyError):
            DeviceBus().call("power_off", {})


# --------------------------------------------------------------- HomePort


class TestHomePort(unittest.TestCase):
    def test_apply_direct(self):
        async def run():
            port = await make_port(prefer="direct")
            env = {
                "room": "bedroom",
                "actions": [
                    {
                        "tool": "set_light",
                        "args": {"brightness_pct": 10, "kelvin": 2700},
                        "rationale": "P5 睡前降亮",
                    },
                    {"tool": "set_climate", "args": {"target_c": 19}},
                ],
            }
            res = await port.apply(env)
            await port.close()
            return res

        res = asyncio.run(run())
        self.assertIsInstance(res, ApplyResult)
        self.assertEqual(res.ok_count, 2)
        self.assertFalse(res.degraded)
        self.assertEqual(res.state["light"]["brightness_pct"], 10.0)
        self.assertEqual(res.state["climate"]["target_c"], 19.0)
        # rationale 必须原样透传（看板与审计依赖它）
        self.assertEqual(res.applied[0]["rationale"], "P5 睡前降亮")

    def test_apply_surfaces_clamp(self):
        async def run():
            port = await make_port(prefer="direct")
            env = {"actions": [{"tool": "set_light", "args": {"brightness_pct": 0}}]}
            res = await port.apply(env)
            await port.close()
            return res

        res = asyncio.run(run())
        self.assertEqual(res.ok_count, 1)
        self.assertEqual(len(res.clamped), 1)
        self.assertEqual(res.clamped[0]["args"]["brightness_pct"], 1.0)

    def test_apply_rejects_without_raising(self):
        async def run():
            port = await make_port(prefer="direct")
            env = {
                "actions": [
                    {"tool": "power_off", "args": {}},
                    {"tool": "set_light", "args": {"brightness_pct": 50}},
                ]
            }
            res = await port.apply(env)
            await port.close()
            return res

        res = asyncio.run(run())
        self.assertEqual(res.ok_count, 1)
        self.assertEqual(len(res.rejected), 1)

    def test_apply_empty_environment(self):
        async def run():
            port = await make_port(prefer="direct")
            res = await port.apply(None)
            await port.close()
            return res

        res = asyncio.run(run())
        self.assertEqual(res.ok_count, 0)
        self.assertIsNotNone(res.state)

    def test_degraded_on_backend_failure(self):
        async def run():
            port = HomePort(FailingBackend())
            env = {"actions": [{"tool": "set_light", "args": {"brightness_pct": 10}}]}
            res = await port.apply(env)
            return res

        res = asyncio.run(run())
        self.assertTrue(res.degraded)
        self.assertEqual(res.ok_count, 0)
        self.assertEqual(len(res.rejected), 1)
        self.assertIn("call_failed", res.rejected[0]["reason"])

    def test_make_port_auto_defaults_to_direct(self):
        """auto 默认直连：MCP 每次调用起子进程，40–50 并发扛不住。"""

        async def run():
            port = await make_port(prefer="auto")
            name = port.backend.name
            await port.close()
            return name

        self.assertEqual(asyncio.run(run()), "direct")

    def test_mcp_backend_not_used_at_runtime(self):
        """MCP per-call 子进程不保状态，运行时必须拒绝它，且给出可执行的替代方案。"""

        async def run():
            await make_port(prefer="mcp")

        with self.assertRaises(NotImplementedError) as ctx:
            asyncio.run(run())
        self.assertIn("probe", str(ctx.exception))


# --------------------------------------------------------------- 架构红线


class TestArchitecture(unittest.TestCase):
    def test_home_layer_does_not_import_scoring(self):
        """设备层不许进入计分：保证主指标逐位可复现。"""
        for path in [
            ROOT / "engine" / "home.py",
            ROOT / "mocks" / "home_mcp" / "envelope.py",
            ROOT / "mocks" / "home_mcp" / "bus.py",
        ]:
            src = path.read_text(encoding="utf-8")
            self.assertNotIn(
                "import scoring", src, f"{path.name} 不该依赖 scoring"
            )
            self.assertNotIn(
                "from scoring", src, f"{path.name} 不该依赖 scoring"
            )

    def test_server_source_has_no_power_tool(self):
        src = (ROOT / "mocks" / "home_mcp" / "server.py").read_text(encoding="utf-8")
        names = re.findall(r"^\s*def (\w+)\(", src, flags=re.MULTILINE)
        for name in names:
            for banned in ("power", "turn_off", "kill", "lock"):
                self.assertNotIn(banned, name.lower(), f"server 里出现了危险工具 {name}")

    def test_server_import_does_not_crash(self):
        import mocks.home_mcp.server as server

        if server.FastMCP is None:
            with self.assertRaises(RuntimeError):
                server.build_server()
        else:
            self.assertIsNotNone(server.build_server())


# --------------------------------------------------------------- 参数表


class TestParams(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import yaml

        raw = (ROOT / "domain" / "home_params.yaml").read_text(encoding="utf-8")
        cls.params = yaml.safe_load(raw)

    def test_paths_reference_existing_scenes(self):
        bedroom = self.params["rooms"]["bedroom"]
        for path, spec in self.params["paths"].items():
            for kind, scenes in spec.items():
                self.assertIn(kind, bedroom, f"{path} 引用了未知设备类型 {kind}")
                for scene in scenes:
                    self.assertIn(
                        scene, bedroom[kind], f"{path}.{kind} 引用了不存在的场景 {scene}"
                    )

    def test_paths_differ_per_device_kind(self):
        """不同路径必须动不同设备组合，否则'个性化环境'是话术。"""
        paths = self.params["paths"]
        # P2（床=睡）与 P5（数字娱乐）都只该动灯
        self.assertEqual(paths["P2"].get("climate", []), [])
        self.assertEqual(paths["P2"].get("curtain", []), [])
        self.assertEqual(paths["P5"].get("climate", []), [])
        # 灯的场景序列不能全是同一条
        light_sigs = {tuple(v.get("light", [])) for v in paths.values()}
        self.assertGreater(len(light_sigs), 1, "所有路径的灯光计划完全一样")

    def test_every_path_declares_all_kinds(self):
        for path, spec in self.params["paths"].items():
            self.assertEqual(
                set(spec), {"light", "climate", "curtain"}, f"{path} 漏声明设备类型"
            )

    def test_every_scene_is_verified_flagged(self):
        bedroom = self.params["rooms"]["bedroom"]
        for kind, scenes in bedroom.items():
            for name, spec in scenes.items():
                self.assertIn("verified", spec, f"{kind}.{name} 缺 verified 标记")

    def test_all_values_inside_envelope(self):
        """参数表里的值必须落在安全包络内，否则场景一上线就被 clamp。"""
        bedroom = self.params["rooms"]["bedroom"]
        for name, spec in bedroom["light"].items():
            lo, hi = envelope.RANGES["brightness_pct"]
            self.assertGreaterEqual(spec["brightness_pct"], lo)
            self.assertLessEqual(spec["brightness_pct"], hi)
            lo, hi = envelope.RANGES["kelvin"]
            self.assertGreaterEqual(spec["kelvin"], lo)
            self.assertLessEqual(spec["kelvin"], hi)
        for name, spec in bedroom["climate"].items():
            lo, hi = envelope.RANGES["target_c"]
            self.assertGreaterEqual(spec["target_c"], lo)
            self.assertLessEqual(spec["target_c"], hi)

    def test_declared_safety_matches_code(self):
        """文档里写的边界必须等于代码里的边界。"""
        declared = self.params["safety_declared"]
        self.assertEqual(declared["max_writes_per_session"], envelope.MAX_WRITES_PER_SESSION)
        self.assertEqual(
            declared["brightness_floor_pct"], int(envelope.RANGES["brightness_pct"][0])
        )


if __name__ == "__main__":
    unittest.main()
