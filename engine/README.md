# engine/ — 会谈循环（S3）

产出符合 `contracts/session.schema.json` 的会谈记录。反思、门禁、版本库在 S4（`zhq/engine-evolve`）。

```bash
.venv/bin/python -m engine.run --mock                       # 契约示例 3 个来访 + mock agent + mock 来访
.venv/bin/python -m engine.run --visitors data/visitors/A --sim sim.xxx:make_sim --screening sim.xxx:make_screening
```

输出 `var/runs/<run_id>/sessions/<visitor_id>.json`（契约）和 `trace/<visitor_id>.json`（调试用，不是契约：
LLM 原始输出、重试、否决记录、history 核验结果、被丢弃的 action=none 安全事件、推测调用命中数）。

## 文件

| 文件 | 内容 |
|---|---|
| `config.yaml` | **冻结配置**：agent 模型参数（temperature 0、top_p、max_tokens、超时、重试）、每轮回合上限 `round_turn_cap`（C4）、并发上限、否决重写次数 |
| `playbook_v0.md` | 五个章节严格对应 `playbook_section`；只写"有筛查工具可用"，不写何时用（C3） |
| `prompts/agent_system.md` | 冻结的 agent 系统提示：边界措辞、输出 JSON 格式（turn / assess / plan） |
| `session.py` | 两轮会谈循环 + 安全层集成 + 处方否决 |
| `run.py` | 批量并发（`asyncio.Semaphore`，默认 50）与 CLI |
| `llm.py` | ds flash 客户端（OpenAI 兼容，读 `DS_*`；缺 key 自动回退 mock，`models.agent` 标 `mock(fallback)`）与 mock agent |
| `interfaces.py` | **与 sim/（S2）的接口**：`VisitorSim.reply(...)`、`ScreeningProvider.screen(...)` |
| `stubs.py` | 接口的离线占位：按隐藏指数出筛查结果；按话题揭示线索的规则来访 |
| `topics.py` | 冻结的关键词话题标注，sim 不报告话题时作为 `asked_topics` 的兜底 |

## 会谈流程

- 第 1 轮来访先开口；第 2 轮 agent 先开口。每轮 agent 最多 `round_turn_cap[round]` 个动作（发言、调筛查工具各占一个；`end_round` 可提前结束）。第 2 轮后出处方，收尾消息讲给来访，**收尾消息不计入回合上限**。
- 每轮结束调一次 `assess`（来访看不到）得到 `path_pred / path_confidence / referral_pred`；危机退出的那一轮也会补调一次。
- **每条来访发言**（含开场、对安全确认的回答、对收尾消息的回答）都过 `SafetyLayer.assess_text`。
  - passive → 插入 `safety_check` 话术（speaker `safety`），来访回答也过安全层。
  - active → 插入 `crisis_protocol` 话术，`status = crisis_exit`，结束会谈，`plan = null`。
  - history → agent 下一条**发言**的 prompt 带【安全层指令】；用 `check_verification` 检查；没核验就紧接着插 `history_check` 兜底话术；然后清 `pending_history_check`。下一动作是工具调用时保持 pending。本轮结束仍 pending（agent 用完回合或 `end_round`）→ 插兜底话术并让来访回答，保证同一轮内有跟进。
  - 自评 PHQ-9 第 9 题 > 0 → `assess_phq9_item9(round 1, turn 0)`，话术插在开场之后；`screen_mood` 返回第 9 题 > 0 → 在该工具回合判定。
- 推测执行：来访发言过安全层的同时，先发 agent 下一回合请求（prompt 在安全判定前固定）；只要安全层返回任何事件就丢弃重算。省掉约 1/3 的串行等待。
- 处方：`domain.vetoes.check_plan` + 对收尾消息、就医建议、卡片做 `check_text`。硬否决 → 带反馈让 agent 重写 1 次 → 仍不过则**冻结兜底**：去掉 sleep_restriction（组件为空时补 sleep_hygiene）、卧床抬到下限并按起床时间倒推就寝。agent 每条发言也过 `check_text`，硬否决重写 1 次，仍不过保留原文并记 trace。
- `contraindications_checked` 不信 agent 自报：只有 agent 问到过 `health_conditions` 话题才为 true。
- LLM 输出非法（非 JSON、枚举外取值）按 `max_retries` 重试；仍失败 → `status = error`，未完成那轮用占位 `P1 / null / R0` 保持契约合法（计分应把 error 会谈当失败）。

## 与 S2 对接

`engine/interfaces.py` 的 docstring 是接口说明。S2 提供 `module:factory` 两个工厂即可通过 `--sim` / `--screening` 接入；
筛查结果必须等于 `visitor.indices`，`phq9_items[8] == visitor.crisis.phq9_item9`（`contracts/validate.py` 会检查）。
