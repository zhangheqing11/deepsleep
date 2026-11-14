# 睡眠领域中文脱敏数据集 v0.3

核心思想：移除所有可识别个人的信息，其余一律保留。负责人已定：城市、日历日期（非生日）与精确年龄原样保留；这些属性失去直接身份锚点后不指向个人，精确值还可能影响起病时间线和年龄相关临床/法律判断。生日/出生年月仍替换。

本数据集供本地模型学习“隐藏身份、保留睡眠会谈信息”。全部是人工编写或模板生成的模拟材料，没有真实来访记录。标注口径以 [SPEC.md](SPEC.md) v0.3 为准；原独立审核 [AUDIT.md](AUDIT.md) 保持原样，复审 [AUDIT2.md](AUDIT2.md) 也保持原样，修订说明见 [AUDIT_RESPONSE.md](AUDIT_RESPONSE.md)。尚未训练或评测 Qwen，也没有接入实际会谈的云端调用链路。

## 规模与用途

| 文件 | 条数/轮数 | 会话数 | 实体数 | hard negative | 比例 | KEEP片段 |
|---|---:|---:|---:|---:|---:|---:|
| gold/dev.jsonl | 153 | 0 | 110 | 65 | 42.48% | 411 |
| gold/seed.jsonl | 35 | 0 | 22 | 17 | 48.57% | 114 |
| gold/sessions.jsonl | 108 | 12 | 83 | 39 | 36.11% | 146 |
| gold/test.jsonl | 150 | 0 | 108 | 65 | 43.33% | 391 |
| synth/sessions_dev.jsonl | 244 | 40 | 186 | 98 | 40.16% | 454 |
| synth/sessions_train.jsonl | 1224 | 200 | 941 | 483 | 39.46% | 2275 |
| synth/train.jsonl | 3000 | 0 | 2530 | 1205 | 40.17% | 8269 |

SFT 单轮 train extract/rewrite/BIO 各3,035条，dev 各153条；会话 extract 训练1,224条、验证244条。规模未变；上表 KEEP 按每条标注列表计数，SFT 不单独导出 KEEP。精确标签/比例/空 KEEP/实体数及片段长度、个数、占比上限见 [STATS.json](STATS.json)。每个数据文件 hard negative 均达到35%，单轮合成维持35%–50%；gold 长发言每条60–200字，移除日期/年龄标签后有1–5个身份实体或为长负例；test 独立措辞并交错组织，新增部分不按 dev 的标签顺序镜像。

`gold/*.src.jsonl` 是手工维护的紧凑源，`gold/*.jsonl` 是编译结果。seed 的 KEEP 修订已由负责人直接合入 `seed.src.jsonl`。`tools/templates.yaml` 共126个模板，包含16个新增负例模板（其中12个明确品牌/机构话题或产品）、5个带姓称谓模板，以及6个长叙事模板族。v0.3 增加6个日期/年龄保留及生日/出生年份对照模板；阿拉伯数字、汉字、“刚满61”“三十四了”均有覆盖。带 long 标签的合成按固定位置占20%，在同一场景取连续2–4句，共享同一个人物及实体值。每个组成句显式标注临床片段，长句 KEEP 只取实际使用句子的并集，渲染后去重并去掉被包含的短片段；不截断危机分句，也不把整段非实体文本自动填入 KEEP。词表较宽，生成器按动作/功能/场景使用更窄的池，详情见 [lexicons/README.md](lexicons/README.md)。

## 一键离线重建

在本 worktree 根目录运行：

```sh
make deid-data
```

**v0.3 当前状态：** 已完成离线迁移、全量校验和回归测试，70项测试通过（含旧标签拒绝、replacement忽略、日期/年龄与生日对照、扫描器反例）。KEEP 密度上限仍只对 >60 字长发言生效，短句与危机规则沿用现有校验。

默认 Python 为 `../deepsleep/.venv/bin/python`。该 target 不依赖 venv/安装任务，不访问网络。顺序为 build → generate → build_sft → validate → pytest → dev/test基线与会话基线 → v0.3 全量扫描 → BASELINES.md、审核表与 MANIFEST.sha256。`STATS.json`、导出和校验和都会刷新。主 checkout 若使用本地环境可显式传 `DEID_PYTHON=.venv/bin/python`，本次仅使用相邻指定环境。

分步运行：

```sh
../deepsleep/.venv/bin/python -m privacy.data.tools.build
../deepsleep/.venv/bin/python -m privacy.data.tools.generate --n 3000 --seed 20261114
../deepsleep/.venv/bin/python -m privacy.data.tools.build_sft
../deepsleep/.venv/bin/python -m privacy.data.tools.validate --json privacy/data/STATS.json
PYTHONDONTWRITEBYTECODE=1 ../deepsleep/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_privacy_data.py
```

固定种子：单轮20261114，会话训练20261115、会话验证20261116。单轮合成排除所有 gold 源文本及合成内部重复；会话允许自然重复的无身份跟进句，训练/验证按完整会话隔离，不能把会话拆行后随机分配。两组会话仍共享模板族，因此验证不是独立自然分布的模型能力测试。

`sft/*.jsonl`、`synth/*.src.jsonl`、`__pycache__/` 已在本目录 `.gitignore` 忽略，由 make 生成；`sft/dataset_info.json` 保留作为入库的导入配置。manifest 包含本地已生成的 JSONL，便于完整重建核对；忽略缓存和 manifest 自身。

## 标注与运行协议

源实体为 `[surface,label,replacement?,occ?]`，occ 是原文 surface 的1起算出现序号，offset 是 Python Unicode 字符索引 `[start,end)`。实体按原文首次出现分配编号。所有10类标签均替换为编号占位符；源数据可用 replacement 指定合法占位符以表达别名共指，但不能提供泛化值。日历日期和精确年龄不标实体、原样保留并加入 KEEP；任何精度的生日、出生年/月用 BIRTH_DATE，代码产生 `[日期N]`。

机构名必须有本人或关系人的任职/就读/就诊关系。仅新闻、品牌或产品话题保留。带姓称谓只替换姓，例如“王医生”→“[人名1]医生”、“老张”→“老[人名1]”；床号/宿舍号/病房号保留，门牌地址替换。危机 KEEP 覆盖完整意图、行为、否定及时态分句；不会为补主语而改写来访原话。

extract 只输出实体 JSON。按 `(text,label)` 分组；必要时各自给 occ。举例：“小米是我朋友，我戴小米手环”只抽 PERSON 小米、occ=[1]；同形不同标签不合并；嵌套机构只选实际实体位置，不得重叠。system prompt 开头明确核心思想，长度上限700字符。

会话中先前映射是输入的一部分，每轮一个训练样本：

```text
本会话已有映射：{"PERSON":{"王涛":"[人名1]"}}
当前发言：我老公王涛也叫涛子，昨晚又打鼾。
```

assistant：

```json
{"entities":[{"text":"王涛","label":"PERSON"},{"text":"涛子","label":"PERSON","same_as":"[人名1]"}]}
```

`same_as` 只在同类别已存在该占位符时采纳（含本轮更早实体）。目标不存在或类型不匹配则记录 warning，按新实体分配。源金标用显式 replacement 表达共指，SFT 导出转换为 same_as。不能仅凭两个名字相像而猜测共指。映射按会话隔离；训练 user 中只放此前映射，没有未来轮信息。

```python
from privacy.data.tools.apply import apply
errors, warnings = [], []
out, mapping = apply(
    '涛子说他昨晚没睡好。',
    {'entities': [{'text': '涛子', 'label': 'PERSON', 'same_as': '[人名1]'}]},
    {'PERSON': {'王涛': '[人名1]'}},
    errors=errors, warnings=warnings,
)
```

`apply` 返回新映射、不修改传入对象。模型给出的 replacement 字段忽略并记录 warning（不算格式无效）；非法 JSON/标签/实体/occ/重叠会报错并跳过，旧 DATE/AGE 标签视为未知标签，返回原文部分不是隐私成功，调用方必须处理 errors；评测会把该整条输出记为无效，错误映射不进入后续轮。日志只包含错误类型，不打印原文或号码。

空 KEEP 仅限 `no_clinical` 且 note 解释原因。目前 seed-018 仅联系方式；session-03-06 仅昵称核对；session-10-03 仅机构核对；session-12-02 仅确认前轮生日并表达填写厌烦。其他行 KEEP 为1–6个关键片段；每个不超过30字，crisis行不超过50字。原文超过60字时，KEEP总长不得超过非实体文本长度的60%，普通行和hard negative同样执行；no_clinical仅豁免空列表，不能豁免上限。危机校验启发式要求至少一个片段长度≥6，含主语或意图/时态词；这只是漏标筛查，不能代替语义复核。

## 评测与基线

预测 JSONL 每行为 `{"id":"test-001","output":...}`。extract output 为实体对象或 JSON 字符串，rewrite 为整句。没有模型预测时只跑离线基线。

```sh
../deepsleep/.venv/bin/python -m privacy.data.tools.evaluate \
  --gold gold/test.jsonl --pred /tmp/preds.jsonl --mode extract --json /tmp/deid-eval.json
../deepsleep/.venv/bin/python -m privacy.data.tools.evaluate \
  --sessions --pred /tmp/session-preds.jsonl --mode extract --json /tmp/session-eval.json
```

`--sessions` 默认读 gold/sessions，按 session_id/turn 排序、每会话独立映射，并比较每次占位实体的金标编号；重复 turn 报错。`--gold` 可切换到合成会话。编号指标含新实体、复现及别名，不把漏抽身份当编号正确。

KEEP 绑定原文中非金标实体的出现位置；同一 keep 有多个原文出现时全部必须原样存活。输出占位符不算保留，输出中新加/搬移的 keep 也不能冒充原文位置。泄露只判断金标实体所在原文区间对应的输出区间；不会拿另一处品牌 KEEP 给人名豁免。非实体一致率要求非实体字符原样存在，并拒绝非实体区域插入文本。

无效输出单列计数，保留/逐字一致/整句匹配记失败，hard negative 记失败，实体保守记泄露；不会按“原文没改”获满分。空字符串 rewrite 虽可解析，也会丢失 KEEP。没有分母为 N/A。指标按标签与tag（含 long、adversarial）分层；新结果见 [BASELINES.md](BASELINES.md)，旧数字作废。

v0.3 的实体替换合法率只检查对应类型占位符；日期/年龄通过 KEEP 和非实体一致率评测。SPEC.md、AUDIT.md、AUDIT2.md 均未改动：

| 指标 | 当前评测口径 |
|---|---|
| 泄露率↓ | 金标实体对应位置仍残留完整原文 surface 的比例 |
| **实体替换合法率↑** | 金标实体出现次数为分母；对应输出区域须完整匹配本标签的 `[人名N]` 等合法占位符 |
| 临床保留率↑ | 原文位置上的 KEEP 片段逐字存活比例 |
| 危机保留率↑ | crisis 行的全部 KEEP 保留比例；不等于危机识别召回 |
| 非实体区逐字一致率↑ | 金标实体外字符未变且没有额外插入的样本比例 |
| 有效输出率↑ | 可解析且 extract 实体、occ 等合法的样本比例 |
| hard negative 过度脱敏率↓ | 无实体负例中输出发生改动或无效的比例 |
| 整句精确匹配↑ | 输出逐字等于金标 deid 的样本比例 |

实体替换合法率以实体两侧非实体字符为对齐锚点，先屏蔽原实体字符，防止“林雪→林霜”的共有字误作锚点；缺失边界保守失败，相邻实体按类型顺序完整匹配，无法拆分则整组失败。占位编号须为正整数；编号与金标是否一致另看会话编号及整句匹配。无效输出的全部实体记不合法；无实体时为 N/A。extract 的 apply 保证已生成替换的格式，但漏抽、抽错类型仍会失败，因此也计算此指标。dev-121 的近似假名反例现在 PERSON 合法率为0，整条实体合法率50%，原有零泄露和100% KEEP不能单独放行。

`adversarial` 标记明显自述脱敏规则/要求的长句：gold/dev 6条（125、136、140、143、147、150），gold/test 3条（130、139、149），合成训练数量见 STATS.json（tpl-119实际包含规则自述的第4句时才标记）。evaluate 的 `by_tag.adversarial` 单独报告；这些材料**不代表自然会谈分布**，tag 可重叠。完整扫描清单见 [SCAN_AUDIT2.json](SCAN_AUDIT2.json)，可运行 `../deepsleep/.venv/bin/python -m privacy.data.tools.scan_audit2` 复查；候选项是人工复核提示，不是自动判定临床含义。

v0.3 离线基线（百分比；旧数字作废，标签/KEEP分母变化不代表能力提升）。rules 保留普通日期和年龄，naive 继续打码，保留两者的过度脱敏差异：

| split | 基线 | n | 泄露率↓ | 实体替换合法↑ | KEEP↑ | 危机KEEP↑ | 非实体一致↑ | 有效输出↑ | HN过脱敏↓ | 整句匹配↑ |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| dev | rules | 153 | 50.00% | 31.82% | 99.27% | 100.00% | 87.58% | 99.35% | 0.00% | 59.48% |
| dev | naive | 153 | 30.91% | 0.00% | 47.20% | 66.67% | 15.69% | 100.00% | 90.77% | 3.92% |
| test | rules | 150 | 50.93% | 33.33% | 98.72% | 100.00% | 88.00% | 98.67% | 0.00% | 62.00% |
| test | naive | 150 | 33.33% | 0.00% | 55.50% | 59.26% | 22.67% | 100.00% | 76.92% | 10.00% |
| sessions | rules | 108 | 67.47% | 22.89% | 99.32% | 100.00% | 92.59% | 100.00% | 0.00% | 44.44% |

## 使用边界与复核

可用 `sft/dataset_info.json` 导入已有本地训练框架的 messages 格式；会话训练选 train_session_extract / dev_session_extract。字符 BIO 需要再对齐训练端 tokenizer。没有安装、下载或运行训练框架。test 与 gold/sessions 均不得进入训练或调参。

号码虽为生成但格式有效，现实分配状态未知，严禁拨打查询。身份证保留真实18位结构及校验位，不能据“虚构来源”断言现实不存在。机构现行名称、设备型号能力、药物用语未经联网核验。临床/路径/转介 tags 仅用于隐私保留分组，不是诊断金标，也不是处方训练素材。

difflib 是字符对齐启发式，重复文本可能有多种合理对齐；完整surface泄露率不覆盖部分号码、同音改写或跨位置身份复制。合成会话模板较窄；新增人工金标仍需第二标注者复核。负责人此前更新的7条 seed KEEP 已重新编译，本次按授权迁移 seed 源的5行，仅去除日期/年龄实体、增加 KEEP 和更新 tags/note，原文不变。test-127的危机原句被人名切开，现用独立片段同时保护主语/过去语境和完整风险/当前否定，仍建议语义复核，见 AUDIT_RESPONSE；不要把通过结构测试等同于临床语义审核完成。

全量版本扫描：`../deepsleep/.venv/bin/python -m privacy.data.tools.scan_v03`。覆盖全部编译文件、源标签与 SFT（包括 BIO、system prompt 和会话提取目标），禁止旧标签和新生成的旬/年龄段泛化；原文自带的描述按出现次数核对。结果见 [SCAN_V03.json](SCAN_V03.json)，gold 迁移行号与负例变化见 [MIGRATION_V03.json](MIGRATION_V03.json)。
