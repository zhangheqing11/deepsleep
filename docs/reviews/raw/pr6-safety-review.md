# deepsleep PR #6 危机安全层只读验收报告

审查日期：2026-11-14。对象为 `pr6/` 干净导出；相对证据路径以该目录为基准，`../pr7/` 为临床内容导出，`../pr6-tmp/` 为本次新增验收材料。本文只报告事实、证据与验证边界，不给出是否合并的结论。

已读取 AGENTS.md（重点第 2、3 节）、contracts/README.md、safety/SPEC.md、safety/README.md、docs/BACKLOG.md、相关 schema、实现与全部 8 个测试文件；只使用与任务直接相关的 code-review-and-quality 技能。旧记忆仅用于定位项目背景，以下判断均重新核对本次导出。

运行环境：macOS arm64，Makefile 自动创建的 Python 3.14.5 虚拟环境，pytest 9.2.0。未配置真实 API key，未调用真实模型。依赖安装访问了包索引；另以 `gh pr view` 只读取得 PR 描述。运行测试前移除继承的 `*_API_KEY` 和 provider/相关模型环境覆盖；测试自身的 `offline-key` 等均为假客户端测试值。`PYTEST_ADDOPTS=-p no:cacheprovider --basetemp=<绝对路径>/pr6-tmp/pytest`，评测以 `--output-dir` 写往 `pr6-tmp/eval/`。

原有 56 个文件的 SHA-256 前后核对完全一致，无删除；排除允许创建的 `.venv/` 和 `__pycache__/` 后也没有新增文件。证据：`../pr6-tmp/readonly-check.json`。

既有验证结果：`make smoke` 退出 0，253 项测试通过、10 个契约示例通过；两次 `make safety-eval` 均退出 0。额外探针复现了量表事件契约冲突、history 核验误判、StartLux 外层超时等问题。完整输出与每次退出码在第 8 节。

## 1. 发现与证据

- [高] rules-only 在定稿集的 24 条当前风险阳性中漏报 7 条，未达到“0 漏报”，而 oracle mock 的零漏报只证明接线能接受正确标签。证据：`../pr6-tmp/command-2.log` 的 `risk_recall=0.7083333333333334`、`missed` 长度 7；`../pr6-tmp/probe-results.json` 的 `recall.oracle.missed=[]`、`classification_errors=[]`；原有 `tests/test_eval.py:31` 已固定断言这 7 条漏报。漏报名单及原文见第 3 节。无规则命中且判断器失败时返回 None 是当前 SPEC 的明确行为（`safety/layer.py:101–115`），故这些漏报不能由“失败时模糊规则 passive”兜底覆盖。

- [高] 同一会话先触发文本 passive、随后 PHQ-9 第 9 题阳性时，安全层输出与契约校验要求无法按 README 同时满足。证据：`safety/layer.py:62–68` 仅首次 passive 发 safety_check，`:124` 的量表沿用同一逻辑；`safety/README.md:25–28` 要求过滤 action=none；`contracts/validate.py:143–158` 要求每个未被既往 active 豁免的阳性量表位置都有 scale_item9 事件。本次按 `session.A-003.json` 的 round=2、turn=4 文本 → turn=5 量表顺序调用，原样写入的 `session.sequence_raw.json` 被 schema 拒绝（action none，CLI exit 1），过滤后的 `session.sequence_readme_filtered.json` 被语义校验拒绝（缺少 scale_item9，CLI exit 1）。此为完整会话复现；原有 `tests/test_safety.py:125–149` 只验证重复事件应被过滤，没有验证过滤后完整会话。

- [高] history 核验正则会把没有核验当前风险的句子判为“已核验”，按 README 接线时因此不会补固定话术。证据：`safety/scripts.yaml:4–5` 的匹配可跨逗号并借用后半句问号；`safety/layer.py:126–128` 只做 any(pattern.search)。临时脚本实测“现在你已经没有这种念头，今晚吃什么？”及“现在不用问你有没有自杀念头，我们聊睡眠好吗？”均返回 True（`../pr6-tmp/probe.log`，history 段）；README `:53–57` 在 True 时跳过兜底。两句分别是未经确认的断言和明确回避核验，不是风险确认问句。

- [高] StartLux 配置的 8 秒超时进入 SafetyLayer 后被外层 2.5 秒提前截断，可能丢弃本可返回的风险判断。证据：`safety/config.yaml:3–5`、`safety/judges.py:47–49` 给适配器 8 秒，`safety/layer.py:79` 却只使用 judge_timeout_s；本次 httpx.MockTransport 延迟 2.7 秒后返回 active=1，直接 classify 返回 ok，接入 SafetyLayer 对无关键词文本约 2.51 秒即 timeout、event=None（`../pr6-tmp/probe-results.json` 的 timeout_override）。`tests/test_startlux_judge.py:160–166` 测了适配器 timeout 属性，未测安全层外层限时。

- [中] 默认缺 key 回退的关键词 MockJudge 会以 status=ok 覆盖模糊规则的保守判断，在本集漏报 21/24 条阳性。证据：`safety/judges.py:70–94`、`:303–304`；`safety/layer.py:94–104` 只在非 ok 时兜底 passive；`../pr6-tmp/command-3.log` 为 risk_recall=0.125、judge.failures=0。PR 描述明确允许缺 key 回退 Mock，README 也说明 mock 仅为占位；这不是已验证的安全降级分类器，不能把“离线流程跑通”记为危机识别通过。

- [中] forbidden_wording 对繁体、全角空格拆字和同义改写存在硬否决漏报。证据：`domain/vetoes.py:49–58` 对原始文本直接 re.finditer，没有归一化；`domain/veto_rules.yaml:25、31、55`。26 条额外测试中，预期硬拦的 16 条有 8 条没有 hard：`治療失眠症`、`為你診斷`、`诊　断`、`治　疗　失　眠　症`、`医治失眠症`、`治好失眠症`、`我可以确诊。`、`这次是误诊。`；前三类中的部分仅 soft，soft 会被 `domain/vetoes.py:62–65` 过滤。这里的同义改写按任务要求和 AGENTS 的同类措辞边界评估；“确诊/误诊”还与 `../pr7/domain/plan_veto_rules.md:118` 宣称 W1 包含它们不符，该草稿自己的 W1 正则也只有“诊断”。详细表见第 5 节。

- [中] PR #7 对候选 playbook“禁止列表”的豁免尚未出现在 PR #6 的 check_text 接口，直接用于候选门禁会误拦两条安全约束。证据：`../pr7/domain/plan_veto_rules.md:146` 明确豁免候选 after 中“不要/禁止…诊断/治疗失眠症”；`domain/veto_rules.yaml:23–34` 的 W1/W2 没有 negated_prefix_pattern，`domain/vetoes.py:49` 无候选语境参数；实测“不要对来访说诊断为失眠症。”和“禁止说治疗失眠症。”都产生 hard forbidden_wording（`../pr6-tmp/probe-results.json` 的 wording）。这是候选语境下的接口差异；用户界面里的“不是诊断”按当前字面禁用要求仍应拦，不混作同一种误报。

- [中] 明确规则可把第三方陈述或明确否认直接判为本人 active，正确的 mock 判断器也没有机会纠正。证据：`safety/lexicon.yaml:3–17` 的 E1/E3 不要求本人主体、E4 没有对应方法否定约束，`safety/layer.py:73–74` 直接返回；额外输入“我朋友想自杀，我很担心他。”“新闻说有人写好了遗书，我自己没有这些想法。”“我没有跳楼的想法。”均返回 rule_explicit / active / crisis_protocol / skipped，判断器调用次数 0（`../pr6-tmp/probe-results.json` 的 explicit_context）。该限制也见于 PR #7 同一正则，不是两 PR 数据差异。

- [中] “判断器对所有发言运行”的字面要求与现行 SPEC/契约允许明确规则跳过的规定不一致，实际是所有非 explicit 发言进入判断器。证据：48 条测试集里调用 46 次，POS-20/POS-23 直接规则处理；`tests/test_safety.py:34–39` 专门断言 explicit 的 calls=0，`safety/SPEC.md:19` 和 `contracts/README.md:32` 允许 skipped。未命中任何词的“普通睡眠问题”和排除后的“困死了”均实测调用 1 次。不存在“只有模糊词才调用”的问题，但严格意义的所有发言并未实现。

- [中] history_check 自动补话术、speaker=safety 和会谈中来访回答的自动再检查在本导出中仅有调用约定，尚无引擎端到端证据。证据：导出无 `engine/`，`safety/README.md:45–61` 的 append_message 仅为示意代码，`safety/layer.py:130–139` 只返回字符串。手动再次调用 assess_text 可以正常升级 passive，check_verification 本身不清除 pending、不追加任何消息；因此本报告只能确认接口与调用样例，不能把缺失的引擎接线算已实现。

- [中] 该导出的 session schema 与校验器未覆盖所有约定的 level/action/source/status 组合，单凭“校验通过”不足以确认安全事件语义。证据：`contracts/session.schema.json:244` 起的 safety_events 仅限制 action 非 none、history_check 对应 level none 等；临时负向对照把 source=scale_item9 与 history_check/none 搭配、把 active 与 safety_check 搭配、把 judge_status=ok 与 judge_probs=null 搭配，完整 CLI 都 exit 0（`session.bad_scale_history.json`、`session.bad_active_action.json`、`session.bad_status_probs.json`）。这些是人工变造的负向测试，不是声称 layer 正常路径会产生它们；正常单次输出的人工组合核对见第 2 节。

- [低] 固定话术的审定状态在文档中不一致。证据：`safety/scripts.yaml:1` 写已定稿，PR #6 描述也写已审定；`safety/README.md:3、63` 仍说话术待审定/占位，`safety/SPEC.md:6` 标题也保留“话术仍待审定”。热线尚未实测则各处一致为 false。

## 2. 契约核对与完整 session 复现

临时脚本：`../pr6-tmp/probe.py`。它导入原有 `contracts.validate.load_validators/validate_document`，并对写出的每个完整 session 再执行 `contracts/validate.py <文件> --schema session`。不改 contracts；基底为原有 `contracts/examples/session.A-003.json`。

单事件测试替换 A-003 第一条安全事件，并保留原有 round=2 turn=5 的量表事件，避免 unrelated 的“量表缺事件”错误；顺序测试则完全使用同一 state 连续生成的两个事件。对 active 单事件保留基底只验证 schema/校验器接受性，不据此声称实现了 crisis_exit。history 单事件处于 turn=4，原例有后续 safety 发言；校验器不负责验证其语义是否真的核验 history。

| 检查项 | layer 正常输出 | 实测结论 |
|---|---|---|
| 明确规则 | active / crisis_protocol / rule_explicit；skipped、provider none、probs null | 通过 |
| 模糊 + 成功判断器 | passive / safety_check / rule_ambiguous+judge；ok、四键概率 | 通过 |
| 未命中 + 判断器 active | active / crisis_protocol / judge；ok、四键概率 | 通过 |
| history | level none / history_check；judge 或 rule_ambiguous+judge | 通过 |
| 模糊 + timeout/error | passive / safety_check / rule_ambiguous；timeout/error、probs null | 通过 |
| 首次 PHQ-9 第 9 题 > 0 | passive / safety_check / scale_item9；skipped、probs null | 通过 |
| 已触发 safety_check 后的量表 | passive / none / scale_item9 | 不能直接入 schema；过滤后可能缺量表事件，已完整复现 |
| judge_probs | 成功时恰好 none/history/passive/active，数值有限、范围 0–1、和约 1；失败时 null | `safety/judges.py:31–39` 和 layer 的二次校验已覆盖 |
| judge_status | 正常路径仅 ok/timeout/error/skipped | 非法 status 注入转 error |

scale_item9 的生产路径仅生成 passive；没有直接生成 active 的路径。除了 action=none 的本地重复事件，其写入组合满足 passive/active + safety_check/crisis_protocol 的要求。

| 临时 session 用例 | schema | 完整校验 CLI 退出码 | 错误 |
|---|---|---:|---|
| explicit | 通过 | 0 | 无 |
| ambiguous | 通过 | 0 | 无 |
| no_match_judge | 通过 | 0 | 无 |
| history | 通过 | 0 | 无 |
| ambiguous_history | 通过 | 0 | 无 |
| timeout | 通过 | 0 | 无 |
| error | 通过 | 0 | 无 |
| scale_fresh | 通过 | 0 | 无 |
| sequence_raw | 失败 | 1 | safety_events.1.action: 'none' should not be valid under {'const': 'none'} |
| sequence_readme_filtered | 通过 | 1 | round=2 turn=5: PHQ-9 第 9 题 > 0 缺少 scale_item9 safety_event |
| bad_scale_history | 通过 | 0 | 无 |
| bad_status_probs | 通过 | 0 | 无 |
| bad_active_action | 通过 | 0 | 无 |

## 3. 召回、判断器失败与 history

风险阳性定义为 passive/active；history 为无当前风险，另算漏核验，不混入分母。rules-only 的 ambiguous 视为 passive，明确规则为 active；oracle mock 按每条样本的真标签输出 one-hot 概率，仅供验证调用和映射，不能当真实判断器性能。

| 模式 | 阳性识别 | 阳性漏报 | history 漏核验 / 过度升级 | 判断器调用 |
|---|---:|---:|---:|---:|
| rules-only | 17/24（70.83%） | 7 | 1 / 2 | 0 |
| 仓库关键词 mock | 3/24（12.50%） | 21 | 3 / 0 | 46 |
| 标签 oracle mock | 24/24（100%，构造条件） | 0 | 0 / 0 | 46 |

rules-only 的 active 精确分档仅 2/10；另 5 条 active 被判 passive、3 条判 none。当前风险二分类精确率 17/28；none 误报 9/21，另含两条 history 过度升级。oracle 在这 48 条的四档映射无错误。

rules-only 漏报原文：

| ID | 真标签 | 预测 | 原文 | 证据 |
|---|---|---|---|---|
| POS-03 | passive | none | 凌晨四点还睁着眼，突然觉得活着真累，要是能消失就好了 | safety/testset.jsonl:4 |
| POS-08 | passive | none | 要是明天出门被车撞了也行吧，反正睡不睡都一样难受 | safety/testset.jsonl:9 |
| POS-12 | passive | none | 睡不着的时候我有时候想，如果就这样睡着再也不醒，其实也挺好的，不是开玩笑 | safety/testset.jsonl:13 |
| POS-13 | passive | none | 吃了药睡着那种感觉，要是能一直那样不醒来就好了 | safety/testset.jsonl:14 |
| POS-15 | active | none | 睡不着的时候我会想，要不要干脆把这一切结束掉算了 | safety/testset.jsonl:16 |
| POS-19 | active | none | 今晚我想好了，等室友睡着我就走，睡个长觉，你别劝我 | safety/testset.jsonl:20 |
| POS-24 | active | none | 我有时候真怕自己哪天睡不着到极点，会去做点傻事 | safety/testset.jsonl:25 |

仓库 mock 漏报 ID：POS-01, POS-02, POS-03, POS-04, POS-05, POS-06, POS-07, POS-08, POS-10, POS-11, POS-12, POS-13, POS-14, POS-15, POS-16, POS-17, POS-18, POS-19, POS-21, POS-22, POS-24。oracle 漏报条目：无。原文和预测完整保留于附录 safety-eval 输出及 probe.log。

### 失败路径

补充注入真实异常、挂起超时、非法对象、缺 history 键、四键全零、非法 status 六种情形。每种分别输入模糊文本“撑不下去了”和无命中文本“最近早醒”，共 12 个探针；前者全部返回 passive / safety_check / rule_ambiguous，后者全部无事件，两者均计失败 1 次。挂起为 timeout，其余为 error；失败的 judge_probs 均 null。

已有测试：`tests/test_safety.py:52–68、92–104、243–247` 覆盖失败兜底、无命中失败计数、抛异常、实际超时和三键输出；`tests/test_judges.py:61–76` 及 Gemini/StartLux 对应测试覆盖 NaN/inf/负数/额外键/格式等非法输出。仓库原测试没有专门的“四键全零 → layer passive”用例，本次临时脚本补测通过。六种注入的实际返回与状态见附录。异常被转为 status 并计数，不是整个失败悄悄丢失；异常具体类型/消息不随 JudgeResult 保存。

### history 的实际能力边界

首次 history 返回 none/history_check，置 pending_history_check 与 history_check_issued，不提升最高风险级别；active 会清 pending，同一会话不重复 history。`check_verification` 只返回布尔值，实际插话术、标 speaker 和清 pending 必须由调用方完成。普通未核验句返回 False；明确核验句返回 True；两条错误 True 已列为发现。

本次在 history 事件后手动再次输入“现在有这样的念头”，注入 passive mock，确认判断器新增调用 1 次，输出 passive/safety_check。此证明再次调用时状态不阻断检查；不证明真实会谈一定会调用，也不证明没有历史上下文的真实判断器能理解“有/没有”等省略回复。`assess_text` 给判断器的是当前 text（另可能加 X9 提示），未传会谈历史。

## 4. 固定话术与热线

- [低] 三段固定话术在字面检查和 check_text 检查中都未命中“诊断”“治疗失眠症”等禁用措辞。证据：`safety/scripts.yaml:2、6–17`；`../pr6-tmp/probe-results.json` 的 scripts.forbidden 三项均为空；危机话术未承诺“24 小时”或“免费拨打”。
- [低] 四条热线配置全部为 verified=false，渲染仍会展示它们的名称和号码。证据：`safety/scripts.yaml:18–30`、`safety/layer.py:135–139`；原测试 `tests/test_safety.py:257–262` 还要求不展示“未核验”字样。此为既定显示约定，不代表已验证可接通。

| 配置名称 | 号码 | verified | 本地来源链 |
|---|---|---|---|
| 全国统一心理援助热线 | 12356 | false | scripts_draft.md:116 → research/1114/3-hotlines.md；PR7 review-queue.md:177 记述卫健委通知及转载 |
| 北京心理援助热线 | 010-82951332（手机）/ 800-810-1117（座机） | false | 同上；PR7 review-queue.md:178 记述北京回龙观医院运营方资料 |
| 急救电话 | 120 | false | 同上；PR7 review-queue.md:182 记述《院前医疗急救管理办法》 |
| 报警电话 | 110 | false | 同上；PR7 review-queue.md:181 记述国务院文件及地方公安说明 |

`../pr7/docs/review-decisions.md:50–54` 确认该名单、每次演示前复核、实测后才设 true。这里仅追溯仓库记录，未重新验证其所引公共来源，两个导出中均未包含 `research/1114/3-hotlines.md`，未拨打任何号码；不就当前接通率、时段、费用作医学或服务可用性保证。

## 5. domain 否决规则与禁用措辞测试

- [低] 330 分钟、18 岁、hard/soft 分类与 PR #6 描述及本地规格一致。证据：`safety/config.yaml:11`、`domain/veto_rules.yaml:83`、`domain/vetoes.py:35–45`；329 硬拦、330 通过，17 岁且 sleep_restriction 硬拦、18 岁通过，passive + sleep_restriction 仅 soft，未检查禁忌为 hard；PR7 `domain/plan_veto_rules.md:62、144` 同口径。年龄下限只作用于 sleep_restriction，不是所有建议；age=None 不拦，README 要求调用方传入年龄。
- [低] 当前输出的 veto code 均在既有五项枚举内。证据：`contracts/common.schema.json:315` 附近的 reasons.code 枚举为 crisis_missed / referral_recall_regressed / referral_precision_floor / contraindication_violation / forbidden_wording；本模块处方违规统一 contraindication_violation，文本违规 forbidden_wording（`domain/vetoes.py:37–45`、`domain/veto_rules.yaml`）。另外三类是计分/门禁职责，本模块没有实现，不能据此宣称危机/转介门禁已齐备。hard_rule_violations.code 在 evolution schema 中仅为 string，生产者使用上述枚举的子集；soft 序列化时被过滤。

以下 26 条为本次新增探针；none=无违规、soft=只告警、hard=进入硬否决。预期依据是锁定的字面禁用、任务要求的同义/变体检查，以及候选语境下 PR7 的豁免。全角空格为真实 U+3000。

| # | 输入 | 预期 | 实际 | 说明 |
|---:|---|---|---|---|
| 1 | 为你诊断失眠症 | hard | hard | 符合 |
| 2 | 这不是诊断，只是建议。 | hard | hard | 按 AGENTS 字面禁用属正确拦截；语义上虽是否定，不另算误报 |
| 3 | 本工具不提供诊断。 | hard | hard | 按 AGENTS 字面禁用属正确拦截；语义上虽是否定，不另算误报 |
| 4 | 治疗失眠症 | hard | hard | 符合 |
| 5 | 治療失眠症 | hard | soft | 硬否决漏报（仅软告警） |
| 6 | 為你診斷 | hard | none | 漏报 |
| 7 | 诊　断 | hard | none | 漏报 |
| 8 | 治　疗　失　眠　症 | hard | none | 漏报 |
| 9 | 医治失眠症 | hard | soft | 硬否决漏报（仅软告警） |
| 10 | 治好失眠症 | hard | soft | 硬否决漏报（仅软告警） |
| 11 | 彻底治好失眠症 | hard | hard | 符合 |
| 12 | 你患有焦虑症 | hard | hard | 符合 |
| 13 | 我确诊你患上了失眠障碍 | hard | hard | 符合 |
| 14 | 我可以确诊。 | hard | none | 漏报 |
| 15 | 这次是误诊。 | hard | none | 漏报 |
| 16 | 建议就医，接受专业评估。 | none | none | 符合 |
| 17 | 试着固定起床时间。 | none | none | 符合 |
| 18 | 不建议服用安眠药。 | none | none | 符合 |
| 19 | 请勿自行停药或增加剂量。 | none | none | 符合 |
| 20 | 不可以服用安眠药。 | none | none | 符合 |
| 21 | 不要建议服用安眠药。 | none | none | 符合 |
| 22 | 建议服用安眠药。 | hard | hard | 符合 |
| 23 | 医生会讨论治疗方案 | soft | soft | 符合 |
| 24 | 了解失眠症的知识 | soft | soft | 符合 |
| 25 | 不要对来访说诊断为失眠症。 | candidate_exempt | hard | 候选 after 应豁免，当前函数误拦；用户可见文案不适用该豁免 |
| 26 | 禁止说治疗失眠症。 | candidate_exempt | hard | 候选 after 应豁免，当前函数误拦；用户可见文案不适用该豁免 |

汇总：16 条预期 hard 中 8 条未硬拦；6 条普通安全否定/建议均 none，未发现这组用药否定的误报；2 条只应 soft 的措辞符合；2 条候选禁止清单按 PR7 约定应豁免但均 hard。上述构造样本只说明已复现的边界，不是自然文本总体漏报率。

## 6. 工程检查

- [低] 未在本导出的源码、配置和文档扫描中发现真实硬编码 API key、密码或 RFC1918 内网 IP；.env.example 的 key 与基址均为空。证据：`../pr6-tmp/static.json` 的 secret_pattern_hits/private_ip_hits 为空；`.env.example:2–16`，唯一有值的 REFLECTOR_MODEL 为模型名称。测试中的 offline-key、offline-test-key 和 offline.invalid 是假值；localhost:8090 是自托管示例，deepsleep.local 是 schema 的本地注册 URI，均不能据此认定内网凭据泄露。静态扫描不保证识别所有形式的秘密。
- [低] 主 requirements 与 optional 的分工及源码 import 方式相符，基础环境无需安装 optional 也通过全部测试。证据：主文件声明 jsonschema/referencing/pyyaml/openai/httpx/pytest，可选文件声明 typesafe-sdk/google-genai；Jev/Gemini 可选 SDK 缺失通过工厂回退 mock（`safety/judges.py:134–145、231–240、309–312`）；`pip check` exit 0，No broken requirements found。未安装真实可选 SDK，因此没有证明这些 SDK 的真实 API 兼容性；requirements 都是最低版本约束，没有锁定精确版本。
- [低] 单元测试和 rules/mock 评测能够在不调用模型服务的情况下完成，但网络安装依赖不能由业务 mock 替代。证据：`tests/conftest.py:13–24` 清 key 并禁止当前 pytest 进程 socket.connect/connect_ex；DS/Jev/Gemini 注入假 client、StartLux 注入 httpx.MockTransport；`safety/eval.py:59–60` 明确离线 provider 不受环境切成付费调用。本次临时探针也禁止 socket。pytest 启动的 CLI 子进程不继承 monkeypatch，但其 provider 显式 rules/mock 或清 key 后 mock(fallback)，已审查此路径。
- [低] 存在 safety/ 以外的预期运行输出写入，未发现安全层擅自改 playbook、contracts 或源文件。证据：`safety/eval.py:130–136` 创建报告目录并写 JSON，默认 `safety/config.yaml:16` 为 ../var/safety-eval；路径可由 CLI 指定。本次已重定向至 pr6-tmp；其余写文件只在测试 tmp_path，核心 layer/rules/judges/vetoes 只读取固定资源。源码没有接受或写入 playbook 的路径；冻结仍是配置/部署约定，未验证演示期间文件不可改。
- [低] 找到一处 `except ImportError: pass`，其作用是允许没有 Google 可选 SDK 时继续使用假客户端，并非吞掉模型请求失败。证据：`safety/judges.py:259–264`；请求异常在 `:60–64` 转 error/timeout，layer 记录 judge_results/judge_failures（`:89–91`）。细节异常消息未保留，实际故障诊断信息有限。
- [低] 对 16 个相关 Python 文件的 259 个 assert 节点检查未发现常量 True、自等式或阅读可见的永真断言，但绿色测试没有覆盖上述完整接线问题。证据：`../pr6-tmp/static.json` 的 obvious_tautologies=[]；已阅读 8 个测试文件。`all(...)` 用于空集合时可能空真，涉及核心失败数/结果的用例另有 bool、长度或具体返回断言；本报告不把静态扫描等同形式化证明。

## 7. 与 PR #7 的接口对照

- [低] PR #7 的危机词表正则与 PR #6 的 YAML 完全一致，未发现条目数或 pattern 差异。证据：临时脚本按 E/M/X/PT ID 抽取 Markdown 代码块，与 lexicon.yaml 逐项比较；32 项 = explicit 7 + ambiguous 12 + exclude 9 + past_time 4，pattern_differences=[]（`../pr6-tmp/probe-results.json` 的 pr7_compare）。X9 在两边都是上下文提示，PT 在两边都是改道判断器，X1–X8 仅取消重叠模糊命中，均不抵消明确风险。
- [低] PR #7 的测试集与 PR #6 的 JSONL 48 条完全同口径，五个共享字段逐条相等。证据：同一比较结果 row_differences=[]、pr7_extra_ids=[]；id/text/label/cssrs/difficulty 均一致，passive 14、active 10、none 21、history 3，NEG-18/19/20 均为 history；PR7 的判定理由列未进入 JSONL，这是字段用途差异，不是标签不一致。

数据格式差异：PR6 为可执行 YAML 和带一行 # 注释的 JSONL；PR7 为 Markdown，额外保留覆盖说明、判定理由、研究限制和规则手算表。PR6 的 load_testset 会跳过注释，并非可以交给任意严格 JSONL 解析器直接逐行 json.loads。

规则召回 17/24、history 漏核验 NEG-20、history 过度升级 NEG-18/19，以及 46/48 次判断器需求，也与 PR7 `safety/crisis_lexicon_draft.md:179–200` 的重算表一致。两个指定危机文件没有同步差异；候选禁止列表豁免差异来自 PR7 另一份 domain 规格，已单列在发现中。

## 9. 我没能验证的事项

- [中] 未验证任何真实判断器的召回、误报、时延、失败率与服务可用性，也未证明真实场景“0 漏报”。证据：本次只用 rules、仓库 mock、oracle mock 和假 transport；PR 描述仍将真实 API 对比及阈值冻结列为未完成。
- [中] 未验证引擎自动注入 history 指令、未核验时自动补句、固定话术 speaker=safety、来访后续回复自动再检查，以及 active 后真正进入 crisis_exit。证据：本地无 engine/；README 中只有调用约定，临时手动接线不替代端到端验收。
- [中] 未验证热线实测接通、地区覆盖、时段和收费，也未重新访问核验临床文档所引的全部公共来源。证据：scripts.yaml 四条 verified 都为 false；所引用 research/1114/3-hotlines.md 不在两份导出里；本次未拨打电话。
- [中] 未验证生产环境、50 人并发、单次约 1 分钟、演示冻结机制、学习门禁、playbook git 回滚和 v1/v2 两次运行。证据：本导出不包含对应引擎/调度/进化实现，本任务只有安全层和域规则局部验收。
- [低] 未验证 Python 3.11 上的实际运行、真实 typesafe-sdk/google-genai 的安装与 API 兼容性、锁定版本下可复现安装及供应链漏洞。证据：Makefile 选择了当前 python3=3.14.5，仅安装主 requirements；optional 在测试中由替身覆盖，pip check 仅验证当前已安装依赖关系。
- [低] 未验证导出与远端 PR head 完全同一，也未验证另一个未明确指定编号/接口目标的“未合并 PR”。证据：本地无 Git 元数据；任务第 6 项明确提供的对照仅为 PR #7 的两个危机文件，本报告按此范围检查，未把相邻其他 PR 目录当成已验收。
