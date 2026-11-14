# PR #6（危机安全层）验收修复清单

> **给修复会话**：在 `zhq/domain-safety` 分支（PR #6）上修。修完让验收会话复验，再合并。
> 验收日期：2026-11-14　对象：PR #6 head `c1e3753`（基于当时 main）　方式：Codex 独立审查 + 验收会话核对。
> 完整证据：[`raw/pr6-safety-review.md`](raw/pr6-safety-review.md)（发现里的 `../pr6-tmp/…` 指验收时的临时文件，不在仓库里；需要时可按文中的复现步骤重做）。

## 1. 验收结论

**测试与接线是通的，但有 4 个高严重度问题涉及安全红线，修完再合。** PR #6 还没接进 `engine/`，合并不影响运行；但 S3（engine-session）会话要基于它开发，这些接口问题会被它直接撞上。

已确认没问题：
- `make smoke` 退出 0，253 项测试通过，10 个契约示例通过；rules/mock 两种评测都正常跑完。
- 正常单次输出（明确规则、模糊+成功判断器、未命中+判断器 active、history、模糊+超时/报错、首次 PHQ-9 第 9 题）都能拼进 `session.A-003.json` 并通过契约校验。
- 判断器失败路径（异常、挂起超时、非法对象、缺 history 键、四键全零、非法 status）共 12 个探针，模糊文本都落到 passive / safety_check / rule_ambiguous，无命中文本都无事件。
- `judge_probs` 的二次校验（四键、有限、0–1、和约 1）有效；非法 status 转 error。
- PR #7 的 32 条词表正则、48 条测试样例与本 PR 的 `safety/lexicon.yaml`、`safety/testset.jsonl` 完全一致。

**涉及临床或安全判据的项（标 ⚠️）必须由心理学同学拍板，修复会话不要自行定口径。**

## 2. 修复规则

- 只改 `safety/`、`domain/`、`tests/`、`Makefile`、`requirements*.txt`。不碰 `contracts/`（契约问题见 `pr1-contracts-fixes.md` 与 BACKLOG G 节）。
- 只加不减：现有 253 项测试必须仍然通过；不得放宽现有检查。
- 不得拿现有 `testset.jsonl` 反复调规则（BACKLOG A6）；新增的反例单独放在新测试文件里。
- 不提交任何真实 API key；不调用真实模型。

## 3. 修复项

### P0：合并前必须修

| 编号 | 问题 | 证据 | 要求 |
|---|---|---|---|
| S1 | **缺 key 时默认回退到关键词 MockJudge，且它返回 `status=ok`**，把"判断器失败 → 模糊规则按 passive"的保守兜底盖掉了。该 Mock 在定稿集 24 条阳性里漏 21 条（召回 12.5%）。缺 key 会让安全层**静默降级** | `safety/judges.py:70–94`、`:303–304`；`safety/layer.py:94–104`（只在非 ok 时兜底） | ① 默认路径（没配置真实判断器、缺 key、判断器不可用）不得返回 `ok`：要么按失败处理（`status=error`，模糊规则 → passive），要么启动时明确报错。② Mock 只在显式 `provider=mock`（测试/离线）下启用，且结果里标明，评测报告里单独标注"mock，不代表识别能力"。③ 加测试：缺 key 启动 → 模糊文本仍得 passive / safety_check |
| S2 | **同一会话先出现文本 passive、随后 PHQ-9 第 9 题阳性，安全层输出与契约校验互相矛盾**：层去重后量表事件 `action=none`，README 要求过滤 action=none，而 `contracts/validate.py` 要求每个阳性量表位置都有 `scale_item9` 事件。原样写入被 schema 拒，过滤后被语义校验拒 | `safety/layer.py:62–68,124`；`safety/README.md:25–28`；`contracts/validate.py:143–158`；复现用例见原始报告第 2 节 | 推荐做法：量表阳性**总是产出**一个 `source=scale_item9` 事件，`level` 为 passive/active，`action` 为 `safety_check` 或 `crisis_protocol`（不输出 none）；"不重复问同一句安全确认"的去重改在**话术层**做（事件照写，话术不重复）。这也与契约 v0.1.1 分支里 F02 的收紧一致（`scale_item9` 事件必须 passive/active 且动作非 none）。**加完整会话测试**：文本 passive → 量表阳性，把事件拼进 `contracts/examples/session.A-003.json` 并用 `contracts/validate.py` 校验通过。若不采用推荐做法，必须先和统筹同学商定契约怎么改 |
| S3 | **history 核验检测会把没核验的句子判成已核验**，按 README 接线时因此不会补固定话术。"现在你已经没有这种念头，今晚吃什么？""现在不用问你有没有自杀念头，我们聊睡眠好吗？"都返回 True | `safety/scripts.yaml:4–5`（正则可跨逗号、借后半句的问号）；`safety/layer.py:126–128`；`safety/README.md:53–57` | 匹配限定在**同一个以问号结尾的子句**内：必须同时含"现在/目前/仍/还有"之类的时间限定和风险词的**询问**；陈述句、否定回避句不算。⚠️ 判定口径（什么算核验）请心理学同学确认。补 ≥6 条正反例测试（含上面两句） |
| S4 | **StartLux 配置的 8 秒超时进入 `SafetyLayer` 后被外层 2.5 秒截断**，本可返回的风险判断被丢弃（实测 2.7 秒后返回 active，经安全层 2.51 秒就 timeout、事件为 None） | `safety/config.yaml:3–5`；`safety/judges.py:47–49`；`safety/layer.py:79` | 层的限时必须尊重判断器自带的超时（取 `max` 或直接用 provider 的 timeout），或把全局超时冻结为不小于任一 provider 的值，并在 `config.yaml` 里写明。加**层级**测试（延迟 2.7 秒的 MockTransport 经 `SafetyLayer` 仍得 active） |

### P1：建议一起修，不修要在 PR 里说明

| 编号 | 问题 | 要求 |
|---|---|---|
| S5 | `forbidden_wording` 没做归一化：繁体（`治療失眠症`、`為你診斷`）、全角空格拆字（`诊　断`、`治　疗　失　眠　症`）、同义（`医治失眠症`、`治好失眠症`）、`我可以确诊。`、`这次是误诊。` 共 8 条本应硬拦的未拦。`domain/vetoes.py:49–58` 对原文直接 `re.finditer`。另 PR #7 的 `plan_veto_rules.md:118` 声称 W1 含"确诊/误诊"，但 W1 自己的正则只有"诊断" | 匹配前做 NFKC + 去空白（含全角空格）+ 繁简归一（优先用小映射表，避免新依赖；若引依赖要写进 requirements 并在 PR 说明）；W1 的词表按 PR #7 定稿（含确诊/误诊）同步。26 条探针见原始报告第 5 节，整理成回归测试 |
| S6 | **候选语境豁免没实现**：PR #7 `plan_veto_rules.md:146` 规定候选 playbook 的 `after` 里"不要/禁止…诊断/治疗失眠症"这类**禁止列表**应豁免，但 `check_text` 无语境参数，"不要对来访说诊断为失眠症。""禁止说治疗失眠症。"被硬拦，会误杀反思器写的安全约束 | `check_text` 加 `context`（`user_facing` / `candidate_playbook`）；用户界面文案仍按字面严格拦（"不是诊断"也要拦），候选语境才豁免否定式禁止列表。两种语境各补正反例 |
| S7 | ⚠️ **明确规则把第三方陈述和明确否认直接判成本人 active**："我朋友想自杀，我很担心他。""新闻说有人写好了遗书，我自己没有这些想法。""我没有跳楼的想法。"都返回 `rule_explicit / active / crisis_protocol`，判断器调用 0 次，正确的判断器也没机会纠正。会话会因此以 `crisis_exit` 结束，演示里是误伤 | `safety/lexicon.yaml:3–17` 的 E1/E3 加主体约束、E4 加否定约束；**安全优先**：这类句子不要直接放行，而是降级为"模糊"交给判断器，而不是丢掉。该限制 PR #7 的同一正则里也有。⚠️ 请心理学同学确认口径，再改词表 |
| S8 | **规则层漏报 7 条**（rules-only 24 条阳性召回 70.83%）：POS-03/08/12/13（passive）、POS-15/19/24（active）。这是设计内的——规则层需要判断器兜底，并非 bug——但 README 和评测里不能让人把"0 漏报"读成规则层单独的指标 | ① `README`/`SPEC` 明确写"0 漏报 = 规则 + 真实判断器联合指标，rules-only 不构成"；② `safety.eval` 输出分三栏：rules-only、mock、真实判断器，真实判断器一栏在 A2/A4 对比完成前标"未测"；③ BACKLOG A2/A4 保持未完成，**演示前必须有真实判断器的漏报数**，漏报数 > 0 不得冻结 |
| S9 | "判断器对所有发言运行"的字面要求与 SPEC 允许明确规则 `skipped` 不一致：48 条里判断器调用 46 次，POS-20/POS-23 由规则直接处理 | 在 SPEC/AGENTS 里统一说法：要么写明"除命中明确规则外的所有发言"，要么去掉 skip（让判断器对明确规则也复核，作为 S7 的另一种解法）。二选一，文档化，测试同步 |

### P2：有空再修

| 编号 | 问题 | 要求 |
|---|---|---|
| S10 | 文档不一致：`safety/scripts.yaml:1` 与 PR 描述写话术已审定，`safety/README.md:3,63`、`safety/SPEC.md:6` 仍写待审定/占位 | 以实际审定状态为准统一；热线 `verified` 仍为 false 的保持 false |
| S11 | `history_check` 自动补话术、`speaker=safety`、来访回答再过安全层的完整接线**没有端到端证据**：导出里没有 `engine/`，README 的 `append_message` 只是示意，`check_verification` 不清除 pending 也不追加消息 | 本 PR 不用解决；登记为 **S3 engine-session 会话的验收项**（BACKLOG），要求有端到端测试 |
| S12 | PR #7 描述的硬否决规则 **V3–V6、V9、F2–F6、候选规则 T3、S1 在 `domain/vetoes.py` 里没有实现**（详见 `pr7-pr10-followups.md`） | 单独开 PR 实现（建议 `zhq/domain-vetoes-v2`），因为 V3–V6 需要"询问记录 / OSA 筛查结果 / 最终 R1 预测"这些输入，要先定接口；F1 还缺文档规定的疑问句与咨询医生豁免 |

## 4. 验证与验收标准

```bash
make smoke          # 253 项原测试必须仍全部通过
```

验收会话复验：
1. P0 四项各有回归测试，且**测试在修复前会失败**（修复会话在 PR 描述里写出这一点）。
2. S2 的完整会话用例：把安全层输出拼进 `session.A-003.json`，`python contracts/validate.py <文件> --schema session` 退出 0。
3. 原始报告第 5 节的 26 条禁用措辞探针重跑：S5 做完后预期应拦的 16 条全部拦住，且"不是诊断"这类用户界面否定句仍被拦。
4. 缺 key 环境下跑 `make safety-eval`：不得出现 mock 判断器返回 ok 的情形。
5. ⚠️ 项（S3、S7）有心理学同学确认的记录（PR 评论或 `docs/review-decisions.md` 增补）。
