# RESOURCES.md 事实核验报告

核验日期：**2026-11-14**（Asia/Taipei；联网采集截至约 12:28，UTC 04:28）。

核验对象：[RESOURCES.md](pr9/RESOURCES.md)。仅核验用户列出的七组事项及直接相关的解释，不作是否合并的判断。

- ✅一致：原始来源支持相应事实；若原文只给约数，单独注明精度。
- ❌不一致：原始来源与原文相反，或原文将来源不能支持的解释写成了来源结论。
- ❓查不到：未取得足够证据，或来源之间有尚未解决的冲突；不等于事实不存在。
- GitHub 使用用户指定的 `gh api repos/<owner>/<repo>`，记录 `license.spdx_id`、`stargazers_count`、`archived`、`pushed_at`。API 许可标签与许可全文分开判断。
- PyPI 使用官方 JSON API；“最新版本”取 `info.version`，发布日期取该版本发行文件最早的 `upload_time_iso_8601`（UTC）。已检查其与最近上传版本相符，所列当前发行文件均未撤回。没有安装或执行这些软件包。
- 本地 PDF 用 `pdftotext -layout` 读取，并渲染检查第 8 页 Figure 6。联网失败后取得的搜索索引、替代官方来源会明确标注。
- 未修改核验对象或任何仓库文件。原始 `RESOURCES.md` SHA-256：`845f85bf3a229e0e39dd8af1e035a1ce6ffb99ea3ed5931fca5f6858dfea769c`。下载及提取的中间证据位于仓库外 `/tmp/pr9-factcheck-evidence/`。

## 1. GitHub 仓库及 §11 许可表

### 1.1 §11 的九个 GitHub 仓库

以下每个 API 请求均成功返回（`gh` 退出码 0），`full_name` 与请求名称一致。时间原值为 UTC。原文没有给出逐仓库的 `archived`、`pushed_at`，这里补列事实，不把“原文未写”算成不一致。表中的 ✅ 只针对许可字段一致性，后面的许可解释仍需单独核对。

| 仓库 / API 原始来源 | 文中许可 | 查到的 `license.spdx_id` | `stargazers_count` | `archived` | `pushed_at` | 标记 |
|---|---|---|---:|---|---|---|
| [ace-agent/ace](https://api.github.com/repos/ace-agent/ace) | Apache-2.0 | `Apache-2.0` | 1455 | `false` | `2026-08-24T18:50:00Z` | ✅字段一致 |
| [gepa-ai/gepa](https://api.github.com/repos/gepa-ai/gepa) | MIT | `MIT` | 7427 | `false` | `2026-11-09T12:46:31Z` | ✅字段一致 |
| [sotopia-lab/sotopia](https://api.github.com/repos/sotopia-lab/sotopia) | MIT | `MIT` | 344 | `false` | `2026-06-05T17:23:42Z` | ✅字段一致 |
| [promptfoo/promptfoo](https://api.github.com/repos/promptfoo/promptfoo) | MIT | `MIT` | 27151 | `false` | `2026-11-14T02:28:37Z` | ✅字段一致 |
| [Arcascope/circadian](https://api.github.com/repos/Arcascope/circadian) | MIT | `MIT` | 18 | `false` | `2026-11-11T19:05:09Z` | ✅字段一致 |
| [CAS-SIAT-XinHai/CPsyCoun](https://api.github.com/repos/CAS-SIAT-XinHai/CPsyCoun) | CC-BY-4.0 | `CC-BY-4.0` | 262 | `false` | `2025-05-21T11:44:39Z` | ✅字段一致 |
| [Emo-gml/TheraMind](https://api.github.com/repos/Emo-gml/TheraMind) | 无 LICENSE；license: null | `license: null（无 spdx_id）` | 34 | `false` | `2026-05-15T02:15:46Z` | ✅字段一致 |
| [sci-m-wang/AnnaAgent](https://api.github.com/repos/sci-m-wang/AnnaAgent) | AGPL-3.0 | `AGPL-3.0` | 99 | `false` | `2026-06-20T17:50:46Z` | ✅字段一致 |
| [circadia-bio/slumbR](https://api.github.com/repos/circadia-bio/slumbR) | NOASSERTION（自定义） | `NOASSERTION` | 0 | `false` | `2026-08-26T12:53:36Z` | ✅字段一致 |

星数单独比较：

| 项目 | 文中原值 | 本次原始值 | 判断与来源 |
|---|---:|---:|---|
| ACE | 1.4k | 1455 | ✅作为粗略数量级接近，但不是精确值；若按一位小数四舍五入应为 **1.5k**，若截断则为 1.4k。报告建议引用原始整数，不能据本次快照倒推作者先前查询时的值。[API](https://api.github.com/repos/ace-agent/ace) |
| GEPA | 7.4k | 7427 | ✅约数一致，四舍五入至一位小数为 7.4k。[API](https://api.github.com/repos/gepa-ai/gepa) |

### 1.2 用户补充指定的仓库

AnnaAgent、Sotopia 已在上表核验，分别是 **AGPL-3.0、MIT**，均存在且可访问。其余六个如下；✅表示原文引用的仓库存在，许可为本次补充事实。

| 仓库 / API 原始来源 | 存在且可访问 | `license.spdx_id` | `stargazers_count` | `archived` | `pushed_at` |
|---|---|---|---:|---|---|
| [Cognition-and-Language-Group/PsiArena](https://api.github.com/repos/Cognition-and-Language-Group/PsiArena) | ✅ | `MIT` | 1 | `false` | `2026-06-22T10:02:49Z` |
| [ImprintLab/MedRSI](https://api.github.com/repos/ImprintLab/MedRSI) | ✅ | `MIT` | 9 | `false` | `2026-09-26T21:01:26Z` |
| [qiuhuachuan/interactive-agents](https://api.github.com/repos/qiuhuachuan/interactive-agents) | ✅ | `MIT` | 65 | `false` | `2026-09-08T14:56:10Z` |
| [zou-group/textgrad](https://api.github.com/repos/zou-group/textgrad) | ✅ | `MIT` | 3794 | `false` | `2025-07-25T14:30:39Z` |
| [stanfordnlp/dspy](https://api.github.com/repos/stanfordnlp/dspy) | ✅ | `MIT` | 39040 | `false` | `2026-11-13T14:13:09Z` |
| [microsoft/TinyTroupe](https://api.github.com/repos/microsoft/TinyTroupe) | ✅ | `MIT` | 7653 | `false` | `2026-11-06T21:51:04Z` |

补充描述也有出处：PsiArena README 给出的原始参数是 **25-turn counseling session、client / supervisor / counselor、33 dimensions total**，与 §3 一致；MedRSI README 明确描述按临床代价优先处理失败，以及新工具须在后续多个患者队列持续获益才登记，亦与原文一致。[PsiArena README](https://github.com/Cognition-and-Language-Group/PsiArena/blob/main/README.md)、[MedRSI README](https://github.com/ImprintLab/MedRSI/blob/main/README.md)。这确认的是当前仓库自述，不额外推断它们的作者身份或临床有效性。

### 1.3 许可字段以外的解释

| 文档断言 | 标记 | 查到的原始值、事实边界与来源 |
|---|---|---|
| slumbR 的 `NOASSERTION` 意味着“自定义许可” | ❌不一致 | API 确实是 `NOASSERTION`，但包内 `DESCRIPTION` 明写 **`License: MIT + file LICENSE`**；`LICENSE` 文件内容是 `YEAR: 2025` 和 `COPYRIGHT HOLDER: Lucas França, Mario Leocadio-Miguel`。不能把未自动识别解释成自定义许可。[DESCRIPTION](https://github.com/circadia-bio/slumbR/blob/main/DESCRIPTION)、[LICENSE](https://github.com/circadia-bio/slumbR/blob/main/LICENSE)。GitHub 说明其许可标签由匹配工具识别，复杂格式可能影响识别。[GitHub 文档](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository) |
| TheraMind 没有 LICENSE | ✅一致 | API `license: null`；默认分支递归树 `truncated: false`，12 个路径中未见 LICENSE/COPYING 文件；README 未找到明确代码许可。与论文首页的 **CC BY 4.0** 是两个对象，论文许可不能自动当成仓库代码许可。[完整树](https://api.github.com/repos/Emo-gml/TheraMind/git/trees/main?recursive=1)、[README](https://github.com/Emo-gml/TheraMind/blob/main/README.md)、[论文 v2](https://arxiv.org/pdf/2510.25758v2) |
| TheraMind 是 official evaluation code and data | ✅一致 | README 原文为 **“official evaluation code and data”**。但“clone 跑不起来是正常的”属于运行推测，本次没有安装运行，不能由这句自述证实。[README](https://github.com/Emo-gml/TheraMind/blob/main/README.md) |
| AnnaAgent 代码一旦拷入，“我们仓库会传染成 AGPL” | ❌表述过度概括 | 许可原值确为 `AGPL-3.0`。许可第 5 节区分修改作品与独立作品的聚合；第 13 节规定修改版供远程用户交互时的对应源码提供义务。是否影响其他代码取决于整合方式和适用条款，不能从“放进同一仓库”自动推断全部文件改用 AGPL。[AnnaAgent LICENSE，第 5、13 节](https://github.com/sci-m-wang/AnnaAgent/blob/main/LICENSE) |
| Apache-2.0“保留 NOTICE 与署名即可” | ❌条件列举不完整 | 第 4 节还有提供许可证副本、为修改文件标明改动、保留适用权利声明等条件；NOTICE 的保留义务以前作本身带 NOTICE 为前提。许可名称没错，“即可”省略了条件。[Apache-2.0 第 4 节](https://www.apache.org/licenses/LICENSE-2.0) |
| CPsyCoun 仓库 CC-BY-4.0；“数据集另需协议” | ✅仓库许可；❌若泛指所有数据集 | 仓库 API 是 `CC-BY-4.0`。**D 与 R 要区分**：官方 CPsyCounD 的 Hugging Face 元数据是 `gated: false`、`license: cc-by-sa-4.0`；CPsyCounR 是 `gated: auto`、`license: other` 并附使用授权书。§3 对 D 公开 / R 申请的区分正确，§11 的笼统文字不精确。[D API](https://huggingface.co/api/datasets/CAS-SIAT-XinHai/CPsyCoun)、[R API](https://huggingface.co/api/datasets/CAS-SIAT-XinHai/CPsyCounR) |
| Agent Hospital：CC BY-NC-SA 4.0 | ✅仅对链接中的 arXiv 论文一致 | arXiv `2405.02957` 的 “view license” 指向 **CC BY-NC-SA 4.0**。该行给的是论文链接，**不是 GitHub 仓库许可结果**，故没有仓库星数、archived 或 pushed_at 可列；不能据此推断其他代码仓库许可或“方法思想禁止商业引用”。[论文](https://arxiv.org/abs/2405.02957)、[其许可链接](https://creativecommons.org/licenses/by-nc-sa/4.0/) |

## 2. arXiv 编号、标题、年份及会议标注

对 `RESOURCES.md` 全文提取到 **3 个不同的显式 arXiv 编号**：2510.04618、2405.02957、2601.07312；重复出现的 Agent Hospital 编号只计一次。TheraMind 的 2510.25758 来自指定 PDF 和官方仓库，另外补核。

### 2.1 编号与论文是否对应

| 文中对象与编号 | 标记 | 原始标题、日期及对应内容 | 来源 URL |
|---|---|---|---|
| ACE / 2510.04618 | ✅一致 | **Agentic Context Engineering: Evolving Contexts for Self-Improving Language Models**。首次提交 **2025-10-06**，v3 **2026-03-29**；Comments 为 `ICLR 2026; 32 pages`。摘要明确描述可演进 playbooks、生成/反思/整理及结构化增量更新。文中将 Language Models 简写为 LMs，不是错引论文。 | [arXiv](https://arxiv.org/abs/2510.04618) |
| Agent Hospital / 2405.02957 | ✅一致 | **Agent Hospital: A Simulacrum of Hospital with Evolvable Medical Agents**。首次提交 **2024-05-05**，v3 **2025-01-17**。正文 Agent Evolution 和附录 B.2/B.3 分别讲成功病例积累、失败经验反思/验证/提炼及检索，吻合文中方法描述。 | [arXiv 元数据](https://arxiv.org/abs/2405.02957)、[v3 全文](https://arxiv.org/html/2405.02957v3) |
| PsyCLIENT / 2601.07312 | ✅一致 | **PsyCLIENT: Client Simulation via Conversational Trajectory Modeling for Trainee Practice and Model Evaluation in Mental Health Counseling**。首次提交 **2026-01-12**，v3 **2026-10-22**。摘要明确使用来访画像、历史对话与会话轨迹控制模拟来访响应。最新 Comments 还写 `Accepted to EMNLP 2026 (Main Conference)`；这是来源补充，原清单没有声称该会议。 | [arXiv](https://arxiv.org/abs/2601.07312) |
| TheraMind / 2510.25758（补核） | ✅一致 | **TheraMind: A Strategic and Adaptive Agent for Longitudinal Psychological Counseling**。首次提交 **2025-10-29**，v2 **2026-03-18**。本地文件虽然叫 `03_Hu_2025a_TheraMind.pdf`，实际页首是 **arXiv:2510.25758v2，18 Mar 2026**，不能按文件名当作 2025 原版。 | [arXiv](https://arxiv.org/abs/2510.25758)、[v2 PDF](https://arxiv.org/pdf/2510.25758v2) |

### 2.2 会议 / 出版归属

| 文档标注 | 标记 | 查到的原始值 | 来源与证据层级 |
|---|---|---|---|
| ACE：ICLR’26 | ✅一致 | `Published as a conference paper at ICLR 2026`；作者官网于 **2026-01-30** 公布接受。 | [OpenReview 论文 PDF](https://openreview.net/pdf?id=eC4ygDs02R)（搜索取得论文首页内容）、[作者公告](https://ace-agent.github.io/blogs/2026-01-30-iclr-acceptance/)、[arXiv Comments](https://arxiv.org/abs/2510.04618)。OpenReview 讨论页本次显示浏览器验证，未声称读到评审意见。 |
| TheraMind：WWW’26 | ✅一致 | 本地 PDF 首页 ACM Reference Format：**Proceedings of the ACM Web Conference 2026 (WWW ’26)**，**April 13–17, 2026, Dubai**；DOI **10.1145/3774904.3793049**。 | [同版 PDF](https://arxiv.org/pdf/2510.25758v2)、[官方仓库](https://github.com/Emo-gml/TheraMind)。已读 PDF 首页；ACM DOI 页面本次无法打开，不把它写成已读出版商正文。 |
| AnnaAgent：ACL 2025 Findings | ✅一致 | **AnnaAgent: Dynamic Evolution Agent System with Multi-Session Memory for Realistic Seeker Simulation**；卷名 `Findings of the Association for Computational Linguistics: ACL 2025`；**July 2025**，页 **23221–23235**，DOI **10.18653/v1/2025.findings-acl.1192**。 | [ACL Anthology](https://aclanthology.org/2025.findings-acl.1192/) |
| PsiArena：AAAI 2026 | ✅一致 | **Ψ-Arena: Interactive Assessment and Optimization of LLM-based Psychological Counselors with Tripartite Feedback**；**40(3):2272–2280**；Published **2026-03-14**；DOI **10.1609/aaai.v40i3.37211**；期次 `AAAI-26 Technical Tracks 3`。 | [AAAI 原始条目](https://ojs.aaai.org/index.php/AAAI/article/view/37211)、[AAAI 目录](https://ojs.aaai.org/index.php/AAAI/issue/view/685)。本次直接访问条目被 BotStopper 拒绝，以上来自官方条目的搜索索引，并由[仓库 Citation](https://github.com/Cognition-and-Language-Group/PsiArena/blob/main/README.md)交叉支持。 |
| CPsyCoun：ACL 2024 Findings | ✅一致 | **CPsyCoun: A Report-based Multi-turn Dialogue Reconstruction and Evaluation Framework for Chinese Psychological Counseling**；`Findings of the Association for Computational Linguistics: ACL 2024`；**2024**；DOI **10.18653/v1/2024.findings-acl.830**。 | [ACL Anthology](https://aclanthology.org/2024.findings-acl.830/) |
| AgentSociety：ACL 2025 industry | ✅一致，需指明对应论文 | 对应 **A Parallelized Framework for Simulating Large-Scale LLM Agents with Realistic Environments and Interactions**，Anthology ID **2025.acl-industry.94**。摘要明确框架名为 AgentSociety。不要把同项目所有其他论文都自动标成该会议。 | [ACL Anthology](https://aclanthology.org/2025.acl-industry.94/) |

## 3. TheraMind PDF 逐项核验

本地依据：[指定 PDF](~/bohack/deepsleep/03_Hu_2025a_TheraMind.pdf)，12 页；网页对应版本：[2510.25758v2](https://arxiv.org/pdf/2510.25758v2)。以下页码均为 PDF 页码。英文标签保留大小写原值。

### 3.1 Figure 6 的十项类别和百分比

已查看 **第 8 页 Figure 6 左图**，不是只依靠 OCR 或二手摘要。每行来源均为该图。

| 文档中文标签 | Figure 6 英文原值 | 文档百分比 | 原图百分比 | 标记 / 翻译说明 |
|---|---|---:|---:|---|
| 情感反映 | Reflection of Feelings | 32.54% | 32.54% | ✅一致 |
| 邀请新视角 | Invite to Take New Perspectives | 16.93% | 16.93% | ✅一致 |
| 邀请新行动 | Invite to Explore New Actions | 15.83% | 15.83% | ✅数值和类别对应；准确译法是“邀请探索新行动”，不直接等于开处方 |
| 解释 | Interpretation | 13.36% | 13.36% | ✅对应；心理咨询语境也常译为“诠释”，不等于一般知识讲解 |
| 面质 | Confrontation | 8.31% | 8.31% | ✅一致 |
| 自我暴露 | Self-disclosure | 7.27% | 7.27% | ✅对应；也可译为“自我表露” |
| 肯定安抚 | Affirmation and Reassurance | 4.01% | 4.01% | ✅一致 |
| 复述 | Restatement | 1.51% | 1.51% | ✅一致 |
| 询问主观信息 | Inquiring subjective Information | 0.14% | 0.14% | ✅一致 |
| 最小鼓励 | Minimal Encouragement | 0.11% | 0.11% | ✅一致 |

共同来源 URL：[Figure 6，PDF 第 8 页](https://arxiv.org/pdf/2510.25758v2#page=8)。逐项数值相加为 **100.01%**，属于图中各项保留两位小数后的总和，不是文档抄错。

### 3.2 组件、温度和 Φinit

| 核验项 | 标记 | 原始内容与定位 | 来源 URL |
|---|---|---|---|
| Reaction Classifier 输出情绪、强度、态度 | ✅一致 | 第 4 页 §3.1.1，式 (1)：`S_t=(E_t,I_t,A_t)=Φ_perceive(U_t)`；`I_t∈[0,1]`，`A_t∈{Cooperative, Resistant}`。 | [第 4 页](https://arxiv.org/pdf/2510.25758v2#page=4) |
| Treatment Stage：Engagement → Exploration → Integration | ✅一致 | 第 8 页 Figure 6 中图与 §4.8：六次会谈从早期 Engagement、中期 Exploration 向后期 Integration 变化。第 4 页式 (4) 根据疗法及当前会谈历史识别阶段。它支持“有阶段变量”，不证明所有对话都必须严格按一次固定单向流程切换。 | [第 8 页](https://arxiv.org/pdf/2510.25758v2#page=8)、[第 4 页](https://arxiv.org/pdf/2510.25758v2#page=4) |
| 生成 0.9 / 判断 0.3 | ✅一致 | §4.3 Experimental Settings 跨第 5–6 页：response generation 温度 **0.9**；judgment tasks 温度 **0.3**；`top-p=0.75`、`top-k=20`，判断任务后二者不变。原论文底模为 DeepSeek-V3，不能当作 ds flash 已经验证的参数结论。 | [第 5 页](https://arxiv.org/pdf/2510.25758v2#page=5)、[第 6 页](https://arxiv.org/pdf/2510.25758v2#page=6) |
| Φinit(Case) → (Patient Profile, Session Guides) | ✅一致 | 第 5 页 §3.3 式 (8)：`(P,G)=Φ_init(Case_CPsyCounR)`，`G={g_1,…,g_K}`，six-session arc；100 个病例，10 类各 10 个。 | [第 5 页](https://arxiv.org/pdf/2510.25758v2#page=5) |
| §2.4 将 Session Guides 说成“每轮一个目标” | ❌若“轮”指 turn | 原文为每个 **session（一次会谈）** 的高层目标，不是每个对话 turn 一张目标卡。清单第 1→2 轮指对话轮次时，这里发生了层级混用；项目可以另行改写，但那是自己的适配。 | [§3.3，第 5 页](https://arxiv.org/pdf/2510.25758v2#page=5) |
| Memory Recall：无相关内容返回 null | ✅一致 | 第 4 页 §3.1.2 在式 (2) 后明确说先检查相关性，没有相关记忆则返回 `null`。 | [第 4 页](https://arxiv.org/pdf/2510.25758v2#page=4) |
| 双环分别负责会话内战术、跨会话战略 | ✅一致 | 摘要与 §3：Intra-Session Loop / Cross-Session Loop；第 4 页 §3.2.1 会谈结束后计算疗效分数，第 5 页疗法调整用于后续会谈。 | [第 1 页](https://arxiv.org/pdf/2510.25758v2#page=1)、[第 4 页](https://arxiv.org/pdf/2510.25758v2#page=4) |
| §1 答辩口径称论文是“会话内换疗法” | ❌不一致 | 论文将疗法调整放在 **Cross-Session** 层；会话内选择/调整的是响应策略等变量。原文自身前面的双环表格反而写对了。 | [§3.2，第 4–5 页](https://arxiv.org/pdf/2510.25758v2#page=4) |
| 4 分制与指标名称 | ✅列出的指标存在，但不完整 | 第 5 页 §4.2.2 是 **0–3** 四档；单会谈有 `T.Alli` 和 `Inter`，多会谈有 `Coh / Flex / Emp / T.Attun`。清单省略了 `Inter`；“4 分制”不要被读成 1–4。 | [第 5 页](https://arxiv.org/pdf/2510.25758v2#page=5) |

### 3.3 图表数值与项目自行设定的规则须分开

**❌不能作为论文结论确认**：“分布差太远就说明会谈风格有问题”“解释要负向计分”“面质对防御型来访禁用”“自我暴露少量加分、过量扣分”等，并没有由 Figure 6 给出。图注原始对象是 **Distribution of TheraMind’s intervention strategies**，即该模型的策略使用分布；§4.8 讨论共情和改变策略，未定义项目所写的奖惩函数或通用合格阈值。“共情 / 改变 / 探查”这一中文分组列也不是原图的一列。

来源：[Figure 6 与 §4.8](https://arxiv.org/pdf/2510.25758v2#page=8)、[§4.3 实验设置](https://arxiv.org/pdf/2510.25758v2#page=5)。因此十个数字抄录准确，与“可以直接当质量基线”得到科学支持，是两项不同判断。本次也没有独立核对 Hill 1999 原书的完整分类体系；论文参考文献 [15] 确实列出 Hill 1999 的 Helping skills 著作。

## 4. 软件包存在性、最新版本与发布日期

十二个 PyPI 名称都存在，未发现“包不存在”。本次 Python 默认 TLS 证书链报错后改用系统 `curl` 读取官方 JSON，个别瞬时 SSL 错误重试后成功；未关闭 TLS 校验。下表时间保留 API 原始 UTC 值。原文没给版本号，因此 ✅针对包存在性和身份，不代表运行兼容性验收。

| PyPI 包 / 官方 JSON 来源 | 标记 | `info.version` | 当前版本最早 `upload_time_iso_8601` | 身份核对 |
|---|---|---|---|---|
| [gepa](https://pypi.org/pypi/gepa/json) | ✅存在 | `0.1.4` | `2026-07-15T14:53:58.422522Z` | 反思与 Pareto 搜索框架；项目链接 gepa-ai/gepa |
| [ace-framework](https://pypi.org/pypi/ace-framework/json) | ✅存在 | `0.13.0` | `2026-09-23T14:11:31.017002Z` | Kayba-ai/agentic-context-engine；不是 ace-agent/ace 的同一代码库 |
| [anna-agent](https://pypi.org/pypi/anna-agent/json) | ✅存在 | `0.3.1` | `2026-06-20T17:51:08.314291Z` | 项目链接 sci-m-wang/AnnaAgent |
| [circadian](https://pypi.org/pypi/circadian/json) | ✅存在 | `1.0.3` | `2025-08-18T21:41:42.224701Z` | 项目链接 Arcascope/circadian |
| [pytest-recording](https://pypi.org/pypi/pytest-recording/json) | ✅存在 | `0.14.1` | `2026-11-02T18:12:35.485811Z` | 基于 VCR.py 的 HTTP 录制 / 回放 pytest 插件 |
| [instructor](https://pypi.org/pypi/instructor/json) | ✅存在 | `1.17.0` | `2026-09-09T02:25:54.888746Z` | LLM 结构化输出；项目链接 567-labs/instructor |
| [pydantic-ai](https://pypi.org/pypi/pydantic-ai/json) | ✅存在 | `2.68.0` | `2026-11-12T02:30:01.931003Z` | Pydantic 的 AI Agent 框架 |
| [datamodel-code-generator](https://pypi.org/pypi/datamodel-code-generator/json) | ✅存在 | `0.96.0` | `2026-11-13T20:52:37.906004Z` | 数据模型代码生成器 |
| [dspy](https://pypi.org/pypi/dspy/json) | ✅存在 | `3.5.0` | `2026-11-10T16:24:08.845107Z` | 项目链接 stanfordnlp/dspy |
| [promptfoo](https://pypi.org/pypi/promptfoo/json) | ✅存在 | `0.2.0` | `2026-09-18T19:52:49.745670Z` | promptfoo CLI 的 Python wrapper，实际逻辑仍运行于 npm / Node.js |
| [gdm-concordia](https://pypi.org/pypi/gdm-concordia/json) | ✅存在 | `2.4.0` | `2026-03-06T19:07:13.916763Z` | 项目链接 google-deepmind/concordia |
| [evoagentx](https://pypi.org/pypi/evoagentx/json) | ✅存在 | `0.1.4` | `2026-06-28T10:21:40.525810Z` | 项目链接 EvoAgentX/EvoAgentX |

**promptfoo 额外核对：**

- ✅ npm 主工具存在。npm registry 的 `dist-tags.latest` 为 **`0.125.1`**，`time["0.125.1"]` 为 **`2026-10-25T02:12:24.374Z`**，`engines.node` 为 **`>=22.22.0`**。[npm 原始 JSON](https://registry.npmjs.org/promptfoo)
- ✅ PyPI 同名包不是无关占名包。其项目链接指向 **`https://github.com/promptfoo/promptfoo-python`**；PyPI 介绍说明它是轻量包装器，需要 **Python 3.10+、Node.js 22.22.0+**，底层执行 **`npx promptfoo@latest`**，也可能使用全局已安装版本。[PyPI 页面](https://pypi.org/project/promptfoo/)、[JSON](https://pypi.org/pypi/promptfoo/json)
- ❓原清单的冻结目标是否能实现，本次未运行验证。可确认的遗漏是：当前包装器默认命令含 `@latest`，所以仅冻结 Python 包不等于冻结 npm CLI（根据公开命令作出的推断）。将 promptfoo 写入 requirements-dev 不是包名错误，但应同时说明 Node/npm 运行条件。[包装器官方说明](https://pypi.org/project/promptfoo/)

## 5. 数据集

### 5.1 NHANES 2017–2018 SLQ 与 DPQ

| 项目 | 标记 | 原始值与实测 | CDC 来源 URL |
|---|---|---|---|
| SLQ 文件存在 | ✅一致 | Codebook 标题 **Sleep Disorders (SLQ_J)**；`Data File: SLQ_J.xpt`；**2017–2018**；首次发布 **February 2020**。成功下载 **470560 bytes**，文件开头为 SAS XPORT 的 `HEADER RECORD*******LIBRARY HEADER RECORD`，不是错误 HTML。适用样本 **16 岁及以上**。 | [SLQ Codebook](https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/SLQ_J.htm)、[SLQ_J.xpt](https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/SLQ_J.xpt) |
| DPQ 文件存在、对应 PHQ-9 | ✅一致 | Codebook 标题 **Mental Health - Depression Screener (DPQ_J)**；`Data File: DPQ_J.xpt`；**2017–2018**；首次发布 **February 2020**。成功下载 **489280 bytes**，同样具有 SAS XPORT 头。说明是过去两周的九项抑郁筛查、每题 0–3；公开文件仅含 **18 岁及以上**，青少年数据另有限制。 | [DPQ Codebook](https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/DPQ_J.htm)、[DPQ_J.xpt](https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/DPQ_J.xpt) |

注意：旧式 `/Nchs/Nhanes/2017-2018/SLQ_J.htm` 和 `DPQ_J.htm` 本次返回 CDC Page Not Found；这不是数据不存在，以上是已找到的当前 CDC 路径。这里没有把“成功下载”扩大为已完成联合分布校准或抽样权重分析。

### 5.2 MMASH

| 文档断言 / 所需字段 | 标记 | 查到的原始值与解释 | 来源 URL |
|---|---|---|---|
| 22 人、24h，含睡眠与心理问卷 | ✅一致 | `22 healthy participants`、`24 hours`；方法说明更具体为 **22 名健康年轻成年男性**；初始问卷包括 PSQI、MEQ 等。 | [PhysioNet MMASH 1.0.0](https://physionet.org/content/mmash/1.0.0/) |
| 23MB | ✅近似大小，但缺少口径 | 官方页面 **Total uncompressed size: 23.5 MB**；整站下载 ZIP 按钮 **22.7 MB**；目录内 `MMASH.zip` 显示 **23.5 MB**。因此“约23MB”数量级没错，精确引用应注明下载对象。页面的 uncompressed 是项目文件集合层级，里面本来还有 MMASH.zip，不能直接推断最终 CSV 展开大小。 | [文件清单](https://physionet.org/content/mmash/1.0.0/#files-panel) |
| 许可（原文未写） | ✅已核得 | **Open Data Commons Open Database License v1.0（ODbL 1.0）**，不是无条件公有领域。页面 Access Policy 允许遵循指定许可的任何人访问。 | [许可页](https://physionet.org/content/mmash/view-license/1.0.0/)、[数据首页](https://physionet.org/content/mmash/1.0.0/) |

### 5.3 PMData

| 核验项 | 标记 | 原始值与解释 | 来源 URL |
|---|---|---|---|
| 16 人、5 个月、Fitbit | ✅一致 | 当前发布站描述 **16 persons during 5 months**；正文列 **Fitbit Versa 2**、PMSys、Google Forms。OSF 项目 API 的 description 也写 5 months / 16 persons。 | [Simula 发布站](https://datasets.simula.no/pmdata/)、[OSF 项目 API](https://api.osf.io/v2/nodes/vx4bk/) |
| 大小 | ✅已核得 | 当前发布站下载表 `pmdata.zip`，**1.4GB**。这是发布站标注值，本次没有下载完整 1.4GB 文件或重新计算解压后大小。 | [下载表](https://datasets.simula.no/pmdata/)、[下载文件](https://datasets.simula.no/downloads/pmdata.zip) |
| 当前公开许可 | ✅已核得两处一致声明 | Simula Terms of use 明写 **Creative Commons Attribution 4.0 International (CC BY 4.0)**。OSF 项目关联许可 API 的 `name` 是 **CC-By Attribution 4.0 International**，`url` 指向 `https://creativecommons.org/licenses/by/4.0/legalcode`。 | [发布站条款](https://datasets.simula.no/pmdata/)、[OSF 关联许可](https://api.osf.io/v2/licenses/563c1cf88c5e4a3877f9e96a/) |
| 原论文与当前许可是否完全一致 | ❌来源不一致；❓变更过程未核得 | 下载原论文后用 pdftotext 核到 §3 写 **Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)**。与当前 Simula / OSF 的 **CC BY 4.0** 相冲突。当前站点、OSF 可作为各自当前声明引用，但未找到正式改许可公告，不能假定所有历史副本、第三方图片都自动按同一许可。原清单写“确认许可”，确实仍需在引用时注明版本和来源。 | [作者机构保存的论文 PDF，§3](https://web-backend.simula.no/sites/default/files/publications/files/3339825.3394926.pdf)、[当前发布站](https://datasets.simula.no/pmdata/) |

证据获取说明：Simula 网页在网页工具中多次超时，但系统 curl 成功取得 **44423 字符 HTML**；上述描述、大小和 Terms of use 均来自该 HTML 正文，不是根据第三方论文猜测。

### 5.4 Kaggle Sleep Health and Lifestyle

**✅374 行属实。** 明确对应作者 **Laksika Tharmalingam / uom190346a** 的数据集；Kaggle API 返回 `currentVersionNumber: 2`、`lastUpdated: 2023-09-18T07:27:03.117Z`、`licenseName: CC0: Public Domain`。下载官方 ZIP 后，用 CSV 解析器实数得到 **374 条数据记录（不计表头）、13 列**，文件名为 `Sleep_health_and_lifestyle_dataset.csv`。

来源：[数据集页面](https://www.kaggle.com/datasets/uom190346a/sleep-health-and-lifestyle-dataset)、[官方元数据 API](https://www.kaggle.com/api/v1/datasets/view/uom190346a/sleep-health-and-lifestyle-dataset)、[本次下载接口](https://www.kaggle.com/api/v1/datasets/download/uom190346a/sleep-health-and-lifestyle-dataset)。ZIP 实际 **2604 bytes**。

**❌“自报、偏合成”不够准确。** 元数据介绍虽写 **400 rows and 13 columns**，与实文件不一致；作者 Acknowledgement 明确用 **synthetic** 描述数据，并说明是自己为示例用途创建。因此可以确认“374 行合成数据”；不能把它当成 374 位真实受试者的自报资料。“不是临床证据”的使用边界与作者声明相容。[同一官方元数据 API](https://www.kaggle.com/api/v1/datasets/view/uom190346a/sleep-health-and-lifestyle-dataset)

### 5.5 CPsyCounD 是否公开

**✅公开。** 官方仓库可直接读取 `CPsyCounD/Data/case_0.txt`；README 标注 **3,134 multi-turn consultation dialogues**，并链接到官方 Hugging Face 的 LLaMA-Factory 格式版本。Hugging Face API 实际返回 **`private: false`、`gated: false`**，文件列表包含 **`CPsyCounD.json`**。

来源：[公开样本](https://raw.githubusercontent.com/CAS-SIAT-XinHai/CPsyCoun/main/CPsyCounD/Data/case_0.txt)、[D README](https://github.com/CAS-SIAT-XinHai/CPsyCoun/blob/main/CPsyCounD/README.md)、[HF API](https://huggingface.co/api/datasets/CAS-SIAT-XinHai/CPsyCoun)、[HF 数据卡](https://huggingface.co/datasets/CAS-SIAT-XinHai/CPsyCoun)。**3,134 是作者公布数量，本次未逐条验证全部 JSON 记录。**

许可不能只看代码仓库：官方 HF 数据卡原值是 **`license: cc-by-sa-4.0`**，代码仓库 API 是 **`CC-BY-4.0`**。原文“D 公开、R 需协议”正确；“公开”也不等于任意改许可复用。[数据卡原文](https://huggingface.co/datasets/CAS-SIAT-XinHai/CPsyCoun/raw/main/README.md)

**✅CPsyCounR 另需授权的说法一致。** 官方 README 写需合理申请并签署隐私数据保护协议；HF API 是 `gated: auto`，带“文本数据（案例）研究使用授权书”，字段 `license: other`、`license_name: cas-siat-xinhai-license`。本次仅查看公开元数据，没有申请或下载 R 数据。[仓库 README](https://github.com/CAS-SIAT-XinHai/CPsyCoun/blob/main/README.md)、[R 元数据 API](https://huggingface.co/api/datasets/CAS-SIAT-XinHai/CPsyCounR)

## 6. 12356 热线及与 3-hotlines.md 的对照

对照文件：[3-hotlines.md](~/bohack/research/1114/3-hotlines.md:5)，主要核对第 11–29 行。

| 待核验说法 | 标记 | 原始值与证据 | 与本地热线报告的关系 |
|---|---|---|---|
| “国内统一心理援助热线 12356” | ✅一致 | 国卫医政函〔2024〕259号，成文 **2024-12-06**、原发布 **2024-12-25**；国家卫健委协调工信部设置 **12356** 为全国统一心理援助热线电话号码。[地方卫健部门全文转载](https://www.ghx.gov.cn/ghx/zwgk/bmxzxx/bm/ghxwsjkj/fdzdgknr/ylws/art/2025/art_1818d9fb9487439d84cb9506942540b1.html?xxgkFlg=xxgk)（本次已读全文） | 与第 11 行一致。这里是中国大陆卫生健康系统口径，不扩大为港澳台统一服务。 |
| “2025 年起全国启用” | ✅概括成立，日期应精确化 | 文件要求争取 2025 年元旦或春节前后运行，确保 **2025-05-01 00:00 前**接入。[通知全文](https://www.ghx.gov.cn/ghx/zwgk/bmxzxx/bm/ghxwsjkj/fdzdgknr/ylws/art/2025/art_1818d9fb9487439d84cb9506942540b1.html?xxgkFlg=xxgk)；**2025-05-20** 国家卫健委发布会的官方搜索索引写 **31 个省（区、市）均已开通运行**。[原始发布会 URL](https://www.nhc.gov.cn/xcs/c100122/202505/5163974755e044cfa3883afa80a1f4d0.shtml)（本次直接访问 412，覆盖结论基于官方搜索索引） | 与第 24–25 行一致。不能改写为“2025-01-01 全国全部同步开通”，现有证据不支持该精确日期。 |
| 是否能据此说“全国 24 小时” | ❓未确认；原清单也未这样写 | 全国通知原始最低要求为 **每日不少于 18 小时**。[通知第 2 条](https://www.ghx.gov.cn/ghx/zwgk/bmxzxx/bm/ghxwsjkj/fdzdgknr/ylws/art/2025/art_1818d9fb9487439d84cb9506942540b1.html?xxgkFlg=xxgk) | 本地报告第 13、29 行明确区分全国最低 18 小时与地方 24 小时；RESOURCES.md 未写服务时长，所以属于省略，不是直接矛盾。 |
| 是否确认今天可接通、全年无休或所有通信免费 | ❓未核验 | 本次原始值是文件/发布会中的公开承诺及覆盖信息，没有电话拨测结果、实时接通率或全国统一免通信费证据。[国家通知](https://www.ghx.gov.cn/ghx/zwgk/bmxzxx/bm/ghxwsjkj/fdzdgknr/ylws/art/2025/art_1818d9fb9487439d84cb9506942540b1.html?xxgkFlg=xxgk) | 本地报告第 3、17、29 行也保留这些限制；清单没有作这些额外承诺。 |

**对照结论：没有发现这句热线描述与 `3-hotlines.md` 的直接事实冲突。** 差别在于清单省略了确切接入期限、18 小时的国家最低要求和未拨测边界，不能为了列出“不一致”而把省略改判为矛盾。更精确的事实表达为：“中国大陆全国统一心理援助热线 12356，各地按要求于 2025 年 5 月 1 日零时前接入；2025 年 5 月 20 日国家卫健委公布 31 个省（区、市）已开通。服务时段以当地公布为准。”依据为上表两份国家资料。

## 7. Kyle 2014 睡眠限制规则

来源已定位为 **Kyle 等，Sleep 2014;37(2):229–237，DOI 10.5665/sleep.3386，PMCID PMC3900612**。题目研究 SRT 对客观睡眠时长、白天困倦及警觉性的影响。原始出处：[PMC 全文](https://pmc.ncbi.nlm.nih.gov/articles/PMC3900612/)、[PubMed](https://pubmed.ncbi.nlm.nih.gov/24497651/)。所引用的本地开题调研第 81 行也明确链接这篇论文。

获取说明：PMC 全文首次可读，之后部分请求被验证码拦截；具体规则已从**同一 PMC 原始条目的搜索索引所返回的 Treatment 段落**核到，下表不冒称来自另一篇文献。

| 文档规则 | 标记 | Kyle 2014 原始值 / 精确含义 | 来源 URL |
|---|---|---|---|
| 初始 TIB = 基线周均 TST | ✅一致 | 用 **1 w** 的基线睡眠日记，TIB 处方反映平均 TST；不是以 PSG 某一晚时长直接定处方。 | [PMC，Treatment 段落](https://pmc.ncbi.nlm.nih.gov/articles/PMC3900612/) |
| TIB ≥5h | ✅一致 | 原文 **minimum sleep window = 5 h**。因此是 `max(基线平均TST, 5h)`，不是把所有人的平均 TST 都假定 ≥5h；最低窗口也适用于后续缩短。 | [PMC，Treatment](https://pmc.ncbi.nlm.nih.gov/articles/PMC3900612/) |
| 每周 SE<85% 减15min | ✅一致 | 原值 **<85% → −15 min**，按周调整。 | [PMC，Treatment](https://pmc.ncbi.nlm.nih.gov/articles/PMC3900612/) |
| 85–90% 不变 | ❌边界表达不精确 | 原文中间档写 **≥85–89%**；连续变量的无重叠表达应为 **85%≤SE<90%**。若把“85–90%”的上界包含在内，就与下一条 ≥90% 增加冲突。 | [PMC，Treatment](https://pmc.ncbi.nlm.nih.gov/articles/PMC3900612/) |
| ≥90% 加15min | ✅一致 | 原值 **≥90% → +15 min**；90% 正好落入增加档。 | [PMC，Treatment](https://pmc.ncbi.nlm.nih.gov/articles/PMC3900612/) |
| “当处方规则的唯一出处”应如何理解 | ✅可追溯至该文；不能推出唯一通用标准 | 若只是项目选择该版规则，属于设计决定，不构成事实错误。Kyle 描述该研究方案，且允许对过于困难或难以依从的窗口由治疗师与患者协商；其他协议有变体。 | [Kyle 原文](https://pmc.ncbi.nlm.nih.gov/articles/PMC3900612/)、[Spielman 等协议章节](https://www.med.upenn.edu/cbti/assets/user-content/documents/btsd--advancedsleeprestriction-spielman.pdf) |

与常见协议的具体对照：Spielman、Yang、Glovinsky 的 **2011 年 Sleep Restriction Therapy** 章节，在“Middle Phase”列 **SE≥90% 增加 15 或 30 分钟、85%≤SE<90% 不变、SE<85% 减少 15 或 30 分钟**；老年人的对应阈值是 **85% / 80%**。同章还说明通常评估 **1–2 周**睡眠日记，当前修改版最低 TIB **5h**；回顾早期原始方案时则写 **2 周**基线及 **4.5h**下限。这些是不同方案/版本，不能混成一个统一处方。

来源：[宾大 CBT-I 项目托管的作者章节 PDF，第 11–14 页印刷页码](https://www.med.upenn.edu/cbti/assets/user-content/documents/btsd--advancedsleeprestriction-spielman.pdf)。本次已下载并提取全文。

因此：**初始时长、5h 下限、85/90 阈值及15分钟步长作为 Kyle 2014 的研究规则基本抄对；需要修正的是中间区间的 90% 边界，并把“唯一出处”理解为项目选择采用的一版规则，而不是所有 CBT-I 协议的共同唯一标准。** 这一判断是来源核对，不是对真实患者的个体化处方建议。

## 我没能核验的事项

1. **PMData 从 CC BY-NC 4.0 到当前 CC BY 4.0 的正式变更过程与覆盖范围。** 已拿到原论文、当前 Simula 条款、OSF 许可，后二者一致，但未找到带日期的正式换许可公告，也未逐个核对 1.4GB 包内所有素材的单独许可。[论文](https://web-backend.simula.no/sites/default/files/publications/files/3339825.3394926.pdf)、[当前站点](https://datasets.simula.no/pmdata/)、[OSF 许可](https://api.osf.io/v2/licenses/563c1cf88c5e4a3877f9e96a/)
2. **论文出版页面的部分直接访问。** TheraMind 的 ACM DOI 页面未成功打开，WWW’26 依据是指定 PDF 首页与官方仓库；PsiArena 的 AAAI 页面直接访问被拦截，依据是 AAAI 官方搜索索引及仓库书目；ACE 的 OpenReview 讨论页受浏览器验证限制，会议归属有论文首页、arXiv 与作者公告交叉支持。[ACM DOI](https://doi.org/10.1145/3774904.3793049)、[AAAI](https://ojs.aaai.org/index.php/AAAI/article/view/37211)、[OpenReview](https://openreview.net/forum?id=eC4ygDs02R)。会议标注不是因此就判成不存在，但证据层级如实保留。
3. **热线当日实际接通、逐地时段、接听率和全部运营商通信费用。** 未拨测；国家发布会原站本次 412，31 省开通的原始值来自该官网搜索索引。也没有确认全国统一 24 小时这一更强说法。[国家发布会](https://www.nhc.gov.cn/xcs/c100122/202505/5163974755e044cfa3883afa80a1f4d0.shtml)、[国家通知转载](https://www.ghx.gov.cn/ghx/zwgk/bmxzxx/bm/ghxwsjkj/fdzdgknr/ylws/art/2025/art_1818d9fb9487439d84cb9506942540b1.html?xxgkFlg=xxgk)
4. **把 TheraMind 分布推广为质量阈值、奖惩规则的有效性，以及 Hill 1999 原书完整类别对应。** Figure 6、组件和参数已核；没有从该论文得到“偏离该分布即有问题”的检验依据，也未获取 Hill 原书全文。[TheraMind v2](https://arxiv.org/pdf/2510.25758v2)
5. **各包和仓库在当前项目的实际安装、运行、兼容性及“clone 是否能跑”。** 本次只核包索引/仓库元数据与相关原文，没有运行任何 agent、模型或评测。[TheraMind README](https://github.com/Emo-gml/TheraMind/blob/main/README.md)、[PyPI JSON 接口说明](https://docs.pypi.org/api/json/)。亦未验证清单中“若干小时接完”“免费且确定”等工程效果承诺。
6. **CPsyCounD 全量逐记录数量与 EmoLLM 镜像的现时文件状态。** D 公开性已由官方无门槛元数据和实际样本访问确认；3,134 为作者声明，本次没有下载完整 D JSON 逐条计数，也没有验证“EmoLLM 仓库也有”的精确镜像路径。[官方 D](https://huggingface.co/datasets/CAS-SIAT-XinHai/CPsyCoun)、[官方仓库](https://github.com/CAS-SIAT-XinHai/CPsyCoun)
7. **作者写下 1.4k / 7.4k 时的历史星数快照。** 当前整数已核；本次没有历史 API 日志，不能用当前1455/7427认定过去查询的精确结果。[ACE API](https://api.github.com/repos/ace-agent/ace)、[GEPA API](https://api.github.com/repos/gepa-ai/gepa)
