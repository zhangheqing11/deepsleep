# deepsleep 可复用开源项目与数据集清单

> 配套：[PLAN.md](../PLAN.md)（方案）、[AGENTS.md](../AGENTS.md)（协作与红线）、[TheraMind 论文](../03_Hu_2025a_TheraMind.pdf)
> 版本 v1 · 2026-11-14 · 本文件只做资源选型，不改任何已锁定设计

**冻结声明**：演示期间不改 `requirements*.txt` 的版本、不升级模型、不换数据集。本清单里的"接入"全部在 11/15 08:00 前完成并冻结；11/15 现场只允许 playbook 变化（见 [AGENTS.md](../AGENTS.md) §2）。

**给 AI 代理的读法**：动手前读 §7（文件级接入点）和 §8（契约变更）；不要碰 `safety/` 的危机判据；不要为了让某个库跑起来去改 `contracts/` 以外的公共结构。

---

## 0. 30 秒速查

| 我要做的东西 | 抄哪个的结构 | 装/用哪个 | 详见 |
|---|---|---|---|
| playbook 的数据结构（可 diff、可计数、可淘汰） | **ACE** bullet + delta | 抄 schema，不装依赖 | §2.1 |
| 反思器出 3 份候选、怎么选最优 | **GEPA** 的 Pareto 前沿 | 可选 `pip install gepa` | §2.2 |
| `behaviors[]` 说什么话 | **Hill 10 类助人技巧**（TheraMind 同款） | 写进契约枚举 | §2.3 |
| 模拟来访怎么建（画像 + 每轮目标 + 状态延续） | **TheraMind `Φinit`** + **AnnaAgent** 三级记忆 | 抄结构自写 | §2.4 |
| 睡眠日记变量、种子画像 | **slumbR**（TIB/TST/SE/SOL/WASO） | 抄变量定义，Python 重写 | §2.5 |
| 免费的确定性冒烟测试 | `pytest-recording` 录制 + `promptfoo` 断言 | 两个 dev 依赖 | §2.6 |
| P4 昼夜节律型的硬后端 | **Arcascope/circadian**（MIT） | `pip install circadian` | §2.7 |
| 来访分布参数从哪来 | **NHANES 2017–2018**（SLQ + DPQ） | 自己下 XPT | §4.1 |

---

## 1. 文献框架 → 我们的模块（借哪一层，不借哪一层）

TheraMind（WWW'26）的核心是**双环**：Intra-Session Loop 做战术（感知→策略→阶段→生成），Cross-Session Loop 做战略（会谈后评疗效→调疗法）。它的**结构可以直接搬，它的指标不能搬**。

| 论文组件 | 论文做法 | 我们的对应模块 | 借什么 | 不借什么 |
|---|---|---|---|---|
| Reaction Classifier | 每轮输出 `(emotion, intensity, attitude∈{Cooperative,Resistant})` | `session.rounds[].behaviors`、同盟值输入 | 把"来访态度"做成**显式中间变量**；防御型来访先否认一次正好用这个字段表达 | 不让 LLM 自由发挥情绪标签，必须落成枚举 |
| Response Strategy | 10 类助人技巧（Hill 1999） | `behaviors[]` 封闭词表、路径判定的行为证据 | 直接做词表，见 §2.3 | — |
| Treatment Stage | Engagement→Exploration→Integration | 每轮"当前干预阶段" | 支撑"第 1 轮只探查、不下处方"这类 playbook 规则 | 它是 6 次会谈的弧，我们是 2 轮，阶段要压缩重定义 |
| Memory Recall | 相关性检查，无关则返回 `null` | 第 2 轮带个人档案 | 拒绝硬塞记忆——第 2 轮不能像背台词 | 不引它的向量库 |
| Cross-Session：Therapy Evaluation | LLM 给疗效打分 `E_k` | `scoring/` 主指标 | 会话后必须有评估步这个**骨架** | **不借**：它是软分自评链，我们要硬指标 |
| Cross-Session：Therapy Selection | LLM 判"换不换疗法" | `engine/` 反思器 + playbook 改写 | "根据失败改策略"这个动作 | 换成"改 playbook + 过门禁 + git 提交"，比它多一层可控性 |
| `Φinit(Case) → (Profile, Session Guides)` | 由真实案例生成"画像 + 每次会谈的目标" | `sim/` 来访生成器 | 两段式结构；`guides` 让模拟来访有目标但不照本宣科 | 它用 CPsyCounR 真实案例，**需签协议**，我们改自成因人设 |
| 温度 | 生成 0.9 / 判任务 0.3 | ds flash 调用参数 | 判路径/转介用低温，会谈生成用中温 | — |
| 指标 | 4 分制、T.Alli/Coh/Flex/Emp/T.Attun，人工 + LLM 打 | 看板解释层 | "内部决策可解释"的叙事 | **不能当主指标**（赛规要程序可判分） |

**答辩口径（一句话）**：TheraMind 证明"会感知来访态度、会跨会话调整策略的 agent 更强"；我们把它从"会话内换疗法"升级成"跨运行改自己的 playbook"，并且加上**硬指标 + 否决规则 + git 回滚**——这是论文没有的可审计性。

**坑**：[Emo-gml/TheraMind](https://github.com/Emo-gml/TheraMind) 自述是 "official evaluation code and data"，不是完整 agent 实现，**clone 跑不起来是正常的**；而且该仓库**没有 LICENSE 文件**（GitHub API 返回 `license: null`），默认保留所有权利——**只引用论文里的方法与结论，不要复制它的代码**。

---

## 2. P0：48 小时内真正能接的 7 件

### 2.1 ACE —— playbook 的数据结构（最重要的一条）

- **出处**：[Agentic Context Engineering: Evolving Contexts for Self-Improving LMs](https://arxiv.org/abs/2510.04618)（ICLR'26）；开源实现两处：论文配套 [`ace-agent/ace`](https://github.com/ace-agent/ace)（**Apache-2.0**，已核，1.4k stars），与 PyPI `ace-framework`（Kayba 的 ACE 引擎）。Apache-2.0 允许复制与修改，保留 NOTICE 与署名即可。
- **它解决了我们的什么问题**：`PLAN.md` §2.2 写"反思器产出 3 份**增量**修改"，但没说增量怎么表示。ACE 的答案是：playbook 是一组 **bullet**，每条带唯一 id、来源、`helpful/harmful` 计数；反思器只提交 **delta**（新增 / 修改 / 删除哪几条）；另有 **grow-and-refine** 定期合并重复 bullet、淘汰 harmful 高的条目。
- **为什么必须是这个结构**：① 看板要展示 diff，bullet 级 diff 天然好看；② 回滚要能定位"哪一条学错了"；③ 不实现 grow-and-refine，3 代之后 playbook 必爆上下文。
- **怎么接**：不引依赖，把 §8.1 的 bullet 格式写进 `engine/playbook_v0.md`，`engine/` 用一个 `PlaybookStore` 负责 parse / apply_delta / refine / commit。

### 2.2 GEPA —— 候选裁决用 Pareto 而不是单指标

- **出处**：[`pip install gepa`](https://pypi.org/project/gepa/)（仓库 [gepa-ai/gepa](https://github.com/gepa-ai/gepa)，**MIT**，已核，7.4k stars；已集成进 DSPy、MLflow、Comet Opik、Pydantic AI、Google ADK）。
- **它解决什么**：`PLAN.md` §2.2 说"取最优"，但单一主指标（ISI 有效率）会被刷——比如把所有来访都开激进睡眠限制。GEPA 的做法是维护 **Pareto 前沿**：一个候选只有在"不拖累其它指标"时才留下。
- **落到我们这**：`scoring/gate.py` 的候选比较同时看 `isi_response_rate`、`path_acc_r2`、`referral_recall`、`referral_precision`，取 Pareto 非支配集里的第一个；再叠你们已经定好的 3 条否决规则。
- **工作量**：自写 Pareto 排序 40 行；`gepa` 只在离线对照实验里跑，不进现场链路。

### 2.3 Hill (1999) 10 类助人技巧 —— `behaviors[]` 的封闭词表

论文 Figure 6 给出实测分布，可直接当我们的基线与对照。

| 词表值 | 类别 | 论文分布 | 在我们这的作用 |
|---|---|---|---|
| 情感反映 | 共情 | 32.54% | 同盟值上升的主要来源 |
| 邀请新视角 | 改变 | 16.93% | P3 认知过度唤醒的关键动作 |
| 邀请新行动 | 改变 | 15.83% | 处方落地的关键动作 |
| 解释 | 改变 | 13.36% | 容易变成说教，需负向计分 |
| 面质 | 改变 | 8.31% | 高风险，防御型来访应禁用 |
| 自我暴露 | 共情 | 7.27% | 少量加分，过量扣分 |
| 肯定安抚 | 共情 | 4.01% | — |
| 复述 | 共情 | 1.51% | — |
| 询问主观信息 | 探查 | 0.14% | 第 1 轮主力 |
| 最小鼓励 | 共情 | 0.11% | — |

**三个用法**：① 人类纠正时说"这里不该直接给建议"，能落到具体枚举；② "共情类 : 改变类"的比例直接喂同盟值规则（`sim/` 状态模型）；③ v1 的行为分布若与论文差太远，说明 v1 的会谈风格本身有问题——这是免费的体检指标。

### 2.4 模拟来访 —— TheraMind `Φinit` + AnnaAgent 的状态机

- **TheraMind 给的**：`Φinit(Case) → (Patient Profile, Session Guides)`。即"一份画像 + 每轮一个目标"，两者分开。这正是我们 `clues[]` + `persona` 缺的那一层：线索是**内容**，guide 是**这一轮想说成什么样**。
- **[AnnaAgent](https://github.com/sci-m-wang/AnnaAgent)**（ACL 2025 Findings，PyPI `anna-agent`）：来访侧的情绪调制器 + 抱怨激发器 + **三级记忆**（短期 / 长期 / 跨会话）。解决我们最实际的问题：第 1→2 轮之间"人设不能漂"、防御型来访要"越聊越松"。
  - ⚠️ **许可：AGPL-3.0（已核）**。AGPL 带网络分发条款，**拷它的代码进我们仓库会传染成 AGPL**。只读论文与源码理解设计，自己实现三个标量的状态转移表。
- **只借设计不借模型**：它的 SFT 小模型是给真机部署用的，我们 temp 0 + 人设卡已经够；两个"调制器"用一个 5 行的状态转移表实现即可（`trust` / `defensiveness` / `disclosure` 三个标量）。
- **补充参考**：[Interactive Agents](https://github.com/qiuhuachuan/interactive-agents) 的"中文来访角色卡池"字段设计；PsyCLIENT（arXiv 2601.07312）的轨迹建模视角。

### 2.5 slumbR —— 睡眠日记变量与种子画像

- **出处**：[circadia-bio/slumbR](https://github.com/circadia-bio/slumbR)（R 包）+ Sleep Diaries app。**作者明示"未经验证、API 可能变"**，只当参考实现。
- ⚠️ **许可：GitHub 标记 `NOASSERTION`（自定义许可，已核）**。所以只借**变量定义**（TIB/TST/SE/SOL/WASO 是数学口径，不是它的代码），不拷实现、不引为依赖。
- **白拿的部分**：TIB / TST / SE / SOL / WASO 的精确计算口径（尤其是"卧床时间"从哪算到哪），以及**三个自带原型**：
  1. 慢性失眠 + 晚型（→ P1 + P3）
  2. 健康早型（→ 对照组）
  3. 轮班护士 + 极端社交时差（→ P4）
- **怎么用**：这 3 个原型直接当 `data/visitors/` 的种子画像，再排列组合出 A/B/C 三组。

### 2.6 免费且确定的冒烟测试

- `pytest-recording` / `vcrpy`：把 ds flash 的响应录成 cassette，`make smoke` 跑 10 个来访时**0 API 花费、结果逐字节确定**。这是"提 PR 前必须跑 smoke"能真正执行的前提。
- [`promptfoo`](https://github.com/promptfoo/promptfoo)（MIT）：把"10 个来访 → 期望路径/转介"写成 yaml 断言，赛前冻结成回归。现场如果要用它，只读不写。

### 2.7 circadian —— P4 的硬后端（可选加分）

- [Arcascope/circadian](https://github.com/Arcascope/circadian)（MIT，`pip install circadian`）：Forger99 / Skeldon23，几秒模拟几周的光照与作息。
- **用在哪**：4 周状态模型里 P4 分支不再用"手写晚睡衰减曲线"，而是真的跑节律模型，给出"如果按这个作息表执行，第 3 周相位能提前多少小时"。评委问"你们的状态模型凭什么"，这是最硬的一条。
- **不影响主线**：P4 只占约 1/5 来访，接口留 `sim/circadian.py` 的单一函数，失败就回退到手写曲线。

---

## 3. P1：可选 / 只离线 / 只讲故事

| 资源 | 是什么 | 我们怎么用 | 成本 |
|---|---|---|---|
| [Ψ-Arena / PsiArena](https://github.com/Cognition-and-Language-Group/PsiArena)（AAAI 2026） | 25 轮会谈 + 来访/督导/咨询师**三方 33 维打分**的闭环评测 | 借"三方视角"写看板解释文本（为什么这条路径错） | 读 README，2h |
| [CPsyCoun](https://github.com/CAS-SIAT-XinHai/CPsyCoun)（ACL 2024 Findings，**CC-BY-4.0**） | 中国咨询报告→多轮对话重建 + 评测框架 | `CPsyCounD` 公开（EmoLLM 仓库也有），可做风格样例；`CPsyCounR` **需签隐私协议**（数据与仓库许可是两回事） | 只取 D |
| [EvoAgentX](https://pypi.org/project/evoagentx/) | 集成 TextGrad/MIPRO/AFlow/EvoPrompt 的自进化工作流框架 | **只当算法参考**，别塞进演示链路 | 读文档 |
| [DSPy](https://github.com/stanfordnlp/dspy) + `dspy.GEPA` | 把 agent 写成 module，用指标离线优化 | 赛前把 v0 playbook 调到健康区间（路径准确率 40%–70%），然后冻结 | 半天，可选 |
| [TextGrad](https://github.com/zou-group/textgrad) | 文本梯度 | 把"人类纠正一句话"形式化成可累积信号 | 叙事用 |
| Reflexion / Self-Refine | 失败→反思→重试 | 反思器的最简兜底实现 | 自己写 150 行 |
| [MedRSI](https://github.com/ImprintLab/MedRSI) | 按**临床代价**排失败优先级；新工具须持续有收益才采纳 | 否决规则的叙事依据（危机 0 漏报 = 最高代价） | 叙事用 |
| [Agent Hospital](https://arxiv.org/abs/2405.02957) | 从失败病例积累经验、检索成功案例 | 我们的**降级方案（案例库）**就是这个范式；许可 **CC BY-NC-SA**，非商用 | 叙事用 |
| [Sotopia](https://github.com/sotopia-lab/sotopia)（MIT）/ [Concordia](https://pypi.org/project/gdm-concordia/) / [TinyTroupe](https://github.com/microsoft/TinyTroupe) / AgentSociety（ACL 2025 industry） | 开放社会模拟、GM 环境、人格化多 agent | 只借"信息不对称 + 目标驱动"的思路，**不引运行时** | 不投入 |
| τ-bench 的 `pass^k` | 同一批任务重复 k 次全过才算过 | 主指标旁加一列 `pass^k`，防"一次运气好" | 1h |

---

## 4. 数据集三档

### 4.1 可直接下载、当天能用

| 数据集 | 内容 | 落到哪 | 坑 |
|---|---|---|---|
| **NHANES 2017–2018**（[CDC/NCHS](https://www.cdc.gov/nchs/nhanes/)） | `SLQ` 睡眠问卷 + `DPQ`（就是 PHQ-9）个体级数据 | `sim/params.yaml` 的**出处**、来访生成器的联合分布校准 | 公开域；`pandas.read_sas` 直读 XPT；**美国人群**，不能当中国患病率，只能当"变量间相关形态"的依据 |
| **MMASH**（PhysioNet，23MB） | 22 人 24h 心率活动 + PSQI 等 | 依从 / 日记方差的经验分布 | 样本小，只用形态不用比例 |
| **PMData**（16 人 5 个月 Fitbit） | 长周期作息 + 睡眠 | "周末补觉 / 社交时差"的真实形态 | 确认许可；只做参数参考 |
| Kaggle "Sleep Health and Lifestyle"（374 行） | 自报睡眠障碍 + 生活方式 | 演示用种子多样性 | 自报、无 PSG、偏合成，**不能当证据** |
| Sleep-EDF / HMC / DOD / Sleep-Accel / Apnea-ECG | PSG 与可穿戴分期 | **本项目不用** | 我们不走分期路线，别花时间下载 |

### 4.2 需要申请 / 签协议（36 小时内的非必需项）

`CPsyCounR`（隐私协议）、`PsyQA`（用户协议 + 邮件申请）、CLPsych / UMD Reddit Suicidality Dataset（申请表）、DAIC-WOZ、NSRR 的 SHHS/MESA、DREAMT、GLOBEM、CCSD。

> **结论：一条都不要写进提交材料的必需项。** 想用就用公开替代（SoulChatCorpus 在 HF 上、CPsyCounD 公开），或者干脆自己写 150 条合成来访。

### 4.3 完全不要碰

NSRR 全系、任何真实用户睡眠数据。`AGENTS.md` §9 已写"只用模拟数据"，这是合规红线，不是效率选择。

---

## 5. 领域规则与量表（`domain/` `safety/` `sim/`）

### 5.1 可直接编码的规则

- **CBT-I 睡眠限制**（Kyle 2014，[调研文档](<../睡眠 × 自进化：BoHack 开题调研.md>)已引）：初始 TIB = 基线周均 TST（≥5h）；每周 SE<85% 减 15min、85–90% 不变、≥90% 加 15min。写进 `domain/` 当处方规则的唯一出处。
- **量表计分**（均可公开使用）：ISI（7 题 0–28，引用 Morin）、PSQI（7 成分 0–21）、DBAS-16、MEQ（Horne–Östberg）、PSAS、STOP-Bang（Chung 2008，≥3 高危）、PHQ-9、GAD-7（PHQ/GAD 系列由 Pfizer 声明**无需授权**可复制分发）。
- **共识睡眠日记**（Carney 2012）：9 个核心条目 → TIB/TST/SE，用 slumbR 的变量定义对照实现。
- **危机层**：PHQ-9 第 9 题 > 0 或明确自伤表述 → 固定规则；话术骨架用 C-SSRS / ASQ；求助资源用**国内统一心理援助热线 12356**（2025 年起全国启用，**演示前再核一次话术与号码**）。CLPsych 只做离线验证。

### 5.2 量表 → 路径的映射（`domain/` 用）

| 路径 | 判别线索 | 专项指数 |
|---|---|---|
| P1 作息与睡眠卫生 | 作息不规律、周末补觉、睡前咖啡/酒 | 日记作息方差 |
| P2 床-清醒条件联结 | 床上辗转、沙发反而睡着 | SOL、WASO、SE |
| P3 认知过度唤醒 | 睡前反刍、怕睡不着、灾难化 | DBAS-16、PSAS |
| P4 昼夜节律延迟/倒班 | 很晚才困、早上起不来、夜班 | MEQ |
| P5 睡前数字娱乐依赖 | 上床刷短视频、报复性熬夜 | 睡前屏幕时长 |

---

## 6. 工程脚手架与依赖

| 目录 | 建议 | 理由 |
|---|---|---|
| `contracts/` | `pydantic` v2 + `datamodel-code-generator`：JSON Schema → Python 模型；前端吃同一份 schema | 单一真源，防前后端字段漂移 |
| `engine/` | `instructor` 或 `pydantic-ai`（结构化输出）+ `tenacity`（重试） | 判 P1–P5 / R0–R3 必须"解析失败能重试"，不能靠正则猜 |
| `api/` | `httpx.AsyncClient` + `asyncio.Semaphore(50)` + 超时降级 | 1 分钟 + 50 并发的唯一可靠写法 |
| 全部 | **不引 LangGraph/LangChain 作为运行时**；纯 asyncio 显式状态机 | 演示链路越少黑盒越好；框架的 checkpoint 在这个规模是负担 |
| playbook 版本库 | `subprocess git` 或 `dulwich`，每代一次 commit，作者标 agent | 已锁定决定，无需新依赖 |
| 测试 | `pytest` + `pytest-recording` + `promptfoo`(dev) | `make smoke` 免费且确定 |
| `web/` | `recharts` + `react-diff-viewer-continued` + `shadcn/ui`；版本树用 `gitgraph` | diff 与版本树是"学到什么/怎么回滚"的展示核心 |

**依赖建议**（生产 / 仅开发分开，测试与优化工具不进演示镜像）：

```
# requirements.txt（生产）
pydantic>=2
httpx
tenacity
instructor          # 或 pydantic-ai，二选一
jinja2
```

```
# requirements-dev.txt（不进镜像）
pytest
pytest-asyncio
pytest-recording
datamodel-code-generator
promptfoo           # 可选，也可用 npx
# 下面两个只在赛前离线实验里用，演示链路不 import
dspy
gepa
```

---

## 7. 文件级接入点（实现时照着改）

| P0 项 | 落到哪个文件 | 交付物 |
|---|---|---|
| 2.1 ACE bullet | `engine/playbook_v0.md`、`engine/playbook_store.py` | bullet 格式（§8.1）+ `apply_delta()` / `refine()` / `commit()` |
| 2.2 Pareto | `scoring/gate.py` | `pareto_front(candidates) -> list` + 复用已有否决规则 |
| 2.3 Hill 词表 | `contracts/session.schema.json`、`domain/behaviors.yaml` | 10 项枚举（§8.2） |
| 2.4 `Φinit` | `sim/generator.py`、`data/visitors/{A,B,C,offline}/` | 画像 + `clues[].guide`（§8.3） |
| 2.4 AnnaAgent 状态 | `sim/visitor_agent.py` | `trust/defensiveness/disclosure` 三个标量 + 转移表 |
| 2.5 slumbR | `sim/diary.py` | TIB/TST/SE/SOL/WASO 函数 + 3 个原型 |
| 2.6 录制回放 | `tests/cassettes/`、`Makefile: smoke` | 10 个来访的免费 smoke |
| 2.7 circadian | `sim/circadian.py` | `simulate_phase_shift(plan) -> (phase_shift_h, sleep_h)` |
| pydantic codegen | `contracts/models.py`（生成物，不为它写测试） | 由 schema 生成，CI 里校验未过期 |

---

## 8. 契约变更提案（需单独 PR，标题加 `[contract]`）

> 按 [AGENTS.md](../AGENTS.md) §7.3：生产方 + 消费方都 approve 才合。**下列三项在没批准之前不要先写代码。**

### 8.1 `engine/playbook_v0.md` 的 bullet 格式（新增，不改契约）

```markdown
- id: pb-014
  when: "首轮只诉'睡不好'，未提睡前行为"
  do: "先问 3 个睡前行为（上床时间 / 睡前 1h 做什么 / 是否在床上刷手机），
       不要先给作息表"
  why: "路径线索只在问到对应话题时才说，先给方案会锁死 P2/P5 判别"
  evidence: ["A-0032", "A-0117"]
  helpful: 7
  harmful: 1
  since: v2
```

规则：`id` 全局唯一不复用；`evidence` 至少 1 条来访 id；`helpful`/`harmful` 由门禁结果自动累加；`refine()` 合并 `when` 语义重叠且 `do` 同向的条目。

### 8.2 `session.schema.json`：`behaviors[]` 改为封闭枚举

```json
"behaviors": {
  "type": "array",
  "items": {
    "type": "string",
    "enum": ["情感反映", "复述", "最小鼓励", "询问主观信息", "肯定安抚",
             "邀请新视角", "邀请新行动", "解释", "面质", "自我暴露"]
  }
}
```

消费方影响：`web/` 的行为标签文案 + `scoring/` 的同盟值规则 + `analysis/` 的行为分布图。生产方：`engine/` 的会谈输出。

### 8.3 `visitor.schema.json`：`clues[]` 增加 `guide`（可选字段，向后兼容）

```json
{"id": "c-snore",
 "content": "我老公说我打呼噜很响，有时候会憋醒",
 "reveal_topic": "打鼾 / 憋气",
 "deny_first": true,
 "guide": "第 1 轮若被问到打鼾则先否认；第 2 轮被追问才承认"}
```

兼容策略：字段可选，缺省时模拟来访按 `reveal_topic` 走旧逻辑；`contracts/examples/` 至少补 3 条带 `guide` 的样例。

---

## 9. 红线、坑与答辩口径

| 风险 / 追问 | 应对 |
|---|---|
| "你们和 TheraMind 有什么区别" | 它是会话内换疗法、软分自评；我们是跨运行改 playbook + 硬指标 + 否决规则 + git 回滚 |
| "论文仓库跑不起来吧" | 我们只借鉴控制流；其仓库是 evaluation code，这一点在答辩里主动说明（显得我们读过） |
| playbook 越写越长撑爆上下文 | 必须实现 ACE 的 grow-and-refine（合并 + 按计数淘汰），否则 3 代必崩 |
| "自己在评自己" | C 集与 A/B 严格分开；C 的标签也来自冻结的规则生成器；留一组从没参与学习的 offline |
| "第二轮带档案本来就该更准" | 报 v1 与 v2 **在同一批新来访（B 组）**上的对比，且比第 1 轮→第 2 轮增幅 |
| 单次运气好 | 主指标旁报 `pass^k` 或 bootstrap 置信区间 |
| 许可用错 | 已核：`ace-agent/ace` Apache-2.0、`gepa` MIT 可拷；**TheraMind 无 LICENSE、AnnaAgent AGPL-3.0、slumbR 自定义**，一律只读不拷（见 §11）；Agent Hospital 是 CC BY-NC-SA，不进商用叙事 |
| "用的哪个评测框架" | 门禁是自写 pytest + promptfoo 冻结回归；Inspect AI 只作离线对照 |

---

## 10. 最小可用组合（若只剩 6 小时）

**ACE bullet 结构的 playbook（自写约 200 行）+ Reflexion 式反思器 + Hill 10 类 behaviors + TheraMind `Φinit` 式来访生成器 + `pytest-recording` 免费 smoke + 自写否决规则。**

砍掉：circadian、GEPA、DSPy、Inspect AI、PsiArena、所有需要申请的数据集。

---

## 11. 许可结论表（2026-11-14 用 GitHub API 逐仓库核过）

| 仓库 | 许可 | 结论 |
|---|---|---|
| [`ace-agent/ace`](https://github.com/ace-agent/ace) | **Apache-2.0** | ✅ **可拷代码**，保留 NOTICE 与署名 |
| [`gepa-ai/gepa`](https://github.com/gepa-ai/gepa) | **MIT** | ✅ 可拷；我们只需要 Pareto 思路 |
| [`sotopia-lab/sotopia`](https://github.com/sotopia-lab/sotopia) | **MIT** | ✅ 可拷（我们不引运行时） |
| [`promptfoo/promptfoo`](https://github.com/promptfoo/promptfoo) | **MIT** | ✅ 可作 dev 依赖 |
| [`Arcascope/circadian`](https://github.com/Arcascope/circadian) | **MIT**（调研文档已核） | ✅ 可装可用 |
| [`CAS-SIAT-XinHai/CPsyCoun`](https://github.com/CAS-SIAT-XinHai/CPsyCoun) | **CC-BY-4.0** | ✅ 仓库代码/文档可署名复用；**数据集另需协议**，两者别混 |
| [`Emo-gml/TheraMind`](https://github.com/Emo-gml/TheraMind) | **无 LICENSE（`license: null`）** | ⛔ 默认保留所有权利：**只引用论文方法，不复制代码** |
| [`sci-m-wang/AnnaAgent`](https://github.com/sci-m-wang/AnnaAgent) | **AGPL-3.0** | ⛔ 网络 copyleft：**只读设计，不拷代码**（否则我们仓库被传染） |
| [`circadia-bio/slumbR`](https://github.com/circadia-bio/slumbR) | **NOASSERTION（自定义）** | ⛔ 只借 TIB/TST/SE 的**数学口径**，不拷实现、不引依赖 |
| Agent Hospital（[arXiv 2405.02957](https://arxiv.org/abs/2405.02957)） | **CC BY-NC-SA 4.0** | ⚠️ 非商用：答辩可说"参考"，**不进商用叙事** |

> 核验方式：`https://api.github.com/repos/<owner>/<repo>` 的 `license.spdx_id`；开工前若仓库改许可，以当时 LICENSE 为准。仍待人工确认的只剩 `Cognition-and-Language-Group/PsiArena`（我们只读，不影响交付）。

> **原则：能不拷代码就不拷。** 我们真正要借的三样东西——**控制流结构、Hill 词表、参数出处**——要么不受版权保护（事实与数学口径），要么一句话署名就能交代清楚。这条原则本身也是答辩素材：我们不是把别人的代码拼起来。

---

## 12. 未决事项（需要人拍板）

1. 第 2 轮是否升级为"带 1 周模拟日记反馈"的两轮半结构？更贴合论文纵向叙事，但要动 `session.schema.json`。
2. `behaviors[]` 是否接受封闭枚举（§8.2）？改了要 `web/` 配合。
3. 是否引 GEPA 做离线对照，还是只写 Pareto 自选？
4. 危机话术里的援助热线号码与表述，演示前谁负责复核？
