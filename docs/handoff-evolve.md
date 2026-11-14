# 交接：自进化学习环节（11/14 夜 – 11/15 凌晨）

> 分支 `wyx/engine-evolve-signal`。写给接手演示的同事和各目录负责人。
> 所有数字都来自真实 API 运行；ISI 是冻结规则状态模型的四周模拟值，不是临床疗效。
> 实验机：Windows，会谈 agent 与路径分类器 ds flash，反思器 gpt-6-astra（high），来访模板渲染，45 人全并发。

## 1. 一页结论

在从未用于学习和门禁的 B 组上，两条**互相独立**的进化链都把主指标提高了约 10 个百分点：

| | 运行 | ISI 有效率 | 转介正确率 | 转介召回 / 精确率 |
|---|---|---|---|---|
| v1（对照，B 组） | 3 次 | 57.0%［53.3 62.2 55.6］ | 67.4% | 0.50–0.61 / 0.45–0.63 |
| E11：v1 → v4（B 组） | 3 次 | **68.1%**［66.7 68.9 68.9］ | 94.1% | 0.83–0.89 / 0.94–1.00 |
| E12：v1 → v4（B 组） | 3 次 | **67.4%**［66.7 68.9 66.7］ | 94.8% | 0.83–0.89 / 1.00 |

- 同一批 45 人的配对差值：E11 **+11.1pp**，95% 区间［+2.2, +21.5］；E12 **+10.4pp**，［+3.0, +19.3］。转介正确率 +26.7pp 与 +27.4pp。
- v1 在 A 组（即运行 1）两次为 55.6% 和 57.8%。六次"进化后在 B 组"的结果最低 66.7%，高于全部 v1 运行的最高值 62.2%。
- B 组结构性上限是 82.2%：45 人里有 8 人因依从倾向过低或主动危机，任何 playbook 都无法使其有效。
- 学习环节 16.7 分钟（E11）与 24.3 分钟（E12）；单次运行 62–85 秒。

**三行进化说明（草稿，供项目说明用）**

1. **比什么**：45 个从未见过的模拟来访的四周 ISI 有效率（下降 > 7 分的占比）。运行 1（v1，A 组）约 56–58%，运行 2（学习后，B 组）约 67–69%；同组对照（v1，B 组）约 57%。副指标转介正确率 67% → 94%。
2. **学到了什么**：系统读运行 1 的全量审计表，自己写进 playbook 的规则，例如"第 1 轮用腿部不适提问替换周末补觉追问""PHQ-9 与 GAD-7 均 <10 时不凭疲乏判 R3""有呼吸线索且无筛查结果时第 2 轮首个动作调用 screen_osa"。每条都带审计数字和在验证集上的效果。
3. **怎么回退**：每代 playbook 是独立 git 库里的一次提交，`python -m engine.evolve rollback v1` 当场退回；未通过门禁的候选不会生效。

## 2. 今晚发现的三个根因

| 根因 | 证据 | 处理 |
|---|---|---|
| **学到的规则没有被执行** | 旧策略提示词规定"来访抗拒时改用支持性策略"，优先级压过 playbook；模板来访的含糊回答会被判成抗拒。旧提示词下 34–41% 的 agent 回合没有实际提问；同一份已学到的 playbook，问到呼吸 13/45、调用 screen_osa 7–10/45 | `engine/prompts/strategy.md` 改两句：playbook 写明的提问、顺序、工具调用优先；抗拒时一句话回应后继续提问，不连续两步只安抚。改后空回合降到 10%，呼吸 23/45、screen_osa 20/45 |
| **反思器近乎盲猜** | 只看 8 个失败案例，看不到全量统计、门禁规则和往代尝试 | 新增运行审计表（全部来访的经验统计），反思器同时读门禁规则、动作预算、往代记录 |
| **门禁由噪声决定** | v1 在 C 组（30 人）单次测量 36.7%–53.3%；旧门禁 9 份候选里 7 份因 1 名来访之差被否；上一代被采纳候选的测量值带选择偏差，直接当下一代基线会抬高门槛 | 候选测 2 次、基线测 3 次并合并；转介召回留 1 人容差；每代重测基线；一代未过不终止；每采纳一代用新版本重跑学习组（自我练习） |

没有改提示词之前，同样的学习流程跑了六条链，B 组 ISI 变化是 −1.1、0.0、+2.2、−1.1、+6.7、−5.6——主指标不稳定，只有转介正确率稳定提升。**提示词那两句是主指标提升的必要条件。**

## 3. 改了什么

| 文件 | 改动 |
|---|---|
| `engine/prompts/strategy.md` | playbook 优先；抗拒时不连续安抚（见上） |
| `engine/evolve/audit.py`（新） | 运行审计：损失总览、转介表（含量表分数按真标签/判断分组）、提问效率、路径、处方、先否认。只用本次运行的结果和标签，不读状态模型，不含任何阈值或关键词 |
| `engine/evolve/reflector.py`、`engine/prompts/reflector_*.md` | 反思器读审计、门禁规则、动作预算、往代记录；每条改动的理由必须引用审计数字 |
| `engine/evolve/gate.py`、`pipeline.py` | 重复测量与合并、按来访数计的容差、配对统计、基线在反思期间并行跑、候选并行评估 |
| `engine/evolve/lineage.py`（新） | 多代链：往代记录、自我练习、一代未过不终止、每代重测基线 |
| `engine/evolve/hard_rules.py` | 防刷分硬规则：禁止"一条消息问多个话题""组件全选" |
| `engine/evolve/llm.py`、`config.yaml` | 反思器输出额度 48000、档位 high、超时 600 秒；可选 ds flash 作主反思器 |
| `engine/network.py`、`classifier.py` | 服务商限流（HTTP 429）退避重试；原先直接放弃 |
| `engine/demo.py` | `--generations`、自我练习、降级超过 10% 判该批无效、每批独立的并发上限、trace 写入来访否认记录、Windows 文件锁 |
| `engine/config.yaml` | 分类器固定 ds flash；`agent_llm.max_inflight` 192；`quality.max_degraded_share` 0.10 |
| `Makefile` | 演示默认 `--generations 3 --visitor-renderer template` |
| `analysis/evo_lab.py`、`evo_compare.py`（新） | 实验驱动与留出对比脚本 |

没有改 `contracts/`、`safety/`、`sim/`、`scoring/`、`domain/`。所有 evolution.json 仍通过契约校验。

## 4. 需要负责人确认的五项

1. **会谈 agent 的策略提示词改动**（harness 负责人）。影响面最大，也是效果来源。
2. **门禁配置**（统筹 / 心理学同学）：`referral_recall_tolerance_visitors: 1`、`replicates: 2`、`baseline_replicates: 3`、`lineage.reuse_baseline: false`、`continue_after_reject: true`。危机相关检查仍是 0 容差。
3. **分类器固定为 ds flash**。Jev 与 ds flash 同组对比主指标无差别，Jev 每场快约 9 秒，但需美国出口且没有在新流程下验证。
4. **反思器是 gpt-6-astra（high）**，不是 AGENTS.md §3 第 8 条写的 Opus 5.5。当晚拿到的 Anthropic key 鉴权失败，未测。
5. **演示时来访用模板渲染**。全部验证都是这个设置；LLM 渲染没有在新流程下测过。

## 5. 在演示机上跑

**预检（缺一项都可能让整批结果无效）**

- `.env`：`REFLECTOR_REASONING_EFFORT` 设为 `high` 或删掉这一行（原来的 `xhigh` 会把输出额度耗尽）；`REFLECTOR_TIMEOUT_S` 留空或 ≥ 600。
- DeepSeek 余额充足。欠费时接口先返回 429 再返回 402，会谈大面积降级但仍会出分。一批 45 人约 1.4 元，整场演示（运行 1 + 三代学习 + 运行 2 与对照，约 1000 场会谈）DeepSeek 部分约 35 元，反思器的 OpenAI 费用另计。
- 网络：`ping -D -s 1372 api.deepseek.com`（macOS）或 `ping -f -l 1372 api.deepseek.com`（Windows）必须通。实验机的 VPN 网卡 MTU 过大，稍大的请求全部在 15 秒后被断开，表现为所有调用失败。
- `python scripts/check_keys.py`，确认 ds_flash 可用；另需能访问 api.openai.com。

**命令**

```bash
make demo-reset
```

```bash
make demo-run1
```

```bash
make demo-run2
```

- `demo-run1` = 运行 1（A 组，约 70 秒）+ 学习（三代，约 17–25 分钟）。按赛规可以在评委到之前跑完，把结果和日志留在屏幕上。
- `demo-run2` = 运行 2（学习后的版本，B 组）与对照（v1，B 组）并行，约 80 秒，当着评委跑。
- 回退：`python -m engine.evolve rollback v1`。
- 批次被判无效（降级会谈超过 10%）时命令会报错停下，查 `var/runs/<run_id>/summary.json` 的 `invalid_reason`，多半是余额或限流。

**必须在演示机上先做一遍完整彩排**。本文的耗时和结果都来自另一台机器，不能直接搬用。

## 6. 已知风险

- **运行 2 不保证每次都高于运行 1**。已有的 6 次对 5 次全部成立，但样本有限；单次运行标准差约 3–5 个百分点。同时展示对照（v1 在 B 组）更稳妥。
- **只验证了两条链**。学习过程里仍有随机性：E11 每代提升 10–15 个百分点，E12 只有 1–7 个，但两者在 B 组上的结果几乎相同。
- **主反思器失败时会降级到 ds flash**。ds flash 当反思器的实测结果是有害的（见第 7 节），门禁能挡住一部分但不保证全部。
- **安全层**（未改动，需负责人处理）：归档数据里有一例主动危机表述在两个判断器都超时后被当成 passive，会谈继续且 `crisis_missed` 仍为 0。连不上 Jev 的环境里这条降级路径更容易触发。
- **状态模型与来访分布仍是占位**（见 `docs/handoff-algo.md`）。模型不惩罚组件数量，v1 的处方平均已有 5.5 个组件。

## 7. 试过但没成的

| 尝试 | 结果 |
|---|---|
| ds flash + 方法 skill 作反思器（E8） | 四代都过了当时的门禁，B 组 ISI −5.6pp，转介召回 0.57 → 0.36。它归纳的规则有错：判 R3 只看了 PHQ-9，漏了 GAD-7。`engine/prompts/reflector_skill.md` 与 `REFLECTOR_PROVIDER=deepseek` 保留，可作消融材料 |
| 阶梯候选（E10，旧提示词） | 候选 2 = 候选 1 + 第二处修复，以此类推。两代都没过门禁；当时规则不被执行，结论不能推到新提示词下 |
| 主指标至少多 2 人才算提高 | 过于保守，E2 里把正确的腿部规则挡掉了 |
| 反思器 medium 档（E6） | 单次 66 秒，但第 2 代没过门禁。只有一条链，不能定论 |

## 8. 数据在哪

实验产物在实验机的 `var/lab/`（不入库），每个目录含 sessions、trace、run_report、summary、http 统计：

- 新提示词：`X-v1-A`、`X-v1-A2`（运行 1）；`X-v1-B`、`X-v1-Bc-r1/r2`（对照）；`E11/`、`E12/`（进化链，含每代 evolution.json、insights.json、lineage.json）；`X-E11v4-B-r1..3`、`X-E12v4-B-r1..3`（留出验证）。
- 旧提示词：`v1-A-*`、`v1-B-*`、`E2`、`E4`–`E10` 及对应的 `*-B-*`。
- 对比命令：`python analysis/evo_compare.py var/lab data/visitors <对照运行,逗号分隔> --vs <实验运行,逗号分隔>`。

## 9. 遗留

- 契约里没有"转介正确率"字段，目前只在对比脚本里算；看板要展示需走 `[contract]` 流程或由前端从 `per_visitor` 计算。
- 多代学习的看板展示（`manifest.evolution.generations`、`manifest.practice`、各代目录下的 `lineage.json`）前端尚未对接。
- `tests/` 在 Windows 上有 8 个与本次改动无关的失败（`engine/integ_trial.py` 依赖 `fcntl`；数据文件换行符；privacy 导出文件缺失）。
- AGENTS.md §3 第 8 条、§10 与 `docs/BACKLOG.md` 尚未按本次改动同步。
