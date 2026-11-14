# deepsleep PR #7 一致性审查

审查日期：2026-11-14。对象为指定的 PR #7、PR #6 本地导出；没有查询远端 PR 状态。本报告不判断临床内容正确与否，不提供是否合并的结论。

证据路径相对于本报告所在的 `scratchpad/`：`pr7/` 为临床文档导出，`pr6/` 为安全层代码导出。核心审查对象是五份草稿和 `review-decisions.md`、`review-queue.md`；同时对照 AGENTS、BACKLOG、PLAN、契约及相关安全层代码。号码、数字、文献清单以这七份文档为主，并补列对照文档中实际使用的临床数字。

操作边界：未改动两份导出中的文件，未调用真实模型、未拨打热线、未检索外部临床资料。验证使用内存中的表格解析、正则比对，以及 PR #6 的 `Rules.match`、`check_plan`、`check_text`；关闭 Python 字节码写入。没有运行会写入 `var/` 的评估命令。临时依赖仅放在 `/private/tmp/pr7-review-deps`。最终复核时，两份导出中基线所记录的原有文件哈希均未改变；期间观察到 PR #6 新出现 `contracts/__pycache__/validate.cpython-314.pyc`，本次脚本均使用 `-B` 且未导入该模块，无法确认这个新增缓存的来源，未删除或改动它。

严重度只表示一致性与实现影响：高＝文档承诺的硬规则在对照实现中没有对应检查；中＝契约语义、路由或审核结论存在分歧；低＝记录、出处或覆盖说明不完整。下列“已落实”仅指文本落实，不代表临床专家逐条认可或运行时已经集成。

## 1. 发现

### 代码与规则文档的差异

1. **[高] V3–V6 被文档列为硬否决，但 PR #6 的 `check_plan` 没有核查询问记录、OSA 筛查结果或最终 R1 预测的输入和逻辑。**
   证据：`pr7/domain/plan_veto_rules.md:42-45`；`pr6/domain/vetoes.py:30-46`。
   具体缺口：V3 要核对 `health_conditions`，V4 要核对 `snoring_breathing`／`screen_osa`／已有 STOP-Bang，V5 要拦 STOP-Bang ≥3，V6 要拦自判 R1 后仍用睡眠限制。现有函数只读组件、禁忌集合、checked、可选年龄、单一危机级别及 TIB。复现：`sleep_restriction`、checked=true、TIB=330、空禁忌、age=30 返回空列表；函数无法进一步区分是否问过禁忌或已有 OSA 阳性结果。这里确认的是该实现未覆盖这些规则，不断言导出外的调用方也未实现。

2. **[高] PV-12 已把 V9“有禁忌但缺就医建议组件”定为硬否决，PR #6 却不会对不含睡眠限制的此类处方报错。**
   证据：`pr7/domain/plan_veto_rules.md:48`、`:201`；`pr7/docs/review-queue.md:65`；`pr6/domain/vetoes.py:35-46`。
   复现：禁忌为 `bipolar`，组件只有 `sleep_hygiene`，TIB=330，返回 `[]`；没有检查 `referral_advice` 组件。

3. **[高] F2–F6 的保健品、酒精助眠、替就医做保证、保证效果与熬通宵检查没有按文档规则进入 PR #6 的文本规则表。**
   证据：`pr7/domain/plan_veto_rules.md:80-106`；`pr6/domain/veto_rules.yaml:16-82`；`pr6/domain/vetoes.py:49-59`。
   PR #6 只有一条 medication-advice 和 W1–W10，部分用语可被其他规则偶然覆盖，但不是完整的 F2–F6。仅作为反例输入的“建议补充镁”“喝点红酒帮助入睡”“不用去医院”“保证有效”“熬个通宵”，`check_text` 均返回 `[]`。

4. **[中] PR #6 的 F1 类实现没有文档规定的疑问句与咨询医生豁免，会把文档允许的用药询问和转交医生判断拦为硬违规。**
   证据：`pr7/domain/plan_veto_rules.md:74-76`、`:92-105`、`:108`；`pr6/domain/veto_rules.yaml:17-22`；`pr6/domain/vetoes.py:52-57`。
   复现：“你现在服用安眠药吗？”和“请咨询医生决定是否停药。”均返回 `forbidden_wording/hard`。此外，PR #6 使用整体文本正则而非文档指定的逐句 DRUG／SUPP／VERB／DOSE／EXEMPT 组合，覆盖范围不同。

5. **[高] 候选硬规则 T3“降低卧床下限”和 S1“跳过禁忌询问”未在 PR #6 的文本检查实现中出现。**
   证据：`pr7/domain/plan_veto_rules.md:70`、`:165`、`:170-172`；`pr6/domain/veto_rules.yaml:16-83`；`pr6/domain/vetoes.py:49-65`。
   复现：“卧床时间4小时”和“无需询问禁忌”均返回 `[]`。`to_hard_rule_violations` 只序列化已有违规，不补做这些检查。

6. **[中] T2 要求的 bedtime、risetime 与 TIB 相差超过 5 分钟的软警告没有在 PR #6 实现。**
   证据：`pr7/domain/plan_veto_rules.md:69`；`pr6/domain/vetoes.py:30-46`。
   复现：bedtime=23:00、risetime=07:00、tib_minutes=330，实际时差 480 分钟，`check_plan` 仍返回 `[]`；未产出 `plan_infeasible`。

7. **[中] 候选 playbook 中“列出禁用词”的豁免在文档中成立，但 PR #6 的 `check_text` 没有候选上下文或对应豁免逻辑。**
   证据：`pr7/domain/plan_veto_rules.md:114`、`:146`；`pr6/domain/vetoes.py:49-59`；`pr6/domain/veto_rules.yaml:23-28`。
   复现：文档自己的豁免例句“不要对来访说诊断为……”仍返回 `forbidden_wording/hard`。

### 契约、审核结论与文档自身的差异

8. **[中] `deny_first` 的触发条件在定稿线索表与契约 README 中不完全相同。**
   证据：`pr7/domain/path_clues.md:26`、`:182` 规定只有 defensiveness=mid/high 才触发；`pr7/contracts/README.md:77` 写成 `deny_first=true` 就首次否认；`pr7/contracts/visitor.schema.json:220-226`、`:272-276` 允许 low 与 true 独立组合。
   因而 low+true 是 schema 合法输入，却有两种行为解释。这不是枚举或布尔类型错误；可通过生成器约束或明确契约语义消除，但两份导出没有相应生成器可验证。

9. **[中] “枚举核对按倾向”会承接 `self_harm` 仅由安全层提问的选项，而 history_check 又要求 agent 下一句亲自核验，文档没有明确两者的例外边界。**
   证据：`pr7/docs/review-decisions.md:18`、`:46-48`；`pr7/docs/review-queue.md:100`；`pr7/domain/referral_cues.md:126`；`pr7/contracts/README.md:30`。
   队列 A 写“不能，只有安全层会问”；history 结论写“agent 下一句必须核验”。若“主动问”仅指 agent 自主选择话题，而不包括安全层指令注入后的核验，可以相容，但该区别目前没有写清；转介草稿仍回指“问题”而未落实此权限说明。

10. **[中] LX-3 审核结论把历史改道路由的成功结果写为 history/passive/active 三档，但草稿通用流程及 PR #6 允许成功判为 none。**
    证据：`pr7/docs/review-decisions.md:25`；`pr7/safety/crisis_lexicon_draft.md:13-15`、`:57`、`:284`；`pr6/tests/test_review_decisions.py:43-50`；`pr6/safety/layer.py:94-115`。
    PR #6 明确测试判断器成功返回 none 时不产生事件。失败时兜底 passive 是一致的；差异只在“成功时能否为 none”，不将 `history → crisis_level none + history_check` 与“完全无事件”混为一谈。

11. **[中] 转介文档把具体筛查触发条件标为供 v0 playbook 参考，与 BACKLOG 对 v0“不说什么时候用筛查工具”的约定相冲突。**
    证据：`pr7/domain/referral_cues.md:50-52`；`pr7/docs/BACKLOG.md:42`。
    文档给出 R1-c1/c2 或 R1-c4+c5 就调用工具的规则；BACKLOG 明确把时机保留为进化空间。这里只确认指导文档冲突，未看到实际 v0 playbook。

12. **[中] 审核结论要求把其余新增枚举记入 BACKLOG E，但该节仅列出少数项目，并仍把已决定的单转介标签问题列为待议。**
    证据：`pr7/docs/review-decisions.md:14`、`:48`；`pr7/docs/review-queue.md:105`、`:123`、`:139-167`；`pr7/docs/BACKLOG.md:57-63`。
    E 节已有 veto 两个 code、`referral_wrong_type`、年龄和 RC-6；未逐项列出六个新增 topic、两个 component、`psychosis`、`chronic_depressive_symptoms`、“疑似其他睡眠障碍”、`path_regressed`、失败标签用途的 `forbidden_wording/tib_below_floor/medication_advice`。这属于待办落实缺口；不是要求立即修改契约。

13. **[中] T1/T3/F 系列的输出 code 在正文、总览和“建议新增”之间没有统一说明实际序列化值，并且候选 hard_rule_violations.code 被误当成现有封闭枚举。**
    证据：`pr7/domain/plan_veto_rules.md:18`、`:68-70`、`:80-85`、`:163-179`；`pr7/contracts/common.schema.json:307-315`；`pr7/contracts/evolution.schema.json:220-239`；`pr6/domain/vetoes.py:44-45`；`pr6/domain/veto_rules.yaml:17-18`。
    正文 T1 写 `tib_below_floor` 暂借 `contraindication_violation`，总览却写“无”；F1 提到暂借 `forbidden_wording`，F2/F3/F6 及 T3 未统一重申映射。运行 veto 只允许五个 code，PR #6 实际返回旧 code；候选 `hard_rule_violations[].code` 则只是 string，当前没有 enum。新名称可作为候选本地字符串，但不能原样进入运行 veto 的封闭枚举。

14. **[中] W1 表格声称“确诊”“误诊”也一律命中，但文档自己的正则和 PR #6 都只匹配“诊断”。**
    证据：`pr7/domain/plan_veto_rules.md:118`、`:132`；`pr6/domain/veto_rules.yaml:23-25`。
    复现：“你已确诊”“这个可能是误诊”均返回 `[]`。这是文字承诺与正则的内部矛盾，不判断这些措辞的临床适切性。

15. **[低] F6 的表格要求排除否定句，但后面的通用命中逻辑只写直接 search 和非疑问句，未定义该否定豁免。**
    证据：`pr7/domain/plan_veto_rules.md:85`、`:100`、`:103-106`。
    按后者直接实现会命中“不要熬个通宵”中的 DEPRIVE；按表格则应豁免。此问题独立于 PR #6 尚未实现 F6。

16. **[低] 审核清单的“15 个带星、32 个不带星”与实际 47 行中的 14 个带星、33 个不带星不符。**
    证据：`pr7/docs/review-queue.md:13-14`、`:28-74`；`pr7/docs/review-decisions.md:31`。
    已按 TS/LX/PC/PV/RC 编号逐行计数；47 项总数本身正确。

17. **[低] PV-8 的最终选择正确同步为软警告，但结论表错误记录了起草倾向。**
    证据：`pr7/docs/review-decisions.md:12` 写“同”；`pr7/docs/review-queue.md:61` 的“我的倾向”却为 B 更保守，用户明确选择 A。
    这是来源记录错误，不是最终硬软分级冲突；`pr7/domain/plan_veto_rules.md:47` 与 `pr6/domain/vetoes.py:42-43` 一致为软警告。

18. **[低] review-queue 仍以未定稿状态陈述已经被后续结论和契约替代的事实，缺少明确的历史快照提示。**
    证据：`pr7/docs/review-queue.md:3`、`:19`、`:35-42`、`:65`；对照 `pr7/docs/review-decisions.md:18-25`、`pr7/contracts/README.md:26-31`、`pr7/domain/plan_veto_rules.md:48`。
    例如仍称契约没写时间窗、判断器按“过去已结束=none”、V9 目前为软。结论文件已声明为唯一结论，因此这些旧倾向不应当作新的否决意见，但交接阅读仍会出现两套现状。

19. **[低] R2 文档将“腿部不适、活动缓解、夜间加重”的具体描述归于 AGENTS 术语表，但实际出处是 PLAN。**
    证据：`pr7/domain/referral_cues.md:66`；`pr7/AGENTS.md:48`；`pr7/docs/PLAN.md:97`。
    AGENTS 只写“R2 疑似不宁腿”；PLAN 才有三项描述。这里指出出处不准确，不判断 R2 判据本身。

## 2. 路径、topic 和其余枚举核对

### 2.1 path_clues.md 实际使用

- P1–P5 五条路径及名称均与契约和 AGENTS 一致，没有 P6 等未定义路径。证据：`pr7/domain/path_clues.md:28-98`；`pr7/contracts/common.schema.json:6-14`；`pr7/AGENTS.md:47`。
- P1–P5 直接线索表共 25 条：P1 6、P2 5、P3 5、P4 4、P5 5；直接使用 14 个不同 topic；连同 D1–D8 鉴别表，共覆盖 17/20 个 topic，所有实际 `reveal_topic` 都合法。证据：`pr7/domain/path_clues.md:34-96`、`:118-125`；`pr7/contracts/common.schema.json:71-94`。
- `reveal_topic` 引用 topic、`deny_first` 为布尔值的说明与 schema 一致；表中的“是/否”是说明表格，并非提交给契约的 JSON 字符串。唯一行为差异见发现 8。证据：`pr7/domain/path_clues.md:7`；`pr7/contracts/visitor.schema.json:272-276`。
- `supports` 的 schema 范围是 path/referral/`crisis`；`path_clues` 未输出完整 visitor JSON，也未把支持强度当成契约字段，因此不能把“强/中/弱”误报为非法枚举。证据：`pr7/domain/path_clues.md:11-19`；`pr7/contracts/visitor.schema.json:278-300`。

| 枚举 | path_clues.md 中未覆盖的现有值 | 证据与解释 |
|---|---|---|
| path | 无 | 五条路径齐全；上述证据 |
| topic | `self_harm`、`medication`、`health_conditions` | 契约 `common.schema.json:90-93`；线索和鉴别表 `path_clues.md:34-125`；该表主要面向路径，不等于应在这里强行加齐安全/用药线索 |
| component | `fixed_risetime`、`stimulus_control`、`sleep_restriction`、`cognitive_restructuring`、`worry_time`、`relaxation`、`schedule_shift`、`digital_curfew`、`referral_advice` | 该文件仅在 `:174-175` 提及 `light_timing`、`sleep_hygiene`；契约 `:96-110` |
| contraindication | 全部 7 个：`bipolar`、`epilepsy`、`untreated_osa`、`pregnancy`、`high_fall_risk`、`drowsy_driving_job`、`parasomnia` | 契约 `:130-140`；实际对应文档是 `plan_veto_rules.md:28-34` |
| failure_tag | 全部 9 个：`path_wrong_r1`、`path_wrong_r2`、`referral_missed`、`referral_false_alarm`、`crisis_missed`、`no_isi_response`、`contraindication_violation`、`plan_infeasible`、`screen_missed` | 契约 `:142-154`；路径线索表没有失败标签清单 |

覆盖范围补充：五份草稿合看，全部 path/component/contraindication 都有出现；topic 仍缺 `medication` 的显式枚举使用，failure_tag 未显式覆盖 `path_wrong_r1/path_wrong_r2/no_isi_response`。加入 `review-queue.md` 后，20 个 topic、11 个 component、7 个 contraindication、9 个 failure_tag 全数列出。证据：`pr7/docs/review-queue.md:80-167`。这些是覆盖清单，不自动算成缺陷。

### 2.2 文档出现但契约没有的值

以下全部是提案或曾考虑的选项，未发现它们被当作已生效的 `reveal_topic` 使用；不把“待走契约流程”误报为非法数据。

| 枚举类别 | 契约之外的名称 | 出现位置／当前身份 |
|---|---|---|
| topic | `nap_habit`、`sleep_monitoring`、`light_exposure`、`bedroom_environment` | `pr7/domain/path_clues.md:168-175`，明确为建议新增 |
| topic | `parasomnia_behaviors`、`pregnancy_status` | `pr7/domain/plan_veto_rules.md:183-184`；`pr7/docs/review-queue.md:105`，建议新增 |
| topic | `caffeine`、`alcohol` | `pr7/docs/review-queue.md:86`，拆分备选；`review-decisions.md:48` 已定不拆 |
| path | 无 | 未发现超出 P1–P5 的路径值 |
| component | `nap_management`、`wind_down` | `pr7/docs/review-queue.md:123`，提案 |
| contraindication | `age_under_18`、`psychosis`、`chronic_depressive_symptoms` | `pr7/domain/plan_veto_rules.md:180-182`；`review-queue.md:141-143`，提案；年龄也允许直接读 persona.age |
| contraindication | “疑似其他睡眠障碍” | `pr7/docs/review-queue.md:144`，只有中文提议，没有确定机器值 |
| failure_tag | `referral_wrong_type`、`path_regressed`、`forbidden_wording`、`tib_below_floor`、`medication_advice` | `pr7/domain/referral_cues.md:165`；`pr7/docs/review-queue.md:151`、`:164-167`，提案；`forbidden_wording` 已存在于 veto code，但不存在于 failure_tag |
| 运行 veto code | `tib_below_floor`、`medication_advice` | `pr7/domain/plan_veto_rules.md:178-179`；映射歧义见发现 13 |

## 3. 否决规则逐条对照

阈值结果：330 分钟是全处方下限；329 返回硬违规，330 不因下限违规；age=17 且含 sleep_restriction 返回硬违规，18 不因年龄违规。禁忌集合的 7 个名字完全相同。证据：`pr7/domain/plan_veto_rules.md:28-34`、`:46`、`:60-62`；`pr6/domain/veto_rules.yaml:2-9`、`:83`；`pr6/safety/config.yaml:11`；`pr6/domain/vetoes.py:35-45`。

| 规则 | PR #7 规定 | PR #6 对照结果与证据 |
|---|---|---|
| V1 | 枚举禁忌 + sleep_restriction，硬 | 一致（契约合法输入范围内）；`vetoes.py:35-37`。每来访只计一次的计分聚合不在此函数内，未验证 |
| V2 | 未检查禁忌 + sleep_restriction，硬 | 一致；`:38-39`；实现还把缺字段/非 true 当未检查 |
| V3 | checked=true 但没问 health_conditions，硬 | 未实现，发现 1；文档 `plan_veto_rules.md:42` |
| V4 | 未问呼吸/未取得 STOP-Bang 就限制，硬 | 未实现，发现 1；文档 `:43` |
| V5 | STOP-Bang ≥3 仍限制，硬 | 未实现，发现 1；文档 `:44` |
| V6 | 自判 R1 仍限制，硬 | 未实现，发现 1；文档 `:45` |
| V7 | 年龄 <18 + sleep_restriction，硬 | 数值与级别一致；`vetoes.py:40-41`。age 可不传，实际调用方是否总传未验证 |
| V8 | 任一轮 passive + sleep_restriction，软 | 单值 passive 的级别一致；`vetoes.py:42-43`。文档聚合两轮，函数接单一 crisis_level，调用方如何聚合未验证 |
| V9 | 有禁忌却无 referral_advice 组件，硬 | 未实现，发现 2 |
| T1 | 所有处方 TIB <330，硬 | 阈值/范围一致；`vetoes.py:44-45`。实际 code=`contraindication_violation`，见发现 13 |
| T2 | 时间差与 TIB 差 >5 分钟，软 | 未实现，发现 6 |
| T3 | 候选文本降低 TIB 下限，硬 | 未实现，发现 5 |
| F1 | 药物词+指令，疑问/医生豁免，硬 | 部分覆盖，正则和豁免不同，发现 4；实际 code=`forbidden_wording` |
| F2 | 保健品建议/剂量，硬 | 仅部分词语可被 medication-advice 覆盖，发现 3 |
| F3 | 酒精助眠，硬 | 无专门对应规则，发现 3 |
| F4 | 替就医做保证，硬 | 某些措辞可能命中 W 规则，但 REASSURE 未移植，发现 3 |
| F5 | 保证效果，硬 | 部分“治愈/根治”等命中 W6，GUARANTEE 未移植，发现 3 |
| F6 | 熬通宵且非否定句，硬 | 未实现；文档内部逻辑另见发现 15 |
| W1 | “诊断”，硬 | 正则与级别一致，表格额外承诺不一致，发现 14；YAML `:23-28` |
| W2 | “治疗失眠症/治疗失眠”，硬 | 一致；YAML `:29-34` |
| W3 | 断言来访患病，硬 | 一致；YAML `:35-40` |
| W4 | “你这是……”断言，硬 | 一致；YAML `:41-46` |
| W5 | 称来访为患者/病人，硬 | 一致；YAML `:47-52` |
| W6 | 治愈类，硬 | 一致；YAML `:53-58` |
| W7 | 医疗行为口吻，硬 | 一致；YAML `:59-64` |
| W8 | 英文同类，硬 | 一致；YAML `:65-70` |
| W9 | 孤立“治疗”，软 | 一致；YAML `:71-76` |
| W10 | 孤立“失眠症”，软 | 一致；YAML `:77-82` |
| S1 | 候选跳过禁忌询问，硬 | 未实现，发现 5 |

W1–W10 的正则逐字比对一致。软违规由 `to_hard_rule_violations` 排除，符合不进入候选 hard_rule_violations 的要求（`pr6/domain/vetoes.py:62-65`）。对 agent/safety/visitor 发言、卡片、转介建议的选择和聚合属于调用方工作：现有 `check_text` 只有字符串输入，不能据此证明文档指定的全部字段已经接入。

## 4. 转介与 screening_coverage

| 项目 | 核对结果 | 证据 |
|---|---|---|
| R0 | 均表示无需转介；允许 STOP-Bang 1–2 仍低于 3，没有数值矛盾 | `pr7/domain/referral_cues.md:15`、`:140`；`pr7/AGENTS.md:48` |
| R1 | STOP-Bang ≥3 一致；0–8 范围与 schema 一致 | `referral_cues.md:16`、`:36`、`:52`；`AGENTS.md:48`；`contracts/visitor.schema.json:74-77` |
| R2 | 名称一致，无专属量表工具；至少 3/4 特征的决定已写入建议策略 | `referral_cues.md:17`、`:26`、`:93`、`:172`；`review-decisions.md:13`；`contracts/common.schema.json:350-355` |
| R2 真值/预测边界 | 生成真值仍写“典型描述”三项，预测策略为四特征至少三项，文档没有给出完整生成规则，因此不能证明二者对每种特征组合等价 | `referral_cues.md:11-18`、`:74-79`、`:93`；`docs/PLAN.md:97`。这是未验证边界，不下临床结论 |
| R3 | PHQ-9 ≥10 **或** GAD-7 ≥10 一致；0–27、0–21 范围一致 | `referral_cues.md:18`、`:107`、`:121`；`AGENTS.md:48`；`contracts/visitor.schema.json:64-72` |
| 危机与 R3 | 第 9 题 >0 进入固定安全层，不以 PHQ-9 总分 ≥10 为前提，一致 | `referral_cues.md:124-125`；`AGENTS.md:49`；`contracts/README.md:27`；`pr6/safety/layer.py:118-124` |
| 单转介标签 | 文档和契约均为单值；避免 R1/R3 重叠已落实为生成器要求 | `referral_cues.md:7`；`contracts/visitor.schema.json:25-27`；生成器执行情况未验证 |
| screen_missed | 文档所述“真值 R1/R3、未自评对应量表、也没调用工具、且判错”与契约一致 | `referral_cues.md:158`；`contracts/README.md:38` |
| screening_coverage | 草稿没有重写该指标，未发现相反公式；不能把补筛低报、R2 问话或是否判错加入该指标 | `contracts/README.md:140`；`referral_cues.md:62`、`:135`、`:158`；`docs/BACKLOG.md:54` |

`screening_coverage` 的精确定义：分母只包含转介阳性且对应量表未自评的来访，R1 看 stop_bang 未填，R3 看 **phq9 和 gad7 都未填**；分子是这些来访中调用了对应工具的人数；分母为 0 返回 null。它不要求“转介判错”，与 `screen_missed` 不同；RC-8 的“低报但补筛”原则可成立，但已填表者的这次补筛不因此计入分母。schema 仅限定 nullable 0–1，语义在 README 中（`pr7/contracts/common.schema.json:201-208`、`:266-268`；`contracts/README.md:140`）。

## 5. 危机词表与测试集

### 5.1 数量、类别和内容

| 类别 | 草稿 | PR #6 | 核对 |
|---|---:|---:|---|
| explicit E1–E7 | 7 | 7 | id、pattern 完全一致，均 active；草稿 `:34-51`，YAML `:2-30` |
| ambiguous M0–M8（含 M2a/b/c、M5a/b） | 12 | 12 | 完全一致；草稿 `:84-111`，YAML `:31-67` |
| exclude X1–X9 | 9 | 9 | 完全一致；X1–X8 真排除，X9 仅提示；草稿 `:124-156`，YAML `:68-96` |
| past_time PT1–PT4 | 4 | 4 | 完全一致；草稿 `:66-75`，YAML `:97-109` |
| 总计 | 32 | 32 | 正则逐字比对无差异 |

上表“草稿”指 `pr7/safety/crisis_lexicon_draft.md`，“YAML”指 `pr6/safety/lexicon.yaml`。

测试集共 48 条，ID 均唯一：passive 14、active 10、none 21、history 3；草稿与 JSONL 的 text、label、cssrs、difficulty 四项全部相同，**没有任何同一样例标签不同的条目**。证据：`pr7/safety/crisis_testset_draft.md:5`、`:36-59`、`:67-90`；`pr6/safety/testset.jsonl:2-49`。

history 恰为 NEG-18/19/20；POS-20 虽描述上周，但标签 active，草稿和 JSONL 均相同。history 是判断器/测试标签，不是新增的 crisis_level；映射 level=none、action=history_check 与契约一致。证据：`pr7/safety/crisis_testset_draft.md:17-26`、`:55`、`:84-86`；`pr7/contracts/common.schema.json:25-31`、`:44-60`。

### 5.2 路由与统计

- 同句 past_time 只改道、不直接判 history；“上周”不自动改道；X9 只提示、不删除命中；未命中规则仍送判断器：草稿和 PR #6 一致。证据：草稿 `:57-78`、`:149-156`、`:276`；`pr6/safety/rules.py:48-77`；`pr6/safety/layer.py:70-106`。LX-3 成功 none 的审核文字差异另见发现 10。
- 定稿草稿的 48 行规则输出、entry_ids、past_time_ids、X9 提示全部可由 PR #6 复现；2 条 explicit、26 条 ambiguous、20 条 none。证据：草稿 `:189`、`:204-251`。
- 重算四档矩阵如下，与草稿 `:193-198` 相同；去掉 X1–X8 排除后 none 误报为 17/21，保留后 9/21，也与 `:188` 一致。

| 真值 \ 规则输出 | none | history | passive | active |
|---|---:|---:|---:|---:|
| none | 12 | 0 | 9 | 0 |
| history | 1 | 0 | 2 | 0 |
| passive | 4 | 0 | 10 | 0 |
| active | 3 | 0 | 5 | 2 |

因此 17/24 当前风险覆盖、19/27 含 history 需处理覆盖、24/48 四档一致、17/28 当前风险二分类精确率、46/48 需要判断器等数字均可复算。这些是自写排错样本上的工程统计，文档已明确不代表真实临床性能（草稿 `:170-189`；测试集 `:9-13`）。

## 6. 审核结论逐项落实

### 6.1 五份草稿的 47 项

来源规则：明确用户选择覆盖起草倾向；history_check 的决定覆盖旧的 TS-8/9/10 与 LX-3；PC-1/4、RC-1/5/9 按结论保留草稿原文。旧清单的未选择备选不视为第二份最终结论。以下均以 `pr7/` 为根；每行勾选表示在目标草稿找到相应内容。

| 核对 | 项目 | 最终要求及落实证据 |
|---|---|---|
| ☑ | TS-1 | POS-11 passive；`safety/crisis_testset_draft.md:46` |
| ☑ | TS-2 | POS-13 passive；`:48` |
| ☑ | TS-3 | POS-15 active；`:50` |
| ☑ | TS-4 | POS-24 active；`:59` |
| ☑ | TS-5 | NEG-05 none；`:71` |
| ☑ | TS-6 | NEG-12 none；`:78` |
| ☑ | TS-7 | NEG-15 none，不混入朋友风险；`:81` |
| ☑ | TS-8 | NEG-18 history、下一句核验；`:84` |
| ☑ | TS-9 | NEG-19 history、下一句核验；`:85` |
| ☑ | TS-10 | NEG-20 history、下一句核验；`:86` |
| ☑ | TS-11 | NEG-22 none；`:88` |
| ☑ | TS-12 | NEG-24 none，同时写需医疗安全提示；`:90`；提示运行时实现不在本次文本落实勾选内 |
| ☑ | LX-1 | 明确档 active，past_time 例外；`safety/crisis_lexicon_draft.md:30`、`:282` |
| ☑ | LX-2 | “不想活/想死”留模糊档；`:24`、`:100-101` |
| ☐ | LX-3 | 改道和失败 passive 已落实；成功结果的 none 边界未统一，发现 10；`:13-15`、`:57`、`:284` |
| ☑ | LX-4 | 保留 X5；`:141` |
| ☑ | LX-5 | X9 仅作提示且未丢命中；`:132`、`:156`、`:270` |
| ☑ | LX-6 | 暂不加繁体、拼音缩写与谐音；`:163-166`、`:287` |
| ☑ | LX-7 | 保留明确档已有否定回看；`:45-50`、`:55`；不解释为全部分支都新增了否定识别 |
| ☑ | PC-1 | 标注保留支持强度原文，仍列强/中/弱；`domain/path_clues.md:11-19` |
| ☑ | PC-2 | mid/high 才触发 deny_first；`:26`；与契约 README 的同步缺口见发现 8 |
| ☑ | PC-3 | 脑中内容为主、换地方为辅；P2-c2 已为中；`:50`、`:118` |
| ☑ | PC-4 | 主次组合保留及资料限制写明；`:131-141` |
| ☑ | PC-5 | 次要线索 1–2 条且靠后；`:143` |
| ☑ | PC-6 | 海外会议移到 P1-c6；`:39`；P4 只余 c1–c4（`:77-80`） |
| ☑ | PC-7 | 睡前特异紧张 P3，白天也有倾向 R3；`:66`、`:123`、`:187` |
| ☑ | PV-1 | 330 分钟、全处方、未提供文献出处；`domain/plan_veto_rules.md:60-62` |
| ☑ | PV-2 | checked=false + 限制为硬；`:41` |
| ☑ | PV-3 | v0 只限制 sleep_restriction，其他组件不一刀切；`:54-56` |
| ☑ | PV-4 | STOP-Bang ≥3 或自判 R1 禁用限制；`:44-45`；代码缺口见发现 1 |
| ☑ | PV-5 | R2/R3 无枚举禁忌可用限制；`:194`；不等于豁免年龄、TIB 等其他规则 |
| ☑ | PV-6 | 18 岁下限；`:46` |
| ☑ | PV-7 | 保留职业风险并注明报告未涉及；`:33` |
| ☑ | PV-8 | passive 为软；`:47` |
| ☑ | PV-9 | 孤立“治疗”为软；`:144`、`:198` |
| ☑ | PV-10 | 孤立“失眠症”为软；`:144`、`:199` |
| ☑ | PV-11 | 保留词表，只许建议咨询医生；`:92-108`；代码豁免差异见发现 4 |
| ☑ | PV-12 | V9 升为硬；`:48`、`:162`、`:201`；代码未落实见发现 2 |
| ☑ | RC-1 | 保留四特征、通俗问法及另一个排除解释条目；`domain/referral_cues.md:70-79` |
| ☑ | RC-2 | 至少 3/4 转介、≤2 不转；`:93` |
| ☑ | RC-3 | 只列 8 个条目名称，条目阈值以原文为准；`:40` |
| ☑ | RC-4 | 憋醒伴心慌先 screen_osa，同时留意 screen_mood；`:61` |
| ☑ | RC-5 | 保留与抽筋的区分；`:100` |
| ☑ | RC-6 | 单标签、避免 R1/R3 重叠；`:7` |
| ☑ | RC-7 | R0 可有 STOP-Bang 1–2 分，比例留给算法层；`:140` |
| ☑ | RC-8 | 自评低但线索强时补调；`:62`、`:135` |
| ☑ | RC-9 | 保留示例，正式文案仍需后续审定；`:142-150`、`:179` |

文本落实统计为 **46 项已定位，1 项部分落实但口径未统一（LX-3）**。这不抹去上文发现的实现缺口。“保留原文”项未取得审前原稿，勾选依据是当前保留状态和内容存在，并非完成了审前/审后逐字 diff。

### 6.2 枚举与热线结论

| 核对 | 结论 | 落实情况与证据 |
|---|---|---|
| ☑ | caffeine_alcohol 不拆 | `review-decisions.md:48`；`domain/path_clues.md:36-37`；schema 仍用合并项 |
| ☐ | 其余新增枚举记入 BACKLOG E | 仅部分列入，发现 12 |
| ☐ | 枚举核对其余事项按倾向 | self_harm 权限未与 history 核验收口，发现 9；`schedule_shift` 定义问题（`review-queue.md:119`）本就没有明确倾向，不能把“按倾向”当作给出了定义 |
| ☑ | 保留 referral_advice 组件与文本字段 | V9 使用组件，文字建议字段仍存在；`review-queue.md:121`、`domain/plan_veto_rules.md:48`、`:74` |
| ☑ | HL-1 默认五个号码，不写 24 小时/免费拨打 | `review-decisions.md:50`；跨 PR 对照 `pr6/safety/scripts.yaml:7-30` 已列 12356、北京两号、120、110，话术不含这些服务承诺 |
| ☑ | HL-2 12356 不加区号 | `review-decisions.md:51`；`pr6/safety/scripts.yaml:20` |
| ☑ | HL-3 不单列 12355 | `review-decisions.md:52`；`pr6/safety/scripts.yaml:18-30` |
| ☑ | HL-4 每次演示前复核 | `review-decisions.md:53`；`pr6/safety/scripts.yaml:1` 已写；实际拨测执行情况未验证 |
| ☑ | 实测后才标 verified=true | `review-decisions.md:54`；`pr6/safety/scripts.yaml:21`、`:24`、`:27`、`:30` 全为 false；这不是已完成实测的证据 |

### 6.3 面向用户的禁用措辞

对五份草稿中的 agent 示例问题、转介建议、推荐替换文案，以及 PR #6 固定安全话术作文本检查，**未发现面向用户的建议文案直接使用“诊断”“治疗失眠症”“治疗失眠”**。转介示例使用“建议……评估/了解原因”（`pr7/domain/referral_cues.md:146-148`），固定安全话术见 `pr6/safety/scripts.yaml:2-17`。

检索命中集中在 `pr7/domain/plan_veto_rules.md:112-146` 的禁用词清单、正则、反例和豁免说明；这些是说明性引用，不计作违规用户建议。`docs/PLAN.md:81` 的“不是诊断分型”也是设计说明。W1 自身描述与正则不符仍单列为发现 14。

## 7. 热线、临床数字和文献的来源与 verified 状态

这里“有来源”只表示文档写出了来源名称或报告指针，**不表示本次核实了原网页、拨通了号码、确认了数字或文献结论**。`verified` 布尔字段只在 PR #6 热线配置中出现；临床数字和文献没有对应字段，统一记录为“未标注”，不能自动等同 false，也不能由“已定”推成 true。

### 7.1 所有号码（含区号示例、历史号和替代号）

下表号码均来自 `pr7/docs/review-queue.md`；默认号码另见 `review-decisions.md:50-54`。队列 `:171` 明说原报告没有拨打任何热线。

| 号码 | 文档记载的来源／身份 | 证据 | verified 状态 |
|---|---|---|---|
| 12356 | 国家卫健委国卫医政函〔2024〕259号地方转载；2025-12-26 发布会转载 | 队列 `:177` | `pr6/safety/scripts.yaml:19-21` 为 false |
| 0591-12356 | 福建“加区号选择地区”的示例，不是全国通用规则的核实结果 | `:177` | 无配置记录、未标注 |
| 010-82951332 | 北京回龙观医院运营方 2026-09-07、2026-08-08 文字；另有 2026-07-22 升级公告 | `:178` | 与下号同一配置项，`pr6/safety/scripts.yaml:22-24` 为 false |
| 800-810-1117 | 同上，文档标为座机号码 | `:178` | false，同上 |
| 400-161-9995 | 希望 24；高校 2026-09-28、2026-01-15 通知转载，官网访问超时 | `:179` | 无配置记录、未标注；文档要求实测前不入话术 |
| 51619995 | 希望 24 的 2013 年历史资料号码，无正式改号公告 | `:179` | 无配置记录、未标注 |
| 12355 | 团中央介绍页、各省服务说明 | `:180` | 无配置记录、未标注；HL-3 决定不单列 |
| 110 | 国务院 2022 年文件、地方公安说明、电信条例 | `:181` | `pr6/safety/scripts.yaml:28-30` 为 false |
| 120 | 《院前医疗急救管理办法》第二十一条/第二十五条、电信条例 | `:182` | `pr6/safety/scripts.yaml:25-27` 为 false |
| 4006-525-580 | 中国科学院大学官方页，另有 2026-04-30 高校转发 | `:183` | 无配置记录、未标注 |
| 18921889095 | 盐城医院 2026-10-13 公告，文档记为停止使用、转 12356 | `:189` | 无配置记录、未标注 |
| 0757-82667888 | 佛山医院公告，文档记为 2026-06-30 停止、转 12356 | `:190` | 无配置记录、未标注；明确未拨测 |
| 010-62715275 | 运营方 2026-07-22 公告，文档记为暂停、未找到恢复公告 | `:191` | 无配置记录、未标注 |
| 0755-25629459 | 深圳医院公告搜索抽取，原页超时，旧号停用日期未找到 | `:192` | 无配置记录、未标注 |
| 400-995-9959 | 同上 | `:192` | 无配置记录、未标注 |
| 400-9633-885 | 深圳龙华媒体二手报道，文档记为整合至 12356 | `:193` | 无配置记录、未标注 |
| 61671027 | 北京怀柔区政府 2023 年历史公告，原页 404 | `:194` | 无配置记录、未标注 |
| 61671003 | 同上 | `:194` | 无配置记录、未标注 |
| 010-88585821 | 同一历史公告中的归并目标 | `:194` | 无配置记录、未标注 |

19 个不同的号码字符串已全部列出。名单内的停用、暂停、时段、费用和运营主体状态均是文档所载信息，本次不判真伪或时效。

### 7.2 临床阈值、范围、时窗与服务数字

| 数字／陈述 | 文档来源及身份 | 证据 | 来源和 verified 状态 |
|---|---|---|---|
| TIB 下限 5.5 小时=330 分钟；备选 5 小时=300 分钟 | PV-1 人工选择／工程阈值 | `pr7/domain/plan_veto_rules.md:16`、`:60-62`、`:190`；`docs/review-queue.md:54` | 明确说已读报告没有该数值出处；verified 未标注 |
| 年龄下限 18；备选 22；18–21 的差别 | Sleepio FDA K233577 ≥18；Somryst IFU ≥22，经 2 号报告转述 | `plan_veto_rules.md:52`、`:180`；`review-queue.md:59`、`:141` | 有二级报告指针，原始资料未随导出提供；verified 未标注 |
| 来访年龄范围 16–80，含 16–17 未成年人 | 契约范围，非文献效应量 | `plan_veto_rules.md:52`；`review-queue.md:180`；`contracts/visitor.schema.json:197-200` | 已核对 schema 数值；没有临床 verified 字段 |
| STOP-Bang ≥3；范围 0–8；R0 可有 1–2 分；共 8 个条目 | 阈值来自 AGENTS，范围来自契约，1–2 来自 RC-7；条目名称凭知识 | `referral_cues.md:16`、`:32`、`:40`、`:140`；`plan_veto_rules.md:44` | 工程定义有来源；条目名称明确未核原文；verified 未标注 |
| PHQ-9 ≥10 或 GAD-7 ≥10；范围分别 0–27、0–21 | AGENTS 与契约 | `referral_cues.md:18`、`:107`、`:121` | 已核对工程定义；未提供独立临床阈值来源；verified 未标注 |
| PHQ-9 第9题 >0；逐题取值 0–3、共9题；第3题涉及睡眠 | 安全层契约；第3/9题内容经 4 号报告转述 | `referral_cues.md:124-125`、`:132`；`contracts/common.schema.json:357-365`；`contracts/visitor.schema.json:34-37` | 工程阈值已核；题目来源报告未提供；verified 未标注 |
| R2 四个核心特征，至少3个转、≤2不转；另有其他原因解释条目 | RC-1 保留转述，RC-2 人工选择 | `referral_cues.md:70-79`、`:93`；`review-queue.md:67` | 作者明确说相关原始资料不在已读报告；verified 未标注 |
| 当前风险“近1个月” | 契约及 PR #6 判断器口径 | `contracts/README.md:26`；`review-queue.md:19`；`pr6/safety/prompts/judge_zh.md:2` | 有内部定义；没有本次外部核实，verified 未标注 |
| C-SSRS 第1条 passive、第2–5条 active，及行为类别 | 4 号报告 §3.1 的英文表单释义 | `safety/crisis_testset_draft.md:17-26`、`:134`；`safety/crisis_lexicon_draft.md:301` | 有报告指针；不是官方中文译文声明，原表单未提供；verified 未标注 |
| HYPO-cn“死”在夸张词项排名第1 | 4 号报告 §6 | `safety/crisis_lexicon_draft.md:24` | 有二级来源指针，未随导出提供原研究；verified 未标注 |
| ISI 下降 >7 分、4周模拟效果、7天日记 | 项目指标/模拟设计；契约 ISI 范围0–28 | `AGENTS.md:31`；`docs/PLAN.md:104`、`:108-120`；`contracts/README.md:72-73` | 有项目定义；未见该阈值的独立文献引用；verified 未标注 |
| MEQ 16–86、DBAS-16 0–10、PSAS 16–80、SE 0–1 | 对照契约的量表/比率范围 | `contracts/README.md:72-73`；`docs/PLAN.md:86-88` | 有契约定义，没有本次外部核实；verified 未标注 |
| Pigeon 2012，RR 2.79、控制抑郁后约1.9 | BACKLOG 引 2 号报告 | `docs/BACKLOG.md:67` | 有二级来源指针，非本 PR 草稿新增结论；verified 未标注 |
| Türkmen 2026，均数比0.77 | BACKLOG 称 Nature Mental Health，并引 2 号报告 | `docs/BACKLOG.md:67` | 同上，未判断真伪；verified 未标注 |
| 12356 每日不少于18小时，不应普遍写24小时；要求2025-05-01前接通 | 国家卫健委通知/转载，文档描述 | `docs/review-queue.md:177` | 有来源名称；未拨测；配置 false |
| 北京热线24小时、全年无休，免费心理支持与通信费区别 | 运营方2026年原文的文档转述 | `review-queue.md:178` | 有来源名称；最终话术不写这些承诺；配置 false |
| 希望24的24小时/免费说法 | 高校转载，运营方网页未读到 | `review-queue.md:179` | 二手来源且限制已注明；verified 未标注 |
| 12355 河南08:30–22:30；广东/南京称24小时；福建时段和节假日差异 | 各地方说明的转述 | `review-queue.md:180` | 无统一全国口径，verified 未标注 |
| 110 的24小时；120 每天24小时；急救费用条款 | 地方公安／《院前医疗急救管理办法》／电信条例 | `review-queue.md:181-182` | 有来源名称；未外部核查；配置 false |
| 启明灯每天24小时、约30分钟应急 | 学校官方页转述 | `review-queue.md:183` | 有来源名称，verified 未标注 |
| 佛山停用时点2026-06-30 24:00 | 医院公告转述 | `review-queue.md:190` | 有来源名称，明确未拨测，verified 未标注 |

不混作真实临床统计的其他数字：次要线索 1–2 条（`path_clues.md:143`）是生成设计；时间一致性容差5分钟、模1440、T3取20字符窗口（`plan_veto_rules.md:69-70`）是工程规则；32条正则、48条样本、各标签条数与第5节全部比例是自写数据统计；故事里的几点睡觉、服药数量、楼层、三年前/五年等都是模拟原话，不是研究数值或用药建议（`crisis_testset_draft.md:9`）。这些项目都没有 clinical verified 字段。

### 7.3 文献、研究、机构标准和报告指针

| 名称 | 文档用来支持什么 | 文件:行 | 来源可追溯性／verified |
|---|---|---|---|
| Kalmbach 2022 | 试验排除双相、癫痫、未治疗OSA、慢性抑郁等；样本包含部分基线自杀意念者的陈述 | `pr7/domain/plan_veto_rules.md:28-34`、`:182`；`docs/review-queue.md:58`、`:61` | 引 2 号报告 §4.1；无完整题名/DOI/原文；未标注 |
| Nazem 2024 | 排除双相I/精神病及睡眠限制禁忌 | `plan_veto_rules.md:28`、`:181` | 引 2 号报告 §4.1；无完整题名/DOI/原文；未标注 |
| Somryst IFU | 禁忌、≥22岁、非紧急用途 | `plan_veto_rules.md:28-34`、`:52`；`safety/crisis_lexicon_draft.md:305` | 引 2 号报告 §6.1；无 IFU 原文；未标注 |
| NICE MTG70 | 其他睡眠障碍高风险者就医评估的陈述 | `plan_veto_rules.md:30`；`review-queue.md:131`、`:144` | 有标准编号，经 2 号报告 §5；未标注 |
| Sleepio／FDA K233577 | ≥18岁许可和不提供危机支持 | `plan_veto_rules.md:52`、`:180`；`safety/crisis_lexicon_draft.md:305` | 有许可编号，经 2 号报告；未标注 |
| 21 CFR 882.5801 | 特殊控制中非单独治疗/非替代药物警告 | `plan_veto_rules.md:87` | 有法规编号，经 2 号报告 §6.2；文档明确不推成所有App法规义务；未标注 |
| C-SSRS 官方英文表单 | 分档、尝试/准备行为、不再醒来的愿望 | `safety/crisis_testset_draft.md:17-26`、`:134-135`；`safety/crisis_lexicon_draft.md:301` | 仅指向 4 号报告 §3.1/§5，非官方中文译文；未标注 |
| 繁中 PHQ-9 表单 | 第3题睡眠、第9题措辞 | `domain/referral_cues.md:32`、`:132` | 经 4 号报告，无本地原表单；未标注 |
| IRLSSG 核心特征 | R2 四特征及排除其他解释 | `domain/referral_cues.md:32`、`:68-79` | 明确凭作者知识转述，不在已读报告，缺具体原始引用；未标注 |
| STOP-Bang 条目 | 八个条目名称 | `domain/referral_cues.md:32`、`:40` | 明确凭知识，阈值“以原文为准”但没有本地原文；未标注 |
| HYPO-cn | 中文夸张用语中“死”的排名 | `safety/crisis_lexicon_draft.md:24` | 引 4 号报告 §6，无原论文；未标注 |
| CSD 等中文词典研究 | 研究背景，明确没有使用词典原文 | `safety/crisis_lexicon_draft.md:28`、`:303` | 引 4 号报告 §2；词典文件/许可未核实；未标注 |
| 走饭类微博评论、PsySUICIDE、热线转写等数据 | 说明自写测试集的来源边界 | `safety/crisis_testset_draft.md:9` | 引 4 号报告 §1，文档明确不复制/回译其数据；未标注 |
| Pigeon 2012 | 睡眠与自杀关联数字 | `docs/BACKLOG.md:67` | 引 2 号报告，无原论文；未标注 |
| Türkmen 2026／Nature Mental Health | CBT-I 结束时自杀意念严重度均数比 | `docs/BACKLOG.md:67` | 引 2 号报告，无原论文；未标注 |
| ICSD-3 | PLAN 中失眠亚型的说明 | `docs/PLAN.md:81` | 只有分类名，没有具体版本原文或页码；未标注 |
| WAI-SR／D-WAI／SRS，ISI／GAD-7／MEQ／DBAS-16／PSAS | 模拟指标与展示层量表名称 | `docs/PLAN.md:87-88`、`:104`、`:114`；`contracts/README.md:72` | 这些是量表名，未提供原始量表文献；未标注 |
| `research/1114/2-sleep-suicide.md` | 睡眠、自杀、CBT-I 与产品边界的汇总来源 | `plan_veto_rules.md:16`；`crisis_testset_draft.md:138`；`docs/BACKLOG.md:67` | 两份导出均没有该报告 |
| `research/1114/3-hotlines.md` | 热线信息汇总 | `docs/review-queue.md:171` | 两份导出均没有该报告；该处明确报告没有拨打电话 |
| `research/1114/4-zh-suicide-detect.md` | 中文表达、C-SSRS、词典/数据集和证据缺口 | `referral_cues.md:32`；`crisis_testset_draft.md:134-137`；`crisis_lexicon_draft.md:301-304` | 两份导出均没有该报告 |

热线文献另已逐号列在7.1：国家卫健委通知及发布会、北京运营方公告/2020公开信、各高校通知、团中央与地方服务说明、国务院2022文件、地方公安说明、电信条例、《院前医疗急救管理办法》、启明灯学校官方页、盐城/佛山/深圳医院公告、龙华媒体、怀柔区政府公告。七份核心审查文档没有附这些原网页的可点击URL或全文；“有来源名称”与“本次可核原文”须分开记录。

## 8. 我没能验证的事项

- 临床判据、阈值、标签、禁忌机理、热线信息、法规或文献陈述本身的正确性、适用性与最新状态：不属于本次一致性审查，本次没有进行外部核实。
- 三份 `research/1114/` 报告、其原论文/表单/IFU/网页不在两个导出中，因此无法确认引文转述是否忠实，也无法核对其声称的“证据缺口”。
- 热线实际能否接通、时段、地域和通信/服务费用，以及演示前是否有人拨测；唯一可确认的机器状态是默认四个热线配置项全部 `verified: false`。代码会渲染配置中的号码（`pr6/safety/layer.py:135-139`），所以 false 也不等于运行时自动隐藏。
- `sim/`、`scoring/`、完整 `engine/` 和前端不在导出中：不能验证 deny_first 与人格绑定、R2 的真值生成、R1/R3 不重叠、screening_coverage 实算、每来访违规只计一次、history_check 下一句注入/兜底，以及全部规则是否由调用方补齐。
- 文档要求检查的 transcript/plan.cards/referral_advice/candidate after 是否都实际传入 `check_text`；V8 的“任一轮 passive”如何汇总成函数参数；age 是否总由调用方传入。
- 审前五份原稿未提供，不能验证“保留原文”的逐字不变；也不能凭“已定”证明每条临床内容曾经被专家逐条复核。RC-9 正式用户措辞仍明确留待后续审定。
- 未跑真实判断器、真实API、端到端会谈或生产环境；本次正则与最小函数复现不能证明真实场景零漏报，亦不证明全部工程集成完成。
- 远端 PR #6/#7 的最新提交、评论、批准、CI及部署状态未查询；两份导出的 `contracts/` 文件逐字一致，但这不替代远端状态证明。
