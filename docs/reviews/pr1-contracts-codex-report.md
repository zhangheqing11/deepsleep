# PR #1 独立验收报告

验收对象：当前工作区 `./pr1` 的干净导出；未查询远端 PR、未调用真实模型、未执行部署。本报告仅陈述事实、证据与验证边界，不给出是否合并的结论。下文 `contracts/...`、`AGENTS.md`、`docs/PLAN.md` 均以 `pr1/` 为根；M 编号为输入变异，E 编号为补充实验。严重度用于描述发现的影响；标为低的“未发现异常”条目是核查记录，并非缺陷。

已先读 AGENTS.md 第 3、4 节（并阅读文件其余规则）、PLAN.md 4.1 与 contracts/README.md；按 code-review-and-quality 技能进行独立静态和运行审查。历史记忆仅用于定位项目背景，没有用历史“通过”记录代替本次验证。

本次 Python 为 3.14.5，macOS arm64。原始 `make contracts` 退出码 **0**，10 个文件全为 OK。42 个独立业务输入变异中 **20 个非零退出、22 个零退出**；22 个接受项中同时包含确定的数据一致性漏检和契约未表达/语义审查边界，下面分别说明。另完成 14 项补充实验。五个 schema 的 **81 个 $ref 全部解析成功**。`jsonschema 4.26.0` 与 `4.18.0` 的原始基线和 42 个变异退出码一致。

## 发现与证据

### F01 [严重度 高] evolution 门禁接受已记录危机漏报或转介召回退化的候选，并允许它保持 chosen/committed。

证据：M21 把已选 c2 的 `val_metrics.crisis_missed` 改为 1、`crisis_recall` 改为 0；M22 把其 `referral_recall` 从基线 1 改为 0；两例均全量 10 文件 OK、退出 0。`contracts/validate.py:294`—301 仅检查硬违规数组、布尔 veto 和 ISI 主指标提升，未检查这些安全指标；run_report 的危机否决检查只在 `validate.py:264`—265，未复用于 evolution。违反 AGENTS.md:32 的“0 漏报”和“其他转介不劣于上一代”。这是**本应报错但没报错**，不是仅少测某个分支。

### F02 [严重度 高] PHQ-9 阳性可以用 level=none 的 history_check 事件冒充合格的 scale_item9 安全处置。

证据：M41 保持 A-003 工具第 9 题为 1，把同位置 `scale_item9` 事件改为 `level=none, action=history_check`，全量退出 0；`validate.py:153`—158 只查 source 与位置，不查 action/level；`session.schema.json:319`—344 又允许 history_check 搭配 none。README:27、30 和 AGENTS.md:49 要求 item9 阳性直接进入当前风险的固定安全层。普通删除事件的 M02、M42 都能检出，说明当前检查能发现“缺事件”，却不能发现“事件内容失真”。此例为**确定漏检**。

### F03 [严重度 中] 危机真值、轮次最高级别、事件动作与判断器概率之间缺少一致性检查。

证据：M26 将 visitor 的 item9 设 1 而 level 仍 none；M27 将有 passive 事件的第 2 轮 crisis_level 改 none；M28 将事件升为 active 而 action 仍 safety_check；M29 将四项 judge_probs 均设为 1；四例均退出 0。`validate.py:95`—97 只做“非 none 需风险证据”的单向检查，没做 item9 阳性的反向约束；`session.schema.json:276`—301 仅分别限制每项概率在 0–1；`validate.py:112`—178 没有对事件求每轮最高级别或按 active/passive 校验动作。依据为 README:30、95、109 的动作映射、概率及“本轮最高判定”。这些是**本应报错但没报错**的数据矛盾，不能据此推断未提供的真实安全层也存在相同错误。

### F04 [严重度 中] 跨文件检查不会拒绝不存在的 visitor 或 session，原始示例也包含 21 条缺失的 session_ref。

证据：M07 让 session 同时改为一致的 `visitor_id=A-999` 与 `session_id=run-20261115-01/A-999`，M08 让 run_report 引用 `missing/session.A-999.json`，均退出 0。`validate.py:105`—108、138—146 在 visitor 不存在时跳过检查；`validate.py:248`—279 没有读取 session_ref，`run_report.schema.json:159` 仅限定为 string。按报告所在目录解析原始 24 条 session_ref，只有 run1 的前 3 条存在，另 21 条不存在；按仓库根解析则 24 条均不存在。原始缺失项见 `examples/run_report.run1.json:163` 等，完整计数见引用扫描表。这些示例可以作为不完整 UI 占位，但当前 CLI 不能提供“关联完整”的验证保证；用户要求的两种不存在引用均为**漏检**。

### F05 [严重度 中] run_report 的内部重算不会证明来访身份、基线、分组和失败标签与原始事实一致。

证据：M25 把 isi_baseline 从 19 改为 1 而 week[0] 保持 19；M30 删除预测仍错误的 path_wrong_r1 标签；M31 制造重复 visitor_id；M32 把 run2 的 split 从 B 改 A 而明细仍全为 B；均退出 0。`validate.py:200` 从 week[0]/week[4] 重算变化，但未使用 isi_baseline；`validate.py:248` 的 visitors 参数未被使用；`validate.py:258`—262 只推导 screen_missed 标签；没有明细 ID 唯一性或分组关联检查。这些**本应报错但没报错**，会使前端显示值、反思输入和重算指标分别自洽却相互矛盾。已有的 >7 边界和数值重算确实工作：M01、M09、M10、M19 均拒绝。

### F06 [严重度 中] veto 的 passed 与 reasons 可以自相矛盾，精确率下限也没有可追溯的契约字段或实现。

证据：M24 保持 run_report `veto.passed=true` 却加入 `crisis_missed` 否决原因，退出 0；`common.schema.json:296`—333 无二者的条件关系。M23 将 c2 的 precision 改为 0 仍退出 0，`validate.py:282`—340 没有精确率下限检查；AGENTS.md:32、PLAN.md:124 要求下限，却未给具体数值，schema 也没有门禁阈值/规则版本。M24 是**确定漏检**；M23 证明下限未被验证，因文档没有指定具体阈值，不单凭“0”声称触发了某个既定数值门槛。

### F07 [严重度 中] 锁定的模拟来访 temperature=0 与冻结状态模型的来源无法从当前契约记录中核对。

证据：AGENTS.md:30、34、149、153 要求温度 0、规则状态模型及冻结参数；`session.schema.json:22`—36 的 models 只有 agent/visitor，`run_report.schema.json:42`—60 只有 agent/visitor/judge，均为封闭对象。五个 schema 没有 temperature、状态模型版本、参数摘要、结果计算来源或冻结配置标识。依从、同盟和 ISI 结果只有数值（`run_report.schema.json:129`—154），所以这些关键过程要求当前只能靠契约外代码和运行证据证明。此处是**记录能力遗漏**，不是断言实际运行温度非零或使用 LLM 计算效果。

### F08 [严重度 中] 已提交进化可以没有 diff，版本关联及真实提交信息仅有弱结构约束。

证据：M33 保持 chosen=c2、outcome=committed、to_version 与 commit 均存在，却令 diff=null，退出 0；`validate.py:328`—339 的联动不含 diff。M39 把 run_report.playbook_version 置空字符串也退出 0；`run_report.schema.json:32`、`session.schema.json:19`、`evolution.schema.json:16` 均未限制非空版本。`evolution.schema.json:344` 的 sha 仅为 string，`validate.py:282`—340 未核对 source_run_id、from/to 与报告/会谈版本，也未将 chosen 与可通过候选中的最优指标比较（PLAN.md:72 要求取最优）。此处只能证明接口接受缺失审计信息，不能验证真实 git 提交；原始示例 commit.message 本来就标为模拟提交。

### F09 [严重度 中] 修改正文与用户文案的边界约束没有由这份校验器执行。

证据：M34 在已选候选的 questioning_strategy 正文写入取消 item9 安全触发的规则；M35 在建议卡 body 加入“诊断”“治疗失眠症”；均退出 0。`common.schema.json:112` 的章节枚举排除了危机章节，但 `evolution.schema.json:187` 的 after 仍是任意字符串；`validate.py:307` 只按声明章节计算 criticality，不读正文；卡片 body 在 `session.schema.json:181` 是任意字符串。与 AGENTS.md:32、37 和 README:54 的边界相比，这是**契约外语义防线未验证**；不把通用 JSON Schema 未理解中文算作类型校验错误，也不声称真实 safety/引擎已经被绕过。该导出没有提供可检查正文的实现。

### F10 [严重度 中] CLI 的 visitor 索引硬编码为内置 examples，即使显式传入另一套 visitor/session 也不会建立正确关联。

证据：`validate.py:366`—375 始终读取 `CONTRACTS/examples/visitor.*.json`；参数 args.files 只控制待检查列表。E14 提供一对新文件，visitor 自评 ISI 从 19 改 20，session.context_scales 同步；新 visitor 返回 OK，session 却报 `context_scales 必须等于 visitor.prefilled`，退出 1。因为它实际比较的是内置旧 visitor。README:75 明确允许自报分与隐藏真值不同，所以这不是新 fixture 本身无效。此为已复现的**误报**，同时造成未知 ID 时的关联漏检（F04）。

### F11 [严重度 中] 部分数量和日记约束过弱，数值溢出也能绕过“非有限数值”拒绝逻辑。

证据：M36 把七天日记的第 2 个 day 改为 1，M37 把 plan.tib_minutes 改为 -1，均退出 0；对应 `visitor.schema.json:128`、191 只有范围/长度，`session.schema.json:143` 只有 integer。E11 把 duration_s 写为 JSON 数字 `1e400`，Python 解码成正无穷，但仍 OK；`run_report.schema.json:29` 只有 number，`validate.py:49`—54 的 parse_constant 只拦字面 NaN/Infinity（E12 的 NaN 确实失败），不拦解析合法数字时的溢出。这是**数值/领域语义漏检**。

### F12 [严重度 中] 默认 examples 为空时校验器会无输出并以成功码退出。

证据：E10 仅在副本把 examples 暂时换成空目录，运行 CLI 得到空 stdout、退出 0；`validate.py:367` 取得空 paths，376 行 failed 初始化 false，396 行直接返回 0。这不是本次原始目录状态，但会让漏打包示例的验收静默成功。

### F13 [严重度 中] PLAN 4.1 仍描述与当前封闭 schema 不同的字段名和结构。

证据：PLAN.md:174 的 session `crisis_flag` 实际为 `rounds[].crisis_level`（session.schema.json:113），`behaviors[]` 实际为 object（:206）；PLAN.md:175 的 `crisis_miss` 实际是 `crisis_missed`（common.schema.json:258）；PLAN.md:176 的 `reflector_model` 实际为 `reflector.model`（evolution.schema.json:39），候选 `diff` 实际改成 changes，只有顶层 diff（:162、363）。README 与实际 schema 对应，PLAN 接口摘要未同步。由于 additionalProperties:false，按旧摘要直接造字段不会兼容；是否为已同意的接口调整不在这份导出中。

### F14 [严重度 低] schema 加载和引用错误会以未捕获 traceback 终止，普通输入错误则有明确 FAIL 输出。

证据：E06 的损坏 JSON、E07 的缺失文件均一行 FAIL/退出 1，`validate.py:378`—384 覆盖 OSError/ValueError，且 354—356 行在结构无效时不进入业务遍历。E08 破坏 $ref、E09 破坏 type 都退出 1 但输出 traceback；`validate.py:365` 的 load_validators 及 374 行 is_valid 不在该异常处理块内。未发生错误放行，问题是诊断形态和后续文件检查中断。原始五个 schema 没有这些结构/引用错误。

### F15 [严重度 低] 依赖版本没有固定，但本次测试未发现 4.18.0 与 4.26.0 的验收行为差异。

证据：requirements.txt:1 为 `jsonschema>=4.18`，Makefile:5—8 以安装标记文件缓存环境；新机器与已有环境可能安装不同依赖图。4.26.0 与 4.18.0 在同一 Python 3.14.5、相同 referencing 0.37.0 / specifications 2025.9.1 / rpds-py 2026.9.1 / attrs 26.1.0 下，基线都通过，42 个变异的退出码逐项相同。这是有界兼容性证据，不能推出整个 >=4.18 范围或未来主版本都一致。代码用公开 Draft202012Validator + Registry，而非旧 RefResolver；自定义 date-time checker 不依赖可选格式包（validate.py:13、30—46、57—69）。官方文档确认 registry、Draft202012Validator 与显式 FormatChecker 用法：[jsonschema Schema Validation](https://python-jsonschema.readthedocs.io/en/stable/validate/)。

### F16 [严重度 低] 公共核心枚举一致，但 judge_label 是孤立定义，hard_rule_violations.code 没有枚举约束。

证据：静态递归扫描 33 个 enum，所有 81 个 $ref 可解析；P1–P5、R0–R3、crisis 三档、failure_tags、veto 均通过 common 引用复用，没有发现同一核心枚举取值分叉。`common.schema.json:53` 的 judge_label 没有任何入向 $ref；session.schema.json:282—299 把其四个名字写成概率对象字段，值名一致，但没有引用约束。`evolution.schema.json:225` 的 hard_rule_violations.code 是自由字符串，M38 的拼错 code 被接受；与 common.schema.json:307 的 veto code 枚举对比，这是未定义代码域的接口空缺，不是已有限定 enum 失效。全量枚举及使用差异见后表。

### F17 [严重度 低] 若干必填字段在示例里恒为 null，错误、回退和部分量表分支没有示范。

证据：3 个 visitor 的 secondary_path、3 个 session 的 error、3 条 human_feedback 的 score、1 个 reflector.fallback_reason 均为 null；gad7/stop_bang 的 prefilled 分支从未出现。各位置和实例计数见 required 全量覆盖表；ISI 自评的 items=null 是 schema 明确规定，不是缺陷。原始 3 个 session 都 completed，进化只有 committed、reflector.fell_back=false；没有 crisis_exit/error、active 危机流程、kept_previous 或反思器回退示例。这意味着前后端不能从现有示例验证这些状态的交互，但不代表 required 字段缺失。

### F18 [严重度 低] 本次未发现未解析引用、有效对象可塞未知字段、Draft 错配、机器绝对路径硬编码或示例中的明显个人标识/密钥。

证据：81 个引用本地 lookup 全通过；41 个显式 object 节点中 40 个直接封闭，唯一基础 result 节点由两种工具的 then 分支封闭（E04、E05 均拒绝未知字段）；五个文件第 2 行都声明 2020-12，与 validate.py:13、65、68 的 Draft202012Validator 一致。`CONTRACTS=Path(__file__).resolve().parent`（:16）相对脚本定位，E01、E02 换 CWD 都通过；显式相对文件参数按 CWD 解释是正常 CLI 行为。隐私正则及完整示例文本阅读未见姓名/联系标识、真实热线数字、密钥或绝对路径，详见隐私扫描及其局限。

## AGENTS.md 第 3 节十条锁定决定逐条对照

“满足”仅指当前契约表达及校验，不代表引擎行为已经实现；“部分满足”明确区分已表达字段和未验证的运行要求。

| 条目与原文位置 | 契约/校验位置 | 是否满足及证据 |
|---|---|---|
| 1 两轮对话，每轮 P1–P5/R0–R3，最终处方（AGENTS:28） | session.schema.json:52、104、110、131；validate.py:109、173 | 正常 completed 的两轮与非空 plan 满足，M11 缺第 2 轮失败；枚举满足。crisis_exit/error 允许 1–2 轮和 null plan，是 README:92—93 明示例外。transcript 本身无 minItems，数量约束不能证明每轮真的对话。 |
| 2 改写 playbook，run2 新 B 组并用 v1 对照（AGENTS:29） | evolution.schema.json:16、19、162；run_report.schema.json:16、32、35；examples/run_report.run2.json:4、8、9；control.json:4、8、9 | 部分满足：run1/v1/A、run2/v2/B、control/v1/B 的示例表达齐全。没有分组新颖性、同分布、同一批 B 或跨报告版本关联验证；M32 错分组接受，F04 的 B 会谈均不在导出。 |
| 3 40–50 并发、模拟来访温度 0、人格卡（AGENTS:30） | visitor.schema.json:194；run_report.schema.json:38、42；session.schema.json:22 | 人格卡存在；温度记录缺失（F07）。n_visitors 仅 >=0，三个报告示例均为 8，数量不是规模验收样本；并发是运行要求，导出不能验证。 |
| 4 4 周模拟 ISI 下降 >7，路径两轮/增幅及转介指标（AGENTS:31） | run_report.schema.json:134（长度 5）；common.schema.json:209；validate.py:195—235、253—278 | 指标结构和阈值满足：计算 week4-week0<−7；恰好 −7 错标 responder 被 M10 拒绝，M01/M09 检出数值错误；副指标会重算。isi_baseline 与轨迹/visitor 真值的一致性遗漏见 F05。 |
| 5 固定危机层不进化、零漏报、转介不退化及精确率下限（AGENTS:32） | common.schema.json:112、296；validate.py:264、282；README:54 | 部分表达、校验有明确遗漏：playbook 章节枚举无 crisis，run_report 危机否决可检出；evolution 危机/召回门禁漏检（F01），item9 事件可冒充（F02），精确率下限未定义/未检查（F06）。固定层本身不在导出中。 |
| 6 失败+人类纠正，3 份增量候选，C 门禁，通过提交否则保留（AGENTS:33） | evolution.schema.json:35、62、81、162、264、267、328、334；validate.py:284—339 | 部分满足：val_split const C，恰 3 份，op 增删改，人工 reject/timeout 能阻止 passed，chosen/commit/to_version/outcome 联动；M03/M16/M17 检出。门禁安全指标遗漏见 F01；失败来源未与 source_run 对照，正文是否增量未验证，未检验自动批注中 rejected/pending 是否被反思器实际读取。 |
| 7 依从/同盟/效果由冻结规则模型算，非 LLM 自报（AGENTS:34） | run_report.schema.json:129—154；validate.py:195 | 只记录数值并汇总重算，不记录状态模型/参数版本及来源，无法从契约验证；未提供 sim/scoring 实现。详见 F07。 |
| 8 agent/visitor ds flash，reflector Opus 5.5，异常自动回退 ds flash 并显示（AGENTS:35） | session.schema.json:22；run_report.schema.json:42；evolution.schema.json:39；examples/evolution.v1-v2.json:10 | 模型名与 fell_back/fallback_reason 字段存在，原示例为 ds-flash / claude-opus-5-5；模型字段是任意 string，未约束回退状态和原因一致性，示例没有回退分支。自动降级与看板提示属于未提供的运行/UI 证据。 |
| 9 响应式会谈页/看板，娱乐/MCP/脱敏演示版（AGENTS:36） | session.schema.json:165—190 | cards 支持 entertainment_control/smart_home/reminder；没有单独假 MCP 执行日志或脱敏事件契约。现有建议卡可供演示；响应式页面、假调用及规则脱敏实现不在导出内，无法验证。 |
| 10 非诊断边界，文案不得出现禁止措辞（AGENTS:37） | session.schema.json:79、159、181；evolution.schema.json:187；common.schema.json:314 | 原始示例文本未发现“诊断”“治疗失眠症”；forbidden_wording 否决 code 存在，但正文不扫描，M35 注入后仍通过（F09）。README:193 也注明示例人话仅为占位、正式文案另审。 |

## 枚举及 additionalProperties 的一致性解释

| 名称/场景 | 共同定义与消费者 | 事实 |
|---|---|---|
| P1–P5 | common:6；visitor:19、281；session:104；run_report:108—115 | 一致；nullable_path 在 common:187 重列 P1–P5 加 null，当前没有值漂移。 |
| R0–R3 | common:16；visitor:25、284；session:110；run_report:117—122 | 一致；common:235 的按类召回只有 R1/R2/R3，R0 是非转介，省略有语义依据。 |
| crisis 三档 / judge 四档 | common:25、53；visitor:31；session:113、258、282；run_report:123 | crisis 没有 history，judge 有 history；README:30—31 明确 history 映射 level=none + history_check，所以这不是枚举不一致。judge_label 无 $ref，见 F16。 |
| failure_tag | common:142、335；run_report:156；evolution:70 | 同一公共定义；仅 screen_missed 有完整推导约束。failure_tag 与 veto.code 是不同粒度，不要求两组取值完全相等。 |
| veto / hard_rule_violations | common:307；run_report:65；evolution:225、246 | 两个 veto 引用同一定义；hard_rule_violations.code 不限值，是独立未规定的代码域，M15 拒绝拼错的 veto，M38 接受拼错的 hard code。 |
| low/mid/high 与 low/medium/high | visitor:220、228 vs common:122 | 人格维度用 mid，改动关键度用 medium；语义不同，不认定为同一枚举漂移。 |
| safety_action | common:44；session:264 | common 允许 none，但事件 action 明确 not none；README:95 只记录非 none 动作，与设计一致。 |
| schema 封闭策略 | 四个业务根及所有实际对象 | 各有效对象均拒绝额外属性；tool result 基础节点虽未封闭，但 screen_mood/osa 的条件分支分别 additionalProperties:false（session:414、444），E04/E05 已证实。common 根是定义库，不能拿它代替四个业务 schema 验证任意数据。 |

## 原始命令及实验输出

以下保留实际输出。make 安装时出现 pip 缓存不可写警告，但依赖安装成功，校验成功；该警告不构成 make 失败原因。所有原始示例运行及 mutations 均未调用模型 API。

## 原始 make contracts

命令：在 `pr1/` 执行 `make contracts`。完整 stdout + stderr（合并捕获）：

```text
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
WARNING: The directory '~/Library/Caches/pip' or its parent directory is not owned or is not writable by the current user. The cache has been disabled. Check the permissions and owner of that directory. If executing pip with sudo, you should use sudo's -H flag.
Collecting jsonschema>=4.18 (from -r requirements.txt (line 1))
  Downloading jsonschema-4.26.0-py3-none-any.whl.metadata (7.6 kB)
Collecting attrs>=22.2.0 (from jsonschema>=4.18->-r requirements.txt (line 1))
  Downloading attrs-26.1.0-py3-none-any.whl.metadata (8.8 kB)
Collecting jsonschema-specifications>=2023.03.6 (from jsonschema>=4.18->-r requirements.txt (line 1))
  Downloading jsonschema_specifications-2025.9.1-py3-none-any.whl.metadata (2.9 kB)
Collecting referencing>=0.28.4 (from jsonschema>=4.18->-r requirements.txt (line 1))
  Downloading referencing-0.37.0-py3-none-any.whl.metadata (2.8 kB)
Collecting rpds-py>=0.25.0 (from jsonschema>=4.18->-r requirements.txt (line 1))
  Downloading rpds_py-2026.9.1-cp314-cp314-macosx_11_0_arm64.whl.metadata (4.1 kB)
Downloading jsonschema-4.26.0-py3-none-any.whl (90 kB)
Downloading attrs-26.1.0-py3-none-any.whl (67 kB)
Downloading jsonschema_specifications-2025.9.1-py3-none-any.whl (18 kB)
Downloading referencing-0.37.0-py3-none-any.whl (26 kB)
Downloading rpds_py-2026.9.1-cp314-cp314-macosx_11_0_arm64.whl (341 kB)
Installing collected packages: rpds-py, attrs, referencing, jsonschema-specifications, jsonschema

Successfully installed attrs-26.1.0 jsonschema-4.26.0 jsonschema-specifications-2025.9.1 referencing-0.37.0 rpds-py-2026.9.1

[notice] A new release of pip is available: 26.1.1 -> 26.3
[notice] To update, run: /private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/.venv/bin/python -m pip install --upgrade pip
touch .venv/.requirements-installed
.venv/bin/python contracts/validate.py
OK contracts/examples/evolution.v1-v2.json
OK contracts/examples/run_report.control.json
OK contracts/examples/run_report.run1.json
OK contracts/examples/run_report.run2.json
OK contracts/examples/session.A-001.json
OK contracts/examples/session.A-002.json
OK contracts/examples/session.A-003.json
OK contracts/examples/visitor.A-001.json
OK contracts/examples/visitor.A-002.json
OK contracts/examples/visitor.A-003.json
```

退出码：`0`。

## 输入变异测试实录

按照题目列出的方式变异输入 JSON；所有测试运行原封不动的 pr1-mut/contracts/validate.py，不删弱校验逻辑。每个用例从原始 10 个示例重新复制、只应用列出的变更，执行全量 CLI，因此不存在前一个用例污染下一个的情况。命令均为：

```sh
cd pr1-mut
../pr1/.venv/bin/python -B contracts/validate.py
```

有意保持部分联动字段一致，以排除其他检查掩盖真正漏检。非零退出只记为“检出”并显示实际报错；零退出仅表示校验器接受，是否属于确定违约见发现汇总。语义文本探针单独注明需要语义检查，不视为 jsonschema 类型检查职责。

### M01：主指标 0.5 改为 0.5001（超过 1e-6 容差）

文件：contracts/examples/run_report.run1.json。结果：**检出**；退出码 1。

```text
FAIL contracts/examples/run_report.run1.json: metrics.isi_response_rate: 实际 0.5001，重算应为 0.5
```

### M02：A-003 工具 PHQ-9 第 9 题原本为 1，删除全部 safety_events

文件：contracts/examples/session.A-003.json。结果：**检出**；退出码 1。

```text
FAIL contracts/examples/session.A-003.json: round=2 turn=5: PHQ-9 第 9 题 > 0 缺少 scale_item9 safety_event
```

### M03：c3 主指标未提升却设 passed=true

文件：contracts/examples/evolution.v1-v2.json。结果：**检出**；退出码 1。

```text
FAIL contracts/examples/evolution.v1-v2.json: c3: passed=true 需 val_metrics.isi_response_rate > baseline_val_metrics.isi_response_rate
```

### M04：P2 拼成 P22

文件：contracts/examples/visitor.A-001.json。结果：**检出**；退出码 1。

```text
FAIL contracts/examples/visitor.A-001.json: main_path: 'P22' is not one of ['P1', 'P2', 'P3', 'P4', 'P5']
```

### M05：删除 visitor 必填 seed

文件：contracts/examples/visitor.A-001.json。结果：**检出**；退出码 1。

```text
FAIL contracts/examples/visitor.A-001.json: $: 'seed' is a required property
```

### M06：封闭 persona 对象加入 unknown

文件：contracts/examples/visitor.A-001.json。结果：**检出**；退出码 1。

```text
FAIL contracts/examples/visitor.A-001.json: persona: Additional properties are not allowed ('unknown' was unexpected)
```

### M07：session 引用不存在 A-999，同时保持 session_id 一致

文件：contracts/examples/session.A-001.json。结果：**未报错（接受破坏输入）**；退出码 0。

```text
OK contracts/examples/evolution.v1-v2.json
OK contracts/examples/run_report.control.json
OK contracts/examples/run_report.run1.json
OK contracts/examples/run_report.run2.json
OK contracts/examples/session.A-001.json
OK contracts/examples/session.A-002.json
OK contracts/examples/session.A-003.json
OK contracts/examples/visitor.A-001.json
OK contracts/examples/visitor.A-002.json
OK contracts/examples/visitor.A-003.json
```

### M08：run_report.session_ref 指向不存在文件

文件：contracts/examples/run_report.run1.json。结果：**未报错（接受破坏输入）**；退出码 0。

```text
OK contracts/examples/evolution.v1-v2.json
OK contracts/examples/run_report.control.json
OK contracts/examples/run_report.run1.json
OK contracts/examples/run_report.run2.json
OK contracts/examples/session.A-001.json
OK contracts/examples/session.A-002.json
OK contracts/examples/session.A-003.json
OK contracts/examples/visitor.A-001.json
OK contracts/examples/visitor.A-002.json
OK contracts/examples/visitor.A-003.json
```

### M09：run_report isi_change -9 改为 -8

文件：contracts/examples/run_report.run1.json。结果：**检出**；退出码 1。

```text
FAIL contracts/examples/run_report.run1.json: per_visitor[0].isi_change: 实际 -8，重算应为 -9
```

### M10：恰好下降 7 分的 A-005 错标 responder=true

文件：contracts/examples/run_report.run1.json。结果：**检出**；退出码 1。

```text
FAIL contracts/examples/run_report.run1.json: per_visitor[4].responder 必须等于 (isi_change < -7)
```

### M11：completed 会谈删除第 2 轮

文件：contracts/examples/session.A-001.json。结果：**检出**；退出码 1。

```text
FAIL contracts/examples/session.A-001.json: status=completed 时 rounds 必须有 2 项
```

### M12：第 1 轮 turn 2 改成 1，造成重复

文件：contracts/examples/session.A-001.json。结果：**检出**；退出码 1。

```text
FAIL contracts/examples/session.A-001.json: rounds[0]: transcript + tool_calls 的 turn 必须从 1 连续递增且不重复
```

### M13：screen_osa 真值 4 改成 5

文件：contracts/examples/session.A-002.json。结果：**检出**；退出码 1。

```text
FAIL contracts/examples/session.A-002.json: tool_calls[0].result.stop_bang 必须等于 visitor.indices.stop_bang
```

### M14：safety 枚举 passive 拼错

文件：contracts/examples/session.A-003.json。结果：**检出**；退出码 1。

```text
FAIL contracts/examples/session.A-003.json: safety_events.0.level: 'pasive' is not one of ['none', 'passive', 'active']
```

### M15：veto code 拼错

文件：contracts/examples/evolution.v1-v2.json。结果：**检出**；退出码 1。

```text
FAIL contracts/examples/evolution.v1-v2.json: candidates.0.veto.reasons.0.code: 'contraindication_violaton' is not one of ['crisis_missed', 'referral_recall_regressed', 'referral_precision_floor', 'contraindication_violation', 'forbidden_wording']
```

### M16：human 来源却 status=pending

文件：contracts/examples/evolution.v1-v2.json。结果：**检出**；退出码 1。

```text
FAIL contracts/examples/evolution.v1-v2.json: human_feedback[0]: source=human 时 status 必须为 approved
```

### M17：候选从三份删为两份

文件：contracts/examples/evolution.v1-v2.json。结果：**检出**；退出码 1。

```text
FAIL contracts/examples/evolution.v1-v2.json: candidates: [{'id': 'c1', 'summary': '尝试统一卧床窗口，被禁忌规则拦下，未运行验证。', 'changes': [{'id': 'c1-plan-1', 'op': 'add', 'section': 'plan_rules', 'before': None, 'after': '即使存在未处理的呼吸暂停风险，也统一安排五小时卧床窗口。', 'reason': '候选尝试以统一窗口简化安排，但该增量被固定禁忌规则拦下。', 'criticality_rule': 'high', 'criticality_self': 'high', 'criticality': 'high'}], 'hard_rule_violations': [{'code': 'contraindication_violation', 'change_id': 'c1-plan-1', 'message': '对未处理呼吸暂停风险人群建议睡眠限制，违反固定禁忌规则。'}], 'val_metrics': None, 'veto': {'passed': False, 'reasons': [{'code': 'contraindication_violation', 'message': '候选包含禁忌人群睡眠限制建议。'}]}, 'passed': False}, {'id': 'c2', 'summary': '补充床外困意、自然节律提问与未自评来访的补筛策略，C 组有效率由上一代 0.50 提升至 0.75。', 'changes': [{'id': 'c2-path-1', 'op': 'add', 'section': 'path_discrimination', 'before': None, 'after': '先问是否在沙发上反而能睡着；如在床外容易困、回床后清醒，优先考虑 P2。', 'reason': 'A-001 第一轮遗漏床外困意线索；需区分作息问题与床上清醒。', 'criticality_rule': 'medium', 'criticality_self': 'medium', 'criticality': 'medium'}, {'id': 'c2-question-1', 'op': 'add', 'section': 'questioning_strategy', 'before': None, 'after': '当作息推迟时，先询问自由日自然入睡和醒来的时间，再询问倒班安排。', 'reason': 'A-002 被归入 P1；先了解自然节律可减少把 P4 当作普通作息问题。', 'criticality_rule': 'low', 'criticality_self': 'medium', 'criticality': 'medium'}, {'id': 'c2-question-2', 'op': 'add', 'section': 'questioning_strategy', 'before': None, 'after': '没填 STOP-Bang 且提到打鼾或白天困的来访，先调 screen_osa；没填 PHQ-9 和 GAD-7 且提到情绪低落或焦虑的来访，先调 screen_mood。', 'reason': 'A-008 未自评且未补筛，导致转介漏报；将补筛提问扩展到呼吸与情绪线索。', 'criticality_rule': 'low', 'criticality_self': 'low', 'criticality': 'low'}], 'hard_rule_violations': [], 'val_metrics': {'isi_response_rate': 0.75, 'mean_isi_change': -8.5, 'path_acc_r1': 0.5, 'path_acc_r2': 0.875, 'path_acc_gain': 0.375, 'referral_recall': 1.0, 'referral_precision': 1.0, 'referral_recall_by_label': {'R1': 1.0, 'R2': 1.0, 'R3': 1.0}, 'crisis_recall': 1.0, 'crisis_missed': 0, 'contraindication_violations': 0, 'screening_coverage': 1.0}, 'veto': {'passed': True, 'reasons': []}, 'passed': True}] is too short
```

### M18：run created_at 移除时区

文件：contracts/examples/run_report.run1.json。结果：**检出**；退出码 1。

```text
FAIL contracts/examples/run_report.run1.json: created_at: '2026-11-15T09:00:00' is not a 'date-time'
```

### M19：run n_visitors 与明细长度不符

文件：contracts/examples/run_report.run1.json。结果：**检出**；退出码 1。

```text
FAIL contracts/examples/run_report.run1.json: n_visitors=9 与 per_visitor 长度 8 不符
```

### M20：run 危机漏报数设 1 但 veto.passed=true

文件：contracts/examples/run_report.run1.json。结果：**检出**；退出码 1。

```text
FAIL contracts/examples/run_report.run1.json: metrics.crisis_missed > 0 时 veto.passed 必须为 false; metrics.crisis_missed: 实际 1，重算应为 0
```

### M21：c2 验证集危机漏报=1、召回=0，却仍 passed/veto=true

文件：contracts/examples/evolution.v1-v2.json。结果：**未报错（接受破坏输入）**；退出码 0。

```text
OK contracts/examples/evolution.v1-v2.json
OK contracts/examples/run_report.control.json
OK contracts/examples/run_report.run1.json
OK contracts/examples/run_report.run2.json
OK contracts/examples/session.A-001.json
OK contracts/examples/session.A-002.json
OK contracts/examples/session.A-003.json
OK contracts/examples/visitor.A-001.json
OK contracts/examples/visitor.A-002.json
OK contracts/examples/visitor.A-003.json
```

### M22：c2 转介召回从基线 1 降为 0，门禁仍通过

文件：contracts/examples/evolution.v1-v2.json。结果：**未报错（接受破坏输入）**；退出码 0。

```text
OK contracts/examples/evolution.v1-v2.json
OK contracts/examples/run_report.control.json
OK contracts/examples/run_report.run1.json
OK contracts/examples/run_report.run2.json
OK contracts/examples/session.A-001.json
OK contracts/examples/session.A-002.json
OK contracts/examples/session.A-003.json
OK contracts/examples/visitor.A-001.json
OK contracts/examples/visitor.A-002.json
OK contracts/examples/visitor.A-003.json
```

### M23：c2 转介精确率降为 0，门禁仍通过

文件：contracts/examples/evolution.v1-v2.json。结果：**未报错（接受破坏输入）**；退出码 0。

```text
OK contracts/examples/evolution.v1-v2.json
OK contracts/examples/run_report.control.json
OK contracts/examples/run_report.run1.json
OK contracts/examples/run_report.run2.json
OK contracts/examples/session.A-001.json
OK contracts/examples/session.A-002.json
OK contracts/examples/session.A-003.json
OK contracts/examples/visitor.A-001.json
OK contracts/examples/visitor.A-002.json
OK contracts/examples/visitor.A-003.json
```

### M24：run veto.passed=true 却有 crisis_missed 否决原因

文件：contracts/examples/run_report.run1.json。结果：**未报错（接受破坏输入）**；退出码 0。

```text
OK contracts/examples/evolution.v1-v2.json
OK contracts/examples/run_report.control.json
OK contracts/examples/run_report.run1.json
OK contracts/examples/run_report.run2.json
OK contracts/examples/session.A-001.json
OK contracts/examples/session.A-002.json
OK contracts/examples/session.A-003.json
OK contracts/examples/visitor.A-001.json
OK contracts/examples/visitor.A-002.json
OK contracts/examples/visitor.A-003.json
```

### M25：isi_baseline 19 改为 1，isi_week[0] 保持 19

文件：contracts/examples/run_report.run1.json。结果：**未报错（接受破坏输入）**；退出码 0。

```text
OK contracts/examples/evolution.v1-v2.json
OK contracts/examples/run_report.control.json
OK contracts/examples/run_report.run1.json
OK contracts/examples/run_report.run2.json
OK contracts/examples/session.A-001.json
OK contracts/examples/session.A-002.json
OK contracts/examples/session.A-003.json
OK contracts/examples/visitor.A-001.json
OK contracts/examples/visitor.A-002.json
OK contracts/examples/visitor.A-003.json
```

### M26：visitor PHQ-9 item9=1 却 crisis.level=none

文件：contracts/examples/visitor.A-001.json。结果：**未报错（接受破坏输入）**；退出码 0。

```text
OK contracts/examples/evolution.v1-v2.json
OK contracts/examples/run_report.control.json
OK contracts/examples/run_report.run1.json
OK contracts/examples/run_report.run2.json
OK contracts/examples/session.A-001.json
OK contracts/examples/session.A-002.json
OK contracts/examples/session.A-003.json
OK contracts/examples/visitor.A-001.json
OK contracts/examples/visitor.A-002.json
OK contracts/examples/visitor.A-003.json
```

### M27：session round 2 标 none，与 passive 安全事件矛盾

文件：contracts/examples/session.A-003.json。结果：**未报错（接受破坏输入）**；退出码 0。

```text
OK contracts/examples/evolution.v1-v2.json
OK contracts/examples/run_report.control.json
OK contracts/examples/run_report.run1.json
OK contracts/examples/run_report.run2.json
OK contracts/examples/session.A-001.json
OK contracts/examples/session.A-002.json
OK contracts/examples/session.A-003.json
OK contracts/examples/visitor.A-001.json
OK contracts/examples/visitor.A-002.json
OK contracts/examples/visitor.A-003.json
```

### M28：passive 安全事件改 active，但 action 仍 safety_check

文件：contracts/examples/session.A-003.json。结果：**未报错（接受破坏输入）**；退出码 0。

```text
OK contracts/examples/evolution.v1-v2.json
OK contracts/examples/run_report.control.json
OK contracts/examples/run_report.run1.json
OK contracts/examples/run_report.run2.json
OK contracts/examples/session.A-001.json
OK contracts/examples/session.A-002.json
OK contracts/examples/session.A-003.json
OK contracts/examples/visitor.A-001.json
OK contracts/examples/visitor.A-002.json
OK contracts/examples/visitor.A-003.json
```

### M29：judge_probs 四项各为 1，总和为 4

文件：contracts/examples/session.A-001.json。结果：**未报错（接受破坏输入）**；退出码 0。

```text
OK contracts/examples/evolution.v1-v2.json
OK contracts/examples/run_report.control.json
OK contracts/examples/run_report.run1.json
OK contracts/examples/run_report.run2.json
OK contracts/examples/session.A-001.json
OK contracts/examples/session.A-002.json
OK contracts/examples/session.A-003.json
OK contracts/examples/visitor.A-001.json
OK contracts/examples/visitor.A-002.json
OK contracts/examples/visitor.A-003.json
```

### M30：删除 A-001 错误路径 failure_tag，预测仍错

文件：contracts/examples/run_report.run1.json。结果：**未报错（接受破坏输入）**；退出码 0。

```text
OK contracts/examples/evolution.v1-v2.json
OK contracts/examples/run_report.control.json
OK contracts/examples/run_report.run1.json
OK contracts/examples/run_report.run2.json
OK contracts/examples/session.A-001.json
OK contracts/examples/session.A-002.json
OK contracts/examples/session.A-003.json
OK contracts/examples/visitor.A-001.json
OK contracts/examples/visitor.A-002.json
OK contracts/examples/visitor.A-003.json
```

### M31：run_report 将第二行 visitor_id 改为 A-001，造成重复

文件：contracts/examples/run_report.run1.json。结果：**未报错（接受破坏输入）**；退出码 0。

```text
OK contracts/examples/evolution.v1-v2.json
OK contracts/examples/run_report.control.json
OK contracts/examples/run_report.run1.json
OK contracts/examples/run_report.run2.json
OK contracts/examples/session.A-001.json
OK contracts/examples/session.A-002.json
OK contracts/examples/session.A-003.json
OK contracts/examples/visitor.A-001.json
OK contracts/examples/visitor.A-002.json
OK contracts/examples/visitor.A-003.json
```

### M32：run2 的 split B 改为 A，明细仍为 B

文件：contracts/examples/run_report.run2.json。结果：**未报错（接受破坏输入）**；退出码 0。

```text
OK contracts/examples/evolution.v1-v2.json
OK contracts/examples/run_report.control.json
OK contracts/examples/run_report.run1.json
OK contracts/examples/run_report.run2.json
OK contracts/examples/session.A-001.json
OK contracts/examples/session.A-002.json
OK contracts/examples/session.A-003.json
OK contracts/examples/visitor.A-001.json
OK contracts/examples/visitor.A-002.json
OK contracts/examples/visitor.A-003.json
```

### M33：committed evolution 把 diff 置 null

文件：contracts/examples/evolution.v1-v2.json。结果：**未报错（接受破坏输入）**；退出码 0。

```text
OK contracts/examples/evolution.v1-v2.json
OK contracts/examples/run_report.control.json
OK contracts/examples/run_report.run1.json
OK contracts/examples/run_report.run2.json
OK contracts/examples/session.A-001.json
OK contracts/examples/session.A-002.json
OK contracts/examples/session.A-003.json
OK contracts/examples/visitor.A-001.json
OK contracts/examples/visitor.A-002.json
OK contracts/examples/visitor.A-003.json
```

### M34：将 c2 增量正文改为修改危机规则，声明章节仍 questioning_strategy

文件：contracts/examples/evolution.v1-v2.json。结果：**未报错（接受破坏输入）**；退出码 0。

```text
OK contracts/examples/evolution.v1-v2.json
OK contracts/examples/run_report.control.json
OK contracts/examples/run_report.run1.json
OK contracts/examples/run_report.run2.json
OK contracts/examples/session.A-001.json
OK contracts/examples/session.A-002.json
OK contracts/examples/session.A-003.json
OK contracts/examples/visitor.A-001.json
OK contracts/examples/visitor.A-002.json
OK contracts/examples/visitor.A-003.json
```

### M35：在会谈建议卡 body 加入禁止措辞

文件：contracts/examples/session.A-001.json。结果：**未报错（接受破坏输入）**；退出码 0。

```text
OK contracts/examples/evolution.v1-v2.json
OK contracts/examples/run_report.control.json
OK contracts/examples/run_report.run1.json
OK contracts/examples/run_report.run2.json
OK contracts/examples/session.A-001.json
OK contracts/examples/session.A-002.json
OK contracts/examples/session.A-003.json
OK contracts/examples/visitor.A-001.json
OK contracts/examples/visitor.A-002.json
OK contracts/examples/visitor.A-003.json
```

### M36：visitor diary 第 2 天 day 改成 1（重复日）

文件：contracts/examples/visitor.A-001.json。结果：**未报错（接受破坏输入）**；退出码 0。

```text
OK contracts/examples/evolution.v1-v2.json
OK contracts/examples/run_report.control.json
OK contracts/examples/run_report.run1.json
OK contracts/examples/run_report.run2.json
OK contracts/examples/session.A-001.json
OK contracts/examples/session.A-002.json
OK contracts/examples/session.A-003.json
OK contracts/examples/visitor.A-001.json
OK contracts/examples/visitor.A-002.json
OK contracts/examples/visitor.A-003.json
```

### M37：session plan 卧床分钟数设为 -1

文件：contracts/examples/session.A-001.json。结果：**未报错（接受破坏输入）**；退出码 0。

```text
OK contracts/examples/evolution.v1-v2.json
OK contracts/examples/run_report.control.json
OK contracts/examples/run_report.run1.json
OK contracts/examples/run_report.run2.json
OK contracts/examples/session.A-001.json
OK contracts/examples/session.A-002.json
OK contracts/examples/session.A-003.json
OK contracts/examples/visitor.A-001.json
OK contracts/examples/visitor.A-002.json
OK contracts/examples/visitor.A-003.json
```

### M38：hard_rule_violations.code 拼错

文件：contracts/examples/evolution.v1-v2.json。结果：**未报错（接受破坏输入）**；退出码 0。

```text
OK contracts/examples/evolution.v1-v2.json
OK contracts/examples/run_report.control.json
OK contracts/examples/run_report.run1.json
OK contracts/examples/run_report.run2.json
OK contracts/examples/session.A-001.json
OK contracts/examples/session.A-002.json
OK contracts/examples/session.A-003.json
OK contracts/examples/visitor.A-001.json
OK contracts/examples/visitor.A-002.json
OK contracts/examples/visitor.A-003.json
```

### M39：run_report playbook_version 变为空字符串

文件：contracts/examples/run_report.run1.json。结果：**未报错（接受破坏输入）**；退出码 0。

```text
OK contracts/examples/evolution.v1-v2.json
OK contracts/examples/run_report.control.json
OK contracts/examples/run_report.run1.json
OK contracts/examples/run_report.run2.json
OK contracts/examples/session.A-001.json
OK contracts/examples/session.A-002.json
OK contracts/examples/session.A-003.json
OK contracts/examples/visitor.A-001.json
OK contracts/examples/visitor.A-002.json
OK contracts/examples/visitor.A-003.json
```

### M40：visitor secondary_path 等于 main_path

文件：contracts/examples/visitor.A-001.json。结果：**检出**；退出码 1。

```text
FAIL contracts/examples/visitor.A-001.json: secondary_path 不能等于 main_path
```

### M41：删除已有 scale_item9，改用同位置 history_check + level none 冒充

文件：contracts/examples/session.A-003.json。结果：**未报错（接受破坏输入）**；退出码 0。

```text
OK contracts/examples/evolution.v1-v2.json
OK contracts/examples/run_report.control.json
OK contracts/examples/run_report.run1.json
OK contracts/examples/run_report.run2.json
OK contracts/examples/session.A-001.json
OK contracts/examples/session.A-002.json
OK contracts/examples/session.A-003.json
OK contracts/examples/visitor.A-001.json
OK contracts/examples/visitor.A-002.json
OK contracts/examples/visitor.A-003.json
```

### M42：自评 PHQ-9 item9 从 0 改 1，总分同步，visitor/context 一致但删 safety

文件：contracts/examples/session.A-001.json, contracts/examples/visitor.A-001.json。结果：**检出**；退出码 1。

```text
FAIL contracts/examples/session.A-001.json: round=1 turn=0: PHQ-9 第 9 题 > 0 缺少 scale_item9 safety_event
```

本批共 42 个独立输入变异：非零退出 20 个，零退出 22 个。每例均运行全部 10 个文件。测试结束已把副本的示例恢复为原始内容。

## 依赖下限实测环境安装

命令：`pr1/.venv/bin/python -m venv pr1-mut/.venv418`

```text
```

退出码：0。
命令：`pr1-mut/.venv418/bin/python -m pip install jsonschema==4.18.0`

```text
WARNING: The directory '~/Library/Caches/pip' or its parent directory is not owned or is not writable by the current user. The cache has been disabled. Check the permissions and owner of that directory. If executing pip with sudo, you should use sudo's -H flag.
Collecting jsonschema==4.18.0
  Downloading jsonschema-4.18.0-py3-none-any.whl.metadata (10 kB)
Collecting attrs>=22.2.0 (from jsonschema==4.18.0)
  Downloading attrs-26.1.0-py3-none-any.whl.metadata (8.8 kB)
Collecting jsonschema-specifications>=2023.03.6 (from jsonschema==4.18.0)
  Downloading jsonschema_specifications-2025.9.1-py3-none-any.whl.metadata (2.9 kB)
Collecting referencing>=0.28.4 (from jsonschema==4.18.0)
  Downloading referencing-0.37.0-py3-none-any.whl.metadata (2.8 kB)
Collecting rpds-py>=0.7.1 (from jsonschema==4.18.0)
  Downloading rpds_py-2026.9.1-cp314-cp314-macosx_11_0_arm64.whl.metadata (4.1 kB)
Downloading jsonschema-4.18.0-py3-none-any.whl (81 kB)
Downloading attrs-26.1.0-py3-none-any.whl (67 kB)
Downloading jsonschema_specifications-2025.9.1-py3-none-any.whl (18 kB)
Downloading referencing-0.37.0-py3-none-any.whl (26 kB)
Downloading rpds_py-2026.9.1-cp314-cp314-macosx_11_0_arm64.whl (341 kB)
Installing collected packages: rpds-py, attrs, referencing, jsonschema-specifications, jsonschema

Successfully installed attrs-26.1.0 jsonschema-4.18.0 jsonschema-specifications-2025.9.1 referencing-0.37.0 rpds-py-2026.9.1

[notice] A new release of pip is available: 26.1.1 -> 26.3
[notice] To update, run: /private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1-mut/.venv418/bin/python -m pip install --upgrade pip
```

退出码：0。

## 五个 schema 的全量结构扫描

扫描方式：对五个 schema 调用 Draft202012Validator.check_schema；递归遍历每个 $ref，在包含五个 $id 的本地 referencing.Registry 中逐一 lookup，包含示例未走到的分支。未依赖网络获取 schema。

| schema | Draft check | $ref 个数 / 解析失败 | 显式 object 节点 / 封闭节点 |
|---|---|---|---|
| common.schema.json | 通过（2020-12） | 13 / 0 | 8 / 8 |
| evolution.schema.json | 通过（2020-12） | 11 / 0 | 10 / 10 |
| run_report.schema.json | 通过（2020-12） | 18 / 0 | 4 / 4 |
| session.schema.json | 通过（2020-12） | 21 / 0 | 13 / 12 |
| visitor.schema.json | 通过（2020-12） | 18 / 0 | 6 / 6 |

总计 81 个 $ref 全部本地解析成功。四个业务顶层均 additionalProperties:false。common 顶层仅为 $defs 类型库，不是业务对象。以下为唯一未直接关闭的显式 object 节点：

- contracts/session.schema.json:367 /properties/tool_calls/items/properties/result：additionalProperties=omitted；须结合条件子 schema 判断。

### 全部 enum 定义清单

以下列出每个 enum 的定义位置（共享类型的使用方通过 $ref 复用，不代表复制定义）；单独的 const 不计为 enum。

| 位置 | JSON Pointer | 值 |
|---|---|---|
| contracts/common.schema.json:96 | /$defs/component | ["sleep_hygiene", "fixed_risetime", "stimulus_control", "sleep_restriction", "cognitive_restructuring", "worry_time", "relaxation", "light_timing", "schedule_shift", "digital_curfew", "referral_advice"] |
| contracts/common.schema.json:130 | /$defs/contraindication | ["bipolar", "epilepsy", "untreated_osa", "pregnancy", "high_fall_risk", "drowsy_driving_job", "parasomnia"] |
| contracts/common.schema.json:25 | /$defs/crisis_level | ["none", "passive", "active"] |
| contracts/common.schema.json:122 | /$defs/criticality | ["low", "medium", "high"] |
| contracts/common.schema.json:142 | /$defs/failure_tag | ["path_wrong_r1", "path_wrong_r2", "referral_missed", "referral_false_alarm", "crisis_missed", "no_isi_response", "contraindication_violation", "plan_infeasible", "screen_missed"] |
| contracts/common.schema.json:53 | /$defs/judge_label | ["none", "history", "passive", "active"] |
| contracts/common.schema.json:62 | /$defs/judge_status | ["ok", "timeout", "error", "skipped"] |
| contracts/common.schema.json:187 | /$defs/nullable_path | ["P1", "P2", "P3", "P4", "P5", null] |
| contracts/common.schema.json:6 | /$defs/path | ["P1", "P2", "P3", "P4", "P5"] |
| contracts/common.schema.json:112 | /$defs/playbook_section | ["communication_style", "questioning_strategy", "path_discrimination", "plan_rules", "referral_rules"] |
| contracts/common.schema.json:16 | /$defs/referral | ["R0", "R1", "R2", "R3"] |
| contracts/common.schema.json:44 | /$defs/safety_action | ["none", "history_check", "safety_check", "crisis_protocol"] |
| contracts/common.schema.json:33 | /$defs/safety_source | ["none", "rule_explicit", "rule_ambiguous", "judge", "rule_ambiguous+judge", "scale_item9"] |
| contracts/common.schema.json:341 | /$defs/scale | ["isi", "phq9", "gad7", "stop_bang"] |
| contracts/common.schema.json:169 | /$defs/split | ["A", "B", "C", "offline", "sample"] |
| contracts/common.schema.json:350 | /$defs/tool | ["screen_mood", "screen_osa"] |
| contracts/common.schema.json:71 | /$defs/topic | ["schedule_regularity", "weekend_catchup", "caffeine_alcohol", "bed_wakefulness", "sleep_elsewhere", "worry_rumination", "fear_of_sleeplessness", "chronotype", "shift_work", "screen_in_bed", "revenge_bedtime", "snoring_breathing", "daytime_sleepiness", "leg_discomfort", "mood", "anxiety", "self_harm", "medication", "life_constraints", "health_conditions"] |
| contracts/common.schema.json:307 | /$defs/veto/properties/reasons/items/properties/code | ["crisis_missed", "referral_recall_regressed", "referral_precision_floor", "contraindication_violation", "forbidden_wording"] |
| contracts/evolution.schema.json:170 | /properties/candidates/items/properties/changes/items/properties/op | ["add", "modify", "delete"] |
| contracts/evolution.schema.json:151 | /properties/candidates/items/properties/id | ["c1", "c2", "c3"] |
| contracts/evolution.schema.json:89 | /properties/human_feedback/items/properties/kind | ["correction", "score", "demonstration"] |
| contracts/evolution.schema.json:97 | /properties/human_feedback/items/properties/source | ["human", "auto_critic"] |
| contracts/evolution.schema.json:104 | /properties/human_feedback/items/properties/status | ["approved", "rejected", "edited", "pending", "timeout"] |
| contracts/evolution.schema.json:275 | /properties/human_review/items/properties/decision | ["approve", "reject", "timeout"] |
| contracts/evolution.schema.json:25 | /properties/outcome | ["committed", "kept_previous"] |
| contracts/run_report.schema.json:16 | /properties/role | ["run1", "run2", "control", "validation", "offline"] |
| contracts/session.schema.json:170 | /properties/plan/properties/cards/items/properties/type | ["entertainment_control", "smart_home", "reminder"] |
| contracts/session.schema.json:71 | /properties/rounds/items/properties/transcript/items/properties/speaker | ["agent", "visitor", "safety"] |
| contracts/session.schema.json:38 | /properties/status | ["completed", "crisis_exit", "error"] |
| contracts/visitor.schema.json:220 | /properties/persona/properties/defensiveness | ["low", "mid", "high"] |
| contracts/visitor.schema.json:228 | /properties/persona/properties/emotionality | ["low", "mid", "high"] |
| contracts/visitor.schema.json:213 | /properties/persona/properties/expressiveness | ["brief", "verbose"] |
| contracts/visitor.schema.json:202 | /properties/persona/properties/gender | ["female", "male", "other"] |

公共定义无入向 $ref：judge_label。其余 common 定义至少有一处引用。

### required 字段的示例覆盖

按实际可匹配的 oneOf/anyOf/if 分支展开四种业务示例（3 visitor、3 session、3 run_report、1 evolution）；common 共享字段合并计数。空值严格指 null、空字符串、空数组或空对象，不把数值 0 或 false 算为空。下表穷举“出现但恒为空”与“所属分支无实例”的 required 字段；恒空不等同契约错误。

| 位置 | 字段 / 所属节点 | 观察次数 | 结果 |
|---|---|---|---|
| contracts/common.schema.json:386 | /$defs/prefilled/items/oneOf/0 → items | 2 | 恒为空：null |
| contracts/common.schema.json:430 | /$defs/prefilled/items/oneOf/2 → items | 0 | 分支未使用 |
| contracts/common.schema.json:430 | /$defs/prefilled/items/oneOf/2 → reported_score | 0 | 分支未使用 |
| contracts/common.schema.json:430 | /$defs/prefilled/items/oneOf/2 → scale | 0 | 分支未使用 |
| contracts/common.schema.json:452 | /$defs/prefilled/items/oneOf/3 → items | 0 | 分支未使用 |
| contracts/common.schema.json:452 | /$defs/prefilled/items/oneOf/3 → reported_score | 0 | 分支未使用 |
| contracts/common.schema.json:452 | /$defs/prefilled/items/oneOf/3 → scale | 0 | 分支未使用 |
| contracts/evolution.schema.json:134 | /properties/human_feedback/items → score | 3 | 恒为空：null |
| contracts/evolution.schema.json:55 | /properties/reflector → fallback_reason | 1 | 恒为空：null |
| contracts/session.schema.json:453 | / → error | 3 | 恒为空：null |
| contracts/visitor.schema.json:307 | / → secondary_path | 3 | 恒为空：null |

已被实例化的对象没有缺失 required 字段；JSON Schema 校验已覆盖该检查。未使用分支中的必填项不等于示例违反 required。

### jsonschema 4.18.0 原始示例验证

命令：`cd pr1-mut && .venv418/bin/python -B contracts/validate.py`

```text
Traceback (most recent call last):
  File "/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1-mut/contracts/validate.py", line 13, in <module>
    from jsonschema import Draft202012Validator, FormatChecker
ModuleNotFoundError: No module named 'jsonschema'
```

退出码：1。

### 4.18.0 修正执行路径后的变异对照

先前测试驱动对 Python 可执行文件使用 resolve()，跟随 venv 符号链接到系统 Python，导致 ModuleNotFoundError；该结果是测试驱动问题，不能归因于 PR 或依赖版本。已改用 absolute() 保留 venv 入口，下面为有效结果。

M01 rc=1

M02 rc=1

M03 rc=1

M04 rc=1

M05 rc=1

M06 rc=1

M07 rc=0

M08 rc=0

M09 rc=1

M10 rc=1

M11 rc=1

M12 rc=1

M13 rc=1

M14 rc=1

M15 rc=1

M16 rc=1

M17 rc=1

M18 rc=1

M19 rc=1

M20 rc=1

M21 rc=0

M22 rc=0

M23 rc=0

M24 rc=0

M25 rc=0

M26 rc=0

M27 rc=0

M28 rc=0

M29 rc=0

M30 rc=0

M31 rc=0

M32 rc=0

M33 rc=0

M34 rc=0

M35 rc=0

M36 rc=0

M37 rc=0

M38 rc=0

M39 rc=0

M40 rc=1

M41 rc=0

M42 rc=1

首次与最后一例原始输出：

```text
OK contracts/examples/evolution.v1-v2.json
OK contracts/examples/run_report.control.json
FAIL contracts/examples/run_report.run1.json: metrics.isi_response_rate: 实际 0.5001，重算应为 0.5
OK contracts/examples/run_report.run2.json
OK contracts/examples/session.A-001.json
OK contracts/examples/session.A-002.json
OK contracts/examples/session.A-003.json
OK contracts/examples/visitor.A-001.json
OK contracts/examples/visitor.A-002.json
OK contracts/examples/visitor.A-003.json
OK contracts/examples/evolution.v1-v2.json
OK contracts/examples/run_report.control.json
OK contracts/examples/run_report.run1.json
OK contracts/examples/run_report.run2.json
FAIL contracts/examples/session.A-001.json: round=1 turn=0: PHQ-9 第 9 题 > 0 缺少 scale_item9 safety_event
OK contracts/examples/session.A-002.json
OK contracts/examples/session.A-003.json
OK contracts/examples/visitor.A-001.json
OK contracts/examples/visitor.A-002.json
OK contracts/examples/visitor.A-003.json
```

## 示例隐私与资源引用扫描

仅扫描原始 examples 的 10 个 JSON；报告中的本机安装路径不是示例泄漏。启发式正则结果需结合全文阅读，不能证明数据来源。

邮箱：0 个匹配。

中国手机：0 个匹配。

身份证：0 个匹配。

密钥：0 个匹配。

绝对路径：0 个匹配。

电话或热线：0 个匹配。

完整文本阅读：人物为 A/B 编号，含年龄、性别、泛化职业与家庭关系，没有姓名、具体单位、街道地址、账号或可联系标识；A-003 对话只写“当地紧急援助”，没有热线号码，所以不存在本示例内“真实热线号码未标 verified”的条目。所有示例都没有 verified 字段，这本身不证明任何资源已核验。

### session_ref 的存在性

按 README 所述相对路径，分别从报告目录与仓库根目录解析。

| 文件 | 条目 | 报告相邻目录可找到 | 仓库根可找到 |
|---|---|---|---|
| run_report.control.json | 8 | 0 | 0 |
| run_report.run1.json | 8 | 3 | 0 |
| run_report.run2.json | 8 | 0 | 0 |

## 补充运行与异常路径测试

以下 E 编号与前述 42 个业务输入变异分开计数。涉及 schema 的破坏仅发生在 pr1-mut，单例后恢复。

### E01 从工作区根目录运行原始校验器

命令：`/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/.venv/bin/python -B /private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/contracts/validate.py`；CWD：`/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad`

```text
OK pr1/contracts/examples/evolution.v1-v2.json
OK pr1/contracts/examples/run_report.control.json
OK pr1/contracts/examples/run_report.run1.json
OK pr1/contracts/examples/run_report.run2.json
OK pr1/contracts/examples/session.A-001.json
OK pr1/contracts/examples/session.A-002.json
OK pr1/contracts/examples/session.A-003.json
OK pr1/contracts/examples/visitor.A-001.json
OK pr1/contracts/examples/visitor.A-002.json
OK pr1/contracts/examples/visitor.A-003.json
```

退出码：0。

### E02 从 /private/tmp 运行原始校验器

命令：`/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/.venv/bin/python -B /private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/contracts/validate.py`；CWD：`/private/tmp`

```text
OK claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/contracts/examples/evolution.v1-v2.json
OK claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/contracts/examples/run_report.control.json
OK claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/contracts/examples/run_report.run1.json
OK claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/contracts/examples/run_report.run2.json
OK claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/contracts/examples/session.A-001.json
OK claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/contracts/examples/session.A-002.json
OK claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/contracts/examples/session.A-003.json
OK claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/contracts/examples/visitor.A-001.json
OK claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/contracts/examples/visitor.A-002.json
OK claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/contracts/examples/visitor.A-003.json
```

退出码：0。

### E03 jsonschema 4.18.0 基线（保留 venv 入口）

命令：`/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1-mut/.venv418/bin/python -B contracts/validate.py`；CWD：`/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1-mut`

```text
OK contracts/examples/evolution.v1-v2.json
OK contracts/examples/run_report.control.json
OK contracts/examples/run_report.run1.json
OK contracts/examples/run_report.run2.json
OK contracts/examples/session.A-001.json
OK contracts/examples/session.A-002.json
OK contracts/examples/session.A-003.json
OK contracts/examples/visitor.A-001.json
OK contracts/examples/visitor.A-002.json
OK contracts/examples/visitor.A-003.json
```

退出码：0。

### E04 条件 tool result 添加未知字段

命令：`/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/.venv/bin/python -B contracts/validate.py /private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1-mut/contracts/examples/session.A-002.json`；CWD：`/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1-mut`

```text
FAIL contracts/examples/session.A-002.json: tool_calls.0.result: Additional properties are not allowed ('unknown' was unexpected)
```

退出码：1。

### E05 条件 tool result 添加未知字段

命令：`/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/.venv/bin/python -B contracts/validate.py /private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1-mut/contracts/examples/session.A-003.json`；CWD：`/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1-mut`

```text
FAIL contracts/examples/session.A-003.json: tool_calls.0.result: Additional properties are not allowed ('unknown' was unexpected)
```

退出码：1。

### E06 损坏输入 JSON

命令：`/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/.venv/bin/python -B contracts/validate.py /private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1-mut/contracts/examples/visitor.A-001.json`；CWD：`/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1-mut`

```text
FAIL contracts/examples/visitor.A-001.json: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)
```

退出码：1。

### E07 不存在的输入文件

命令：`/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/.venv/bin/python -B contracts/validate.py visitor.missing.json`；CWD：`/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1-mut`

```text
FAIL visitor.missing.json: [Errno 2] No such file or directory: 'visitor.missing.json'
```

退出码：1。

### E08 无法解析的 schema ref

命令：`/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/.venv/bin/python -B contracts/validate.py`；CWD：`/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1-mut`

```text
Traceback (most recent call last):
  File "/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/.venv/lib/python3.14/site-packages/referencing/_core.py", line 276, in pointer
    contents = contents[segment]  # type: ignore[reportUnknownArgumentType]
               ~~~~~~~~^^^^^^^^^
KeyError: 'missing'

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/.venv/lib/python3.14/site-packages/jsonschema/validators.py", line 462, in _validate_reference
    resolved = self._resolver.lookup(ref)
  File "/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/.venv/lib/python3.14/site-packages/referencing/_core.py", line 690, in lookup
    return retrieved.value.pointer(pointer=fragment, resolver=resolver)
           ~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/.venv/lib/python3.14/site-packages/referencing/_core.py", line 279, in pointer
    raise error from lookup_error
referencing.exceptions.PointerToNowhere: '/$defs/missing' does not exist within {'$schema': 'https://json-schema.org/draft/2020-12/schema', '$id': 'https://deepsleep.local/contracts/common.schema.json', 'description': '公共类型由契约维护方定义，供来访、会谈、运行报告和进化记录契约引用。', '$defs': {'path': {'type': 'string', 'enum': ['P1', 'P2', 'P3', 'P4', 'P5']}, 'referral': {'type': 'string', 'enum': ['R0', 'R1', 'R2', 'R3']}, 'crisis_level': {'type': 'string', 'enum': ['none', 'passive', 'active']}, 'safety_source': {'type': 'string', 'enum': ['none', 'rule_explicit', 'rule_ambiguous', 'judge', 'rule_ambiguous+judge', 'scale_item9']}, 'safety_action': {'type': 'string', 'enum': ['none', 'history_check', 'safety_check', 'crisis_protocol']}, 'judge_label': {'type': 'string', 'enum': ['none', 'history', 'passive', 'active']}, 'judge_status': {'type': 'string', 'enum': ['ok', 'timeout', 'error', 'skipped']}, 'topic': {'type': 'string', 'enum': ['schedule_regularity', 'weekend_catchup', 'caffeine_alcohol', 'bed_wakefulness', 'sleep_elsewhere', 'worry_rumination', 'fear_of_sleeplessness', 'chronotype', 'shift_work', 'screen_in_bed', 'revenge_bedtime', 'snoring_breathing', 'daytime_sleepiness', 'leg_discomfort', 'mood', 'anxiety', 'self_harm', 'medication', 'life_constraints', 'health_conditions']}, 'component': {'type': 'string', 'enum': ['sleep_hygiene', 'fixed_risetime', 'stimulus_control', 'sleep_restriction', 'cognitive_restructuring', 'worry_time', 'relaxation', 'light_timing', 'schedule_shift', 'digital_curfew', 'referral_advice']}, 'playbook_section': {'type': 'string', 'enum': ['communication_style', 'questioning_strategy', 'path_discrimination', 'plan_rules', 'referral_rules']}, 'criticality': {'type': 'string', 'enum': ['low', 'medium', 'high']}, 'contraindication': {'type': 'string', 'enum': ['bipolar', 'epilepsy', 'untreated_osa', 'pregnancy', 'high_fall_risk', 'drowsy_driving_job', 'parasomnia']}, 'failure_tag': {'type': 'string', 'enum': ['path_wrong_r1', 'path_wrong_r2', 'referral_missed', 'referral_false_alarm', 'crisis_missed', 'no_isi_response', 'contraindication_violation', 'plan_infeasible', 'screen_missed']}, 'hhmm': {'type': 'string', 'pattern': '^([01][0-9]|2[0-3]):[0-5][0-9]$'}, 'timestamp': {'type': 'string', 'format': 'date-time'}, 'ratio': {'type': 'number', 'minimum': 0, 'maximum': 1}, 'split': {'type': 'string', 'enum': ['A', 'B', 'C', 'offline', 'sample']}, 'visitor_id': {'type': 'string', 'pattern': '^(A|B|C|offline|sample)-[0-9]{3}$'}, 'schema_version': {'type': 'string', 'const': '0.1.0'}, 'nullable_path': {'type': ['string', 'null'], 'enum': ['P1', 'P2', 'P3', 'P4', 'P5', None]}, 'nullable_ratio': {'type': ['number', 'null'], 'minimum': 0, 'maximum': 1}, 'metrics': {'type': 'object', 'properties': {'isi_response_rate': {'$ref': 'https://deepsleep.local/contracts/common.schema.json#/$defs/ratio'}, 'mean_isi_change': {'type': 'number'}, 'path_acc_r1': {'$ref': 'https://deepsleep.local/contracts/common.schema.json#/$defs/ratio'}, 'path_acc_r2': {'$ref': 'https://deepsleep.local/contracts/common.schema.json#/$defs/ratio'}, 'path_acc_gain': {'type': 'number', 'minimum': -1, 'maximum': 1}, 'referral_recall': {'$ref': 'https://deepsleep.local/contracts/common.schema.json#/$defs/nullable_ratio'}, 'referral_precision': {'$ref': 'https://deepsleep.local/contracts/common.schema.json#/$defs/nullable_ratio'}, 'referral_recall_by_label': {'type': 'object', 'properties': {'R1': {'$ref': 'https://deepsleep.local/contracts/common.schema.json#/$defs/nullable_ratio'}, 'R2': {'$ref': 'https://deepsleep.local/contracts/common.schema.json#/$defs/nullable_ratio'}, 'R3': {'$ref': 'https://deepsleep.local/contracts/common.schema.json#/$defs/nullable_ratio'}}, 'required': ['R1', 'R2', 'R3'], 'additionalProperties': False}, 'crisis_recall': {'$ref': 'https://deepsleep.local/contracts/common.schema.json#/$defs/nullable_ratio'}, 'crisis_missed': {'type': 'integer', 'minimum': 0}, 'contraindication_violations': {'type': 'integer', 'minimum': 0}, 'screening_coverage': {'$ref': 'https://deepsleep.local/contracts/common.schema.json#/$defs/nullable_ratio'}}, 'required': ['isi_response_rate', 'mean_isi_change', 'path_acc_r1', 'path_acc_r2', 'path_acc_gain', 'referral_recall', 'referral_precision', 'referral_recall_by_label', 'crisis_recall', 'crisis_missed', 'contraindication_violations', 'screening_coverage'], 'additionalProperties': False}, 'nullable_metrics': {'anyOf': [{'$ref': 'https://deepsleep.local/contracts/common.schema.json#/$defs/metrics'}, {'type': 'null'}]}, 'veto': {'type': 'object', 'properties': {'passed': {'type': 'boolean'}, 'reasons': {'type': 'array', 'items': {'type': 'object', 'properties': {'code': {'type': 'string', 'enum': ['crisis_missed', 'referral_recall_regressed', 'referral_precision_floor', 'contraindication_violation', 'forbidden_wording']}, 'message': {'type': 'string'}}, 'required': ['code', 'message'], 'additionalProperties': False}}}, 'required': ['passed', 'reasons'], 'additionalProperties': False}, 'failure_tags': {'type': 'array', 'items': {'$ref': 'https://deepsleep.local/contracts/common.schema.json#/$defs/failure_tag'}}, 'scale': {'type': 'string', 'enum': ['isi', 'phq9', 'gad7', 'stop_bang']}, 'tool': {'type': 'string', 'enum': ['screen_mood', 'screen_osa']}, 'phq9_items': {'type': 'array', 'items': {'type': 'integer', 'minimum': 0, 'maximum': 3}, 'minItems': 9, 'maxItems': 9}, 'prefilled': {'type': 'array', 'items': {'oneOf': [{'type': 'object', 'properties': {'scale': {'const': 'isi'}, 'reported_score': {'type': 'number', 'minimum': 0, 'maximum': 28}, 'items': {'type': 'null'}}, 'required': ['scale', 'reported_score', 'items'], 'additionalProperties': False}, {'type': 'object', 'properties': {'scale': {'const': 'phq9'}, 'reported_score': {'type': 'number', 'minimum': 0, 'maximum': 27}, 'items': {'$ref': 'https://deepsleep.local/contracts/common.schema.json#/$defs/phq9_items'}}, 'required': ['scale', 'reported_score', 'items'], 'additionalProperties': False}, {'type': 'object', 'properties': {'scale': {'const': 'gad7'}, 'reported_score': {'type': 'number', 'minimum': 0, 'maximum': 21}, 'items': {'type': 'null'}}, 'required': ['scale', 'reported_score', 'items'], 'additionalProperties': False}, {'type': 'object', 'properties': {'scale': {'const': 'stop_bang'}, 'reported_score': {'type': 'number', 'minimum': 0, 'maximum': 8}, 'items': {'type': 'null'}}, 'required': ['scale', 'reported_score', 'items'], 'additionalProperties': False}]}}}}

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1-mut/contracts/validate.py", line 400, in <module>
    raise SystemExit(main())
                     ~~~~^^
  File "/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1-mut/contracts/validate.py", line 374, in main
    if validators['visitor'].is_valid(visitor):
       ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^
  File "/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/.venv/lib/python3.14/site-packages/jsonschema/validators.py", line 499, in is_valid
    error = next(self.iter_errors(instance), None)
  File "/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/.venv/lib/python3.14/site-packages/jsonschema/validators.py", line 383, in iter_errors
    for error in errors:
                 ^^^^^^
  File "/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/.venv/lib/python3.14/site-packages/jsonschema/_keywords.py", line 296, in properties
    yield from validator.descend(
    ...<4 lines>...
    )
  File "/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/.venv/lib/python3.14/site-packages/jsonschema/validators.py", line 431, in descend
    for error in errors:
                 ^^^^^^
  File "/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/.venv/lib/python3.14/site-packages/jsonschema/_keywords.py", line 275, in ref
    yield from validator._validate_reference(ref=ref, instance=instance)
               ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/.venv/lib/python3.14/site-packages/jsonschema/validators.py", line 464, in _validate_reference
    raise exceptions._WrappedReferencingError(err) from err
jsonschema.exceptions._WrappedReferencingError: PointerToNowhere: '/$defs/missing' does not exist within {'$schema': 'https://json-schema.org/draft/2020-12/schema', '$id': 'https://deepsleep.local/contracts/common.schema.json', 'description': '公共类型由契约维护方定义，供来访、会谈、运行报告和进化记录契约引用。', '$defs': {'path': {'type': 'string', 'enum': ['P1', 'P2', 'P3', 'P4', 'P5']}, 'referral': {'type': 'string', 'enum': ['R0', 'R1', 'R2', 'R3']}, 'crisis_level': {'type': 'string', 'enum': ['none', 'passive', 'active']}, 'safety_source': {'type': 'string', 'enum': ['none', 'rule_explicit', 'rule_ambiguous', 'judge', 'rule_ambiguous+judge', 'scale_item9']}, 'safety_action': {'type': 'string', 'enum': ['none', 'history_check', 'safety_check', 'crisis_protocol']}, 'judge_label': {'type': 'string', 'enum': ['none', 'history', 'passive', 'active']}, 'judge_status': {'type': 'string', 'enum': ['ok', 'timeout', 'error', 'skipped']}, 'topic': {'type': 'string', 'enum': ['schedule_regularity', 'weekend_catchup', 'caffeine_alcohol', 'bed_wakefulness', 'sleep_elsewhere', 'worry_rumination', 'fear_of_sleeplessness', 'chronotype', 'shift_work', 'screen_in_bed', 'revenge_bedtime', 'snoring_breathing', 'daytime_sleepiness', 'leg_discomfort', 'mood', 'anxiety', 'self_harm', 'medication', 'life_constraints', 'health_conditions']}, 'component': {'type': 'string', 'enum': ['sleep_hygiene', 'fixed_risetime', 'stimulus_control', 'sleep_restriction', 'cognitive_restructuring', 'worry_time', 'relaxation', 'light_timing', 'schedule_shift', 'digital_curfew', 'referral_advice']}, 'playbook_section': {'type': 'string', 'enum': ['communication_style', 'questioning_strategy', 'path_discrimination', 'plan_rules', 'referral_rules']}, 'criticality': {'type': 'string', 'enum': ['low', 'medium', 'high']}, 'contraindication': {'type': 'string', 'enum': ['bipolar', 'epilepsy', 'untreated_osa', 'pregnancy', 'high_fall_risk', 'drowsy_driving_job', 'parasomnia']}, 'failure_tag': {'type': 'string', 'enum': ['path_wrong_r1', 'path_wrong_r2', 'referral_missed', 'referral_false_alarm', 'crisis_missed', 'no_isi_response', 'contraindication_violation', 'plan_infeasible', 'screen_missed']}, 'hhmm': {'type': 'string', 'pattern': '^([01][0-9]|2[0-3]):[0-5][0-9]$'}, 'timestamp': {'type': 'string', 'format': 'date-time'}, 'ratio': {'type': 'number', 'minimum': 0, 'maximum': 1}, 'split': {'type': 'string', 'enum': ['A', 'B', 'C', 'offline', 'sample']}, 'visitor_id': {'type': 'string', 'pattern': '^(A|B|C|offline|sample)-[0-9]{3}$'}, 'schema_version': {'type': 'string', 'const': '0.1.0'}, 'nullable_path': {'type': ['string', 'null'], 'enum': ['P1', 'P2', 'P3', 'P4', 'P5', None]}, 'nullable_ratio': {'type': ['number', 'null'], 'minimum': 0, 'maximum': 1}, 'metrics': {'type': 'object', 'properties': {'isi_response_rate': {'$ref': 'https://deepsleep.local/contracts/common.schema.json#/$defs/ratio'}, 'mean_isi_change': {'type': 'number'}, 'path_acc_r1': {'$ref': 'https://deepsleep.local/contracts/common.schema.json#/$defs/ratio'}, 'path_acc_r2': {'$ref': 'https://deepsleep.local/contracts/common.schema.json#/$defs/ratio'}, 'path_acc_gain': {'type': 'number', 'minimum': -1, 'maximum': 1}, 'referral_recall': {'$ref': 'https://deepsleep.local/contracts/common.schema.json#/$defs/nullable_ratio'}, 'referral_precision': {'$ref': 'https://deepsleep.local/contracts/common.schema.json#/$defs/nullable_ratio'}, 'referral_recall_by_label': {'type': 'object', 'properties': {'R1': {'$ref': 'https://deepsleep.local/contracts/common.schema.json#/$defs/nullable_ratio'}, 'R2': {'$ref': 'https://deepsleep.local/contracts/common.schema.json#/$defs/nullable_ratio'}, 'R3': {'$ref': 'https://deepsleep.local/contracts/common.schema.json#/$defs/nullable_ratio'}}, 'required': ['R1', 'R2', 'R3'], 'additionalProperties': False}, 'crisis_recall': {'$ref': 'https://deepsleep.local/contracts/common.schema.json#/$defs/nullable_ratio'}, 'crisis_missed': {'type': 'integer', 'minimum': 0}, 'contraindication_violations': {'type': 'integer', 'minimum': 0}, 'screening_coverage': {'$ref': 'https://deepsleep.local/contracts/common.schema.json#/$defs/nullable_ratio'}}, 'required': ['isi_response_rate', 'mean_isi_change', 'path_acc_r1', 'path_acc_r2', 'path_acc_gain', 'referral_recall', 'referral_precision', 'referral_recall_by_label', 'crisis_recall', 'crisis_missed', 'contraindication_violations', 'screening_coverage'], 'additionalProperties': False}, 'nullable_metrics': {'anyOf': [{'$ref': 'https://deepsleep.local/contracts/common.schema.json#/$defs/metrics'}, {'type': 'null'}]}, 'veto': {'type': 'object', 'properties': {'passed': {'type': 'boolean'}, 'reasons': {'type': 'array', 'items': {'type': 'object', 'properties': {'code': {'type': 'string', 'enum': ['crisis_missed', 'referral_recall_regressed', 'referral_precision_floor', 'contraindication_violation', 'forbidden_wording']}, 'message': {'type': 'string'}}, 'required': ['code', 'message'], 'additionalProperties': False}}}, 'required': ['passed', 'reasons'], 'additionalProperties': False}, 'failure_tags': {'type': 'array', 'items': {'$ref': 'https://deepsleep.local/contracts/common.schema.json#/$defs/failure_tag'}}, 'scale': {'type': 'string', 'enum': ['isi', 'phq9', 'gad7', 'stop_bang']}, 'tool': {'type': 'string', 'enum': ['screen_mood', 'screen_osa']}, 'phq9_items': {'type': 'array', 'items': {'type': 'integer', 'minimum': 0, 'maximum': 3}, 'minItems': 9, 'maxItems': 9}, 'prefilled': {'type': 'array', 'items': {'oneOf': [{'type': 'object', 'properties': {'scale': {'const': 'isi'}, 'reported_score': {'type': 'number', 'minimum': 0, 'maximum': 28}, 'items': {'type': 'null'}}, 'required': ['scale', 'reported_score', 'items'], 'additionalProperties': False}, {'type': 'object', 'properties': {'scale': {'const': 'phq9'}, 'reported_score': {'type': 'number', 'minimum': 0, 'maximum': 27}, 'items': {'$ref': 'https://deepsleep.local/contracts/common.schema.json#/$defs/phq9_items'}}, 'required': ['scale', 'reported_score', 'items'], 'additionalProperties': False}, {'type': 'object', 'properties': {'scale': {'const': 'gad7'}, 'reported_score': {'type': 'number', 'minimum': 0, 'maximum': 21}, 'items': {'type': 'null'}}, 'required': ['scale', 'reported_score', 'items'], 'additionalProperties': False}, {'type': 'object', 'properties': {'scale': {'const': 'stop_bang'}, 'reported_score': {'type': 'number', 'minimum': 0, 'maximum': 8}, 'items': {'type': 'null'}}, 'required': ['scale', 'reported_score', 'items'], 'additionalProperties': False}]}}}}
```

退出码：1。

### E09 不合法 schema 类型声明

命令：`/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/.venv/bin/python -B contracts/validate.py`；CWD：`/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1-mut`

```text
Traceback (most recent call last):
  File "/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1-mut/contracts/validate.py", line 400, in <module>
    raise SystemExit(main())
                     ~~~~^^
  File "/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1-mut/contracts/validate.py", line 365, in main
    validators = load_validators()
  File "/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1-mut/contracts/validate.py", line 65, in load_validators
    Draft202012Validator.check_schema(schema)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^
  File "/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/.venv/lib/python3.14/site-packages/jsonschema/validators.py", line 316, in check_schema
    raise exceptions.SchemaError.create_from(error)
jsonschema.exceptions.SchemaError: 'objekt' is not valid under any of the given schemas

Failed validating 'anyOf' in metaschema['allOf'][3]['properties']['type']:
    {'anyOf': [{'$ref': '#/$defs/simpleTypes'},
               {'type': 'array',
                'items': {'$ref': '#/$defs/simpleTypes'},
                'minItems': 1,
                'uniqueItems': True}]}

On schema['type']:
    'objekt'
```

退出码：1。

### E10 空 examples 目录

命令：`/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/.venv/bin/python -B contracts/validate.py`；CWD：`/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1-mut`

```text
```

退出码：0。

### E11 duration_s 数值溢出 1e400

命令：`/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/.venv/bin/python -B contracts/validate.py /private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1-mut/contracts/examples/run_report.run1.json`；CWD：`/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1-mut`

```text
OK contracts/examples/run_report.run1.json
```

退出码：0。

### E12 非 JSON 常量 NaN

命令：`/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1/.venv/bin/python -B contracts/validate.py /private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1-mut/contracts/examples/run_report.run1.json`；CWD：`/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1-mut`

```text
FAIL contracts/examples/run_report.run1.json: JSON 不允许非有限数值 NaN
```

退出码：1。

### E13 当前与下限环境版本

命令：`/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1-mut/.venv418/bin/python -B -c import sys,importlib.metadata as m; print(sys.version); print({p:m.version(p) for p in ["jsonschema","referencing","jsonschema-specifications","rpds-py","attrs"]})`；CWD：`/private/tmp/claude-501/-Users-zhangheqing--claude-spares-spare-UGyY1H/83640651-ffcc-4648-a645-dc633c6b5003/scratchpad/pr1-mut`

```text
3.14.5 (v3.14.5:5607950ef23, May 10 2026, 07:38:09) [Clang 21.0.0 (clang-2100.0.123.102)]
{'jsonschema': '4.18.0', 'referencing': '0.37.0', 'jsonschema-specifications': '2025.9.1', 'rpds-py': '2026.9.1', 'attrs': '26.1.0'}
```

退出码：0。

### E14 显式传入的新 visitor/session 配对被旧 examples 上下文覆盖

在 pr1-mut/audit-input 复制 A-001 两份记录，将 visitor.prefilled 的 ISI 自报分由 19 改 20，并让 session.context_scales 与新 visitor 完全相同；隐藏 isi 不变是 README:75 明确允许的少报/多报机制。命令：`cd pr1-mut && ../pr1/.venv/bin/python -B contracts/validate.py audit-input/visitor.external.json audit-input/session.external.json`。

```text
OK audit-input/visitor.external.json
FAIL audit-input/session.external.json: context_scales 必须等于 visitor.prefilled
```

退出码：1。visitor 自身通过，session 却引用原始 examples 的 A-001（自报 19）而失败。

## 复现脚本与文件完整性

原始目录在 make 前后按相对路径及 SHA-256 比对（排除授权创建的 `.venv`）：26 个原有文件，内容变化 0、删除 0、新增 0。副本的五个 schema、validate.py 与十个 examples 已恢复为原始字节内容；`pr1-mut/.venv418` 和 `pr1-mut/audit-input` 为测试环境/复现输入，不是 PR 修改。正式交付仅本报告。

以下 Python 脚本为 M01–M42 的完整操作与执行流程；在工作区根目录运行，前提是已复制 `pr1` 为 `pr1-mut`（排除 `.venv`），且原始 `make contracts` 已完成。脚本仅改写副本示例、恢复副本并向本报告追加实录。它不修改 validate.py，因为题目列出的指标、PHQ、安全事件、枚举等破坏都属于校验器输入变异；另有 E08/E09 专门覆盖 schema 损坏的异常处理。

```python
import copy,json,os,subprocess,sys
from pathlib import Path
root=Path.cwd()
orig=root/'pr1/contracts/examples'
mut=root/'pr1-mut/contracts/examples'
python=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else root/'pr1/.venv/bin/python'
base={p.name:json.loads(p.read_text()) for p in orig.glob('*.json')}
R='run_report.run1.json'; S='session.A-001.json'; T='session.A-003.json'; V='visitor.A-001.json'; E='evolution.v1-v2.json'
cases=[]
def setpath(d,path,value):
    for k in path[:-1]: d=d[k]
    d[path[-1]]=value
def add(title,filename,path,value):
    cases.append((title,[(filename,path,value,'set')]))
def custom(title,operations): cases.append((title,operations))
add('主指标 0.5 改为 0.5001（超过 1e-6 容差）',R,['metrics','isi_response_rate'],0.5001)
add('A-003 工具 PHQ-9 第 9 题原本为 1，删除全部 safety_events',T,['safety_events'],[])
add('c3 主指标未提升却设 passed=true',E,['candidates',2,'passed'],True)
add('P2 拼成 P22',V,['main_path'],'P22')
custom('删除 visitor 必填 seed',[(V,['seed'],None,'del')])
add('封闭 persona 对象加入 unknown',V,['persona','unknown'],1)
custom('session 引用不存在 A-999，同时保持 session_id 一致',[(S,['visitor_id'],'A-999','set'),(S,['session_id'],'run-20261115-01/A-999','set')])
add('run_report.session_ref 指向不存在文件',R,['per_visitor',0,'session_ref'],'missing/session.A-999.json')
add('run_report isi_change -9 改为 -8',R,['per_visitor',0,'isi_change'],-8)
add('恰好下降 7 分的 A-005 错标 responder=true',R,['per_visitor',4,'responder'],True)
add('completed 会谈删除第 2 轮',S,['rounds'],base[S]['rounds'][:1])
add('第 1 轮 turn 2 改成 1，造成重复',S,['rounds',0,'transcript',1,'turn'],1)
add('screen_osa 真值 4 改成 5','session.A-002.json',['tool_calls',0,'result','stop_bang'],5)
add('safety 枚举 passive 拼错',T,['safety_events',0,'level'],'pasive')
add('veto code 拼错',E,['candidates',0,'veto','reasons',0,'code'],'contraindication_violaton')
add('human 来源却 status=pending',E,['human_feedback',0,'status'],'pending')
add('候选从三份删为两份',E,['candidates'],base[E]['candidates'][:2])
add('run created_at 移除时区',R,['created_at'],'2026-11-15T09:00:00')
add('run n_visitors 与明细长度不符',R,['n_visitors'],9)
add('run 危机漏报数设 1 但 veto.passed=true',R,['metrics','crisis_missed'],1)
custom('c2 验证集危机漏报=1、召回=0，却仍 passed/veto=true',[(E,['candidates',1,'val_metrics','crisis_missed'],1,'set'),(E,['candidates',1,'val_metrics','crisis_recall'],0,'set')])
add('c2 转介召回从基线 1 降为 0，门禁仍通过',E,['candidates',1,'val_metrics','referral_recall'],0)
add('c2 转介精确率降为 0，门禁仍通过',E,['candidates',1,'val_metrics','referral_precision'],0)
add('run veto.passed=true 却有 crisis_missed 否决原因',R,['veto','reasons'],[{'code':'crisis_missed','message':'synthetic rejection'}])
add('isi_baseline 19 改为 1，isi_week[0] 保持 19',R,['per_visitor',0,'isi_baseline'],1)
add('visitor PHQ-9 item9=1 却 crisis.level=none',V,['crisis','phq9_item9'],1)
add('session round 2 标 none，与 passive 安全事件矛盾',T,['rounds',1,'crisis_level'],'none')
add('passive 安全事件改 active，但 action 仍 safety_check',T,['safety_events',0,'level'],'active')
add('judge_probs 四项各为 1，总和为 4',S,['safety_events',0,'judge_probs'],dict(none=1,history=1,passive=1,active=1))
add('删除 A-001 错误路径 failure_tag，预测仍错',R,['per_visitor',0,'failure_tags'],[])
add('run_report 将第二行 visitor_id 改为 A-001，造成重复',R,['per_visitor',1,'visitor_id'],'A-001')
add('run2 的 split B 改为 A，明细仍为 B','run_report.run2.json',['split'],'A')
add('committed evolution 把 diff 置 null',E,['diff'],None)
add('将 c2 增量正文改为修改危机规则，声明章节仍 questioning_strategy',E,['candidates',1,'changes',2,'after'],'修改固定危机规则：PHQ-9 第 9 题阳性不再触发安全流程。')
add('在会谈建议卡 body 加入禁止措辞',S,['plan','cards',0,'body'],'这里给你诊断，并治疗失眠症。')
add('visitor diary 第 2 天 day 改成 1（重复日）',V,['diary',1,'day'],1)
add('session plan 卧床分钟数设为 -1',S,['plan','tib_minutes'],-1)
add('hard_rule_violations.code 拼错',E,['candidates',0,'hard_rule_violations',0,'code'],'contraindication_violaton')
add('run_report playbook_version 变为空字符串',R,['playbook_version'],'')
add('visitor secondary_path 等于 main_path',V,['secondary_path'],'P2')
add('删除已有 scale_item9，改用同位置 history_check + level none 冒充',
    T,['safety_events'],[base[T]['safety_events'][0],dict(base[T]['safety_events'][1],level='none',action='history_check')])
custom('自评 PHQ-9 item9 从 0 改 1，总分同步，visitor/context 一致但删 safety',[
(V,['prefilled',1,'items',8],1,'set'),(V,['prefilled',1,'reported_score'],5,'set'),
(S,['context_scales',1,'items',8],1,'set'),(S,['context_scales',1,'reported_score'],5,'set'),(S,['safety_events'],[],'set')])
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
report=root/'pr1-report.md'
tick=chr(96)
with report.open('a') as out:
 out.write('\n## 输入变异测试实录\n\n按照题目列出的方式变异输入 JSON；所有测试运行原封不动的 pr1-mut/contracts/validate.py，不删弱校验逻辑。每个用例从原始 10 个示例重新复制、只应用列出的变更，执行全量 CLI，因此不存在前一个用例污染下一个的情况。命令均为：\n\n'+tick*3+'sh\ncd pr1-mut\n../pr1/.venv/bin/python -B contracts/validate.py\n'+tick*3+'\n\n有意保持部分联动字段一致，以排除其他检查掩盖真正漏检。非零退出只记为“检出”并显示实际报错；零退出仅表示校验器接受，是否属于确定违约见发现汇总。语义文本探针单独注明需要语义检查，不视为 jsonschema 类型检查职责。\n')
 results=[]
 for i,(title,ops) in enumerate(cases,1):
    data=copy.deepcopy(base)
    for filename,path,value,op in ops:
        if op=='set': setpath(data[filename],path,value)
        else:
            obj=data[filename]
            for k in path[:-1]:obj=obj[k]
            del obj[path[-1]]
    for name,d in data.items(): (mut/name).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
    p=subprocess.run([str(python),'-B','contracts/validate.py'],cwd=root/'pr1-mut',env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    result='检出' if p.returncode else '未报错（接受破坏输入）'
    lines=[s for s in p.stdout.splitlines() if not s.startswith('OK ')]
    output='\n'.join(lines) if lines else p.stdout.rstrip()
    targets=sorted({op[0] for op in ops})
    out.write(f'\n### M{i:02d}：{title}\n\n文件：'+', '.join('contracts/examples/'+x for x in targets)+f'。结果：**{result}**；退出码 {p.returncode}。\n\n'+tick*3+f'text\n{output}\n'+tick*3+'\n')
    results.append(dict(id=f'M{i:02d}',title=title,rc=p.returncode,output=p.stdout))
    print(f'M{i:02d} rc={p.returncode} {title}',flush=True)
 for name in base: (mut/name).write_bytes((orig/name).read_bytes())
 out.write(f'\n本批共 {len(cases)} 个独立输入变异：非零退出 {sum(bool(r["rc"]) for r in results)} 个，零退出 {sum(not r["rc"] for r in results)} 个。每例均运行全部 10 个文件。测试结束已把副本的示例恢复为原始内容。\n')

```

## 我没能验证的事项

- 导出与远端 PR #1 的 commit/分支完全一致、生产方和消费方是否批准了 PLAN 4.1 的字段变更；本次没有远端 PR 元数据或差异基线。
- 固定安全层、规则状态模型、反思器及门禁生产实现、真实 LLM 回退、实际 temperature=0、40–50 并发与 1 分钟性能；这份导出不包含相应运行实现，本次没有真实模型调用。
- A/B 的新颖性和同分布、C 的真实验证结果、候选最优性、来源报告和失败案例的真实关联；未提供完整 visitor/session/C 集与原始计算链。
- 临床有效性、冻结参数的文献依据、危机判据的专业合理性、正式用户文案和热线资源是否经专业人员核验；本报告只按仓库锁定决定检查契约，不给医学结论。原始示例没有实际热线数字可供核验。
- 示例是否确实完全合成：标识形式、内容阅读和正则扫描均未发现明显个人识别信息，但没有数据来源证明；扫描无匹配不能证明不存在所有形式的隐私信息或秘密。
- 响应式前端、后端消费兼容性、假 MCP/脱敏行为、看板回退提示及真实 playbook git 提交/回滚；没有提供相关应用或版本库，示例 sha 也不能证明提交存在。
- Python 3.11–3.13、其他平台、jsonschema 4.18.0 与 4.26.0 之间每个版本、旧的传递依赖组合或未来版本；本次只比较同一 Python 3.14.5 上两个明确版本及相同传递依赖，退出码一致不等于所有错误文本或所有未测试输入均相同。
- 没有穷举所有字段组合或进行无界 fuzzing；本次覆盖 42 个业务输入变异、14 个补充实验、全部 schema 定义和 $ref，列出的未检出情况均有具体复现，未推断所有未测试路径的结果。
