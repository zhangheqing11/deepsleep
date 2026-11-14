# 验收工程修复总结

日期：2026-11-14  
工作目录：`/Users/zhangheqing/bohack/ds-fix`  
分支：`zhq/engine-accept-fixes`  
状态：修改留在工作区，未 commit；未执行 add、fetch、rebase、push 等仓库写操作，未调用真实 API。

## 结果

完成两项工程修复及 summary 服务商切换统计。全量离线验收 **787 passed**，契约校验 **10 个示例全部通过**，`git diff --check` 通过。

修改范围：

- `engine/plan_postprocess.py`（新增）：处方组件补标与证据提取。
- `engine/session.py`：接入处方后处理、完善否决兜底、收尾回复后刷新最终分类。
- `engine/reporting.py`：新增 `provider_switches`（服务商切换次数）。
- `engine/classifier.py`：切换发生时记录次数，即使备用调用随后取消也保留记录。
- `tests/test_engine_accept_fixes.py`（新增）：32 项回归与边界测试。
- `tests/fixtures/accept/regressions.json`（新增）：从原始模拟验收产物提取的必要处方、对话、记忆和调用元数据，测试不依赖原 `var/` 路径。

未修改 `contracts/`、`safety/`、`sim/`、`engine/evolve/` 或 `domain/`；未新增依赖。

## 1. PV-2：处方后处理及禁忌否决

以结构化 `bedtime` / `risetime` 计算跨午夜卧床分钟数，不信任模型自行填写的 `tib_minutes` 来判断是否缩短。与来访已披露的作息或会谈事实记忆比较，缩短 **≥ 30 分钟**时补入 `sleep_restriction`，再调用原有 `domain.vetoes.check_plan`。

基线仅来自已收到的 visitor 发言、memory.facts / summary，不读取 visitor 隐藏属性、未来回复、agent 的建议或 memory.open_questions。支持钟点、中文钟点、明确卧床小时数和分条披露；无法确定时不推断，记录 `trace.plan_postprocessing[].warnings = ["tib_baseline_unknown", ...]`。

检查 closing_message、referral_advice 和卡片中的明确限制表述；与组件或结构化时长不一致时记录 `sleep_restriction_inconsistent`，并同样补标后走现有否决。对“先不缩短”“暂不压缩”“再决定要不要压缩”等否定或待定表述不补标。

每个候选均重新后处理；硬否决仍按既有次数要求改写。改写耗尽时，除了删除限制组件，还恢复不短于已知基线的卧床时长、重算上床时间，并清空被拒方案的收尾与卡片，防止只删组件却保留限制建议。独立的转介建议保留；含明确限制表述的转介文本一并移除。没有基线时不能恢复未知作息，但会移除明确限制文案。

原始回归证据：

| 案例 | 修复前 | 修复后离线回放 |
|---|---|---|
| sample-007 r1 | 已披露卧床近 10 小时；计划 23:00–06:00（420 分钟）；未核对禁忌、组件无 sleep_restriction；旧 check_plan 返回空 | 补标后触发 contraindications_checked 硬否决；要求改写一次；重复原处方后进入兜底，卧床恢复 600 分钟，旧收尾及卡片不再输出 |
| sample-002 r2 | 已披露 22:40–06:30（470 分钟）；计划 23:20–06:30（430 分钟）；旧 check_plan 返回空 | 40 分钟缩短触发补标及硬否决；改写耗尽后恢复 470 分钟，即 22:40–06:30 |

另覆盖恰好 30 分钟、29 分钟、跨午夜、结构化 tib_minutes 与钟点不符、未知基线、文本独立触发、已询问且存在禁忌、已询问且无禁忌、成功改写等分支。领域否决规则口径未变化。

## 2. 收尾回复进入最终路径分类

保留处方生成前的分类供原有记忆/计划使用。在收尾和既有安全追问处理完毕后，如果新增来访回复，再运行路径分类器，并更新 `path_pred` / `path_confidence`。每轮 `trace.path_probs` 仍仅有一条 `final=true` 记录。没有新来访回复时不增加分类调用。

sample-005 r2 回归使用原始 t7 收尾、t8“上床以后就爱刷短视频，一刷就是一两个小时”的回复，以及此前真实对话。确定性分类器在接到 t8 后从 P2 返回 P5，测试确认最后分类输入包含 t8，最终预测采用该返回值；agent 调用仍为 memory、plan 两次，最后 turn 仍为 8。

该测试证明时序和数据流修复，**不宣称真实服务在这段完整上下文上必然返回 P5**；本任务没有运行真实 API。每轮有收尾回复时会多一次分类器调用，但不增加会谈动作、对话回合或 agent 调用；真实延迟未复测。

## 3. 服务商切换统计

`summary.provider_switches` 与既有 `degraded_sessions` 分别统计：

- 分类器优先读取调用记录中的明确切换次数；兼容旧 trace 中 `ds_flash(fallback:jev_error/timeout/cancelled)` 的返回标记。
- 安全判断器从 `all_judge_results` 还原当前冻结的 ds_flash → Jev 链切换；备用失败后下一条发言重新请求主服务不算额外切换。
- 不从重复的 path_probs 或缓存复用记录计数；mock / 配置不可用等确定性回退不当作实际服务切换。
- 已实际切换的调用即使随后被丢弃或取消，仍计入服务切换。

使用原始 10 场 trace 重新统计，得到 **8 次服务商切换（分类器 1 次，安全判断器 7 次）**，`degraded_sessions` 仍为 **0**。

## 验证命令与环境

```sh
PYTHONPATH=tests /Users/zhangheqing/bohack/ds-safety/.venv/bin/python -m pytest -q --ignore=api
# 787 passed in 10.23s

make -o .venv/.requirements-installed contracts
# 10 个契约示例全部 OK

GIT_OPTIONAL_LOCKS=0 git diff --check
# 通过
```

仓库现有测试使用 `from test_engine_session import ...`，因此设置 `PYTHONPATH=tests`。离线测试 fixture 禁止 socket.connect，并禁止加载真实环境配置。

Makefile 固定使用 `.venv/bin/python`。校验时临时将 `.venv` 链接到用户指定的 ds-safety 虚拟环境，用 `-o .venv/.requirements-installed` 复用已安装依赖，跳过重建环境和 pip 安装；校验后已删除该临时链接，未修改 Makefile 或依赖文件。

开发过程先运行原始证据回归：两个处方断言、最终分类断言、summary 字段断言均在旧实现上失败（4 failed），修复后通过；其后扩展边界测试并通过全量验收。

## 证据来源与边界

依据：`/Users/zhangheqing/bohack/research/codex-tasks/accept-report.md` 问题 1、5，及用户要求补充的问题 6 统计。

原始产物：`/Users/zhangheqing/bohack/ds-accept/var/integ/accept-ten-20261114-165333/` 中 sessions、trace；均只读。

基线和明确限制表述使用确定性文本解析，未引入新的 LLM 抽取或临床判据。无法识别、时间含糊的表达保留 unknown；未声称覆盖所有自然语言改写。服务商旧 trace 的安全链还原按当前冻结的 ds_flash → Jev 口径实现。
