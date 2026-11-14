# 独立审核回应（v0.2）

2026-11-14。依据只读保留的 AUDIT.md（审核基于v0.1）和已升级的 SPEC.md v0.2 修订。SPEC.md / AUDIT.md 未修改；无网络、无git提交。所有“已修”指本地源数据/工具及验证，不表示第二标注者批准、训练完成或生产安全。

修复上游模板后全部synth重建，因此旧报告的synth行号不再对应相同文本；下表按原审核定位回应，当前追溯用新行note中的tpl-id。seed只改015的生日标签、018的no_clinical说明、025/026的危机KEEP；其余seed语义记录保持不变。

## P0/P1：标注、协议与评测

| 级别 | 原审核定位 | 回应 |
|---|---|---|
| P0 | synth/train.jsonl:synth-00041、synth-01843 | 已修：同形正例 tpl-071–078 全部有明确角色，苹果用“我的雇主”；新增产品/新闻负例。旧synth编号随重建变化，修复发生于上游模板。 |
| P0 | synth/train.jsonl:synth-00049、synth-00845、synth-02141 | 已修：美团正例始终含“我的雇主”，产品/外卖话题独立 KEEP；按实际槽位计算occ，不按第一次出现猜测。 |
| P0 | synth/train.jsonl:synth-01042、synth-01241、synth-01545、synth-02443 | 已修：小米 PERSON 槽始终有“我闺蜜”，手环另行KEEP；所有原gold同形条目复查。 |
| P0 | synth/train.jsonl:synth-00449；sft/train_extract.jsonl:1949、2942（synth-01949、synth-02942） | 已修：腾讯/华为槽有“我的单位/我的工作单位”，SFT从修订源重新生成；test-081明确“我在腾讯上班”。 |
| P0 | tools/evaluate.py:13–22；gold/seed.jsonl:seed-027 | 已修：difflib 原文位置对齐，泄露只在原实体区域判定，复制新增KEEP不构成豁免；seed-027对抗回归报泄露。 |
| P0 | gold/seed.jsonl:seed-025；tools/evaluate.py:30–32 | 已修：seed-025 KEEP精确改为指定两个完整分句；删“想过”回归报危机损失，非实体一致也失败。 |
| P1 | tools/evaluate.py:30；gold/test.jsonl:test-055 | 已修：test-055 KEEP为“我接电话一紧张”“后半夜就没困意”；输出占位符不能充当原位置KEEP，删电话回归失败。 |
| P1 | tools/evaluate.py:30；gold/sessions.jsonl:session-01-05 | 已修：按逐条表补全血氧与会话KEEP；原28个空KEEP补26个，另2个仅身份/机构核对用no_clinical和note显式豁免。 |
| P1 | tools/apply.py:14–15；tools/build_sft.py:extract_target；gold/sessions.jsonl:session-05-01、session-05-02、session-05-05、session-05-06 | 已修：extract支持same_as，build_sft由显式共指生成目标；apply只采纳同类别已有token，未知目标分配新实体并warning；会话全量回放验证。 |
| P1 | tools/prompts.py:3；sft/train_extract.jsonl:1441；gold/test.jsonl:test-118 | 已修：prompt按(text,label)分组，不同泛化目标也分组；occ实例“小米是我朋友，我戴小米手环”，嵌套test-118继续通过导出回放。 |
| P1 | tools/prompts.py:2；gold/dev.jsonl:dev-102、dev-105；lexicons/keep/cities.txt | 已修：prompt明确国家/省/市KEEP，生日及出生年/月/日期统一BIRTH_DATE（v0.2取代原报告的DATE建议），总长668字。 |
| P1 | gold/test.jsonl:test-051；lexicons/ambiguous.jsonl:12（天天） | 已修：test-051及ambiguous天天正例明确“小名叫天天”，消除“每天”读法。 |
| P1 | tools/rules.py:63–75；gold/dev.jsonl:dev-096（对抗输入） | 已修：普通DATE只接受合法旬replacement，缺失/占位都报错；BIRTH_DATE单列，validate/apply/导出/BIO一致。 |

## P1：逐条临床 KEEP

| 级别 | 原审核定位 | 回应 |
|---|---|---|
| P1 | gold/seed.jsonl:seed-001 | 不修（本轮）：建议合理，但超出本次仅A/B2可改seed的范围；保留原KEEP，列入人工决策。 |
| P1 | gold/seed.jsonl:seed-010 | 不修（本轮）：建议合理，但超出本次仅A/B2可改seed的范围；保留原KEEP，列入人工决策。 |
| P1 | gold/seed.jsonl:seed-016 | 不修（本轮）：建议合理，但超出本次仅A/B2可改seed的范围；保留原KEEP，列入人工决策。 |
| P1 | gold/seed.jsonl:seed-024 | 不修（本轮）：建议合理，但超出本次仅A/B2可改seed的范围；保留原KEEP，列入人工决策。 |
| P1 | gold/seed.jsonl:seed-030 | 不修（本轮）：建议合理，但超出本次仅A/B2可改seed的范围；保留原KEEP，列入人工决策。 |
| P1 | gold/seed.jsonl:seed-031 | 不修（本轮）：建议合理，但超出本次仅A/B2可改seed的范围；保留原KEEP，列入人工决策。 |
| P1 | gold/dev.jsonl:dev-001 | 已修：源KEEP采用 `["这周", "两点多才能睡", "六点闹钟响了就心烦"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/dev.jsonl:dev-004 | 已修：源KEEP采用 `["小米手环", "反倒没盯着睡眠分数"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/dev.jsonl:dev-007 | 已修：源KEEP采用 `["天天午睡两小时", "夜里当然困意少了"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/dev.jsonl:dev-008 | 已修：源KEEP采用 `["明明困得不行", "上床就又清醒了"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/dev.jsonl:dev-013 | 已修：源KEEP采用 `["vivo手表", "昨夜没记录", "挺失落"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/dev.jsonl:dev-014 | 已修：源KEEP采用 `["OPPO手环", "睡了六小时", "可我觉得没睡"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/dev.jsonl:dev-018 | 已修：源KEEP采用 `["红牛加浓茶撑夜班", "休息时还是很精神"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/dev.jsonl:dev-019 | 已修：源KEEP采用 `["下了夜班就刷抖音", "刷着刷着天又黑了"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/dev.jsonl:dev-026 | 已修：源KEEP采用 `["医院", "这周排大小夜", "白天想补觉又睡不实"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/dev.jsonl:dev-027 | 已修：源KEEP采用 `["我妈", "别午睡", "下午撑不住"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/dev.jsonl:dev-028 | 已修：源KEEP采用 `["褪黑素吃了3mg", "只困了一会儿又精神了"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/dev.jsonl:dev-029 | 已修：源KEEP采用 `["右佐匹克隆半片", "嘴苦", "半夜还醒"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/dev.jsonl:dev-030 | 已修：源KEEP采用 `["晚上", "客厅等困意", "回床上就又想工作"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/dev.jsonl:dev-040 | 已修：源KEEP采用 `["纽约", "连午饭都赶在半夜吃"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/dev.jsonl:dev-041 | 已修：源KEEP采用 `["睡前烟抽得有点凶", "半夜心慌醒来"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/dev.jsonl:dev-050 | 已修：源KEEP采用 `["夜里总想白天说错的话"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/dev.jsonl:dev-058 | 已修：源KEEP采用 `["熬得连数字都看花了"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/dev.jsonl:dev-074 | 已修：源KEEP采用 `["天津", "凌晨垃圾车响得很"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/dev.jsonl:dev-077 | 已修：源KEEP采用 `["总担心楼上掉东西"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/dev.jsonl:dev-103 | 已修：源KEEP采用 `["不是开始失眠那天"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/test.jsonl:test-004 | 已修：源KEEP采用 `["小米手环", "凌晨3:40还醒着"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/test.jsonl:test-007 | 已修：源KEEP采用 `["天天捧着手机睡", "眼睛酸还舍不得放"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/test.jsonl:test-009 | 已修：源KEEP采用 `["春眠不觉晓", "我的觉怎么越春越少"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/test.jsonl:test-010 | 已修：源KEEP采用 `["白天坐地铁能睡过去", "床上一点睡意都没"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/test.jsonl:test-012 | 已修：源KEEP采用 `["睡前", "苹果", "吃完又点开短视频"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/test.jsonl:test-018 | 已修：源KEEP采用 `["红牛当水喝扛通宵", "第二天人特别虚"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/test.jsonl:test-019 | 已修：源KEEP采用 `["倒时差", "上海的夜里", "洛杉矶吃午饭"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/test.jsonl:test-024 | 已修：源KEEP采用 `["GAD-7我选出12分", "一闭眼就在盘工作"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/test.jsonl:test-025 | 已修：源KEEP采用 `["沙发上点头打瞌睡", "挪到卧室却醒透了"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/test.jsonl:test-026 | 已修：源KEEP采用 `["出租车司机", "昼夜倒着来", "休班也睡不对点"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/test.jsonl:test-027 | 已修：源KEEP采用 `["同事", "上午像掉线", "下午倒挺能聊"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/test.jsonl:test-031 | 已修：源KEEP采用 `["王者荣耀赢一把又想下一把", "队友都下线我才睡"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/test.jsonl:test-033 | 已修：源KEEP采用 `["十二点前后困一下", "硬撑过去再想睡就难"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/test.jsonl:test-035 | 已修：源KEEP采用 `["寝室", "床硬得慌", "总找不着舒服姿势"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/test.jsonl:test-037 | 已修：源KEEP采用 `["不是熬夜学习", "脑子里开会停不住", "反复 replay 白天的事", "税不着"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/test.jsonl:test-038 | 已修：源KEEP采用 `["Apple Watch", "夜里亮一下我就醒", "后来摘了"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/test.jsonl:test-076 | 已修：源KEEP采用 `["每晚电梯响就惊醒"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/test.jsonl:test-079 | 已修：源KEEP采用 `["重庆", "晚上老想第二天怎么走"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/test.jsonl:test-081 | 已修：源KEEP采用 `["连腾讯视频都不看了", "两点收工"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/test.jsonl:test-086 | 已修：源KEEP采用 `["读书", "睡前听见舍友翻页都烦"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/test.jsonl:test-090 | 已修：源KEEP采用 `["学生", "下午睡过头就去不上晚课"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/test.jsonl:test-100 | 已修：源KEEP采用 `["日记", "夜醒比想的还多"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/test.jsonl:test-105 | 已修：源KEEP采用 `["睡前却总想不起白天的事"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/test.jsonl:test-108 | 已修：源KEEP采用 `["睡前一盘算房租就心慌"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/test.jsonl:test-110 | 已修：源KEEP采用 `["爷爷", "午后打盹挺久", "夜里睡一会儿就起来"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-01-01 | 已修：源KEEP采用 `["老公", "最近打鼾", "老被吵醒"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-01-02 | 已修：源KEEP采用 `["白天开车也犯困"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-01-05 | 已修：源KEEP采用 `["昨天", "医生", "血氧，最低83%"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-02-01 | 已修：源KEEP采用 `["最近一到床上就精神"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-02-02 | 已修：源KEEP采用 `["老师", "别在床上改作业"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-02-03 | 已修：源KEEP采用 `["床边就是电脑"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-02-04 | 已修：源KEEP采用 `["老师", "昨天", "睡眠日记"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-02-05 | 已修：源KEEP采用 `["客厅", "不困就去坐"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-02-06 | 已修：源KEEP采用 `["昨晚只睡四小时"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-03-01 | 已修：源KEEP采用 `["上夜班真没法睡"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-03-03 | 已修：源KEEP采用 `["室友", "白天打电话容易吵醒我"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-03-04 | 已修：源KEEP采用 `["下周仍排夜班"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-04-02 | 已修：源KEEP采用 `["别整天盯深睡数据"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-04-05 | 已修：源KEEP采用 `["医生", "有没有憋醒"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-04-06 | 已修：源KEEP采用 `["医生", "听见过我憋气"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-05-01 | 已修：源KEEP采用 `["朋友", "躺下老想工作"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-05-02 | 已修：源KEEP采用 `["最近白天很困"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-05-03 | 已修：源KEEP采用 `["临睡还在回消息"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-05-04 | 已修：源KEEP采用 `["晚上开线上会"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-05-05 | 已修：源KEEP采用 `["老婆", "早点停工作"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-05-06 | 已修：源KEEP采用 `["又熬夜了", "难受"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-06-01 | 已修：源KEEP采用 `["微信", "最近群聊停不住"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-06-05 | 已修：源KEEP采用 `["昨天", "玩到一点"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-06-06 | 已修：源KEEP采用 `["已经卸载了", "我还想刷"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-07-01 | 已修：源KEEP采用 `["考试前睡不实"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-07-02 | 已修：源KEEP采用 `["老师", "别一直想着分数"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-07-05 | 已修：源KEEP采用 `["我妈", "以前也焦虑"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-07-06 | 已修：源KEEP采用 `["晚上总问我睡没睡"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-08-02 | 已修：源KEEP采用 `["晚上也静音", "倒班"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-08-04 | 已修：源KEEP采用 `["这周连续大夜"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-08-05 | 已修：源KEEP采用 `["搭班", "护士", "白天也睡不着"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-08-06 | 已修：源KEEP采用 `["护士", "手环摘了试试"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-09-02 | 已修：源KEEP采用 `["那晚就走了好几趟"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-09-05 | 已修：源KEEP采用 `["以前没这样", "最近晚上难受"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-09-06 | 已修：源KEEP采用 `["走到街口才好点"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-10-01 | 已修：源KEEP采用 `["以前觉得活着没意思，现在没有了", "睡还是差"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-10-04 | 已修：源KEEP采用 `["医生", "问现在还有没有"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-11-01 | 已修：源KEEP采用 `["早班常困"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-11-02 | 已修：源KEEP采用 `["枕头", "下班偶尔眯会儿"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-11-03 | 已修：源KEEP采用 `["排班最近不固定"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-11-04 | 已修：源KEEP采用 `["同事", "开车得注意犯困"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-12-01 | 已修：源KEEP采用 `["那天也没睡好"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-12-05 | 已修：源KEEP采用 `["凌晨还收工作邮件"]`；重建offset/deid/SFT，校验片段原样存在。 |
| P1 | gold/sessions.jsonl:session-12-06 | 已修：源KEEP采用 `["提醒关了", "今晚试试早点睡"]`；重建offset/deid/SFT，校验片段原样存在。 |

## P1：合成内容与自然度

| 级别 | 原审核定位 | 回应 |
|---|---|---|
| P1 | synth/train.jsonl:synth-00005、synth-00010、synth-00135、synth-00905、synth-01429、synth-02128、synth-02627 | 已修：饮料、烟/电子烟、口服药分别按喝/抽/吃分池；非饮料不进入喝模板，药物模板改中性记录。 |
| P1 | synth/train.jsonl:synth-00101、synth-00319、synth-00419、synth-01628、synth-02717 | 已修：睡眠监测仅用监测设备池；Switch/PS5在游戏模板，不能落进查睡眠数据模板。 |
| P1 | synth/train.jsonl:synth-01931、synth-02637 | 已修：看屏幕/时间只用有屏设备；Oura Ring仅监测数据场景，没有手环屏幕动作。 |
| P1 | synth/train.jsonl:synth-00608 | 已修：上床触发仅脑子停不下来/心慌/清醒等池，起床困难不进入该槽。 |
| P1 | synth/train.jsonl:synth-00721、synth-01804、synth-02037 | 已修：客厅清醒场景用没困意/觉得累/担心睡着后呼吸暂停，不直接拼接正在睡眠的症状。 |
| P1 | synth/train.jsonl:synth-00212、synth-00409、synth-00426、synth-00551、synth-01654、synth-02414、synth-02635、synth-02955 | 已修：夜间钟点池固定20:00–6:59；白天补觉另用8–17点池；早醒模板另限凌晨钟点。 |
| P1 | synth/train.jsonl:synth-02004、synth-02518 | 已修：排班/工牌/任职场景仅用可排班职业，待业/退休/学生/全职家长不进入排班池。 |

## P2：分组回应

| 审核分组 | 回应 |
|---|---|
| 姓氏称谓与会话训练 | 已修：王医生/欧阳老师/李姐/老张/小陈只取姓；王者荣耀/老板/小区负例；新增200训练和40验证合成会话，整会话隔离、每轮附已有映射。gold/sessions仅评测。 |
| dev/test镜像与长句 | 已修新增覆盖：各独立手写30条60–200字，多实体或长负例；test新条目交错，标签组合和叙事不照搬dev。旧120条的历史组织未重排，不能声称旧分布完全自然。 |
| 同形词正负语境 | 已修8个旧模板角色证据，并增12个纯机构/品牌话题负例模板；不把旧283个缺角色候选等同283个确定错标。 |
| 临床KEEP P2 | 除seed-012受本次范围限制未改，逐条建议均落实源文件；保留必要同形词/作品/关系信息，避免把“不是症状”误当删除理由。 |
| 巧克力、药物、饮品动作 | 已修：喝的池只含饮料（含热巧克力）；吃药独立口服池，广义药物用“用/记录”，不统一暗示即时催眠效果。 |
| 同住关系、职业、症状时间 | 已修：睡着/打鼾/蹬腿配同住关系；排班过滤职业；清醒、上床、聚会紧张等触发分别取池，去掉重复“晚上尤其明显”。 |
| ID用途及App动词 | 已修：YB医保、MZ门诊、ZY住院、BL病历；18位只在身份证语境。刷短视频、玩游戏、看小说、逛购物及网盘看视频分别搭配。 |
| ambiguous第4/7/15/17/56及天天 | 已修：协和和弦、窗户朝南语句自然化；作品内不出现“虚构”捷径，来源放note；天天明确小名。 |
| 朝阳/黄山/人名同形词 | 已修说明：ambiguous全部context_required，补辽宁朝阳市；词表不能直接白名单/黑名单替换，现实关系仍需上下文。 |
| 有效格式号码偶合 | 按用户决定保留：身份证真实形状/校验位，说明现实分配未知、禁止拨打查询。没有更换为失真格式，没有查归属；这不解决现实偶合本身。 |
| 自然无身份会话轮 | 已修：每个gold会话补3轮，36/108=33.33%；synth每会话4–8轮，有别名、复现和至少2个无实体轮。 |

## 验证与未解决事项

本地完整 `make deid-data` 已通过，pytest **41 passed**。446条gold金标自回放：944/944 KEEP、51/51 crisis KEEP、361个实体零泄露，446/446非实体一致；gold会话108/108整句匹配、83/83占位编号正确。这些是工具/标注协议自检，不是模型能力结果。

验证入口为 `make deid-data`，具体规模见 STATS.json，新口径基线见 BASELINES.md，内容指纹见 MANIFEST.sha256。测试覆盖三个审核对抗反例、无效输出、日期强制泛化、same_as退路/隔离、所有单轮导出回放、三套会话回放、长句配额、合成搭配、种子复现与split文本交叉检查。

仍未解决/需要人工拍板：

- 普通seed的7项KEEP补强：seed-001/010/012/016/024/030/031。建议合理，本轮没有授权改；是否另行扩大范围由负责人决定。
- 新增手写60条、改写机构关系和自然度池仍需第二标注者/心理学负责人复核。规则/naive远未达生产要求，无训练模型效果可报告。
- 药物口语名、机构现行名称、设备型号能力未联网核验；临床tags仅供隐私分组，不可复用为危机或转介真值。
- 合成会话训练/验证按整会话隔离但共享模板，不能证明新叙事泛化。无身份短句可重复，正文不同不是语义独立保证。
- SPEC文字存在需澄清处：§5“出现在输出”弱于§6“原位置”，本轮按§6；§1 DATE与BIRTH_DATE共用日期编号，但DATE又必须泛化，本轮DATE不消耗编号、BIRTH_DATE续用已有日期占位序列。§3.11保留原文已有主语，不能为省略主语的原话补词。SPEC本轮未修改。
- difflib对重复内容是启发式，字面泄露不覆盖部分号码、同音改写或跨位置复制；应同时看非实体逐字一致率与有效输出率。

审核报告原有待决项中，品牌关系、危机完整分句、床号、same_as、无身份会话轮与新指标已由本次v0.2/任务要求决定；不再重复请求这些决定。城市、年龄、日期泛化、公众人物继续执行SPEC暂定值。

## 第二轮修订

2026-11-14。本节描述本轮最终文件，前文的41项测试、旧KEEP分母以及“seed补强未处理”均为上一轮历史记录。未联网、未提交；SPEC.md、AUDIT.md、gold/seed.src.jsonl 和已有 Makefile 均未改。dev/test 源只修改 keep，text、实体、tags、note 均与开工快照一致。

### 修改数量与标注方式

以本轮开工时的已编译JSONL为比较基准，不重复计数源文件、编译结果和SFT副本：

| 数据 | KEEP发生变化的条数 | 说明 |
|---|---:|---|
| gold/dev | 30 | dev-121–150，每条人工选取2–6个关键片段 |
| gold/test | 31 | test-121–150逐条人工选择；另收紧test-037，原文超过40字但没有long标签 |
| synth/train | 993 | 600条long + 393条普通模板样本 |
| synth/sessions_train | 483 | 无身份跟进轮由整句改为显式关键片段 |
| synth/sessions_dev | 98 | 同上 |
| 本轮修改合计 | 1,635 | 不含负责人先前已经更新的seed源 |
| gold/seed重新编译 | 7 | seed-001/010/012/016/024/030/031，直接采用负责人已更新的源；不是本轮编辑 |

合计1,642条编译记录的KEEP相较开工时发生变化。gold/sessions没有变更。本地实际long标签为dev/test各30条、synth/train为600条；不是dev31/test32条long。不能把全体高占比样本数与long标签数混为一谈。

金标保留钟点及行为、时长/频率、症状、关键否定、指标、App/设备、城市、班次等；没有用自动分句替代逐条选择，也没有改写原文来凑子串。dev/test全部long的KEEP为2–6项，每项最多30字；危机分句按50字上限验证。所有片段都有不跨实体的连续原文位置。

合成的6个long模板族改成每个组成句显式携带text/keep；只合并本次选中的2–4句，渲染后稳定去重、去除被其他片段包含的短片段。删除“把所有非实体段加进KEEP”的逻辑。普通品牌话题模板与会话跟进轮也改为片段；不再有普通样本将整段发言作为单个KEEP。tpl-063保留设备名这一同形易错片段，删除额外短片段以满足占比限制。

tpl-080/081/083/087/089原本几乎只含身份和完整危机句，部分变体无法同时满足完整时态/否定和60%上限。这5个模板增加各自的具体睡眠叙述（入睡、早醒、白天功能、回床清醒），也为新增临床线索标注KEEP，未裁短危机句；本种子下59条合成正文随之变化。其余合成正文保持一致，金标正文完全未变。

### 校验与复跑结果

validate新增：KEEP个数1–6（no_clinical加note仅允许0，不豁免上限）；单片段30字、crisis行50字；原文>60字时KEEP总长≤非实体字符数的60%，hard negative同样执行；至少有一个不跨实体的原文位置。边界用整数比较，恰好60%允许，超过即失败。STATS新增片段总数、最大个数、最大长度、>40字最大占比。

已按build → generate → build_sft → validate → pytest → make deid-data（DEID_PYTHON=../deepsleep/.venv/bin/python）执行。build/generate/build_sft通过。**pytest为50通过、1失败，validate与make均未通过，唯一数据阻塞是seed-014。** 没有跳过该测试、放松规则或把seed标成例外。其余所有数据文件通过新校验。

make在validate处正确停止，因此单独离线重算了dev/test rules、naive和会话rules基线，并刷新BASELINES.md及MANIFEST.sha256；STATS.json记录当前实际数据，README规模表加入KEEP片段总数。报告会显式展示当前全量校验错误，不能把报告生成等同于整条流水线通过。

446条gold自回放为1044/1044 KEEP、58/58危机KEEP、361实体零泄露、446/446非实体一致；gold会话108/108精确匹配、83/83编号正确。新增回归覆盖30/50字边界、60/61字触发点、60%分母、6/7个片段、hard negative/no_clinical、实体跨越、长句片段并集与危机时态/否定。另用dev-121证实：非关键叙述变动可保持KEEP=100%而非实体一致=0；改“两点才睡”则KEEP下降。

本轮rules的dev/test KEEP为99.25%/98.71%，非实体一致仍为87.58%/88.00%；naive的KEEP为49.75%/58.76%。KEEP分母变化，预测器未变化，这些数字不代表模型提升。完整结果见BASELINES.md。

### 尚需处理或复核的样本

- **seed-014（硬阻塞）**：原文42字，实体外28字，KEEP `["睡眠科","睡眠监测","AHI是32","血氧最低84%"]` 共20字，20/28=71.43%。用户明确禁止修改seed.src，因此本轮保持不动。已请求负责人修改或单条授权；建议删除“睡眠监测”，保留 `["睡眠科","AHI是32","血氧最低84%"]`，16/28=57.14%。必须实际修改源并重跑才能声明全绿。
- **test-127（语义复核）**：“我曾经跟陶医生说过……”的主语/过去语境与后半句被PERSON实体“陶”切开，不能用一个连续、不跨实体的KEEP覆盖整个原始句。本轮分别保留“我曾经跟”和“医生说过想从阳台跳下去，现在已经没有这个念头了”，另保留“不是说我今天要这样做”，三者共同保护原始时态、意图和否定。删除各关键语段的对抗测试通过，但这种跨身份的完整性仍应由第二标注者确认，不能只凭结构校验定论。
- dev-091、test-091、test-118仍触发rules基线的重叠实体无效输出，是既有预测器缺陷；不是新增KEEP标注错误，本轮未改预测器。


### 负责人处理 seed-014 阻塞

KEEP 总长 ≤60% 的密度规则意在防止长发言 keep 退化为整段原文，因此把触发阈值从 >40 字改为 >60 字；seed-014（42 字、临床信息密集）不再触发，源标注不改。相应回归测试改为 60/61 字边界。

## 第三轮（回应 AUDIT2）

2026-11-14；本轮仅修改 `privacy/` 与 `tests/test_privacy_data.py`，不联网、不 commit，全部 Python 使用 `../deepsleep/.venv/bin/python`。SPEC.md、AUDIT.md、AUDIT2.md、gold/seed.src.jsonl 及既有 Makefile 修改保持原样；本节覆盖前文历史状态，不改写独立审核结论。

### 危机主语与短 KEEP

- **session-10-05**：KEEP 改为 `我跟`、`医生说现在没有那个念头了`、`只是早醒`，按原文分段且不跨 PERSON 实体。将“我跟”替换为“他跟”或删除，危机 KEEP 从100%降至66.67%。
- 全量脚本扫描每条 crisis 的所有“我/本人”位置，并人工区分危机主语与联系方式、登记、普通睡眠或元话语。另补齐 **dev-111、session-10-01** 的共享主语 `我叫`，及 **seed-026** 的 `我住在`；四条均有删除/替换主语回归。
- **session-11-06** → `一般比我精神`；**session-08-01** → `白天别打`；**session-12-02** → `no_clinical`、空 KEEP 和仅核对生日/填写厌烦的 note。
- 全量遍历 gold 的长度≤2 KEEP，扩展相关否定、比较、程度与限制语境。例如 `test-054` 的 `白天别打`、`test-005` 的 `别再惊醒`、`test-008` 的 `我却比上班还早醒`、`test-051` 的 `上白班很困`、`dev-016` 的 `越买越焦虑`、`dev-033` 的 `周末也补不回`、`dev-053` 的 `我太怕黑`、`test-064` 的 `我常凌晨才看消息`。扩展后去掉已被长片段包含的旧短片段，避免重复计分。
- 受保护的 seed 源不直接改：`gold/seed.keep_patch.json` 为 **seed-003、008、021、026、035** 保存原文、原 KEEP 与新 KEEP，`build.compile_source` 校验前置条件后应用。只改变编译后的 KEEP，不改变实体、原文、deid 或 note；源有变化即报错，防止静默覆盖负责人后续修订。测试验证补丁只改 KEEP、可重放且能检测源漂移。

扫描器 `tools/scan_audit2.py` 与 `SCAN_AUDIT2.json` 保留本轮全量复核线索：共4,914条、210条 crisis；修补后仍有228个未落入 KEEP 的代词候选，**并不等于228处危机漏标**。其中 gold 的6个位置为 dev-150 的2个元话语“我”、test-111/112 的身份说明、test-113 的回电宾语、test-139 的澄清要求；真正风险分句有显式主语时已覆盖。其余222个来自11个合成模板（079、081、082、083、085、086、087、088、089、090、119），属于另一个登记/联系/睡眠/元话语分句；逐模板核对危机槽与历史/当前状态 KEEP，未发现还需补齐的风险主语。不能把全行所有“我”机械塞进临床 KEEP。

扫描后仍有234个长度≤2的 gold KEEP，宽松±5字窗口提示44个待判断上下文；复核为修饰别的分句、邻近含已有完整 KEEP、身份实体边界，或短片段本身已含程度词（如“太冷”）。没有为了让候选数归零而把关系称谓、钟点等全部扩成长句。扫描清单是复核候选，不作为自动临床判定。

### 合成自然度与对抗标签

- **tpl-035** 使用单独的 `birthday_md` 月日槽；原生日登记模板改为明确的“我出生于……”语境，保留出生年份/完整日期的 BIRTH_DATE 覆盖。
- **tpl-017、tpl-069** 的症状值进入自带“夜里”的模板前去掉相同前缀；不修改脱敏预测输出。**tpl-037** 的中国式地址只搭配明确的国内城市池，不再把海外地名与中国县/小区拼接。
- 对全部数据扫描任意连续重复的2–4字符片段（含数字及重叠位置），本次63个命中中61个在身份实体内部，属于号码等重复；非实体处仅 gold 的 `dev-019:刷着刷着` 与 `dev-141:会不会不`（原句“会不会不稳”），均是正常中文结构。合成正文的非实体区域无命中，不为清零破坏号码或正常语义。
- 新增 **adversarial**：dev-125、136、140、143、147、150；test-130、139、149；tpl-119 仅在实际选中第4句自述保留规则时赋标签（本次12条）。evaluate 的 by_tag 单独报告，README/BASELINES 明示这些长句不代表自然会谈分布；自然的叙述或睡眠记录请求不因有“我想/记录”就自动归为对抗。

### 实体替换合法率

`evaluate.score` 对 rewrite、rules、naive 和 extract 统一计算 `entity_replacement_legal_rate`，提供 overall、by_tag、by_label 及 `counts.replacement_legal`。分母为金标实体出现次数；先屏蔽原实体字符，再对齐两侧非实体边界，整个对应区域须为该类型的正整数编号占位符，或 AGE/DATE 的金标 replacement。近似假名、错误类型、漏抽、删除或附加文字不合法；无效输出按全部不合法计；无实体时 N/A。连续相邻实体按有序类型组合完整匹配，不能拆分或边界无法对齐时保守失败。编号正确性仍另看会话编号与整句匹配。

AUDIT2 的 **dev-121“林霜”** 反例写入回归：泄露率仍0、KEEP仍100%，但 PERSON 替换合法率为0，整条实体替换合法率为50%（另一个单位实体正确）。extract 由 apply 生成的替换格式合法，但漏抽和错标签仍可能失败，不能将该模式直接赋100%。新增测试覆盖合法不同编号、错类型、0编号、假名、原名残留、额外文本、空替换、naive占位符、AGE/DATE、相邻实体、无效输出和无实体分母。

这是 SPEC 之外的追加检查，未修改 SPEC；README 新增完整指标表，BASELINES 与基线 JSON 同步更新。difflib 仍是启发式对齐，无法对齐边界的失败不一定意味着占位字符串本身非法，需联合逐字一致率解释。

### 重建、基线与范围核验

已完成 build → generate → build_sft → validate → pytest → `make deid-data DEID_PYTHON=../deepsleep/.venv/bin/python`。**validate通过，67项测试全部通过**（此前51项，新增16项）。刷新全部派生 gold/synth/SFT、STATS.json、基线 JSON/BASELINES.md、README 与 MANIFEST.sha256。

规模维持 gold 446条、合成单轮3,000条、合成会话训练1,224轮/200会话及验证244轮/40会话。KEEP分母：seed110、dev400、test380、sessions144、synth/train8173；标注合并会改变分母，不表示模型能力改变。gold 自回放：361/361实体替换合法、零泄露、1034/1034 KEEP、62/62危机KEEP、446/446非实体一致与整句匹配；会话108/108回放、83/83编号正确。

| 数据/基线 | 泄露率↓ | 实体替换合法率↑ | KEEP↑ | 危机KEEP↑ | 非实体一致↑ | 有效输出↑ |
|---|---:|---:|---:|---:|---:|---:|
| dev / rules | 56.00% | 28.00% | 99.25% | 100.00% | 87.58% | 99.35% |
| dev / naive | 27.20% | 0.00% | 49.50% | 66.67% | 18.95% | 100.00% |
| test / rules | 56.56% | 29.51% | 98.68% | 100.00% | 88.00% | 98.67% |
| test / naive | 29.51% | 0.00% | 57.89% | 59.26% | 25.33% | 100.00% |
| sessions / rules | 68.97% | 21.84% | 99.31% | 100.00% | 92.59% | 100.00% |

naive的 `[已隐藏]` 不是任一身份标签的合法占位符，所以合法率为0符合预期。rules仍有dev1条/test2条无效输出，未改变基线预测器；两种基线仍未达到可用脱敏器标准。这里只证明数据重建、指标回归和协议回放，不是训练效果或线上运行结果。


### 负责人收尾

`gold/seed.keep_patch.json` 的 5 条 KEEP 修订已直接合入 `seed.src.jsonl`，补丁文件与编译期补丁机制删除，避免长期维护两份口径。


## v0.3 迁移

2026-11-14，按负责人已拍板的 SPEC v0.3 执行。核心思想：移除所有可识别个人的信息，其余一律保留。日历日期、精确年龄和城市原样保留，生日及出生年份/月仍以 BIRTH_DATE 替换为 `[日期N]`。负责人理由是：直接身份锚点移除后，这些非标识性属性不指向特定个人，而日期、年龄的精确值可能影响起病时间线及临床/法律判断。SPEC.md、AUDIT.md、AUDIT2.md 未改。

| gold源文件 | 修改行数 | 新增hard_negative |
|---|---:|---:|
| seed.src.jsonl | 5 | 3 |
| dev.src.jsonl | 15 | 10 |
| test.src.jsonl | 14 | 10 |
| sessions.src.jsonl | 4 | 3 |
| 合计 | 38 | 26 |

全部gold原文、id、剩余身份实体及BIRTH_DATE标注不变。迁移清单见 MIGRATION_V03.json。原DATE/AGE移入KEEP，删除age/date_generalize，新增age_keep/date_keep；日期按需连同相邻起病/换班描述保留。dev-124补日期后超出既有60%密度上限，因此将“那时我还以为只是偶尔早醒”精简为“还以为只是偶尔早醒”；dev-131仅新增“11月9日”而不扩展到出差动作，其余KEEP不变。校验上限未放宽。

生成器共126模板，增加6个普通日期、年龄保留和生日/出生年份对照模板；阿拉伯数字、汉字、“刚满61”“三十四了”均有覆盖，同句出生年份与年龄保持一致。最终单轮合成hard_negative为1,205/3,000（40.17%），维持35%–50%区间，无需降低负例配额。

删除age_band/date_to_xun及相应泛化测试；所有实体标签均使用编号占位符。apply忽略模型replacement并记warning，不将warning当无效输出；旧DATE/AGE为未知标签报错跳过。extract/BIO、prompt、校验及实体替换合法率已同步，编译金标中的replacement仅作为占位符结果/显式别名使用。naive继续遮蔽日期年龄，rules不处理普通日期年龄。BASELINES.md按v0.3重跑，旧数字作废；README统计和基线表、HUMAN_REVIEW第2/3节由report.py从编译数据生成，审核id与顺序保留。

验证：build → generate → build_sft → validate → pytest（70项）→ `make deid-data DEID_PYTHON=../deepsleep/.venv/bin/python`。scan_v03覆盖4,914条编译数据、4,914条源数据及11,032条SFT/BIO记录：禁止旧标签、extract replacement和新产生的旬/年龄段描述；原文本身如此描述的情况允许。STATS.json、SCAN_V03.json、MANIFEST.sha256随构建刷新。未联网、未commit、未训练模型；修改限定在privacy/、tests/test_privacy_data.py和Makefile的deid-data target。
