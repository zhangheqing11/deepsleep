# 智能家居联动：演示脚本与接线说明

> 配套代码：`mocks/home_mcp/`（协议 + 模拟总线 + 安全包络）、`engine/home.py`（执行器）
> 参数表：`domain/home_params.yaml`
> 测试：`python -m unittest tests.test_home_mcp`（37 passed；本机 pytest 会挂起，见 [handoff-home.md](handoff-home.md) §6.5）

## 0. 一句话

**协议是真的，设备是模拟的。** MCP server 完整实现且用 `probe.py` 验证过；运行时为了并发稳定走直连模拟总线。替换一个 adapter 就能接 Home Assistant，agent 与工具定义都不用改。

---

## 1. 当前状态（2026-11-14 实测）

| 文件 | 作用 | 依赖 `mcp` 包 |
|---|---|---|
| `mocks/home_mcp/envelope.py` | L1 安全包络：范围、写入预算、能力白名单 | 否 |
| `mocks/home_mcp/bus.py` | 模拟设备总线：状态、历史、可重置 | 否 |
| `mocks/home_mcp/server.py` | **MCP server**，4 个工具（1 读 3 写） | 是 |
| `mocks/home_mcp/probe.py` | **协议探针**：真实握手 + 4 工具调用，一条命令自证 | 是 |
| `engine/home.py` | `HomePort`：执行 `plan.environment`，带重试 | 否 |
| `mocks/home_mcp/demo.py` | 按路径生成环境计划并打印 trace | 否 |
| `domain/home_params.yaml` | L3 参数表（场景数值 + 出处状态） | 否 |

**已验证**：

```
$ python -m mocks.home_mcp.probe
tools/list -> 4 个: ['get_home_state', 'set_light', 'set_climate', 'set_curtain']
get_home_state -> {"ok": true, ...}
set_light     -> {"ok": true, "clamped": false, "state": {...}}
set_light(0)  -> {"ok": true, "clamped": true, "notes": ["brightness_pct:0->1"]}
probe: OK（协议链路完整）      exit=0
```

**环境说明**：本机 `mcp 1.27.0` 原本导入失败（`jsonschema` → `referencing` 缺失），已从本机 anaconda 环境离线补齐 `referencing 0.30.2` 与 `jsonschema-specifications 2023.7.1` 到 user site-packages。**换机器或建 venv 时仍需重新安装**：

```bash
pip install "mcp[cli]"
python -c "import mcp" && echo MCP_OK
```

---

## 2. 90 秒演示脚本

主演示用 **P3（认知过度唤醒）**：三条动作全在夜间语义内（降亮 → 入睡照度 + 偏凉），不会出现"半夜把窗帘拉开"的怪画面。

| 时间 | 屏幕 | 台词 |
|---|---|---|
| 0–15s | 会谈页，agent 说出处方 | "它判她是 P3——躺下就开始反刍。处方不只是'放松点'，而是一串具体的环境动作。" |
| 15–35s | 点"应用到卧室" → 工具面板滚出 3 条调用 | "灯从 80% 降到 10%、2700K，15 分钟渐变；入睡后再降到 1%；空调 26 度降到 19 度。" |
| 35–55s | 卧室视图：光源变暖变暗、温度数字下落 | "渐进降亮本身就是提示信号，比弹一条'该睡了'有效。" |
| 55–70s | 切到 P5 对比（`demo P5`）→ 只有 2 条调光 | "同一个人如果是数字娱乐型，我们**只动灯**，不碰空调窗帘——路径决定环境，不是一份模板套所有人。" |
| 70–85s | 跑 `probe.py`（或点"越界测试"） | "这是真实的 MCP 握手；亮度 0 会被 clamp 到 1，而且工具集里根本没有'关机'这个动作。" |
| 85–90s | 页脚 | "设备是模拟的，协议是真的。" |

**页脚常驻**：`设备为模拟总线；MCP 协议已实现并验证，替换 adapter 即可接 Home Assistant。`

> 为什么不用 P1/P4 做主线：它们含 `wake`（晨间）场景，一次性应用会让窗帘在夜里拉开，观众会觉得系统坏了。晨间场景放产品叙事，不放 90 秒演示。

---

## 3. 一键命令

```bash
# 主演示：P3 的计划与 trace（3 条动作）
python -m mocks.home_mcp.demo P3

# 对比：P5 只动灯（2 条动作）
python -m mocks.home_mcp.demo P5

# 越界探测（独立总线，不影响上面的结果）
python -m mocks.home_mcp.demo P3 --bad

# 协议自证：真实 MCP 握手 + 4 个工具 + clamp（最有力的 10 秒）
python -m mocks.home_mcp.probe

# 启动 MCP server（stdio，给外部 client 用）
python -m mocks.home_mcp.server

# 测试
python -m unittest tests.test_home_mcp
```

---

## 4. 契约补丁（`contracts/session.schema.json`）

按 [AGENTS.md](../AGENTS.md) §7.3 走 `[contract]` PR，生产方（`engine/`）+ 消费方（`web/` `scoring/`）都要 approve。

```json
"environment": {
  "type": "object",
  "description": "演示版：智能家居环境计划。不参与计分与状态模型。",
  "required": ["room", "actions"],
  "properties": {
    "room": {"type": "string", "enum": ["bedroom"]},
    "actions": {
      "type": "array",
      "maxItems": 8,
      "items": {
        "type": "object",
        "required": ["tool", "args"],
        "properties": {
          "tool": {
            "type": "string",
            "enum": ["get_home_state", "set_light", "set_climate", "set_curtain"]
          },
          "args": {"type": "object"},
          "rationale": {"type": "string", "description": "给看板的解释，也是审计依据"}
        }
      }
    }
  }
}
```

- `maxItems: 8` 与 `MAX_WRITES_PER_SESSION` 对齐，但**权威仍是 `envelope.py`**（配置不能抬高边界）。
- 旧数据缺 `environment` 时行为不变，向后兼容。

---

## 5. API 层接线（三行）

```python
from engine.home import make_port

port = await make_port()          # 运行时后端：直连模拟总线
try:
    result = await port.apply(session.plan.get("environment"))
finally:
    await port.close()

# 只推给演示层，不进 run_report / scoring
await ws.broadcast({"type": "device", **result.as_dict()})
```

**重要**：`result` 不许写进 `run_report`。设备层与计分的隔离由 `tests/test_home_mcp.py::TestArchitecture::test_home_layer_does_not_import_scoring` 守着。

---

## 6. 冷启动检查（演示前 5 分钟）

```bash
# 1) 一句判断 MCP 包能不能用。别看 pip list，要看 import。
python -c "import mcp" && echo MCP_OK || echo MCP_DOWN

# 2) 设备层能不能跑（这才是演示真正依赖的）
python -m mocks.home_mcp.demo P3
```

- 第 2 条能跑出 3 条动作 → 演示可以开始（**它不依赖 MCP**）
- 第 1 条 `MCP_OK` → 才允许跑 `probe.py` 那一镜；`MCP_DOWN` 就把 70–85s 那一镜换成"越界测试"，并改口"预留 MCP 接口"

---

## 7. 失败模式

| 现象 | 处理 |
|---|---|
| `mcp` 导入失败 | **不影响演示**：跑 demo 就行。不要在台上 debug 依赖 |
| 卧室视图不更新 | 后端 `DeviceBus` 是内存态，重启进程即复位 |
| 想回到初始状态 | `DeviceBus().reset()`；与 playbook 回滚是两件事，别混讲 |
| 评委问"能关灯/关空调吗" | **工具集里没有这个能力**，这是刻意的：产品边界写进代码 |
| 评委问"运行时真的走 MCP 吗" | 如实答：**协议已实现并验证，运行时走直连**，原因见 §9 |

---

## 8. 三个必答题

**Q：你们真的控制设备了吗？**
> 协议层是真的——`probe.py` 现场跑一次就能看到 4 个工具和真实握手；设备层是模拟总线，因为我们不想在游园会上赌网络和硬件配对。

**Q：凭什么 10% 亮度、19 度？**
> **目前不能给正式引用。** `domain/home_params.yaml` 里每条都标了 `verified: false`，赛前要么补齐文献，要么在对外材料里不提"有研究支持"。这是底线。

**Q：设备层会不会污染你们的分数？**
> 不会。设备计划只进演示与叙事，`run_report` 里不出现；有一条测试专门守着这个隔离。

---

## 9. 为什么运行时不用 MCP（如实版）

试过、也跑通了，但有两个硬问题：

1. **状态不跨调用保持。** stdio client 每次调用都要新建 server 进程，三条 `set_*` 落在三个独立的内存总线上——设备面板会显示"什么都没变"。
2. **并发开销。** 40–50 个来访并发时，每次调用拉起一个子进程不可接受。

要既走协议又保状态，正确做法是**把 server 起成长驻进程、用 streamable-http 连**（MCP 支持的另一种传输）。这属于路线图，不在 18 小时内的范围。

所以当前的分工是：**协议由 `server.py` 承载、由 `probe.py` 证明；运行时由 `DirectBackend` 承载。** 两者接口相同（`Backend` Protocol），接真设备时换成 HTTP adapter 即可。

---

## 10. 待办

| 谁 | 做什么 | 截止 |
|---|---|---|
| 崔秀净 | 卧室视图 + 工具面板组件（吃 `ApplyResult.as_dict()`） | 今天 21:00 |
| 王译旋 | `api/` 里接 `HomePort`，WebSocket 推设备事件 | 今天 18:00 |
| 你 | 契约 PR（`plan.environment`）+ `home_params.yaml` 的 `verified` 处理 | 今天 19:00 |
| 数据科学 | `home_params.yaml` 出处核实（能核就核，不能核就删表述） | 11/15 08:00 前 |
| 朱贺恺 | 按 §2 排练；确认页脚文案与"运行时直连"的口径 | 今天 21:00 |
