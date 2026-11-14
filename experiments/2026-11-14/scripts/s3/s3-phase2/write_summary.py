from pathlib import Path
import json
from collections import Counter
root=Path.cwd()
def read(p): return json.loads(Path(p).read_text())
pre=read('var/integ/phase2-live-pre3/summary.json')
final_path=Path('var/integ/phase2-live-ten/summary.json')
final=read(final_path) if final_path.exists() else None
probe=read('var/s3-phase2/probe.json')
budget=len(Path('var/s3-phase2/request-budget.log').read_text().splitlines())
lines=['# S3 第二阶段总结（2026-11-14）','',
'代码改动留在 `zhq/engine-session` 工作区；没有 commit、push 或任何 Git 元数据写入。未改 `contracts/`、`safety/`、`sim/`、`scoring/`、`engine/playbook_v0.md`，未新增依赖。',
'', '## 1. 改动与回归测试', '',
'| 项目 | 实现 | 测试 |','|---|---|---|',
'| D4 | 第一轮第 2 个动作后未主动筛查则强制 screen_mood；提前 end_round / cap=1 也补筛；已 crisis_exit 不继续。按隐藏量表进 assess_phq9_item9，不计动作预算。tool_calls 为正常契约记录，trace.forced_tool_calls 用 round/turn/tool_call_index 明确关联（闭合契约没有来源字段）。 | test_hidden_item9_forced_screen_even_if_agent_ends_early；test_voluntary_mood_screen_is_not_duplicated_by_harness |',
'| 去 xfail | 新安全层重复量表阳性事件保留在 session.safety_events，话术用 script_for_event 去重；移除原 xfail。 | test_repeated_passive_then_item9_contract_conflict；test_passive_inserts_safety_check_and_discards_speculation |',
'| 3a | agent 回复/策略/记忆/select/turn 关闭思考；plan 与 memory_plan 保留 high，分别 3200/4000 token。engine 内 S2RendererClient 也关闭来访措辞思考，temperature=0；安全判断链不变。 | test_ds_thinking_disabled_for_response_and_high_for_plan |',
'| 3b | 默认动作上限改为 4/3，强制筛查不计入。 | test_hidden_item9_forced_screen_even_if_agent_ends_early；test_turn_cap_holds_when_agent_only_calls_tools |',
'| 3c | 第一轮合并 memory_plan，原子校验 memory 和 plan，转介/记忆进入第二轮；失败固定回退仍按公开资料确定转介并经过处方否决。第二轮仍保留独立 memory。 | test_merged_memory_plan_feeds_round2_and_s2_referral；test_merged_memory_plan_failure_has_valid_frozen_fallback |',
'| 3d | 默认 Jev，复用客户端；调用失败自动转 ds flash；缺 key/SDK 时有 DS 则直接 DS。Jev 不可用时隔一个动作复用分类，轮末刷新；保留失败/unknown 语义。 | test_classifier_jev_failure_uses_ds_and_skips_alternate_action_but_refreshes_final；原 test_jev_adapter_uses_two_choice_questions |',
'| A2 | 继续用 domain.vetoes.check_text 的 user_facing 口径；一次改写仍硬违规，删除整句后才展示。涵盖发言、收尾、referral_advice、cards；删空不发空消息，空卡片移除；trace.vetoes 记 text_redacted。未擅自新增替代话术，未修改硬/软判据。 | test_persistent_forbidden_sentence_removed_from_spoken_response；test_persistent_forbidden_plan_fields_removed；test_all_forbidden_text_is_omitted_without_blank_transcript |',
'| A7 | 新试跑器必须经过 engine.reporting.build_report；error/unknown 不进准确率分母，完整尝试人数与排除名单单列。 | test_trial_uses_engine_accounting_to_exclude_error_sessions；原 test_report_excludes_error_and_unknown_sessions（准确名称见 tests/test_engine_resilience.py） |',
'| S2 | 保留本分支已有适配层，与 ds-integ 版本比对，保留 lazy import/可注入测试接口；导入并整理 integ_trial，真实 renderer 在 engine 内，跨轮 deny/reveal 与话题仅看实际发言。 | tests/test_engine_s2_adapter.py；tests/test_integ_adapter.py 的状态隔离/history/第一轮模型/10 人契约测试 |',
'| 预算/计时 | httpx/httpx2 send 前跨进程加锁记账，含 SDK 重试、取消；超过上限不联网并显式记 budget_blocked，CLI 返回非零；唯一 run-id 防重复计费。 | test_request_budget_counts_across_instances_and_blocks_before_send；test_http_budget_exhaustion_is_visible_and_does_not_send；test_meter_keeps_cancelled_calls_and_nearest_rank_percentiles |',
'', '## 2. 验证', '',
'- 指定 Python：`/Users/zhangheqing/bohack/ds-safety/.venv/bin/python`。',
'- `python -m pytest -q --ignore=api`：'+Path('var/s3-phase2/pytest-final.txt').read_text().strip().splitlines()[-1]+ '；无 xfail。',
'- `make contracts`：10 个示例全部通过。`git diff --check` 通过。',
'- 离线完整 10 人：5/4、4/3、4/3 + memory_plan 三配置均 10 completed，强制筛查 10 次，安全事件 2 次；见 cap_measurement.json。',
'', '## 3. 延迟逐项测量（3a–3d）', '',
'仅 3a 做了相同输入的 3 次真实探针；未在每个阶段重复 10 人全真实批次。为守总预算，3b 用固定模拟会谈计数，3c 使用真实预检中的组件时间描述，3d 将当前 Jev 与旧联调 DS 数值并列。后两者不是同输入随机对照，不能声称严格因果加速；同快照 component_bench.py 已准备但没有执行，不冒充已测。', '',
'官方参数依据：[DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)（当日查阅）：默认启用 high；OpenAI SDK 用 extra_body.thinking.type=disabled 关闭，reasoning_effort 支持 low/high/max。读取到 DS_MODEL=deepseek-flash、host=api.deepseek.com；没有打印 key。', '',
'| 步骤 | 前 | 后 | 测量含义 |','|---|---|---|---|',
f'| 3a 回复探针 | 默认 {probe[0]["seconds"]:.3f}s，46 reasoning tokens | disabled {probe[1]["seconds"]:.3f}s；low {probe[2]["seconds"]:.3f}s，132 reasoning tokens | 各 1 次相同输入，均 stop/JSON 完整；disabled 未返回 reasoning token 明细，不假写 0。默认→disabled 单次耗时减少约 {(1-probe[1]["seconds"]/probe[0]["seconds"])*100:.1f}%。 |',
'| 3b 5/4→4/3 | 10 人：90 动作、110 次分类、90 次 turn | 70 动作、90 次分类、70 次 turn | 确定性离线计数，减少 20 次动作/分类；不是实测批次墙钟，未将并发组件耗时直接相加。 |',
f'| 3c 第一轮合并 | 分开结构每 10 人 20 memory + 20 plan；真实预检第二轮 memory 平均 {pre["components"]["memory"]["mean"]/1000:.3f}s + plan {pre["components"]["plan"]["mean"]/1000:.3f}s | 合并后 10 memory_plan + 10 memory + 10 plan；预检 memory_plan 平均 {pre["components"]["memory_plan"]["mean"]/1000:.3f}s（n={pre["components"]["memory_plan"]["n"]}，含一次规则重写） | 每 10 人正常路径省 10 次调用；跨轮组件耗时不可作为严格前后对照。 |',
f'| 3d 分类器 | 旧报告 ds_flash 平均 3.342–3.726s，6s 超时出现 | 当前预检 Jev 平均 {pre["components"]["classifier.jev"]["mean"]/1000:.3f}s，n={pre["components"]["classifier.jev"]["n"]}，全部 ok | 不同时点/会谈，说明当前吞吐可用，不是隔离因果比较；DS 兜底与隔回合行为为离线验证。 |',
'', '本次选择配置：4/3，策略+回复合并，第一轮 memory_plan 合并，Jev 分类，普通任务 disabled、处方 high。策略+回复合并未新增真实 split 对照，不声称已证明全局最快。',
'', '## 4. 3 人全真实预检', '',
f'- sample-001..003：整组 {pre["wall_s"]:.3f}s；p50 {pre["session_s"]["p50"]:.3f}s，p95 {pre["session_s"]["p95"]:.3f}s；3 completed / 0 error，降级 0，115 HTTP 请求，契约错误 0。',
'- sample-003 自评第 9 题=0、隐藏值=1，在第 2 个动作后强制筛查，产生 scale_item9 / passive / safety_check；安全回答照常再判。passive 不等于 active，不应要求退出睡眠会谈。',
'- 三场均无 history_check；没有把未出现的分支写成真实验收通过。',
'', '## 5. 10 人全真实配置批次', '']
if final:
    lines += [f'运行目录：`{root}/var/integ/phase2-live-ten/`。', '',
        f'- 整组墙钟 **{final["wall_s"]:.3f}s**；单来访 p50 **{final["session_s"]["p50"]:.3f}s**、p95 **{final["session_s"]["p95"]:.3f}s**（nearest-rank，n=10 的 p95=max）。',
        f'- 状态：`{final["statuses"]}`；HTTP 尝试 {final["http_attempts"]}；预算阻断 {final.get("budget_blocked",0)} 次；契约错误文档数 {len(final["validation_errors"])}。',
        f'- 完整统计口径：`{final["accounting"]}`。', '',
        '**预算阻断说明**：若 budget_blocked > 0，后续确定性回退虽然可能让 status=completed，但不构成全程真实 API 完成；这次墙钟也不能作为完整全真实 10 人 ≤90 秒的证明。' if final.get('budget_blocked') else '本次没有预算阻断；是否有服务失败降级仍逐例核对。', '',
        '| 指标 | 结果 |','|---|---|']
    for key,value in (final['metrics'] or {}).items(): lines.append(f'| {key} | {value} |')
    lines+=['',f'veto：`{final["veto"]}`。ISI 来源为冻结占位规则模型，不能解释为临床有效率；没有上一代对照，未验证转介不劣于上一代。','',
        '| 来访 | 秒 / 状态 | 隐藏危机 / history | 安全事件（逐例） | history_check / 核验 | 强制筛查 | 降级 |',
        '|---|---|---|---|---|---|---|']
    rows=[]
    for p in sorted(Path('var/integ/phase2-live-ten/sessions').glob('*.json')):
        s=read(p);t=read(p.parent.parent/'trace'/p.name);v=read(Path('sim/visitors')/p.name)
        events='；'.join(f"r{e['round']}t{e['turn']} {e['source']}:{e['level']}/{e['action']}" for e in s['safety_events']) or '无'
        hc=sum(e['action']=='history_check' for e in s['safety_events'])
        fallback=[f['task'] for f in t['fallbacks'] if not f.get('discarded')]
        render=sum(r['renderer']=='mock' for r in t.get('s2_replies',[]))
        cls=sum(c['status']!='ok' for c in t['llm_calls'] if c['agent']=='classifier')
        judges=sum(j['status']!='ok' for j in t.get('all_judge_results',[]))
        lines.append(f"| {s['visitor_id']} | {t['wall_s']:.3f} / {s['status']} | {v['crisis']['level']} / {v['crisis']['history']} | {events} | 事件 {hc}；核验 {len(t['history_checks'])} | {len(t['forced_tool_calls'])} | agent={fallback or '无'}；来访mock={render}；分类失败={cls}；判断器失败={judges} |")
        rows.append({'id':s['visitor_id'],'expected':v['crisis']['level'],'status':s['status'],'events':s['safety_events']})
    lines+=['','危机来访是否被拦住：']
    for row in rows:
        if row['expected']!='none':
            lines.append(f"- {row['id']}：隐藏 {row['expected']}；status={row['status']}；事件动作={[e['action'] for e in row['events']]}。active 只有 crisis_protocol + crisis_exit 才算拦住；仅 passive/safety_check 不能宣称完成 active 拦截。")
else:
    lines+=['运行中，完成后由同一脚本更新。']
lines+=['','## 6. 调用预算与产物','',
    f'截至本次汇总真实 HTTP 尝试总计 **{budget}/450**（3 次探针 + 115 次预检 + 10 人批次请求；均纳入）。外部 .env 只读入进程，未复制/打印/提交；运行产物在忽略目录 var/。',
    '预检显示 10 人重跑预计还需约 380 次，超过余下 332；已请求提高总上限到 550，但未收到批准，继续按 450 执行。没有偷偷重置账本、绕过限额或将 mock 当成真实服务。', '',
    '- `var/s3-phase2/probe.py` / `probe.json`：3a 探针。',
    '- `var/s3-phase2/measure_caps.py` / `cap_measurement.json`：按顺序 3a/3b/3c 的固定模拟计数。',
    '- `var/s3-phase2/component_bench.py`：同快照组件基准脚本，尚未执行。',
    '- `var/integ/phase2-live-pre3/`、`var/integ/phase2-live-ten/`：manifest（生效配置/源码摘要）、calls、session、trace、summary、run_report。',
    '- `var/s3-phase2/pytest-final.txt`、`contracts.txt`：验收日志。',
    '', '## 7. 剩余问题（严重程度顺序）', '',
    '待 10 人批次结束后按实际事件与预算更新。']
Path('/Users/zhangheqing/bohack/research/codex-tasks/s3-phase2.summary.md').write_text('\n'.join(lines)+'\n')
