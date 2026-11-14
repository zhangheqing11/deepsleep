# 睡眠领域中文脱敏数据集：独立对抗式审核

审核日期：2026-11-14。唯一判定准则：`SPEC.md` v0.1。未联网、未执行 git 操作、未修改数据或工具；本报告是唯一写入的文件。所有脚本通过标准输入运行，禁用 Python 字节码和 pytest 磁盘缓存。以下药物和设备检查限于离线文字与搭配审核，不声称完成药品注册名称、适应证或硬件功能的外部核验。

## 总评

**不建议将当前全量数据直接作为定稿训练集或验收金标；可以保留为修订中的离线试验材料。** 347 条 gold 已逐条阅读，200 条 synth 已按固定随机种子逐条阅读；主要实体标签、年龄段、旬、称谓边界、occ 和危机原文总体做得较好，未发现 gold 中明确的学校/心理机构错标、号码漏标或危机词被金标改写。结构校验通过，四组历史基线完全复现，全部 dev_extract 回放 0/120 不一致。但合成同形词样本存在没有身份关系证据却强行 REDACT 的训练口径问题；多轮 keep 大量缺失或过碎；评测可把占位符当作临床保留、把新增 KEEP 片段当作泄露豁免。合成器还产生“喝了尼古丁”“买 Switch 了解睡眠”等明显拼接问题。应先修复 P0、补齐临床 keep、明确会话别名协议，再重建 SFT 和重算基线；当前“100% 保留”不能解释为临床内容完整无损。

## 问题清单

严重度：P0＝会使训练口径学错、身份泄露被漏计或危机语义破坏被错误通过；P1＝局部标注、协议或明显内容错误；P2＝风格、多样性或需进一步澄清的弱项。对缺少上下文的样本，优先补写原句使标签可判定，不凭猜测翻转标签。建议句子是供维护者修订数据源的方案，**不是允许脱敏模型改写来访者原文**。表内 `ents` 使用源文件的紧凑格式；修改后应重新编译 offsets/deid/SFT。

### 标注口径、工具与评测

| 严重度 P0/P1/P2 | 文件:id 或行 | 问题 | 建议修改（给出改后的 ents/keep 或改后句子） |
|---|---|---|---|
| P0 | synth/train.jsonl:synth-00041、synth-01843 | “说起苹果我就担心，晚上还吃了个苹果”没有雇主关系证据，首个“苹果”却一律 ORG。可指水果，不能作为确定金标。 | 01843 改句为“说起我工作的苹果公司我就担心，晚上还吃了个苹果，7点半了也难放下。”；`ents=[["苹果公司","ORG"]]`；keep 保留吃水果与钟点。00041 同样补明单位。 |
| P0 | synth/train.jsonl:synth-00049、synth-00845、synth-02141 | 美团被谈及/令人担心不等于来访者身份；这些句子只明确了 App 使用，首个美团却标 ORG。 | 00049 改“别把我的雇主美团和这事弄混，我还用美团订早餐；我到15点多才睡。”；`ents=[["美团","ORG",null,[1]]]`。00845、synth-02141 同样补“我的雇主”。 |
| P0 | synth/train.jsonl:synth-01042、synth-01241、synth-01545、synth-02443 | 小米同时可指公司、品牌和人，缺少关系提示，直接 PERSON 无法从文本判定。 | 分别将身份位置写为“闺蜜小米的事”“说起闺蜜小米”“提起闺蜜小米”；保持设备“小米手环”不动，按改后位置重新求 occ。 |
| P0 | synth/train.jsonl:synth-00449；sft/train_extract.jsonl:1949、2942（synth-01949、synth-02942） | “刚聊到腾讯/华为的事”并不证明是自己的单位；SFT 直接继承此歧义。 | 01949 改“12点半还没睡，刚聊到我在华为上班的事，华为手环显示我没睡好。”；`ents=[["华为","ORG",null,[1]]]`。腾讯样本同理补任职关系。 |
| P0 | tools/evaluate.py:13–22；gold/seed.jsonl:seed-027 | 泄露豁免在输出中重新搜任意 keep，不核对它是否源自原文的 KEEP 位置。把原文“闺蜜小米”改成“闺蜜小米手环”，未隐藏的人名也被设备词遮蔽，测得 leakage=0、keep=1。 | KEEP 豁免须绑定原文 occurrence 并对齐输出；新增/复制的 keep 不得获豁免。此反例应报人名泄露，或因原文非实体区域被改而拒绝通过。 |
| P0 | gold/seed.jsonl:seed-025；tools/evaluate.py:30–32 | keep 只存“不想活了”“把攒的安眠药一次全吃了”，漏“想过”。删“想过”后从想法变成像已发生行为，crisis_keep 仍为100%。金标原文并未被改，问题在监督/评测覆盖。 | `keep=["有时候真的不想活了","想过把攒的安眠药一次全吃了"]`；保留意图/行为、否定与时态范围。严格逐字保留危机语义跨度。 |
| P1 | tools/evaluate.py:30；gold/test.jsonl:test-055 | 删除“我接电话”里的“电话”，输出“这是[电话1]，我接一紧张……”仍 keep=100%，因为占位符含“电话”。 | 计 keep 前排除生成占位符区间，使用原文位置对齐；本句改 `keep=["我接电话一紧张","后半夜就没困意"]`。 |
| P1 | tools/evaluate.py:30；gold/sessions.jsonl:session-01-05 | 原句血氧83%未列入 keep，删掉全部血氧内容不会产生任何 keep 损失。28/72 会话行的 keep 为空。 | 按下方逐条表补齐，尤其 `keep=["昨天","医生","血氧，最低83%"]`；报告空 keep 行数，不能把无分母样本当作临床保留成功。 |
| P1 | tools/apply.py:14–15；tools/build_sft.py:extract_target；gold/sessions.jsonl:session-05-01、session-05-02、session-05-05、session-05-06 | 金标明确张伟=伟哥且编号正确；标准 extract 不带 replacement，apply 只按 surface 建映射，无法表达别名。按会话传 mapping 回放，4/72 行与金标不符。 | 保留现有金标。进入会话时需有可表达/验证 coreference 的协议；例如确定别名后映射 `{"PERSON":{"张伟":"[人名1]","伟哥":"[人名1]"}}`。当前由调用者预置只是前置条件，不能声称模型标准输出即可自动做到。 |
| P1 | tools/prompts.py:3；sft/train_extract.jsonl:1441；gold/test.jsonl:test-118 | “同一surface列一次”未说明同 surface 不同标签/泛化目标时如何处理；模型可能只给一类。嵌套机构的 occ 也未给例子。 | 改为“按(text,label,replacement)分组；不同语义分别输出，各自明确occ；不得重叠”。用“小米是我朋友，我在小米上班”展示 PERSON occ=[1] 与 ORG occ=[2]；用 test-118 展示学校只取首处。 |
| P1 | tools/prompts.py:2；gold/dev.jsonl:dev-102、dev-105；lexicons/keep/cities.txt | prompt 只显式说“生日”“城市国家”，省级地点与“出生年份/出生月份/出生日期”没有像 SPEC 那样明确列全。属于提示歧义，当前样本目标正确。 | 加“国家/省/市保留；出生年份、月份、年月日及生日不论精度均 DATE 替换”。AGE 与日历 DATE 仍按现规则。 |
| P1 | gold/test.jsonl:test-051；lexicons/ambiguous.jsonl:12（天天） | “我对象天天白班很困”“我弟天天睡着老踢腿”中的天天也可自然理解为每天。不是可靠的 PERSON 正例。 | test-051 改“我对象小名叫天天，上白班很困，他说是被我的呼噜吵的。”；`ents=[["天天","PERSON"]]`；词表改“我弟小名叫天天，他睡着老踢腿。” |
| P1 | tools/rules.py:63–75；gold/dev.jsonl:dev-096（对抗输入） | 日历 DATE 忘传 replacement 时，apply 无报错地当生日替换；`11月10号`→`[日期1]`。现有 SFT 无此错误，但后处理无法检出这类模型协议错误。 | 协议需显式区分 birthday/calendar，或上游做语境校验；本句必须 `{"text":"11月10号","label":"DATE","replacement":"11月上旬"}`。不可仅凭形状拒绝所有完整出生日期。 |
| P2 | tools/build_sft.py:37；gold/sessions.jsonl:session-01-01 至 session-12-06 | sessions 没进入 SFT；3035 条训练中姓氏称谓主要靠 seed-021、seed-032，synth 中此类为0。会话编号/别名没有实际训练覆盖。 | 增设独立会话训练/验证格式并防止会话拆分泄漏；补“张医生”“欧阳老师”等只取姓的正反例。不要将会话行孤立导出后从1重新编号。 |
| P2 | gold/dev.jsonl:dev-001 至 dev-120；gold/test.jsonl:test-001 至 test-120 | dev/test 每段类别顺序和标签数几乎镜像。8-gram 未检出强近重复，但测试结构较可预测，不能代表独立自然分布。 | 独立编写组合实体、隐含称谓、跨轮别名和更多混合句式；按来源/模板族划分评测，分层报告。 |
| P2 | tools/templates.yaml:tpl-071 至 tpl-078；synth/train.jsonl:synth-00039、synth-00042、synth-00045 | 同形语境模板反复刻意把相同词摆在一行；8个模板中仅071/075显式带角色。283/360 ambiguous 行缺少该角色字段，是复核候选，不能把283条都断言为错标。 | 所有训练正例增加足够语境；同时保留真正无身份关系的品牌讨论负例，避免只学习“第一次出现就删”。 |

### 逐条临床 KEEP 修订建议

下表只修改 keep，不修改实体或原句。当前 deid 的这些临床文字仍在；问题是评测未覆盖或只覆盖了零碎字词。P1 用于遗漏症状、指标、危机上下文、睡眠时长/行为及重要否定；P2 用于关系/泛指场所/相对时间等补强。词表反例中的“苹果”“明明”“罗翔”等本身有区分语境的作用，**不因不是症状而一概删除**；“睡”“名字”“登记”等缺少语义范围的 keep 则应替换。

| 严重度 P0/P1/P2 | 文件:id 或行 | 问题 | 建议修改（给出改后的 ents/keep 或改后句子） |
|---|---|---|---|
| P1 | gold/seed.jsonl:seed-001 | 现 keep=["昨天", "两点", "六点半"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["昨天", "两点才睡", "早上六点半又醒了", "再也睡不着"]` |
| P1 | gold/seed.jsonl:seed-010 | 现 keep=["华为手环", "深睡", "四十分钟", "五六次"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["华为手环", "深睡只有四十分钟", "夜里醒了五六次"]` |
| P2 | gold/seed.jsonl:seed-012 | 现 keep=["成都", "早上八点"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["成都", "邻居装修从早上八点吵到晚上"]` |
| P1 | gold/seed.jsonl:seed-016 | 现 keep=["这半年", "一个多小时"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["以前倒头就睡", "这半年躺下要一个多小时才睡着"]` |
| P1 | gold/seed.jsonl:seed-024 | 现 keep=["晚上", "腿里就像有虫子在爬", "起来走两圈", "白天"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["晚上一躺下腿里就像有虫子在爬", "非得起来走两圈才好一点", "白天反而没事"]` |
| P1 | gold/seed.jsonl:seed-030 | 现 keep=["咖啡至少三杯", "下午四点以后", "一罐红牛", "两杯"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["每天咖啡至少三杯", "下午四点以后", "一罐红牛", "晚上再小酌两杯"]` |
| P1 | gold/seed.jsonl:seed-031 | 现 keep=["ISI自评18分", "每周", "五个晚上", "半小时", "周一到周五", "七点"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["ISI自评18分", "每周有五个晚上入睡超过半小时", "周一到周五七点就得起"]` |
| P1 | gold/dev.jsonl:dev-001 | 现 keep=["两点多", "六点", "这周"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["这周", "两点多才能睡", "六点闹钟响了就心烦"]` |
| P1 | gold/dev.jsonl:dev-004 | 现 keep=["小米手环", "睡眠分数"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["小米手环", "反倒没盯着睡眠分数"]` |
| P1 | gold/dev.jsonl:dev-007 | 现 keep=["天天", "午睡两小时"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["天天午睡两小时", "夜里当然困意少了"]` |
| P1 | gold/dev.jsonl:dev-008 | 现 keep=["明明", "上床就又清醒"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["明明困得不行", "上床就又清醒了"]` |
| P1 | gold/dev.jsonl:dev-013 | 现 keep=["vivo手表", "昨夜"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["vivo手表", "昨夜没记录", "挺失落"]` |
| P1 | gold/dev.jsonl:dev-014 | 现 keep=["OPPO手环", "六小时"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["OPPO手环", "睡了六小时", "可我觉得没睡"]` |
| P1 | gold/dev.jsonl:dev-018 | 现 keep=["红牛", "浓茶", "夜班"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["红牛加浓茶撑夜班", "休息时还是很精神"]` |
| P1 | gold/dev.jsonl:dev-019 | 现 keep=["夜班", "抖音"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["下了夜班就刷抖音", "刷着刷着天又黑了"]` |
| P1 | gold/dev.jsonl:dev-026 | 现 keep=["医院", "大小夜", "白天", "睡不实"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["医院", "这周排大小夜", "白天想补觉又睡不实"]` |
| P1 | gold/dev.jsonl:dev-027 | 现 keep=["我妈", "午睡", "下午"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["我妈", "别午睡", "下午撑不住"]` |
| P1 | gold/dev.jsonl:dev-028 | 现 keep=["褪黑素", "3mg", "又精神"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["褪黑素吃了3mg", "只困了一会儿又精神了"]` |
| P1 | gold/dev.jsonl:dev-029 | 现 keep=["右佐匹克隆半片", "嘴苦", "半夜"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["右佐匹克隆半片", "嘴苦", "半夜还醒"]` |
| P1 | gold/dev.jsonl:dev-030 | 现 keep=["客厅", "等困意", "想工作"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["晚上", "客厅等困意", "回床上就又想工作"]` |
| P2 | gold/dev.jsonl:dev-031 | 现 keep=["原神", "十分钟", "一小时"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["睡前玩原神", "十分钟", "一小时"]` |
| P1 | gold/dev.jsonl:dev-040 | 现 keep=["纽约", "半夜"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["纽约", "连午饭都赶在半夜吃"]` |
| P1 | gold/dev.jsonl:dev-041 | 现 keep=["烟", "半夜", "心慌"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["睡前烟抽得有点凶", "半夜心慌醒来"]` |
| P2 | gold/dev.jsonl:dev-048 | 现 keep=["护士", "半夜", "憋醒"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["昨晚", "护士", "半夜仍然憋醒"]` |
| P1 | gold/dev.jsonl:dev-050 | 现 keep=["夜里", "白天"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["夜里总想白天说错的话"]` |
| P1 | gold/dev.jsonl:dev-058 | 现 keep=["熬", "数字都看花"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["熬得连数字都看花了"]` |
| P1 | gold/dev.jsonl:dev-074 | 现 keep=["天津", "凌晨"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["天津", "凌晨垃圾车响得很"]` |
| P1 | gold/dev.jsonl:dev-077 | 现 keep=["担心"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["总担心楼上掉东西"]` |
| P1 | gold/dev.jsonl:dev-103 | 现 keep=["开始失眠"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["不是开始失眠那天"]` |
| P2 | gold/dev.jsonl:dev-105 | 现 keep=["腿酸醒"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["最近常常腿酸醒"]` |
| P2 | gold/dev.jsonl:dev-106 | 现 keep=["午睡不了", "不愿关灯"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["午睡不了", "晚上也不愿关灯"]` |
| P2 | gold/dev.jsonl:dev-108 | 现 keep=["姐姐", "腿酸", "起来走"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["姐姐", "夜里腿酸到要起来走"]` |
| P2 | gold/dev.jsonl:dev-119 | 现 keep=["微信", "半夜"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["微信", "别半夜给我发消息"]` |
| P1 | gold/test.jsonl:test-004 | 现 keep=["小米手环", "凌晨3:40"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["小米手环", "凌晨3:40还醒着"]` |
| P1 | gold/test.jsonl:test-007 | 现 keep=["天天", "手机", "眼睛酸"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["天天捧着手机睡", "眼睛酸还舍不得放"]` |
| P1 | gold/test.jsonl:test-009 | 现 keep=["春眠不觉晓"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["春眠不觉晓", "我的觉怎么越春越少"]` |
| P1 | gold/test.jsonl:test-010 | 现 keep=["白天", "地铁", "床上一点睡意都没"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["白天坐地铁能睡过去", "床上一点睡意都没"]` |
| P1 | gold/test.jsonl:test-012 | 现 keep=["苹果", "短视频"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["睡前", "苹果", "吃完又点开短视频"]` |
| P1 | gold/test.jsonl:test-018 | 现 keep=["红牛", "通宵", "第二天"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["红牛当水喝扛通宵", "第二天人特别虚"]` |
| P1 | gold/test.jsonl:test-019 | 现 keep=["倒时差", "上海", "洛杉矶", "午饭"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["倒时差", "上海的夜里", "洛杉矶吃午饭"]` |
| P1 | gold/test.jsonl:test-024 | 现 keep=["GAD-7", "12分", "一闭眼就在盘工作"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["GAD-7我选出12分", "一闭眼就在盘工作"]` |
| P1 | gold/test.jsonl:test-025 | 现 keep=["沙发", "卧室", "醒透了"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["沙发上点头打瞌睡", "挪到卧室却醒透了"]` |
| P1 | gold/test.jsonl:test-026 | 现 keep=["出租车司机", "昼夜倒着来", "休班"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["出租车司机", "昼夜倒着来", "休班也睡不对点"]` |
| P1 | gold/test.jsonl:test-027 | 现 keep=["同事", "上午", "下午"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["同事", "上午像掉线", "下午倒挺能聊"]` |
| P1 | gold/test.jsonl:test-031 | 现 keep=["王者荣耀", "队友"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["王者荣耀赢一把又想下一把", "队友都下线我才睡"]` |
| P1 | gold/test.jsonl:test-033 | 现 keep=["十二点前后", "困一下"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["十二点前后困一下", "硬撑过去再想睡就难"]` |
| P1 | gold/test.jsonl:test-035 | 现 keep=["寝室", "床硬得慌"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["寝室", "床硬得慌", "总找不着舒服姿势"]` |
| P1 | gold/test.jsonl:test-037 | 现 keep=["脑子里开会停不住", "replay", "税不着"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["不是熬夜学习", "脑子里开会停不住", "反复 replay 白天的事", "税不着"]` |
| P1 | gold/test.jsonl:test-038 | 现 keep=["Apple Watch", "夜里", "醒"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["Apple Watch", "夜里亮一下我就醒", "后来摘了"]` |
| P2 | gold/test.jsonl:test-040 | 现 keep=["三号床", "打鼾", "耳塞", "没睡好"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["昨儿", "三号床", "打鼾", "耳塞", "没睡好"]` |
| P2 | gold/test.jsonl:test-062 | 现 keep=["睡眠分数", "脑子钝"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["睡眠分数", "最近脑子钝"]` |
| P1 | gold/test.jsonl:test-076 | 现 keep=["每晚", "惊醒"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["每晚电梯响就惊醒"]` |
| P1 | gold/test.jsonl:test-079 | 现 keep=["重庆", "晚上", "第二天"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["重庆", "晚上老想第二天怎么走"]` |
| P1 | gold/test.jsonl:test-081 | 现 keep=["腾讯视频", "两点"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["连腾讯视频都不看了", "两点收工"]` |
| P1 | gold/test.jsonl:test-086 | 现 keep=["读书", "睡前", "舍友"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["读书", "睡前听见舍友翻页都烦"]` |
| P1 | gold/test.jsonl:test-090 | 现 keep=["学生", "下午睡过头"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["学生", "下午睡过头就去不上晚课"]` |
| P1 | gold/test.jsonl:test-100 | 现 keep=["日记", "夜醒"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["日记", "夜醒比想的还多"]` |
| P1 | gold/test.jsonl:test-105 | 现 keep=["睡前", "白天"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["睡前却总想不起白天的事"]` |
| P1 | gold/test.jsonl:test-108 | 现 keep=["睡前", "心慌"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["睡前一盘算房租就心慌"]` |
| P1 | gold/test.jsonl:test-110 | 现 keep=["爷爷", "午后打盹", "夜里"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["爷爷", "午后打盹挺久", "夜里睡一会儿就起来"]` |
| P2 | gold/test.jsonl:test-119 | 现 keep=["邮件", "半夜"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["邮件", "别催我半夜回复"]` |
| P1 | gold/sessions.jsonl:session-01-01 | 现 keep=["打鼾"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["老公", "最近打鼾", "老被吵醒"]` |
| P1 | gold/sessions.jsonl:session-01-02 | 现 keep=["白天"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["白天开车也犯困"]` |
| P2 | gold/sessions.jsonl:session-01-03 | 现 keep=[]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["天津", "卧室很安静"]` |
| P1 | gold/sessions.jsonl:session-01-05 | 现 keep=[]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["昨天", "医生", "血氧，最低83%"]` |
| P2 | gold/sessions.jsonl:session-01-06 | 现 keep=[]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["医生"]` |
| P1 | gold/sessions.jsonl:session-02-01 | 现 keep=["精神"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["最近一到床上就精神"]` |
| P1 | gold/sessions.jsonl:session-02-02 | 现 keep=[]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["老师", "别在床上改作业"]` |
| P1 | gold/sessions.jsonl:session-02-03 | 现 keep=[]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["床边就是电脑"]` |
| P1 | gold/sessions.jsonl:session-02-04 | 现 keep=["睡"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["老师", "昨天", "睡眠日记"]` |
| P1 | gold/sessions.jsonl:session-02-05 | 现 keep=[]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["客厅", "不困就去坐"]` |
| P1 | gold/sessions.jsonl:session-02-06 | 现 keep=["睡", "名字"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["昨晚只睡四小时"]` |
| P1 | gold/sessions.jsonl:session-03-01 | 现 keep=["夜班"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["上夜班真没法睡"]` |
| P2 | gold/sessions.jsonl:session-03-02 | 现 keep=[]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["做运维"]` |
| P1 | gold/sessions.jsonl:session-03-03 | 现 keep=["白天"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["室友", "白天打电话容易吵醒我"]` |
| P1 | gold/sessions.jsonl:session-03-04 | 现 keep=["夜班"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["下周仍排夜班"]` |
| P2 | gold/sessions.jsonl:session-04-01 | 现 keep=["小米手环"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["闺蜜", "小米手环"]` |
| P1 | gold/sessions.jsonl:session-04-02 | 现 keep=["深睡"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["别整天盯深睡数据"]` |
| P1 | gold/sessions.jsonl:session-04-05 | 现 keep=["憋醒"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["医生", "有没有憋醒"]` |
| P1 | gold/sessions.jsonl:session-04-06 | 现 keep=[]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["医生", "听见过我憋气"]` |
| P1 | gold/sessions.jsonl:session-05-01 | 现 keep=["工作"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["朋友", "躺下老想工作"]` |
| P1 | gold/sessions.jsonl:session-05-02 | 现 keep=["白天"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["最近白天很困"]` |
| P1 | gold/sessions.jsonl:session-05-03 | 现 keep=["睡", "工作"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["临睡还在回消息"]` |
| P1 | gold/sessions.jsonl:session-05-04 | 现 keep=["晚上"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["晚上开线上会"]` |
| P1 | gold/sessions.jsonl:session-05-05 | 现 keep=["工作"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["老婆", "早点停工作"]` |
| P1 | gold/sessions.jsonl:session-05-06 | 现 keep=[]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["又熬夜了", "难受"]` |
| P1 | gold/sessions.jsonl:session-06-01 | 现 keep=[]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["微信", "最近群聊停不住"]` |
| P2 | gold/sessions.jsonl:session-06-02 | 现 keep=[]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["失眠帖"]` |
| P2 | gold/sessions.jsonl:session-06-03 | 现 keep=["王者荣耀"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["同事", "王者荣耀"]` |
| P2 | gold/sessions.jsonl:session-06-04 | 现 keep=[]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["下班"]` |
| P1 | gold/sessions.jsonl:session-06-05 | 现 keep=[]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["昨天", "玩到一点"]` |
| P1 | gold/sessions.jsonl:session-06-06 | 现 keep=[]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["已经卸载了", "我还想刷"]` |
| P1 | gold/sessions.jsonl:session-07-01 | 现 keep=["睡不实"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["考试前睡不实"]` |
| P1 | gold/sessions.jsonl:session-07-02 | 现 keep=[]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["老师", "别一直想着分数"]` |
| P2 | gold/sessions.jsonl:session-07-03 | 现 keep=["早上六点"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["宿舍", "早上六点"]` |
| P2 | gold/sessions.jsonl:session-07-04 | 现 keep=[]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["上回", "老师", "我妈"]` |
| P1 | gold/sessions.jsonl:session-07-05 | 现 keep=[]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["我妈", "以前也焦虑"]` |
| P1 | gold/sessions.jsonl:session-07-06 | 现 keep=["睡", "晚上"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["晚上总问我睡没睡"]` |
| P1 | gold/sessions.jsonl:session-08-02 | 现 keep=["晚上"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["晚上也静音", "倒班"]` |
| P1 | gold/sessions.jsonl:session-08-04 | 现 keep=[]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["这周连续大夜"]` |
| P1 | gold/sessions.jsonl:session-08-05 | 现 keep=["白天", "护士"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["搭班", "护士", "白天也睡不着"]` |
| P1 | gold/sessions.jsonl:session-08-06 | 现 keep=["护士"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["护士", "手环摘了试试"]` |
| P1 | gold/sessions.jsonl:session-09-02 | 现 keep=[]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["那晚就走了好几趟"]` |
| P2 | gold/sessions.jsonl:session-09-04 | 现 keep=[]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["医生"]` |
| P1 | gold/sessions.jsonl:session-09-05 | 现 keep=["晚上"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["以前没这样", "最近晚上难受"]` |
| P1 | gold/sessions.jsonl:session-09-06 | 现 keep=[]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["走到街口才好点"]` |
| P1 | gold/sessions.jsonl:session-10-01 | 现 keep=["以前觉得活着没意思，现在没有了"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["以前觉得活着没意思，现在没有了", "睡还是差"]` |
| P2 | gold/sessions.jsonl:session-10-02 | 现 keep=[]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["医生", "知道那段经历"]` |
| P1 | gold/sessions.jsonl:session-10-04 | 现 keep=[]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["医生", "问现在还有没有"]` |
| P2 | gold/sessions.jsonl:session-10-06 | 现 keep=["登记", "名字"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["别把我以前那段话删了"]` |
| P1 | gold/sessions.jsonl:session-11-01 | 现 keep=[]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["早班常困"]` |
| P1 | gold/sessions.jsonl:session-11-02 | 现 keep=["枕头"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["枕头", "下班偶尔眯会儿"]` |
| P1 | gold/sessions.jsonl:session-11-03 | 现 keep=[]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["排班最近不固定"]` |
| P1 | gold/sessions.jsonl:session-11-04 | 现 keep=["犯困"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["同事", "开车得注意犯困"]` |
| P1 | gold/sessions.jsonl:session-12-01 | 现 keep=["睡", "生日"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["那天也没睡好"]` |
| P2 | gold/sessions.jsonl:session-12-04 | 现 keep=["时差", "日期"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["别把时差删了"]` |
| P1 | gold/sessions.jsonl:session-12-05 | 现 keep=["凌晨"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["凌晨还收工作邮件"]` |
| P1 | gold/sessions.jsonl:session-12-06 | 现 keep=["睡"]；缺少完整临床关系、数值/否定或保留范围过碎。 | `keep=["提醒关了", "今晚试试早点睡"]` |

### 合成内容、词表与自然度

| 严重度 P0/P1/P2 | 文件:id 或行 | 问题 | 建议修改（给出改后的 ents/keep 或改后句子） |
|---|---|---|---|
| P1 | synth/train.jsonl:synth-00005、synth-00010、synth-00135、synth-00905、synth-01429、synth-02128、synth-02627 | 通用“喝了”模板填入香烟/烟/电子烟/尼古丁。02627 在随机200条内，其余为全量定向追查。 | 00005 改“两班倒结束本来困，抽了香烟反倒清醒。”；00010/00135/02128 同样用“抽了烟”；00905 用“抽了香烟”；01429 用“用了电子烟”；02627 改“用了含尼古丁的产品后到9点多还不困，怪难受的。”；均 `ents=[]`，keep 保留班次/物质/时点/清醒。 |
| P2 | synth/train.jsonl:synth-00901 | “喝了巧克力”可能指热巧克力但原文未说；不是确定药理错误。 | 改“固定夜班结束本来困，喝了热巧克力反倒清醒。”或“吃了巧克力”；`ents=[]`，keep 依新句同步。 |
| P1 | synth/train.jsonl:synth-00101、synth-00319、synth-00419、synth-01628、synth-02717 | “买Switch/PS5本想了解睡眠…查数据”是设备池与睡眠监测模板错配；未说明经其他设备或软件查看。 | 如00101改“买Switch本想放松，结果一到22点半还在玩。”；或保留原骨架改成明确的睡眠监测设备。`ents=[]`；keep 用改后完整行为片段。 |
| P1 | synth/train.jsonl:synth-01931、synth-02637 | “拿Oura Ring看时间…盯着屏幕”语义把戒指当作有屏幕手表。 | 改“拿手机看Oura Ring的数据，已经11点多了，眼睛还盯着屏幕。”；02637保留0点多；`ents=[]`。无需改动品牌 KEEP 策略。 |
| P1 | synth/train.jsonl:synth-00608 | “一躺进被窝就起床困难”把起床症状接到入床触发上；时间事件不合理。 | 改“一躺进被窝就脑子停不下来，挪到沙发倒想睡，已经18点了。”；`keep=["一躺进被窝就脑子停不下来","挪到沙发倒想睡","18点"]`。 |
| P1 | synth/train.jsonl:synth-00721、synth-01804、synth-02037 | “在客厅坐到0点，还早醒”“坐到3点多，还越睡越累”“坐到12点半，还呼吸暂停”把持续清醒场景与睡眠症状直接拼接，缺少先后/转述。 | 00721改“躺了挺久才肯离床，在客厅坐到0点，还没困意。”；01804改“……还觉得累”；02037改“……还担心睡着后呼吸暂停”；keep 应包含完整事件，`ents=[]`。 |
| P1 | synth/train.jsonl:synth-00212、synth-00409、synth-00426、synth-00551、synth-01654、synth-02414、synth-02635、synth-02955 | “昨晚”与14/15/16点搭配不合钟点语义（02955=昨晚15点）。这8条是明确候选；02954的17点半可能为傍晚，不与它们混作硬错误。 | 用“昨天下午”匹配13–16点，或将时点改为21–23点；00551/01654/02955有危机片段，修源数据时危机字词原样保留。重建 deid 与 keep，不能让脱敏器自行纠时。 |
| P1 | synth/train.jsonl:synth-02004、synth-02518 | “我是待业…早班排得多”“退休人员…固定夜班排得多”，无兼职/返聘上下文。 | 02004改“我最近刚开始做保安，早班排得多，困劲全错位了。”；02518改“我退休后又去做保安，最近固定夜班排得多，困劲全错位了。”；`ents=[]`，keep 新职业/班次/睡眠体验。 |
| P2 | synth/train.jsonl:synth-02417 | 全职家长“晚班排得多”可能是照顾孩子的比喻，但未给该情境。 | 改“我是全职家长，最近晚上总得起来照顾孩子，困劲全错位了。”；keep 包含关系、夜间照护与节律。 |
| P2 | synth/train.jsonl:synth-01436 | “下属睡着以后我才敢开七猫小说”无共同住宿/值守背景，关系池机械拼接。 | 改“孩子睡着以后我才敢开七猫小说，一看就是大半夜。”，或明确同住值守语境；`ents=[]`。 |
| P2 | synth/train.jsonl:synth-00581、synth-02475、synth-01771 | 医保卡用了ZY前缀、睡眠科排号用了XH、病历登记号用了18位身份证结构；都仍属 ID_NUM，不是标签错，但混用内部生成类别。 | 00581 使用YB格式的虚构医保卡；02475使用门诊MZ格式；01771如确实是身份证就改“登记的身份证号…”。号码格式与字段用途分池，避免身份信息拼接成为假常识。 |
| P2 | synth/train.jsonl:synth-00479、synth-01522、synth-01795、synth-02499、synth-02520、synth-02727 | “玩拼多多”“刷百度网盘/支付宝/和平精英”“看崩坏星穹铁道/梦幻西游”统一动词套用；有些现实中可成立，但缺少活动对象导致模板味强。 | 00479“睡前总逛拼多多”；01522“在百度网盘看视频没刹住”；01795“刷支付宝里的内容”；02499“玩和平精英”；02520/02727改“玩…”或“看…直播”。身份实体不变。 |
| P2 | synth/train.jsonl:synth-00116、synth-00304、synth-00617、synth-00802、synth-00996、synth-02028、synth-02515 | 症状与时间槽自由组合：如“现在声音忽大忽小”缺声源，“想到聚会就非得活动腿”突兀；14点回消息/18点半醒着本身并非睡眠异常。 | 00617改“室友说我的呼噜声音忽大忽小……”；00996改“想到那天要聚会就紧张”；白天醒着类增加夜班/补觉背景。00116、synth-00304的并列症状不算明确错误，仅作为自然度复核例。 |
| P2 | synth/train.jsonl:synth-00420、synth-00611、synth-01720；lexicons/keep/drugs_substances.txt | 药物词表类别是“药物或补充剂”，没有把这些词明示为“失眠药”；但“吃过X，可到某点还清醒”广泛填充非单一催眠用途的词，会暗示立即助眠预期。当前不能据此断言用药错误。 | 这类统一改中性自述，例如“我在用度洛西汀，昨晚5点半还醒着，想把情况记下来。”；药名依 SPEC KEEP，不能改成身份实体。用途与口语品牌名请负责人离线复核。 |
| P2 | lexicons/ambiguous.jsonl:4、7、15、17、56 | “协和弦”“这首虚构曲子”“虚构播客”“窗户朝南开”等为凑同形词，口语和自然度较弱；不能把自然语言中的“虚构”提示当识别作品的捷径。 | 4改“夜里做协和和弦的听辨练习，越听越精神”；7/15/56去掉句内“虚构”，把来源说明放 note；17改“窗户是朝南开的，天一亮就睡不着”。 |
| P2 | lexicons/keep/cities.txt:朝阳、黄山；lexicons/redact/nicknames.txt:天天、明明、白天、静静 | 这些不是词表本身错放，而是同形语境依赖。README 已注明不能无条件白名单/黑名单。县区/人名语境仍需区别。 | 保留词条，在词表结构上明确 `context_required` 或给正反例；“辽宁朝阳市”KEEP、“北京朝阳区”ADDRESS、“同事黄山”PERSON。不要整表直接用于字符串替换。 |
| P2 | gold/seed.jsonl:seed-018、seed-035；synth/train.jsonl:synth-00060、synth-01874、synth-02785；tools/generate.py:17–31 | 人工生成只能证明来源方式，不能证明号码现实未分配。synth有69个18位身份证格式实例、18个长银行卡实例，采用真实地域码/卡号前缀与校验位；手机也采用正常号段。未发现姓名+电话同句，但仍有偶然碰撞风险。 | 保留“合成来源/禁止联系”说明，避免“绝不对应真人”的绝对保证；由负责人选择经批准的测试标识策略并统一替换，复算 entities/deid。不得联网查询或拨号来证实。 |
| P2 | gold/sessions.jsonl:session-01-01 至 session-12-06 | 多轮几乎每轮重复完整身份片段、全部72轮都有实体；现实中连续6轮都给身份并不常见。未含自然无身份跟进轮。 | 增补“昨晚也是”“后来几点醒？”等无实体轮，使会话编号与空输出都受测；整会话分组保留。 |

## 统计与复现结果

### 覆盖范围与抽样方法

- gold 全量逐条阅读：seed-001–035、dev-001–120、test-001–120、12个session各6轮，共347条。逐条查看原文、实体surface/label/replacement/start、keep，并结合原文检查身份语义；deid/offset的逐字一致性由全量重放和校验器另行验证。没有把只跑校验器称作人工审核。
- synth 随机样本：从原文件顺序3000行中，`sorted(random.Random(20261114).sample(range(3000),200))`，无放回200条，逐条阅读相同字段。另对发现的模板问题定向扫描，报告中区分随机样本与后续发现；没有把规则扫描当作其余2800条人工审核。
- SFT 随机：种子20261115，从train的3035行抽20个行号，配对阅读 extract 和 rewrite，因此是20条extract+20条rewrite。全量逐字回放另外覆盖 train/dev。
- lexicons：阅读全部KEEP/REDACT文本、YAML、56条ambiguous（56种surface），检查语义边界及正反例。没有把“词表有同形词”自动当错放。

| 文件 | 样本 | 实体出现数 | hard_negative | ambiguous | crisis | 空keep |
|---|---:|---:|---:|---:|---:|---:|
| gold/seed.jsonl | 35 | 27 | 14 (40.00%) | 7 (20.00%) | 2 (5.71%) | 1 |
| gold/dev.jsonl | 120 | 82 | 45 (37.50%) | 29 (24.17%) | 9 (7.50%) | 0 |
| gold/test.jsonl | 120 | 82 | 45 (37.50%) | 32 (26.67%) | 9 (7.50%) | 0 |
| gold/sessions.jsonl | 72 | 87 | 0 | 0 | 2 (2.78%) | 28 |
| synth/train.jsonl | 3000 | 2396 | 1140 (38.00%) | 360 (12.00%) | 239 (7.97%) | 0 |

SPEC 唯一明确的样本比例门槛是 hard_negative≥30%。synth、seed、dev、test分别达标；全体1244/3347=37.17%。若把所有gold合成一个评测集，则104/347=29.97%，略低于30%；sessions单独为0%。应明确会话集是否豁免，不能悄悄选分母。**SPEC 没规定 ambiguous/crisis 最低占比，不能据其他文件的目标宣称其“按SPEC达标”。** 作为实现自检，现有测试中synth的ambiguous≥240、带身份crisis≥90均满足：360、150；150/3000=5%。239条crisis包含89条无身份样本，这些类别互相重叠。

随机200条中：hard_negative=83 (41.5%)、ambiguous=20 (10%)、crisis=17 (8.5%)。全量hard_negative无已标实体与原文改写；人工读过的104条gold负例及83条随机synth负例未发现确定身份漏标（“三号床”另列口径问题）。其余synth负例只做结构/模板核查，不能断言语义零漏标。

### 骨架多样性

按生成note中的tpl-id追溯到 `templates.yaml` 的未填槽text，90个不同骨架均被使用（不是把填入不同姓名的句子算作新模板）。最常见tpl-076=51/3000=1.70%；其次tpl-073=49、tpl-074=48、tpl-063=48、tpl-041=47。前10骨架共468/3000=15.60%。90个骨架仍以少量语法结构重复填槽，不等于90种独立临床叙事。ambiguous只组合6组同形对；缺角色字段的模板实例283/360=78.61%，为重点复核候选。

### 校验和测试

Python使用指定的 `../deepsleep/.venv/bin/python`，版本3.14.5，未使用fallback。

1. `PYTHONDONTWRITEBYTECODE=1 ../deepsleep/.venv/bin/python -m privacy.data.tools.validate`：退出码0，校验通过。
2. 为执行 `python -m pytest -q tests/test_privacy_data.py` 的同一测试集合且严格不写文件，使用Python审计钩子禁止写入，增加 `--capture=sys -p no:cacheprovider -p no:logging` 并禁用第三方插件自动加载。最初默认fd捕获尝试创建临时文件，随后默认日志尝试写入，也都被拦截；关闭这些机制后：**28 passed, 1 error in 0.78s**。唯一error发生在 `test_validator_handles_broken_json_and_detects_split_leaks` 的tmp_path setup，原因是写入被审计禁止，不是数据断言失败。
3. 追加只在进程内运行的pytest插件，将该用例tmp_path的mkdir/write_text/open/glob转为字典+StringIO，不写任何文件，保持该用例的断言和业务函数不变；全套 **29 passed in 0.72s，退出码0**。此为内存文件系统适配后的结果，不冒充未经适配的原命令完全通过，也不能证明真实磁盘临时文件行为。
4. 全量src→compiled一致性、entities重放、AGE/DATE泛化、occ、所有导出回放等均由现有测试通过。样本中AGE共122次、DATE共262次，未发现现有replacement十岁段/旬的确定错误。gold中25行有单字姓氏称谓，未见“张医生”把医生一起删掉；synth没有该类称谓样本。

### SFT 与会话回放

| 导出文件 | 条数 | 与金标不一致 | apply诊断 |
|---|---:|---:|---:|
| train_extract | 3035 | 0 | 0 |
| dev_extract | 120 | 0 | 0 |
| train_rewrite | 3035 | 0 | 不适用，直接比金标 |
| dev_rewrite | 120 | 0 | 不适用，直接比金标 |

每个导出文件只有1种system prompt；抽检20对中，输出均与已有金标一致，包括occ与生日/日历日期的不同形式。**一致只能证明导出正确，不能消除上游错误金标**；1949/2942等歧义会原样进入训练。extract不能在不改变协议/预先提供别名的情况下还原全部会话：按顺序传mapping得到4/72不一致，全部来自session-05的张伟/伟哥别名及其后编号漂移。

抽检SFT的1-based行号：104, 190, 389, 662, 727, 788, 983, 1233, 1441, 1853, 1949, 2115, 2479, 2576, 2708, 2794, 2857, 2873, 2877, 2942。

全部dev_extract回放脚本（只读，不写辅助文件）：

```python
import json
from pathlib import Path
from privacy.data.tools.apply import apply
p = Path('privacy/data')
read = lambda f: [json.loads(x) for x in (p/f).read_text().splitlines()]
gold = {r['text']: r for r in read('gold/dev.jsonl')}
bad, diagnostics = [], []
for line, row in enumerate(read('sft/dev_extract.jsonl'), 1):
    text = row['messages'][-2]['content']
    target = row['messages'][-1]['content']
    errors = []
    output, _ = apply(text, target, errors=errors)
    if output != gold[text]['deid']:
        bad.append((line, gold[text]['id']))
    diagnostics.extend(errors)
print(len(bad), len(diagnostics))  # 0 0
```

### 指标定义与对抗反例

- `exact_match`、hard_negative输出不等于输入、按keep计临床/危机保留以及无分母返回None，基本对应SPEC §6。危机率的分母是crisis样本的**全部keep**，包含普通时点；这是SPEC定义，不能擅自改成危机词准确率。
- 泄露遍历所有金标label，未发现故意漏掉AGE、DATE、PHONE或ID_NUM等类别。按重复实体出现次数计数。
- 同形词KEEP豁免是实现增加的解释，SPEC未给计算公式。其目的合理，但在输出任意位置重新匹配豁免范围使泄露率可能虚低，需原文occurrence对齐。
- `k in output`满足SPEC字面定义，却不能保证原位置存活、次数、顺序或否定语义；故占位符假匹配、短keep、危机片段缺时态均需修正或补充完整性指标。不能仅靠提升F1掩盖。
- 模型缺预测时以原文计分且给diagnostics；这使负例仍可能拿满分。应同时报告预测有效率，不把未产生有效输出视为端到端成功。该实现不是静默忽略样本。

| 对抗样本 | 内存构造的错误输出 | 实测 | 含义 |
|---|---|---|---|
| seed-027 | 原文中的“闺蜜小米”换成“闺蜜小米手环”，其余不变 | leakage=0；keep=100%；exact=0 | 人名未隐藏，被新增KEEP遮蔽 |
| test-055 | 金标中“接电话”改成“接” | leakage=0；keep=100%；exact=0 | 占位符[电话1]冒充原文“电话” |
| seed-025 | 原文删去“想过” | crisis_keep=100%；keep=100%；exact=0；HN过脱敏=100% | 危机保留指标没有捕获想法/行为差别，其他指标仍能报错，不能只看crisis率 |

这些反例未写回数据。两组基线都是rewrite输出，所以上述子串/原位问题会直接影响它们的计分可信范围。纯字面泄露也检测不了号码只剩大部分、去掉空格或同音转写；BASELINES已披露部分这一限制，应保持披露，不以其低泄露率做隐私安全结论。

### BASELINES复现

直接调用 `evaluate(rows, baseline_name=...)`，未运行会重建文件的make目标，未传`--json`。dev/test × rules/naive 四个结果与 `baselines/*.json` **整个JSON对象相等**，包括by_tag、by_label、counts和diagnostics；Markdown所列百分比均吻合。

| 数据集 | 基线 | 泄露率 | 临床保留率 | 危机保留率 | HN过脱敏率 | 整句匹配 |
|---|---|---:|---:|---:|---:|---:|
| dev | rules | 50.00% (41/82) | 99.63% (272/273) | 100% (19/19) | 0% (0/45) | 60.83% (73/120) |
| dev | naive | 19.51% (16/82) | 63.00% (172/273) | 84.21% (16/19) | 86.67% (39/45) | 5.00% (6/120) |
| test | rules | 47.56% (39/82) | 100% (282/282) | 100% (19/19) | 0% (0/45) | 61.67% (74/120) |
| test | naive | 19.51% (16/82) | 67.02% (189/282) | 68.42% (13/19) | 66.67% (30/45) | 12.50% (15/120) |

规则基线预测函数只读取原text、正则和词表，未用金标entities/keep/tags；打分使用keep属评测设计。naive是刻意粗暴对照，不是某个真实产品。当前结果可复现，不代表口径漏洞不存在。

### test 与 dev/synth 近重复

对原始text按Python Unicode字符取连续8-gram，保留标点、空格、数字、大小写，不先脱敏；比较全部120×120=14,400对与120×3000=360,000对。Jaccard=交集/并集；containment=交集/min(两侧8-gram数)。阈值预先明确：Jaccard≥0.3为较宽近重复候选，≥0.5为较强；containment≥0.8为短句被包含候选。以下不是编辑距离结论。

| 比较 | 完全相同 | 至少1个共同8-gram（配对数/涉及test行） | J≥0.3 | J≥0.5 | containment≥0.8 |
|---|---:|---:|---:|---:|---:|
| test vs dev | 0 | 10 / 8 | 0 | 0 | 0 |
| test vs synth | 0 | 293 / 24 | 0 | 0 | 0 |

最高test/dev：test-119 ↔ dev-066，J=0.145161，共9个8-gram，主要来自`@example.invalid`；test-043 ↔ dev-111，J=0.130435，共同危机表达。最高test/synth：test-119 ↔ synth-00657，J=0.186441，共11个8-gram，主要为邮箱格式；test-077 ↔ synth-02888，J=0.171429，共6个8-gram，重复地址组件。**该判据未发现强近重复/整句泄漏**，不能把共享安全词或邮箱后缀直接算训练泄漏；它也不能排除语义改写和镜像题型分布。

可复现核心：`G=lambda s:{s[i:i+8] for i in range(len(s)-7)}`；对所有跨split对计算集合交/并，不使用随机抽样。SFT导出与test原文的完全相交也为0（现有测试通过）。

### 危机、词表与虚构来源的专项结论

- gold的22条crisis及随机synth的17条crisis逐条检查，身份替换没有改掉危机字词；全量239条synth crisis的显式keep通过原样检查。过去已结束、否定与第三方转述多数有保留；seed-025的keep语义范围不足已列P0。未把“新闻有人自杀”“我是不是快死了”改判为本人的自杀意图，crisis在这里应仅是保留测试tag。
- 所读gold与随机synth里，具体学校标SCHOOL、医疗/心理机构标HOSPITAL、城市保留、连续细地址整体替换、年龄段/旬规则总体正确；没有发现确定的occ错选。test-118中的学校与医院嵌套位置可正确回放。
- KEEP词表没有发现确定的具体个人身份条目；REDACT的姓、名字组件、昵称不是无条件要删的普通词黑名单。词表README的语境限定至关重要。`朝阳`、`黄山`不应离开上下文判错。
- 药名词表将相关词归为“药物或补充剂”“饮品或物质”，未统一宣称为失眠药；未发现可以仅凭当前材料确认的药名错字。它混有抗抑郁/其他用途药物、补充剂、俗称、药物大类及饮品品牌，作为KEEP素材本身不违反SPEC；模板需要更细的动作/剂型/用途限制。未发现随机样本中的离谱具体药量，synth药物模板也没有随机拼接剂量。
- 未发现真实来访来源痕迹；人工注释与生成器支持“人工编写/模板生成”的来源声明。全量gold和synth单句同时标PERSON与PHONE的数量均为0；这不证明所有文本绝无真人碰撞。正常手机号、地址、校验有效证件/银行卡仍可能偶合，不能离线证实“号码未分配”。没有拨打、查询或联网核验。

## 需要心理学背景项目负责人拍板的口径

1. **保持SPEC现有暂定值，或正式修订**：城市保留、日历日期泛化旬、年龄十岁段、公众人物保留、带编号占位符。审核没有擅自改这些规则；10岁→十几岁、20岁→二十多岁虽口语近似，当前按SPEC是正确金标。
2. **危机keep必须涵盖多大语义跨度**：seed-025须包含“想过”；是否统一要求包含全部否定、过去/现在、意图/行为、第一/第三人称范围？危机率是否仍按所有keep计算，同时新增危机跨度完整性指标？新增指标需修SPEC，不能只改代码。
3. **身份关系不明确的品牌讨论**：synth-01843等应补明确的任职/人际关系，还是保留为无法判定样本并退出确定金标？仅提品牌/机构是否就REDACT，SPEC的“指向这个人是谁”与示例尚不足以覆盖所有讨论情境。
4. **病房床号**：test-040和ambiguous第36条把“三号床/3号床”KEEP。SPEC未把床号列为ID_NUM，但它也可能局部指向病人；应明确其与病历/住院号的区别。本次没有按扩展隐私标准擅自判漏标。
5. **会话集比例与覆盖**：hard_negative≥30%是对训练总体、每个split还是每个会话文件？sessions应否加入无身份轮？把gold含sessions合计恰为29.97%，应明确分母。
6. **crisis和路径/转介tag含义**：新闻转述、已结束意念、怕死、自我负担感均可作为“必须保留”材料，但不能被后续复用为已确认的危机/转介标签。ref_R2中腿酸、ref_R1中疲劳等本次不作临床判定，建议与隐私评测标签清楚隔离。
7. **设备、药品、症状模板的临床自然度**：将“吃过X仍清醒”的叙述、不同药类、夜班补觉、呼吸暂停自述和稀有症状交给负责人筛选；不把当前脱敏数据当作处方或临床因果训练材料。
8. **别名共指协议**：张伟/伟哥怎样由模型输出、harness如何在同会话中验证并维护映射？当前gold正确而标准extract无法表达，需先定协议再扩展会话SFT。
9. **号码虚构策略**：是否允许格式/校验有效但现实分配状态未知的合成号码；是否采用批准的测试标识池？不能仅靠“随口编的”文案作无真人保证。
10. **字面指标与逐字保留原则的验收关系**：修复KEEP占位符假匹配、occ豁免范围后，是否把非实体区域逐字一致和有效输出率设为独立门槛？不要把“整句匹配仅供参考”理解为允许危机上下文被改变。

## 附录：抽样清单与审计快照

200条随机synth ID（非定向追加样本）：

```text
synth-00030, synth-00049, synth-00101, synth-00109, synth-00116, synth-00118, synth-00125, synth-00162, synth-00186, synth-00231
synth-00236, synth-00250, synth-00263, synth-00299, synth-00304, synth-00364, synth-00420, synth-00439, synth-00449, synth-00463
synth-00464, synth-00479, synth-00506, synth-00511, synth-00512, synth-00529, synth-00574, synth-00578, synth-00581, synth-00601
synth-00605, synth-00608, synth-00611, synth-00613, synth-00616, synth-00617, synth-00630, synth-00633, synth-00671, synth-00692
synth-00706, synth-00718, synth-00721, synth-00722, synth-00723, synth-00727, synth-00732, synth-00737, synth-00752, synth-00756
synth-00783, synth-00792, synth-00802, synth-00814, synth-00834, synth-00842, synth-00845, synth-00865, synth-00900, synth-00903
synth-00925, synth-00966, synth-00967, synth-00969, synth-00979, synth-00987, synth-00996, synth-01042, synth-01054, synth-01055
synth-01085, synth-01089, synth-01105, synth-01111, synth-01114, synth-01145, synth-01154, synth-01189, synth-01193, synth-01199
synth-01204, synth-01211, synth-01241, synth-01253, synth-01318, synth-01325, synth-01336, synth-01363, synth-01369, synth-01436
synth-01448, synth-01461, synth-01464, synth-01484, synth-01489, synth-01493, synth-01500, synth-01505, synth-01518, synth-01522
synth-01531, synth-01540, synth-01545, synth-01553, synth-01573, synth-01601, synth-01617, synth-01627, synth-01652, synth-01660
synth-01720, synth-01724, synth-01731, synth-01740, synth-01761, synth-01771, synth-01773, synth-01774, synth-01793, synth-01795
synth-01798, synth-01804, synth-01818, synth-01843, synth-01855, synth-01863, synth-01865, synth-01874, synth-01886, synth-01956
synth-01970, synth-01971, synth-01984, synth-01995, synth-01997, synth-02019, synth-02021, synth-02028, synth-02037, synth-02050
synth-02069, synth-02071, synth-02081, synth-02094, synth-02099, synth-02124, synth-02125, synth-02141, synth-02157, synth-02192
synth-02213, synth-02268, synth-02278, synth-02281, synth-02309, synth-02316, synth-02320, synth-02323, synth-02367, synth-02405
synth-02443, synth-02450, synth-02475, synth-02481, synth-02489, synth-02499, synth-02514, synth-02515, synth-02520, synth-02578
synth-02580, synth-02600, synth-02601, synth-02602, synth-02620, synth-02623, synth-02627, synth-02629, synth-02675, synth-02677
synth-02681, synth-02693, synth-02695, synth-02704, synth-02715, synth-02727, synth-02763, synth-02773, synth-02785, synth-02844
synth-02852, synth-02866, synth-02873, synth-02884, synth-02907, synth-02909, synth-02948, synth-02955, synth-02965, synth-02969
```

关键输入SHA-256（防止把后续改版与本次结论混用）：

| 文件 | SHA-256 |
|---|---|
| SPEC.md | `298741fd11d1c78bafedd7f92940297a4f36a5b4a6d39f6224e5c38baa45b9b4` |
| gold/seed.jsonl | `6148a8f65d7226738aebbcc4bac7442be34d4f179e3969960a6ba32bebc93248` |
| gold/dev.jsonl | `f207db7324dc19ebf405c6b2446d81abc92f6d3b100959dd39ef8466442c7406` |
| gold/test.jsonl | `b5af5444e2482fef50240c6c972340001393fa74253bf435e7b8a856abc40fda` |
| gold/sessions.jsonl | `9d8fd03c89346a8bc4fcb7b3fb813afd36c16770fdcb6a1e4f4265c6bb40653c` |
| synth/train.jsonl | `91f2f63344c5485477411754443ef95bec62e7ce3eb4494e43ad897887990321` |
| sft/dev_extract.jsonl | `71a4af7eb4014490297701fbe819faf18280aa8717ac4874356ce5402d087c80` |
| tools/evaluate.py | `abaacdf707a515694f577e9b5fec955df38062a079c15b5191b92d5339e53175` |
| tools/apply.py | `d6e5785656e2e30472b2679dda467d499423043c85e7792ae13857fe8738edae` |


### 只读pytest复现适配

下列命令对应29通过的补充运行。`tmp_path`只对唯一使用它的测试提供内存文件；真实输入仍从磁盘只读。审计钩子拦截任何真实写文件/建目录，pytest日志插件和磁盘捕获关闭。若移除`plugins=[MemoryTmp()]`，则对应28通过、1个tmp_path错误的受限运行。不要把此适配提交到测试代码中。

```sh
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ../deepsleep/.venv/bin/python - <<'PYTEST_AUDIT'
import sys, io, fnmatch
from pathlib import Path
import pytest

class MemoryTmp:
    @pytest.fixture
    def tmp_path(self, monkeypatch):
        root = Path('/__audit_memory_only__')
        files = {}
        old = {n: getattr(Path, n) for n in ['mkdir', 'write_text', 'open', 'glob']}
        def virtual(p):
            return p == root or root in p.parents
        def mkdir(p, *args, **kwargs):
            if not virtual(p):
                return old['mkdir'](p, *args, **kwargs)
        def write(p, text, *args, **kwargs):
            if not virtual(p):
                return old['write_text'](p, text, *args, **kwargs)
            files[p] = text
            return len(text)
        def open_(p, *args, **kwargs):
            if not virtual(p):
                return old['open'](p, *args, **kwargs)
            if p not in files:
                raise FileNotFoundError(str(p))
            return io.StringIO(files[p])
        def glob(p, pattern, *args, **kwargs):
            if not virtual(p):
                return old['glob'](p, pattern, *args, **kwargs)
            return iter(q for q in files if q.parent == p and fnmatch.fnmatch(q.name, pattern))
        for name, func in [('mkdir', mkdir), ('write_text', write), ('open', open_), ('glob', glob)]:
            monkeypatch.setattr(Path, name, func)
        return root

def readonly(event, args):
    if event == 'open' and len(args) > 2 and isinstance(args[2], int) and args[2] & (1|2|64|512|1024):
        raise PermissionError('AUDIT read-only: file write blocked')
    if event in {'os.mkdir', 'os.remove', 'os.rmdir', 'os.rename', 'os.link', 'os.symlink', 'os.chmod', 'os.utime', 'os.truncate'}:
        raise PermissionError('AUDIT read-only: filesystem mutation blocked')

sys.addaudithook(readonly)
raise SystemExit(pytest.main([
    '-q', '--capture=sys', '-p', 'no:cacheprovider', '-p', 'no:logging',
    'tests/test_privacy_data.py'
], plugins=[MemoryTmp()]))
PYTEST_AUDIT
```
