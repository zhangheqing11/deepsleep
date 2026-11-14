# 智能家居场景控制：合并交接单

> 交给主 agent 的合并说明。本文件是**唯一权威**的功能现状描述。
> 版本：2026-11-14 15:20 · 作者：本轮实现者 · 配套：[demo-home.md](demo-home.md)（演示脚本）、[RESOURCES.md](RESOURCES.md)（选型）

---

## 0. 给主 agent 的三句话

1. **这是演示层功能，不进 `run_report`、不进计分、不进 4 周状态模型。** 合并时不要把它接进评分链路。
2. **入口只有一个**：`engine/home.py::make_port()` → `port.apply(session.plan.environment)`。
3. **你只需要做三件事**：搬文件、加一个契约字段、在 `api/` 调一次。

---

## 1. 完成度（如实，分四层）

| 能力 | 状态 | 证据 |
|---|---|---|
| 环境计划（干预路径 → 设备动作） | ✅ **完成** | 五条路径动作数 6/1/3/4/2，各不相同 |
| 安全包络（范围 / 写入预算 / 能力白名单） | ✅ **完成** | `TestEnvelope` 16 个测试 + 越界探测 |
| 模拟设备总线（状态 / 历史 / 重置） | ✅ **完成** | `TestBus` 5 个测试 |
| MCP server（4 个工具，1 读 3 写） | ✅ **完成并验证** | `python -m mocks.home_mcp.probe` → `exit=0`，4 个工具列表 |
| MCP 接入运行时 | ❌ **主动弃用** | per-call 子进程不保状态，见 §6.1 |
| 接真实设备（Home Assistant / Hue） | ⬜ 路线图 | 需换 HTTP adapter，接口已留好 |
| 前端卧室视图 + 工具面板 | ⬜ 未做 | 归崔秀净，吃 `ApplyResult.as_dict()` |
| 参数文献出处 | ⚠️ **全部 `verified: false`** | 归数据科学同学，见 §6.3 |

**一句话**：**功能本体完成并通过 37 个测试；协议可自证；运行时走模拟总线；真设备和前端未做。**

---

## 2. 文件清单（本功能 13 个 + 工作区其他功能 4 个）

### A. 功能本体（必须搬）

| 文件 | 新增/改 | 行数 | 职责 |
|---|---|---|---|
| `mocks/home_mcp/envelope.py` | 新增 | 225 | L1 安全包络：白名单、参数范围、clamp、写入预算 |
| `mocks/home_mcp/bus.py` | 新增 | 152 | 模拟设备总线：内存状态 + 事件历史 + `reset()` |
| `mocks/home_mcp/server.py` | 新增 | 172 | MCP server，4 个工具，server 侧再校验一遍包络 |
| `mocks/home_mcp/probe.py` | 新增 | 50 | 协议探针：真实握手 + 4 工具调用，现场自证用 |
| `mocks/home_mcp/demo.py` | 新增 | 180 | 按 P1–P5 生成环境计划并打印 trace |
| `engine/home.py` | 新增 | 257 | `HomePort`：执行环境计划，重试、clamp 上浮、绝不抛穿 |
| `domain/home_params.yaml` | 新增 | 104 | L3 参数：场景数值 + 路径→设备组合 + 出处状态 |
| `tests/test_home_mcp.py` | 新增 | 386 | 37 个测试（包络/总线/执行器/架构红线/参数表） |

### B. 需要主 agent 判断的（可能和仓库冲突）

| 文件 | 行数 | 说明 |
|---|---|---|
| `mocks/__init__.py` | 4 | 只为本地 `python -m` 可用；**若仓库已有，删我的** |
| `mocks/home_mcp/__init__.py` | 7 | 同上 |
| `engine/__init__.py` | 4 | 同上，`engine/` 归王译旋 |
| `tests/__init__.py` | 1 | 同上；若仓库用别的测试布局，按仓库来 |

### C. 文档

| 文件 | 行数 | 说明 |
|---|---|---|
| `docs/demo-home.md` | 204 | 90 秒演示脚本 + 接线 + 冷启动检查 |
| 本文件 | — | 合并交接单 |

### D. 工作区里的**其他**功能（不属于本交接单，但会一起合入）

同一工作区里还有一份「日程个性化」的产出（15:09–15:10 生成，非本功能）：

| 文件 | 说明 |
|---|---|
| `domain/schedule.py` | 日程领域模型（周重复时段、跨午夜、冲突检测） |
| `engine/schedule_skill.py` | 本机 JSON 存储 + 上下文适配器 |
| `tests/test_schedule_skill.py` | 对应测试（用的是 pytest） |
| `docs/schedule-skill.md` | 那份功能的说明 |

**合并注意**：
- `engine/__init__.py` 和 `tests/__init__.py` 是**两边共用**的，合并时只保留一个。
- 那个功能没有 `mocks/` 依赖，与本功能互不干扰。
- 它的测试**在本机跑不全**：`python -m unittest tests.test_schedule_skill.TestScheduleDomain` 的 5 个测试瞬间通过，但整个模块会挂起（疑似文件存储相关用例）；`pytest` 同样挂（§6.5）。**这部分我没有验证，交给它的负责人**，别把它的通过当成合并门槛。

**不要提交**：`__pycache__/`、`.pytest_cache/`、根目录下的 `pytest-cache-files-*/`。
建议 `.gitignore` 补三行：

```
__pycache__/
.pytest_cache/
pytest-cache-files-*/
```

---

## 3. 合并步骤（按顺序，5 步）

**第 1 步 · 搬功能本体**
把 §2-A 的 8 个文件按原路径放进仓库。`engine/home.py` 依赖 `mocks.home_mcp.envelope`，两者要同时到位。

**第 2 步 · 处理 `__init__.py`**
若仓库对应目录已有 `__init__.py`，**保留仓库的**，不要用我的覆盖（我的只有一行 docstring）。

**第 3 步 · 依赖（关键）**
`mcp[cli]` 必须标为**可选依赖**，写在 `requirements-dev.txt` 或注释里：

```
# 可选：只有跑 MCP server / probe 时才需要
# mcp[cli]
```

理由：**不装 `mcp` 时，`import mocks.home_mcp.envelope` / `engine/home.py` / demo / 测试全部正常工作**。这是刻意设计，不要让主链路的 `pip install` 因为 MCP 而失败。

**第 4 步 · 契约 PR（`[contract]`）**
只加一个可选字段 `plan.environment`，片段见 [demo-home.md](demo-home.md) §4。按 [AGENTS.md](../AGENTS.md) §7.3 请 `engine/`（生产方）+ `web/` `scoring/`（消费方）approve。

**第 5 步 · api 接线**

```python
from engine.home import make_port

port = await make_port()
try:
    result = await port.apply(session.plan.get("environment"))
finally:
    await port.close()

await ws.broadcast({"type": "device", **result.as_dict()})   # 只推演示层
```

---

## 4. 验收（复制粘贴即可）

```bash
# 1) 测试（用 unittest，别用 pytest —— 原因见 §6.5）
python -m unittest tests.test_home_mcp
# 期望：Ran 37 tests ... OK

# 2) 主演示路径
python -m mocks.home_mcp.demo P3
# 期望：后端 direct；3 条动作；前 80%/5000K/26C → 后 1%/2200K/19C

# 3) 路径差异化
python -m mocks.home_mcp.demo
# 期望：P1=6 条、P2=1 条、P3=3 条、P4=4 条、P5=2 条

# 4) 安全包络
python -m mocks.home_mcp.demo P3 --bad
# 期望：亮度 0→1、色温 9000→6500、温度 30→26，power_off 被拒

# 5) 协议自证（可选，需要 mcp 包）
python -m mocks.home_mcp.probe
# 期望：tools/list -> 4 个；probe: OK；exit=0
```

五条全过，才算合并成功。

---

## 5. 接口契约（主 agent 必须遵守）

### 输入：`plan.environment`

```json
{
  "room": "bedroom",
  "actions": [
    {"tool": "set_light",
     "args": {"brightness_pct": 10, "kelvin": 2700, "transition_s": 900},
     "rationale": "P5：睡前 90 分钟逐步降亮"}
  ]
}
```

- `tool` 只能是 `get_home_state` / `set_light` / `set_climate` / `set_curtain`
- 每条动作最多 8 条；超出的进 `rejected`，不会静默丢弃
- `rationale` 建议必填（看板文案 + 审计依据）

### 输出：`ApplyResult.as_dict()`

```json
{
  "applied":  [{"tool": "...", "args": {...}, "clamped": false, "rationale": "..."}],
  "clamped":  [{"tool": "...", "args": {...}, "notes": ["brightness_pct:0->1"], "rationale": "..."}],
  "rejected": [{"tool": "power_off", "ok": false, "reason": "tool_not_allowed"}],
  "degraded": false,
  "error": null,
  "state": {"room": "bedroom", "light": {...}, "climate": {...}, "curtain": {...}, "rev": 3}
}
```

### 三条红线

| 红线 | 为什么 |
|---|---|
| `engine/home.py` **不许** `import scoring` | 保证主指标逐位可复现；有测试守着 |
| `ApplyResult` **不许**写进 `run_report` | 设备效果不进评测 |
| 安全边界**不许**被配置抬高 | 权威是 `envelope.py` 的常量，不是 yaml |

---

## 6. 已知问题（合并前必读）

### 6.1 MCP 为什么不接运行时

试过并跑通了，但两个硬问题：

1. **状态不跨调用保持**：stdio client 每次调用新建 server 进程，三条 `set_*` 落在三个独立内存总线上，面板显示"什么都没变"。
2. **并发开销**：40–50 来访并发时，每次调用拉一个子进程不可接受。

正确做法是把 server 起成长驻进程 + `streamable-http`，属于路线图。当前：**协议由 `server.py` + `probe.py` 证明，运行时由 `DirectBackend` 承载**，两者同接口。

**如果主 agent 想"顺手接上 MCP"：不要。** 会导致设备面板不更新，且现场并发下超时。

### 6.2 `mcp` 依赖是手工补的

本机 `mcp 1.27.0` 原本导入失败（`jsonschema` → `referencing` 缺失），已从本机 anaconda 离线拷贝 `referencing 0.30.2` + `jsonschema-specifications 2023.7.1` 到 user site-packages。

**换机器 / 建 venv 必须重装**：

```bash
pip install "mcp[cli]"
python -c "import mcp" && echo MCP_OK
```

不装也不影响演示（只影响 `probe.py` 那一镜）。

### 6.3 参数表全部 `verified: false`

`domain/home_params.yaml` 里 7 处场景参数都标了未核实。**在 11/15 08:00 前必须二选一**：

- 补齐正式文献引用（数据科学同学）
- 在对外材料里删掉"有研究支持"的表述

不允许含糊，这是 [AGENTS.md](../AGENTS.md) §9「参数注明出处」的底线。

### 6.4 测试布局可能冲突

`tests/` 目前是扁平布局 + `tests/__init__.py`（为了 `python -m unittest tests.xxx` 可用）。若仓库用 `pytest` 的 rootdir 自动发现，我的 `__init__.py` 可以删。

### 6.5 本机 pytest 会挂起（环境问题，不是代码问题）

这台机器上 `python -m pytest` 会在 rootdir 扫描阶段无限阻塞。根因不在测试代码，而是工作区根目录的 `var/`：它的 ACL 带 `Everyone:(DENY)(DC)` + Low Mandatory Level（沙箱加固留下的），任何递归目录枚举都会卡在那里。

已验证的规避方式：

| 命令 | 结果 |
|---|---|
| `python -m unittest tests.test_home_mcp` | ✅ 37 tests, 2s |
| `python -m pytest tests -q` | ❌ 挂起 |
| `python -m pytest tests -q --ignore=var` | ❌ 仍挂起（rootdir 扫描在 --ignore 之前） |

**合并到正常机器后 pytest 应该正常**（没有那个 DENY ACL）。如果仓库 CI 用 pytest，先在本机确认一遍再推。

另外：工作区根目录曾被 pytest 留下 `pytest-cache-files-*/` 与 `.pytest_cache/`（带拒绝 ACL），已删除；建议 `.gitignore` 防住（见 §2）。

---

## 7. 主 agent 可能会问的三个问题

**Q：这功能会不会影响主指标？**
> 不会。设备层不 import scoring（有测试守着），执行结果也不写进 `run_report`。

**Q：为什么要建 MCP server 却不接？**
> 因为它能证明"工具层是可插拔的标准协议"，成本约 4 小时；而接进运行时反而会让设备面板失灵。这是主动的取舍，不是没做完。

**Q：合并后我要不要动 `envelope.py`？**
> 不要。它是安全边界，改了就要重新跑 `TestEnvelope`。要加设备能力（比如 `set_fan`）必须同时改 `envelope.py` 的白名单 + `server.py` 的工具 + 参数表，并且新能力要在包络里有明确范围。

---

## 8. 还需要谁做什么

| 谁 | 做什么 | 截止 |
|---|---|---|
| **主 agent** | 按 §3 合并 + 契约 PR | 今天 |
| 崔秀净 | 卧室视图 + 工具面板（吃 `ApplyResult.as_dict()`） | 今天 21:00 |
| 王译旋 | `api/` 接线 + WebSocket 推设备事件 | 今天 18:00 |
| 数据科学 | `home_params.yaml` 出处核实或删表述 | 11/15 08:00 前 |
| 朱贺恺 | 按 [demo-home.md](demo-home.md) §2 排练；口径改成"运行时直连" | 今天 21:00 |
