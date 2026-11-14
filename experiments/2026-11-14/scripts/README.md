# 历史脚本索引

这些文件是源码归档，不是安装包。实验已跑过，本次未执行任何真实驱动。MANIFEST.json 记录逐文件来源、原 SHA256 与目标路径，历史脚本保留原字节；归档路径改变后，脚本的 `__file__.parents[...]`、ROOT、输出路径与依赖不能直接照用。

## main 已有入口（只引用）

- [engine/integ_trial.py](../../../engine/integ_trial.py)：当前版本与首次联调旧版本默认值不同，需参考每批 manifest.config/source_sha256。
- [analysis/classifier_compare.py](../../../analysis/classifier_compare.py)：原始数据已在 analysis/out；`--resume` 可能调用模型，只有离线分析参数适合只读重分析。
- [engine/demo.py](../../../engine/demo.py) 与 [Makefile](../../../Makefile)：demo-run1/2；实际运行选项见 rehearsal 的 options/cohorts。
- [safety/eval.py](../../../safety/eval.py)：历史请求和实际 provider 可能不同，不能只看文件名前缀。

## 未在本次 main checkout 的历史驱动

| 归档路径 | 来源与用途 | 复用注意 |
|---|---|---|
| [ds-accept/analysis/evo_trial.py](ds-accept/analysis/evo_trial.py) | ds-accept/analysis；三分类器两代进化、文件快照、预算计数、统计与图表 | 历史初始文件名 playbook_v0.md；ROOT 按原 analysis 目录层级定位；report-only 仍依赖历史路径和绘图库，不安装 evo-viz-deps。 |
| [ds-accept/analysis/evo40.py](ds-accept/analysis/evo40.py) | ds-accept/analysis；A40/C32 噪声、顺序 evaluator、一代进化 | 导入 analysis.evo_trial；`--run` 真实调用，`--report`/`--audit` 的旧输出路径需在独立副本修正。 |
| [astra-light/run_light.py](astra-light/run_light.py) | ds-accept/var/astra-light；复用 Jev r0 的轻量实测 | 同目录 audit.py/finalize.py/report.py 一并收录；源脚本按旧相对层级定位 ROOT，不能从归档位置直接执行。 |
| [ds-gate/analysis/gate_fix.py](ds-gate/analysis/gate_fix.py) | gate-fix 报告引用的 ds-gate 工作区；修复后 A40 重测 | 依赖同目录 gate_support.py、gate_diagnose.py、gate_report.py、gate_resume.py、gate_finalize.py 和当时修改过的 engine；基线提交加本地改动不等于当前 main，报告记录的是未提交快照。 |
| [s3/s3-fix1/live.py](s3/s3-fix1/live.py) | engine-session worktree/var/s3-fix1；3 人受限真实 agent 验收 | probe.py、offline_s2.py 同收；live 只用 mock 分类/安全与确定性来访。 |
| [s3/s3-phase2/probe.py](s3/s3-phase2/probe.py) | engine-session worktree/var/s3-phase2；参数探针 | measure_caps.py 是离线计数；component_bench.py 尚未执行；write_summary.py 为报告生成。 |
| [initial-integration/write_report.py](initial-integration/write_report.py) | ds-integ/var/integ；联调报告生成 | 依赖旧 var/integ 目录与当时字段，不能覆盖原归档报告。 |
| [accept-ten/accept/build_report.py](accept-ten/accept/build_report.py) | ds-accept/var/accept；验收报告生成 | 具体文件名以本目录实际文件及 MANIFEST 为准。 |
| [reflection/refl-openai.smoke.py](reflection/refl-openai.smoke.py) | research/codex-tasks；反思器接入 smoke | 可能调用真实模型，仅作来源快照保存。 |

gate-fix 数据目录里原有的 probe/report 辅助 Python 也按原相对路径移到 scripts/gate-fix。所有 Python 的源/目标映射可用 MANIFEST.files 查询。历史驱动所依赖的未提交引擎代码未被伪装成主干实现；本包保存调用入口和配置/源码摘要，不声称单靠这份数据包就能逐字节重现当时全部执行环境。

## 本次归档新增的离线工具

- [verify_archive.py](verify_archive.py)：扫描普通文件和 gzip 内全部成员，验证 MANIFEST SHA256、JSON 可读、路径和大小；没有网络或写入操作，JSON 结果打印到标准输出。
- [validate_checkout.py](validate_checkout.py)：在临时目录运行已有 SFT 生成器；只临时链接缺失的 8 份被忽略导出，拒绝覆盖已有文件。指定解释器运行 pytest，保留日志后清理链接。生成的 dataset_info 必须和仓库原件逐字节一致；不改已有元数据。
