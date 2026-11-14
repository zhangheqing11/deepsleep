# deepsleep 模拟数据实测报告

> 输入：`deepsleep-datasets-1114.zip`（158 KB / 102 条目）+ `使用说明.md`
> 环境：Windows 11 · Python 3.13 · 独立 venv（未改你的项目代码）
> 时间：2026-11-14 20:40 前后
> 说明：**本机没有 `.env`、没有 API key**，因此跑的是离线 mock 链路（agent/分类器/来访渲染均为规则实现）。真实 ds flash 会谈、真实反思器、门禁采纳**未跑**。

---

## 1. 数据本身：完全对得上，契约全过

| 检查 | 方法 | 结果 |
|---|---|---|
| 包完整性 | 102 条目解压，逐个 SHA256 与仓库对应目录对比 | **92/92 完全一致，0 差异**（A40 → `data/visitors/interim/A`、C32 → `interim/C`、sample18 → `sim/visitors`、2 份 jsonl → `safety/`） |
| 来访卡契约 | `contracts/validate.py --schema visitor`（90 张卡） | **90/90 OK，exit 0** |
| 分布核对 | 抽查卡片字段 | 与说明文档一致：A 40 人 8/8/8/8/8 路径、24/6/5/5 转介；C 32 人；sample 18 人 |

**结论：这份包就是仓库里 `interim` 临时集的导出，没有隐藏差异，可以直接当正式入参用。**

---

## 2. 真的跑起来了：A 组 40 人 + C 组 32 人

命令（都在仓库根目录）：

```bash
python -m engine.run --visitors data/visitors/interim/A --run-id ds-check3 \
  --mock --visitor-renderer template --scorer scoring.score:score_run
python -m engine.run --visitors data/visitors/interim/C --run-id ds-C32 \
  --mock --visitor-renderer template --scorer scoring.score:score_run
```

产物：`var/runs/ds-check3/{sessions,trace,run_report.json,summary.json}`、`var/runs/ds-C32/...`

### 2.1 运行状态（全部正常，没有 error）

| 指标 | A 组 40 人 | C 组 32 人 |
|---|---|---|
| 会话数 / 完成 | 40 / 40 | 32 / 32 |
| error / unknown 路径 | 0 / 0 | 0 / 0 |
| crisis_exit | 0 | 0 |
| 实际耗时 | **0.35 s**（mock，不代表真实） | 0.30 s |
| llm_attempts | 840，全部 `ok` | — |

### 2.2 计分指标（这是你们主指标的第一次"看数"）

| 指标 | A 组 | C 组 | 健康区间 / 判读 |
|---|---|---|---|
| ISI 有效率（降 >7 分） | **50.0%** | **40.6%** | 无标准；mock 口径 |
| ISI 平均变化 | −7.25 | −6.22 | — |
| 路径准确率 第 1 轮 | **85.0%** | 68.8% | 设计期望 40–70%；**A 组偏高** |
| 路径准确率 第 2 轮 | 87.5% | 81.3% | 第 2 轮确实上升 |
| 第 1→2 轮增幅 | +2.5 pp | +12.5 pp | C 组增幅更明显 |
| 转介召回 | **31.3%** | 30.8% | 按标签：R1 0%、R2 0%、**R3 100%** |
| 转介精确率 | 100% | 100% | 下限 0.5 |
| 危机召回 / 漏报 | 1.0 / 0 | 1.0 / 0 | 但见 §4 警告 |
| 禁忌违规 | **2 例** | **2 例** | 硬否决 → **veto 未通过** |
| 筛查覆盖率 | 33.3% | **0%** | C 组一次筛查都没做 |

### 2.3 门禁判读

两组 `veto.passed` 都是 **False**，原因都是 `contraindication_violation`（对带禁忌的来访开了睡眠限制，或没问过禁忌就开）。

**这其实是好消息**：否决层在真实数据上真的会拦人，不是摆设。反过来说，mock agent 的行为本身不达标——它的处方策略不看禁忌，需要靠后处理兜底（`plan_postprocess` 的硬否决重写）才合规。

---

## 3. 一份会谈长什么样（A-001，可直接给队友看）

```
[visitor] 晚上老是睡得很晚，睡眠时间不够，想调整一下。
[agent]   先了解一下，你平时几点上床、几点起床？
[visitor] 平时大概23:35上床，07:30起床。
[agent]   躺在床上的时候，你通常是清醒着，还是脑子里在想事情？
...
round 1: 11 条发言, path_pred=P3, referral=R0, crisis=none
round 2:  8 条发言, path_pred=P3, referral=R0
plan: worry_time + cognitive_restructuring, 卧床 450 分钟, 1 张卡片
```

两轮结构、路径判定、处方组件、卡片、安全事件字段都符合契约，`contracts/validate.py` 对 session 也全过。**这说明"会谈记录"这条产品主线是通的**，不是空壳。

---

## 4. ⚠️ 最重要的发现：没有 key 时，安全线会静默掉档

我用规则层单独跑了两份危机测试集（离线，不调 API）：

| 集合 | 风险召回 | 风险精确率 | active 召回 | 漏报条数 |
|---|---|---|---|---|
| 开发集 48 条 | 70.8% | 60.7% | **20%（2/10）** | 7 |
| 留出集 40 条 | **52.4%** | 57.9% | **10%（1/10）** | **10（其中 4 条 active 判成 none）** |

而文档记载的判断器链（ds flash → Jev）留出集是**漏报 0、风险召回 21/21**。

**关键链条**：`safety/judges.py` 的链在无 key / 超时 / 报错时 → 降级到规则 → 规则对 active 只有 10% 召回 → **等于漏掉一半以上的高危来访**。

这次 A 组运行里也能看到证据：`judge_calls=394`，`judge_fallbacks=394`——**全部走了兜底**，报告里的 `judge_provider` 却仍显示 `ds_flash`。同源的还有 `make smoke` 里的 `crisis_missed=2`。

**现场风险**：游园会网络抖动 / 限流 / 判断器超时（冻结值 2.5 秒，ds flash 实测 p95 5.2 秒，本来就容易超）→ 系统会安静地降级 → 台上看起来一切正常，但安全线已经破了。这比分数不涨严重得多。

建议今晚做三件事（都很小）：
1. **探活**：启动时打一次真实判断器探针，失败就在看板显红，别让它静默降级；
2. **兜底口径**：把"判断器失败 → 按 none 处理"改成"→ 兜底 passive 安全确认"（BACKLOG A7 提过，属于安全判据变更，需心理学同学点头）；
3. **看板标注**：`judge_provider` 改成显示"实际生效的提供方 + 降级标记"，现在显示的是配置值，会误导。

---

## 5. 其他值得记下的观察

1. **转介是明显短板**：R1（疑似 OSA）、R2（疑似不宁腿）召回 0。原因不是计分，是 agent 根本没做 `screen_osa` 和腿部线索追问。这恰好是 playbook `questioning_strategy` / `referral_rules` 该进化的地方——**这是你们最好的"进化有东西可学"的实证素材**，比 ISI 涨几个点更有说服力。
2. **A 组路径准确率 85% 偏高**（设计期望 40–70%）。注意这是 mock 分类器按关键词打分，不能代表真实 Jev；但拿真实分类器跑一次这张表，就能判断"v1 是不是太强、没得进化"（PLAN §8 已预警）。
3. **C 组筛查覆盖率 0%**：32 人一次筛查都没做，却仍有 30.8% 转介召回（全靠记忆更新里的判断），这个组合在真实跑里几乎不可能出现，说明 mock 策略的"筛查"分支没被触发，别拿这个数字下结论。
4. **ISI 仍然是占位模型的产物**：`mean_isi_change −7.25` 这种数在答辩时不要当疗效讲，按前一份报告的口径说"规则推演"。

---

## 6. 我没能跑的部分（如实说明）

| 想跑 | 为什么没跑 | 需要什么 |
|---|---|---|
| 真实 ds flash 会谈（40 人） | 无 `.env` / 无 key | `DS_BASE_URL`、`DS_API_KEY`、`DS_MODEL` |
| 真实判断器链（ds flash → Jev） | 同上 + Jev 的 `TYPESAFE_API_KEY`（可能要 VPN） | key；单批 40 条文本约 40 次调用 |
| 反思器 → 3 候选 → 门禁采纳 | 反思器无 mock provider，必须真实模型 | `OPENAI_API_KEY` 或 `ANTHROPIC_API_KEY` |
| `make demo-run1 / run2 / demo-all` 一键编排 | `engine/demo.py:12` 的 `fcntl` 在 Windows 不可用 | macOS/Linux，或按前一份报告改 3 处 |
| 前端控制台看这次结果 | `web/dist` 未构建（npm 拉包超时） | `cd web && npm install && npm run build` |

**只要你把 key 填进仓库根的 `.env`，我可以立刻按"3 人小批 → 8/8/6 全批"的顺序再跑一次真实链路**，并把真实耗时、判断器实际提供方、门禁结果一起报给你。

---

## 7. 一句话总结

**数据是干净的、链路是通的、否决是会咬人的；但（a）转介能力弱、（b）没有 key 时安全线会静默跌到"active 只认一成"、（c）一键编排在 Windows 上跑不起来。**

这三条里，(b) 是今晚最该修的，(a) 是明天讲故事最好的材料，(c) 是明天能不能开演的开关。
