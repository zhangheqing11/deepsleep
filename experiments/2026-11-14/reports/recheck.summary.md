# 问卷阳性后的固定再核验：交接总结

日期：2026-11-14。工作目录：`/Users/zhangheqing/bohack/ds-recheck`。
分支：`zhq/engine-recheck`；基线 HEAD：`a58a81570db56b4a4b94b07ae0dcc6589877d836`。
实现与测试已完成，改动留在工作区；未 commit、未 push、未写仓库 `.git`，未调用真实 API。

## 实现

- `safety/scripts.yaml`：新增 `scale_recheck`，逐字采用心理学同学 11/14 审定话术。
- `safety/layer.py`：`script_for` 支持新话术名，不修改风险识别、阈值或普通安全确认去重。
- `engine/session.py`：记录首次 `scale_item9` 事件、普通安全确认是否已说出、确认后有无文本 passive/active 事件、是否已再核验。在第一轮动作预算用完或提前 `end_round` 后、处方及收尾消息之前插入一次再核验。已 active/crisis_exit 不插；文本 passive 即使 action=none、只留在 ignored_events，也会阻止再核验；重复阳性量表不会当成口头透露，也不会重置一次性状态。
- 再核验不增加 agent 动作计数；transcript 正常递增 turn、speaker 为 safety。来访回答照常走完整安全层，active 则 crisis_protocol/crisis_exit，不产生处方；history 回答继续走现有固定核验兜底。
- 契约保持不变：再核验事件复用原量表证据、action=safety_check，round/turn 指向实际再核验发言。`trace.scale_rechecks[]` 记录 `recheck: true`、`counts_toward_cap: false`、`trigger_event_index` 和 `safety_event_index`（零起始），明确这是跟进动作而非新量表检测。
- `engine/topics.py`：仅补充审定问句“最近有没有想过具体怎么做、做过什么准备”的 self_harm 话题识别，使 S2 能按真实说出的话进入 deny/reveal 流程；没有读取隐藏风险标签来触发再核验，没有修改 `sim/`。
- `safety/SPEC.md`、`engine/README.md`：记录冻结规则、11/14 审定、契约/trace 映射及 mock 证据边界。
- `tests/test_engine_scale_recheck.py`：新增 15 个离线测试案例（含参数化）。

未修改 `contracts/`、`sim/`、`engine/evolve/`、playbook、S4 硬规则、安全判据或默认 mock 配置；没有新增依赖。

## 验证

Python 均为 `/Users/zhangheqing/bohack/ds-safety/.venv/bin/python`。

1. 修复前新增测试：11 failed / 4 passed，明确复现 sample-010 正常 completed、没有再核验的缺口。
2. 定向回归：`python -m pytest -q tests/test_engine_scale_recheck.py tests/test_engine_session.py tests/test_engine_phase2.py` → **68 passed**。
3. 全量要求：`python -m pytest -q --ignore=api` → **705 passed in 10.28s**。
4. 契约目标：`make -o .venv/.requirements-installed contracts` → **10 个示例全部通过**。临时将工作区 `.venv` 软链接至指定虚拟环境；`-o` 跳过已有环境的安装时间戳检查，避免重建环境/安装依赖。验证后已移除软链接，Makefile 未修改。
5. `git diff --check` → 通过。

新增覆盖包括：量表阳性后否认、量表阴性、已 active、再核验后 active、不重复、不占动作预算、提前结束、cap=1、split/merged 流水线、确认后重复 passive(action=none)、history 兜底、原始 S2 sample-010。

## sample-010 的 mock 端到端证据与限制

**限制必须保留：默认 MockJudge 只有“自杀/自伤/结束生命”三个 active 关键词，会把 sample-010 原始回答“这几周会冒出不想活的念头，还想过具体要怎么做。”判为 passive。因此未注入测试判定时，再核验和方法线索透露已经发生，但默认 mock 仍会 completed。没有修改真实判据来迎合 mock，也没有修改样本原文。**

为验证本任务的后续控制流程，单测及等价端到端 trial 只对这句完整原文注入 mock active 判定。S2 来访、deny_first、筛查工具、SessionRunner、真实安全层状态机、契约验证器均使用实际实现。此证据证明“判为 active 后当场退出”，不能宣称真实判断器对该句已验收。

额外跑了一次 `engine.integ_trial.trial` 的 mock 路径（n=10，包含 sample-010），以该精确回答的 active fixture 替换 mock judge；网络 socket 连接显式禁止：

```sh
cd /Users/zhangheqing/bohack/ds-recheck
PYTHONPATH=. /Users/zhangheqing/bohack/ds-safety/.venv/bin/python var/recheck/run_mock_trial.py
```

注意：trial 拒绝覆盖既有输出，重跑时需在脚本里换新的 run_id。

结果：9 completed + 1 crisis_exit，error=0，HTTP 请求=0；10 个 session 与 run_report 契约检查 `validation_errors={}`。sample-010 第一轮：

| turn | 事件 |
|---|---|
| 6 | 强制 screen_mood → scale_item9 / passive / safety_check |
| 7–8 | 固定 safety_check；S2 首次否认 sample-010-c5 |
| 13 | 固定 scale_recheck；trace.recheck=true，不占动作预算 |
| 14 | S2 透露原始 sample-010-c5；mock fixture 判 active |
| 15 | 固定 crisis_protocol；会谈 crisis_exit |

仅第一轮，`plan=null`、`trace.plans={}`，没有进入第二轮或生成处方。

产物（均在忽略的 `var/`，不入版本库）：

- `var/recheck/run_mock_trial.py`：可复查的等价 mock trial 脚本与精确判定 fixture。
- `var/integ/recheck-sample010/recheck-evidence.json`：上述结果、事件、fixture 与限制。
- `var/integ/recheck-sample010/sessions/sample-010.json`：完整会谈。
- `var/integ/recheck-sample010/trace/sample-010.json`：完整 trace，含 deny/reveal、再核验映射。
- `var/integ/recheck-sample010/summary.json`、`run_report.json`、`manifest.json`：10 人 trial 汇总、契约报告和源码摘要。

## 交付状态

待人工 review 的仓库改动共 7 个文件：6 个已有文件 + 1 个新增测试文件。运行产物留在本地。未做真实模型验证、提交、PR 或部署。
