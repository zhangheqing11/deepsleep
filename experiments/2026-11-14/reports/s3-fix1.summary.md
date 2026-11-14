# S3 fix1 总结（2026-11-14）

**代码修复和受限真实验收已完成；Git rebase 与提交被沙箱权限阻塞，尚未完成全部交付要求。没有 push、没有开 PR。**

工作目录：`/Users/zhangheqing/bohack/deepsleep/.claude/worktrees/engine-session-b8fd78`。分支仍为 `zhq/engine-session`，HEAD 仍为 `9f84342`；改动保留在工作区。未修改 `contracts/`、`safety/`、危机判据或强制筛查流程，无新增依赖。

## 1. 根因验证与真实调用预算

凭据仅由进程从 `/Users/zhangheqing/bohack/ds-safety/.env` 加载；未打印、复制或提交。原配置其实已经启用 `response_format={"type":"json_object"}`，因此问题不是简单漏开 JSON 模式。

使用原 plan prompt、S2 sample-001 开场内容、原 800 token 上限进行直接真实探针：

| 探针 | 耗时 | finish_reason | completion tokens | reasoning tokens | JSON 解析 |
|---|---:|---|---:|---:|---|
| 1 | 6.000 s | length | 800 | 442 | 失败，字符串未闭合 |
| 2 | 6.323 s | length | 800 | 376 | 失败，字符串未闭合 |

第一次调用返回终端的会话句柄未被保留，最初检查时文件尚未落盘，误发了一次重复探针；两次都计入预算。第二次覆盖了 probe.json，第一条数值保留在工具输出和本总结中。未再重跑。

证据说明：推理部分与正文共享输出上限；JSON 模式不能保证在 800 token 内生成完整对象。这确认了原报告所怀疑的截断机制，但不将它声称为原 20 个 error 的唯一原因。

**实际总调用 26 次：2 次探针 + 24 次短会谈请求；小于 30 次上限。** 会谈 SDK 自动重试为 0；脚本在 create 入口有全局请求预算保护。测试和后续联调全部离线。

## 2. 代码改动

- `engine/llm.py`、`engine/config.yaml`、`engine/prompts/*`：保留 JSON 模式，支持完整 json/JSON 围栏；上限按任务设置（plan 3200、strategy 1600、turn 2200、response/select 1200、memory 1800），明确 JSON 类型、闭合要求与文本长度。`finish_reason=length` 立即认定截断，即使正文恰好可解析也不采纳。
- `engine/session.py`：截断仅用两倍上限重试一次；该次仍失败立即固定降级，不再启动另一串普通重试。普通请求/结构失败沿用冻结 max_retries。plan、strategy、response、turn、memory、select 都有确定性回退；复用已有 mock policy，只读取对 agent 公开的状态，不读取隐藏标签。plan 回退仍经过原处方否决；memory 回退不伪造摘要，保留既有转介。
- 降级标记：trace.fallbacks 记录任务、轮次、尝试数和是否丢弃；session.models.agent 的 `(fallback:...)` 标记实际采用的降级任务。未向契约添加字段。
- `engine/telemetry.py`：在尝试开始时直接记录到本会谈 trace；失败、取消、已完成但被丢弃的推测调用均保留，按 scope 标记 discarded。取消任务后 await 清理，再返回 trace。agent/classifier 记录 finish_reason、truncated、usage、上限；无响应/mock 时为 null，不臆造 stop。最终代码增加 request_started 和 phase，区分等待额度取消、实际请求、解析/结构验证阶段。
- `engine/classifier.py`、session：超时/错误仍保留均匀权重供诊断；失败状态的 top 为 None，最终 path_pred 沿用本会谈上一次成功结果，没有成功结果则 trace 标 unknown、summary 单列。契约不能表达 unknown，因此 session 使用兼容占位 P1 + path_confidence=null，绝不能直接当有效预测计分。分类缓存不再重复计调用数或延迟。
- `engine/reporting.py`、`engine/run.py`：S3 提供 build_report 适配入口，先排除 error/unknown 会谈再交给 S2 scorer。report.n_visitors 是可评分人数；全 attempted、完成率、error/crisis_exit、unknown、覆盖率、排除原因、全样本危机漏报、调用统计进入必须配套读取的 summary。存在排除时 report.veto.passed=false；契约没有对应原因枚举，具体原因留在 summary。全排除时不生成无定义的空样本 report。已有 safety_summary 字段使用全部 judge_results，计入 none 及失败 fallback 链路，不再仅从 safety_events 反推。
- `engine/adapters_sim.py`：薄适配 S2 的来访、筛查和状态模型，按会谈隔离 simulator，跨轮保留 deny/reveal，只依据实际 agent/safety 发言标话题，环 2 去掉尚未完成的第二轮占位；依赖延迟导入，当前 S3 分支不必加入 sim/scoring 源码。
- 安全事件改为优先调用 `script_for_event(event, state)`；返回空话术时保留事件、不添加空 transcript、不额外触发来访。由于 rebase 受阻，当前旧安全层仍使用显式标记 legacy_safety_api 的兼容路径；新版去重的实际分支集成尚未完成。
- `engine/README.md` 已说明统计入口、降级语义、旧安全层兼容状态和真实验收范围。

## 3. 三个 S2 来访的真实 API 验收

为遵守总共 30 次的硬预算，采用 **真实 ds flash 会谈 agent + S2 确定性来访 renderer + mock 路径分类器/安全判断器**。两轮各 1 次动作，strategy/response 合并。生产默认 5/4 动作没有修改。已在执行前说明并给出选择，用户未回复，按此受限方案执行。

| 来访 | 状态 | 每场墙钟 | 真实请求 | finish_reason | 最终降级 |
|---|---|---:|---:|---|---|
| sample-001 | completed | 40.292 s | 8 | stop × 8 | 无 |
| sample-002 | completed | 26.235 s | 7 | stop × 7 | 无 |
| sample-007 | completed | 55.806 s | 9 | stop × 9 | 无 |

三场均完成两轮并产出最终处方；24 次真实响应全部 stop，无 length。sample-001 和 sample-007 各有一次 plan 的 LLMError，经普通重试恢复，已计入 trace 与总数。该次验收时失败输出尚未按阶段保留，不能区分这两次是 JSON 解析还是字段验证失败；最终代码补充 phase 和可解析输出记录，未因此再付费重跑。

3 份 session 和 1 份 run_report 均通过契约校验；完成率 100%、error=0、unknown=0、最终降级=0。另有 12 次 mock 分类器逻辑调用，不能与真实请求混为一谈。

产物（均在忽略目录，不提交）：

- `var/s3-fix1/probe.py`、`probe.json`：原上限探针与最后一次结果。
- `var/s3-fix1/live.py`：可复现脚本，输出目录已存在时拒绝再次计费执行。
- `var/s3-fix1/live/manifest.json`：真实验收的配置和当时 engine 源文件 SHA-256。
- `var/s3-fix1/live/requests.json`：24 次真实请求清单。
- `var/s3-fix1/live/{sessions,trace}/`、`run_report.json`、`summary.json`：逐场记录和统计。

**这不是默认回合数的完整实时性能验收，也不是所有组件真实调用的全链路验收，不证明 40–50 人能在一分钟内完成。** 真实运行后的小改动（记录阶段、request_started、截断重试失败立即降级、unknown 的额外防守检查）由离线测试验证，原始真实证据未被改写。

## 4. 离线验证

指定解释器：`/Users/zhangheqing/bohack/ds-safety/.venv/bin/python`。

- `python -m pytest -q --ignore=api`：**324 passed, 1 xfailed**。xfail 为原有“重复 passive 后 screen_mood 第 9 题契约冲突”，未隐藏或改为 skip；新版 safety rebase 后应重新验证并更新对应旧断言。
- `make contracts`：10 个原有示例全部通过（执行现有 Makefile 的本地 .venv）。
- `git diff --check`：通过。
- 新增测试覆盖大小写围栏、length 即便可解析也重试、加倍上限、只重试一次、plan 固定回退、六类子智能体降级、分类器沿用和 unknown、缓存不重复计数、推测成功/失败/取消记录不丢失、error/unknown 不进入计分、完整 judge 计数、新版话术接口的空返回、S2 会谈状态隔离与第一轮模型上下文。
- 额外只读借用 ds-integ 的 S2 模块，以默认 5/4 动作完整离线运行当前样例目录 **18 人**：18 completed，session/report 无契约错误，真实请求 0。复制结果并注入 1 error + 1 unknown 后，报表正确只评分 16 人、veto=false；完整 611 次 agent/classifier 逻辑调用与 215 次 mock judge 结果仍保留，报表仍通过契约校验。结果见 `var/s3-fix1/offline_s2.json`，脚本 `offline_s2.py`。
- 此离线运行仍报告全样本危机漏报 2 例；未通过新增强制筛查改变这个待心理学同学决定的问题。

## 5. Git 阻塞与后续提交

下列命令实际尝试，均被系统拒绝写 Git 元数据：

- `git fetch origin`：无法写 `.git/worktrees/engine-session-b8fd78/FETCH_HEAD`。
- `git rebase origin/zhq/domain-safety`：无法创建同目录下 `rebase-merge`。
- `git add ...`：无法创建同目录下 `index.lock`。

均为 `Operation not permitted`。没有使用临时 Git 库/替代索引绕过限制，没有伪称提交成功。

只读 `git ls-remote origin refs/heads/zhq/domain-safety` 已核验远端为 **86b1257fd14ef1f3a6ea6d8fe5a8578cb8e324d0**，与本地 origin/zhq/domain-safety 相同。失败的 rebase 未留下进行中状态。

完整改动补丁（含新增 engine/tests 文件，不含 var/、凭据）：`/Users/zhangheqing/bohack/research/codex-tasks/s3-fix1.patch`。补丁基于当前 HEAD，不应在当前已有改动的工作区重复 apply。

权限恢复后需先保存当前改动，再 rebase 到 origin/zhq/domain-safety，解决冲突、移除旧安全层兼容分支（若无需支持旧版）、更新旧 xfail 并重跑测试。建议按两组提交：

1. `fix(engine): recover structured outputs and preserve evaluation accounting` — 客户端、prompt/配置、session/classifier/telemetry、reporting/run 以及相应回归测试。
2. `test(engine): bridge S2 sessions and document bounded live validation` — adapters_sim、S2 适配测试与 engine/README.md。

每笔英文 commit message 最后一行均为：`Co-Authored-By: Codex <noreply@openai.com>`。**当前未产生这两笔 commit。** 不 push、不开 PR。

## 6. 尚待完成或不应误读之处

1. rebase、冲突处理和分主题 commit 尚未完成，需恢复 Git 元数据写权限。
2. 真实验收仅 3 个短会谈；完整默认流程和全真实组件尚未付费验证，剩余预算 4 次不足以重新跑 3 场完整会谈。
3. 新版安全层实际集成未完成，当前测试验证了接口调用与空返回行为，不能代替 rebase 后全链路验证。
4. S2 原始 score_run 直接接 session 的旧入口未被修改。下游必须调用 engine.reporting.build_report 并同时读取 summary，才能获得本次 error/unknown 排除和完整计数语义。
5. 安全层 API 不暴露 finish_reason；全部 judge 尝试状态有记录，但该字段仍无法从 S3 获得。agent/classifier 的实际 OpenAI 返回已记录。其余外部模拟 renderer 的物理 SDK 重试需由其提供方或独立 HTTP 计时器观测。
6. 既有危机漏报、S2 占位状态模型和演示规模耗时仍按原边界保留，没有用完成率替代临床/安全效果证明。
