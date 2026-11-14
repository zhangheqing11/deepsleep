# PR #6 危机安全层修复总结

日期：2026-11-14。工作目录 `/Users/zhangheqing/bohack/ds-safety`，分支 `zhq/domain-safety`，起始与当前 HEAD 均为 `9a7058121e962ca7b722074e43e61e889b9321bf`。

依据：已通读 `origin/main:docs/reviews/pr6-safety-fixes.md` 与 `origin/main:docs/reviews/raw/pr6-safety-review.md`，结合本任务明确覆盖的 S2/S3/S7/S9/S10 口径。未修改 contracts、原定稿 safety/testset.jsonl、AGENTS 或 BACKLOG。未调用真实模型，未读取或打印仓库 .env；已有 dotenv 解析测试只使用临时目录内人工构造的假配置文件。

## 交付状态与权限阻塞

源文件修复与验收完成，所有修改留在当前 worktree；没有 push，也没有合并。

**没有创建 commits**：尝试 git add 时，沙箱拒绝创建 `/Users/zhangheqing/bohack/deepsleep/.git/worktrees/ds-safety/index.lock`，错误为 `Operation not permitted`。这是 worktree 外的 Git 元数据目录，不在当前可写范围；当前会话不允许申请提权。未使用其他途径绕过限制。下方给出按项提交安排及英文消息，每次提交须使用指定 Co-Authored-By 尾行。

用户指定总结位置 `/Users/zhangheqing/bohack/research/codex-tasks/pr6-fixes.summary.md` 同样位于沙箱可写范围外。本文件保存至 `/tmp/pr6-fixes/pr6-fixes.summary.md`。已实际尝试复制到目标路径，系统返回 `Operation not permitted`，指定路径未写入。

## S1–S10 逐项记录

| 项目 | 状态与实现 | 修改文件 | 回归测试名 | 修复前是否失败 |
|---|---|---|---|---|
| S1 | 已修复默认入口。此前 8851901 只修复 strict eval；默认层缺 key 仍返回成功 Mock。本次加入 UnavailableJudge，保留所请求 provider，返回 error/null probabilities；可用真实后备照常尝试，全失败按规则兜底。Mock 仅显式模式使用。增加 --no-env / SAFETY_EVAL_NO_DOTENV，保证验收与 CLI 子进程不读取真实 .env。 | safety/judges.py、safety/eval.py、tests/conftest.py、tests/test_pr6_judge_failures.py、tests/test_judges.py、tests/test_gemini_judge.py、tests/test_startlux_judge.py、tests/test_eval.py | test_s1_default_missing_keys_preserves_ambiguous_fallback；test_s1_unavailable_provider_is_never_a_successful_mock（4 providers）；test_s1_missing_primary_can_use_available_real_fallback；test_s1_partial_ds_configuration_reports_error；test_s1_no_env_cli_never_opens_dotenv | 是。当前起始 HEAD 的前两组共 5 条失败；缺 key 的模糊文本被 Mock 判 none。strict eval 的缺 key 报错在本次之前已修复。 |
| S2 | 已修复。每个阳性量表位置都产生 scale_item9 / passive / safety_check；已有 active 则 active / crisis_protocol。事件不去重，script_for_event 用独立 safety_check_spoken 状态去重确认话术。完整 A-003 副本按文本 turn=4、量表 turn=5 组装并通过真实契约 CLI。 | safety/layer.py、safety/README.md、safety/SPEC.md、tests/test_pr6_scale_events.py、tests/test_safety.py | test_s2_passive_then_scale_complete_session_validates；test_s2_every_positive_scale_has_action；test_s2_deduplicates_speech_without_dropping_scale_events | 是。完整会话 CLI 因 action none 失败；已 passive/active 后量表动作的两组测试也失败。 |
| S3 | 已按指定口径实现，临床确认待办。同一问号子句必须同时有时间限定、风险词和询问；不能跨逗号/冒号/换行借用问号，过滤回避语句。新增 16 条正反例。为使已审定固定话术也符合严格边界，只删除“念头，或者”中的一个逗号，不改其他文字。 | safety/scripts.yaml、safety/README.md、safety/SPEC.md、tests/test_pr6_history_verification.py | test_s3_verification_requires_one_current_risk_question_clause；原 test_history_verification、test_history_check_script_itself_passes_verification 均保留通过 | 是。首批 14 条中的 8 条失败，包含报告两条反例；自查新增“不讨论/不需要确认”2 条也先失败再修复。 |
| S4 | 8851901 已修复，本次补回归、不重复改计时逻辑。外层用 provider timeout 或链总 timeout 加 0.1s；StartLux 主判断器为 8s，默认 ds flash 6s + Jev 3s = 9s。 | tests/test_pr6_timeouts.py；safety/README.md、safety/SPEC.md 更新说明 | test_s4_startlux_27_second_reply_survives_layer_timeout；test_s4_layer_allows_sum_of_chain_budgets；原 test_outer_timeout_covers_entire_chain_and_bounds_hanging_primary、test_factory_timeouts_and_single_provider_evaluation | 起始 HEAD 已通过，故没有伪造再次修复。将同一个 2.7 秒 MockTransport 层级测试放进 c1e3753 的隔离导出，真实复现约 2.5 秒外层截断、event None 的失败。当前 8s/整链测试均通过。 |
| S5 | 已修复。NFKC、小型繁简映射、去空白；英文 W8 保留词界与空格语义。W1 加确诊/误诊；W2 加医治失眠症/治好失眠症。没有新增依赖。 | domain/vetoes.py、domain/veto_rules.yaml、tests/test_pr6_wording.py；safety/README.md、safety/SPEC.md | test_s5_s6_all_26_review_probes（probe-01…26）；test_s5_normalization_and_existing_english_rules | 是。报告中的 8 个漏拦逐条失败后修复；26 条最终全部通过。 |
| S6 | 已修复。check_text 新增 user_facing（默认）/candidate_playbook 参数，未知值报错。仅候选明确禁止列表豁免，逗号/句号/分号/换行/转折结束豁免；不会放过后续断言。用户界面“不是诊断”等仍硬拦。 | domain/vetoes.py、tests/test_pr6_wording.py；safety/README.md、safety/SPEC.md | test_s6_candidate_does_not_exempt_assertions_or_other_clauses；test_s6_only_candidate_prohibition_lists_are_exempt；test_s6_unknown_context_rejected；probe-25/26 | 是。新增 context 调用在旧实现报 TypeError，原禁止列表也会硬拦。两语境反例与禁止列表现均通过。 |
| S7 | 已按安全优先口径实现，临床确认待办。E1/E3 加本人主体约束；E4 加否定及主体约束。第三方、主体不明或明确否认只改道 ambiguous，不丢弃命中；成功判断可判 none/history/passive/active，失败仍 passive。另一个本人当前明确风险子句仍直接升级。 | safety/lexicon.yaml、safety/rules.py、tests/test_pr6_rule_context.py；safety/README.md、safety/SPEC.md | test_s7_third_party_denial_and_unknown_subject_route_not_drop（10 文本 × 3 status）；test_s7_current_self_explicit_still_skips_judge；test_s7_downgraded_context_can_still_escalate_on_judge_evidence | 是。首批该文件 29 failed / 9 passed；复查后置否认“我对跳楼没有任何想法”再复现 3 个失败后修复。 |
| S8 | 已实现证据区分。eval 输出 evidence_columns 三栏：rules-only、mock、real_judge；mock 明示“不代表识别能力”，离线运行的真实判断器栏“未测”。freeze_acceptance 固定为待人工完成，不由单次零漏报自动放行。README/SPEC 说明 0 漏报为规则+真实判断器联合指标；演示前须真实漏报数，>0 不得冻结。A2/A4 留出集验收未标完成。 | safety/eval.py、Makefile（EVAL_ARGS）、tests/test_pr6_eval_evidence.py、safety/README.md、safety/SPEC.md | test_s8_offline_reports_separate_three_evidence_columns；test_s8_zero_mock_misses_does_not_authorize_freeze | 本项主要新增报告标注；未单独做修复前红灯运行，不宣称已做。原实现无该三栏结构。 |
| S9 | 已统一成“除命中明确规则外的所有发言”。普通发言、排除后的口头禅、模糊/否认语境均调用判断器；本人明确规则允许 skipped。 | safety/README.md、safety/SPEC.md、tests/test_pr6_rule_context.py | test_s9_every_nonexplicit_utterance_calls_judge；test_s7_current_self_explicit_still_skips_judge；原 test_explicit_skips_judge | 普通发言和口头禅原已通过；否认文本在修 S7 前失败。已有正确行为没有硬改。 |
| S10 | 已统一文档状态：固定话术已审定、热线已于 2026-11-14 实测；四条 verified true 完全保留。S3/S7 另标“口径待心理学同学确认（决定清单 D 节）”。 | safety/README.md、safety/SPEC.md | 原 test_hotline_rendering_is_name_and_number_only、test_history_check_script_itself_passes_verification；配置与文档 diff 核对 | 文档项，不声称测试前失败；热线 verified true 在 9a70581 已完成。 |

S11、S12 按任务要求未实现。未访问或改动 engine/，因此不声称 history_check 自动插话或 crisis_exit 的引擎端到端接线已完成。

## 验收结果

- `.venv/bin/python -m pytest -q`：**417 passed in 6.21s**，没有跳过或禁用测试。
- `make contracts`：**10 个示例全部 OK**。
- S2 完整会话：新测试读取 `contracts/examples/session.A-003.json`，写临时副本，将两次安全层原样事件写入，执行 `contracts/validate.py <副本> --schema session`，退出 0。
- 原审查 26 条探针：**26/26 通过**，其中 16 条应 hard 全部 hard、6 条 none、2 条 soft、2 条仅候选语境豁免；相同两条在 user_facing 仍硬拦。
- 无 key 环境：临时移除相关 provider/model/base URL/API key 环境覆盖，设置 `SAFETY_EVAL_NO_DOTENV=1`，并传 `--no-env`。`make safety-eval PROVIDER=ds_flash` 和 `PROVIDER=chain` 均明确报缺 key，退出 2，无报告；`PROVIDER=rules` 退出 0，0 次判断调用，不存在 mock fallback ok。
- rules-only 仍为 7 个漏报，原有精确矩阵及漏报 ID 断言未放宽；报告的 real_judge 为“未测”。没有声称真实联合指标达到 0 漏报。
- `git diff --check` 通过；`git diff --name-only HEAD -- contracts safety/testset.jsonl` 为空。
- 既有少数断言本身要求旧错误行为（缺 key 必须返回 Mock、重复阳性量表 action none 且不能过 schema），已替换为更严格的 error/非 Mock、非 none/可过契约断言；没有删除测试用例或放宽安全检查。原自定义核验规则配置、概率校验、阈值、失败统计、矩阵、药物否定、热线渲染检查均继续通过。

## 修复前红灯证据

目录 `/tmp/pr6-fixes/`：

- `p0-before.log`：在起始 HEAD 先写测试后运行，16 failed / 8 passed。最初文件名 test_pr6_p0_regressions.py，后来按项拆成 judge_failures / scale_events / history_verification / timeouts 四个文件。
- `s4-before.log`：c1e3753 的隔离导出，StartLux 2.7 秒层级测试 1 failed（event None），没有切换或改动当前分支。
- `s1-s4-after.log`、`s2-after.log`、`s3-after.log`：各阶段通过日志。
- `s5-s6-before.log` / `s5-s6-after.log`：措辞与候选语境红灯/绿灯。
- `s7-before.log` / `s7-after.log`：主体/否认语境红灯/绿灯。
- `context-review-before.log` / `context-review-after.log`：自查新增 5 个失败后全部修复（含参数化状态）。
- `pytest-final.log`：最终 417 项通过。
- `contracts.log`：10 个契约示例通过。
- `no-key-ds_flash.log`、`no-key-chain.log`、`no-key-rules.log`：清环境后的 make safety-eval 输出。

## 待获得 Git 元数据写权限后的提交安排

每个 commit message 最后一行均为：

`Co-Authored-By: Codex <noreply@openai.com>`

1. `fix: report unavailable safety judges and separate evaluation evidence` — S1/S4/S8，judges.py、eval.py、Makefile、conftest 与现有 adapter/eval 测试、test_pr6_judge_failures/timeouts/eval_evidence。
2. `fix: preserve positive scale events and verify current risk questions` — S2/S3，layer.py、scripts.yaml、test_safety.py、test_pr6_scale_events/history_verification。
3. `fix: normalize forbidden wording and scope candidate exemptions` — S5/S6，domain/vetoes.py、domain/veto_rules.yaml、test_pr6_wording。
4. `fix: route uncertain crisis subjects and denials to the judge` — S7/S9，rules.py、lexicon.yaml、test_pr6_rule_context。
5. `docs: align safety acceptance and reviewed content status` — README.md、SPEC.md，统一 S1–S10 接入/证据口径与待确认项。

不得 push。S3/S7 及固定 history 话术的标点调整仍须心理学同学在决定清单 D 节确认，随后由统筹 review。
