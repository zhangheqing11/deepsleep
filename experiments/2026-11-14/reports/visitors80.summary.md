# 临时扩充来访集交付总结（2026-11-14）

完成 A 40 + C 32，共 **72 张**来访卡。文件名沿用任务指定的 `visitors80.summary.md`，不代表 80 人。
工作目录 `/Users/zhangheqing/bohack/ds-vis`，分支 `zhq/sim-interim-visitors`。
纯代码规则生成，默认 seed `20261114`，未调用任何 LLM API，未新增依赖。

## 交付物

- `sim/gen_interim.py`：读取审定线索表，配额分配、组合去重、日记/自评生成、契约校验、CLI 与分布统计。
- `data/visitors/interim/A/A-001.json` 至 `A-040.json`。
- `data/visitors/interim/C/C-001.json` 至 `C-032.json`。
- `tests/test_gen_interim.py`：13 项测试，含五个 seed 的配额检查。
- `docs/handoff-algo.md` 第 7 节“临时扩充集”：生成、读取、替换目录、出处、分布与局限。

## 生成

```bash
cd /Users/zhangheqing/bohack/ds-vis
/Users/zhangheqing/bohack/ds-safety/.venv/bin/python -m sim.gen_interim --seed 20261114
```

可加 `--out /tmp/interim-preview`。同 seed、同源码及审定语料版本确定性复现；
不会读取 `.env`、访问网络或操作 git。覆盖本批对应文件，不清理其他文件。

## 分布统计

| 指标 | A（40） | C（32） |
|---|---:|---:|
| P1 | 8（20.0%） | 7（21.9%） |
| P2 | 8（20.0%） | 7（21.9%） |
| P3 | 8（20.0%） | 6（18.8%） |
| P4 | 8（20.0%） | 6（18.8%） |
| P5 | 8（20.0%） | 6（18.8%） |
| 有次路径 | 12（30.0%） | 10（31.3%） |
| R0 | 24（60.0%） | 19（59.4%） |
| R1 | 6（15.0%） | 5（15.6%） |
| R2 | 5（12.5%） | 4（12.5%） |
| R3 | 5（12.5%） | 4（12.5%） |
| 已预填自评 | 16（40.0%） | 13（40.6%） |
| defensiveness low | 16（40.0%） | 13（40.6%） |
| defensiveness mid | 16（40.0%） | 13（40.6%） |
| defensiveness high | 8（20.0%） | 6（18.8%） |
| passive | 3 | 2 |
| active | 2 | 1 |
| history | 3 | 2 |
| none（排除 history） | 32 | 27 |
| 至少一个睡眠限制禁忌 | 6 | 5 |

history 的字段仍为 `level=none, history=true, phq9_item9=0`；上表把它单列。
所有 R1 带 `untreated_osa`；R1-c4 对应驾驶职业同时带 `drowsy_driving_job`。
无 R1/R3 重叠。R2 明确有静息/想动、活动缓解、夜间加重线索。
R0 每人带一条审定近似线索；每组 R1/R3 各至少一个防御型低自评难例。

## 出处与去重

每条 `clues[].id` 格式为 `<visitor-id>::<file>#<source-id>`。
普通路径/转介直接引用 Pn-cn / Rn-cn。近似线索引用 `RC-7:1.3/2.4/3.3`。
危机/history 保留已审定 sample 原文，引用 `review-C7:sample-NNN-cN`，
对应 `docs/review-decisions.md` 第二批 C7；未新编危机话术。

72 张卡的无序出处集合及整卡线索文本集合均不重复；不靠 ID、人格、顺序或标点去重。
与 S2 18 张旧卡的文本集合不重合，并排除可重合的 sample-003 / sample-006 来源组合。
其他转介样例的主线索条数或倒班线索与本集不同；所有新 R0 另有旧样例不含的 RC-7 近似线索。
单条线索、开场和审定危机原文可重复，不把本批称作独立临床留出集。

## 验证结果

- RED：新增测试在生成器不存在时失败；日记测试进一步复现 P4 放假入睡时间与 P5 屏幕时长不一致，随后修正生成参数。
- 最终 `/Users/zhangheqing/bohack/ds-safety/.venv/bin/python -m pytest -q --ignore=api`：**834 passed in 13.50s**。
- `make -o .venv/.requirements-installed contracts`：**10 个契约示例全部 OK**。
  使用短暂 `.venv` 链接指向任务指定的 Python 环境；`-o` 只跳过 venv 重建/依赖安装，执行原 `contracts` 目标。链接已在结束前移除，不改变 Makefile 或共享环境。
- 新增 72 卡另由生成器写前校验及测试调用 `validate_document` 逐张校验通过（并非仅靠上面的示例检查）。
- 实际 `engine.run.load_visitors` 从 A/C 目录分别读到 40/32 张；全部通过 `SimVisitor(visitor, None)` 的 mock 两次话题追问，所有线索 ID 可正确释放。
- `git diff --check` 通过；受保护目录与文件未修改。

## 今晚接入与替换

A 输入目录 `data/visitors/interim/A`；C evaluator 输入目录 `data/visitors/interim/C`。
现有目录加载器不递归；不要只传 `data/visitors/interim` 父目录。
数据科学同学替换时只需换上述两个数据输入目录，继续产出 visitor v0.1.0，接口不变。
换批次使用新的 run_id/输出目录，避免相同 A/C ID 混入历史结果。

**当前引擎 CLI 限制：** `engine/run.py` 的 `--scorer` 分支把报告 `split` 固定成 `sample`
且 role 固定成 validation。今晚驱动需对 A/C 向 `score_run` / `build_report` 传正确 split/role。
本任务未修改引擎。S4 `--visitors` 提供的是运行组卡片，C 由 evaluator 单独加载；
不得把 C 失败案例用于反思学习。

## 局限与状态

- 临时模板组合，仅供工程实测。共享模板、固定配额和占位量表/人格不能代表人群分布，未证明增益或波动减少。
- 没有 B/offline；P4 只覆盖节律偏晚，未覆盖倒班；禁忌限于已有审定 OSA 与驾驶风险，不覆盖全部禁忌。
- 日记按 S2 算法与文本时间约束生成；MEQ/DBAS/PSAS 留 null。四周状态模型未改变，仍是原有占位模型。
- 未改 `contracts/`、`engine/`、`safety/`、`sim/visitor_sim.py`；未运行真实会谈或进化、未 commit/push/PR。
- 本会话未写工作区 `.git` 或执行 fetch/rebase。开工时本地与 origin/main 相同；收尾时 origin/main 已被外部更新一个提交。
  当前 HEAD `eedbf73`，本地跟踪的 origin/main `90aab15`（根目录上下文文件移动，#32）。依“不写 .git”要求保留当前 checkout。

## 数据摘要

按相对路径排序，依次输入 UTF-8 相对路径、NUL、文件字节计算 SHA-256：

`9e068022ec3dc44f7845782295e71c2efa8661695e356d192d40ec7d5970ab11`
