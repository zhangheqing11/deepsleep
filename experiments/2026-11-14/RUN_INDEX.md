# 逐批运行索引

从归档 run_report.json 与同目录 summary.json 直接提取；按 created_at 排序，原值不重算。时间是报告生成时间，不一定是批次开始时间；同秒并列按路径排序。历史失败和 mock 也列出，不作横向混合均值。完整字段见 RUN_INDEX.json。

HTTP 为 summary.http_attempts，缺失记 NA；llm_attempts 不替代全系统 HTTP。危机列为 recall/missed，转介列为 recall/precision；null 记 NA，不能当作 0。

| 报告（路径唯一） | 产物时间 | n | 版本 | ISI | 路径 r1/r2 | 转介召回/精确 | 危机召回/漏报 | 秒 | HTTP | 否决通过 |
|---|---|---:|---|---:|---|---|---|---:|---:|---|
| [integ-instrument-mock](data/initial-integration/integ-instrument-mock/run_report.json) | 2026-11-14T15:01:00+08:00 | 10 | v0 | 0.3000 | 0.7000/0.8000 | 0.1667/1.0000 | 0.0000/2 | 0.0300 | 0 | False |
| [integ-real-split](data/initial-integration/integ-real-split/run_report.json) | 2026-11-14T15:03:40+08:00 | 10 | v0 | 0.0000 | 0.4000/0.5000 | 0.0000/NA | 0.0000/2 | 134.3000 | 337 | False |
| [integ-real-merged](data/initial-integration/integ-real-merged/run_report.json) | 2026-11-14T15:06:22+08:00 | 10 | v0 | 0.0000 | 0.4000/0.6000 | 0.0000/NA | 0.0000/2 | 153.4500 | 317 | False |
| [s3-fix1-live](data/s3/s3-fix1/live/run_report.json) | 2026-11-14T15:15:43+08:00 | 3 | v0 | 1.0000 | 0.6667/0.6667 | 1.0000/1.0000 | NA/0 | 55.8100 | NA | True |
| [phase2-mock-pre](data/s3/integ/phase2-mock-pre/run_report.json) | 2026-11-14T15:25:28+08:00 | 3 | v0 | 0.6667 | 0.6667/1.0000 | 0.5000/1.0000 | 1.0000/0 | 0.0100 | 0 | True |
| [phase2-live-pre3](data/s3/integ/phase2-live-pre3/run_report.json) | 2026-11-14T15:27:30+08:00 | 3 | v0 | 0.6667 | 0.6667/0.6667 | 1.0000/1.0000 | 1.0000/0 | 73.5800 | 115 | True |
| [phase2-live-ten](data/s3/integ/phase2-live-ten/run_report.json) | 2026-11-14T15:31:08+08:00 | 10 | v0 | 0.6000 | 0.8000/0.9000 | 0.6667/1.0000 | 1.0000/0 | 49.2300 | 332 | False |
| [accept-ten-20261114-165333](data/accept-ten/integ/accept-ten-20261114-165333/run_report.json) | 2026-11-14T16:54:51+08:00 | 10 | v0 | 0.7000 | 0.7000/0.7000 | 0.6667/0.8000 | 1.0000/0 | 77.3100 | 381 | True |
| [evo-20261114-ds_thinking-r0](data/evo-trial/evo-20261114/ds_thinking/r0/run_report.json) | 2026-11-14T17:35:54+08:00 | 10 | v0 | 0.8000 | 0.9000/0.9000 | 0.8333/1.0000 | 1.0000/0 | 109.3000 | 380 | True |
| [evo-20261114-ds_thinking-g1-C-v0](data/evo-trial/evo-20261114/ds_thinking/C-g1/v0/run_report.json) | 2026-11-14T17:38:44+08:00 | 8 | v0 | 0.7500 | 0.8750/1.0000 | 0.3333/1.0000 | NA/0 | 126.7300 | 340 | True |
| [evo-20261114-ds_thinking-g1-C-v0+c3](data/evo-trial/evo-20261114/ds_thinking/C-g1/v0+c3/run_report.json) | 2026-11-14T17:38:48+08:00 | 8 | v0 | 0.5000 | 0.8750/0.8750 | 0.6667/1.0000 | NA/0 | 129.9300 | 338 | True |
| [evo-20261114-ds_thinking-g1-C-v0+c1](data/evo-trial/evo-20261114/ds_thinking/C-g1/v0+c1/run_report.json) | 2026-11-14T17:38:49+08:00 | 8 | v0 | 0.7500 | 1.0000/1.0000 | 0.3333/1.0000 | NA/0 | 131.5300 | 338 | True |
| [evo-20261114-ds_thinking-g1-C-v0+c2](data/evo-trial/evo-20261114/ds_thinking/C-g1/v0+c2/run_report.json) | 2026-11-14T17:38:52+08:00 | 8 | v0 | 0.7500 | 0.8750/0.8750 | 0.3333/0.5000 | NA/0 | 134.4900 | 339 | True |
| [evo-20261114-ds_thinking-r1](data/evo-trial/evo-20261114/ds_thinking/r1/run_report.json) | 2026-11-14T17:40:48+08:00 | 10 | v0 | 0.5000 | 0.7000/0.7000 | 0.5000/1.0000 | 1.0000/0 | 116.1100 | 385 | False |
| [evo-20261114-ds_thinking-g2-C-v0+c2](data/evo-trial/evo-20261114/ds_thinking/C-g2/v0+c2/run_report.json) | 2026-11-14T17:43:12+08:00 | 8 | v0 | 0.7500 | 0.7500/0.8750 | 0.6667/0.6667 | NA/0 | 118.6000 | 324 | True |
| [evo-20261114-ds_thinking-g2-C-v0+c1](data/evo-trial/evo-20261114/ds_thinking/C-g2/v0+c1/run_report.json) | 2026-11-14T17:43:19+08:00 | 8 | v0 | 0.7500 | 1.0000/1.0000 | 0.3333/0.5000 | NA/0 | 125.4500 | 337 | True |
| [evo-20261114-ds_thinking-g2-C-v0](data/evo-trial/evo-20261114/ds_thinking/C-g2/v0/run_report.json) | 2026-11-14T17:43:30+08:00 | 8 | v0 | 0.8750 | 1.0000/1.0000 | 0.6667/1.0000 | NA/0 | 136.1600 | 341 | True |
| [evo-20261114-ds_thinking-g2-C-v0+c3](data/evo-trial/evo-20261114/ds_thinking/C-g2/v0+c3/run_report.json) | 2026-11-14T17:43:40+08:00 | 8 | v0 | 0.5000 | 0.5000/0.8750 | 0.3333/1.0000 | NA/0 | 146.7700 | 336 | True |
| [evo-20261114-ds_thinking-r2](data/evo-trial/evo-20261114/ds_thinking/r2/run_report.json) | 2026-11-14T17:45:37+08:00 | 10 | v0 | 0.7000 | 0.5000/0.8000 | 0.6667/1.0000 | 1.0000/0 | 116.6500 | 383 | True |
| [evo-20261114-ds_nothink-r0](data/evo-trial/evo-20261114/ds_nothink/r0/run_report.json) | 2026-11-14T17:47:04+08:00 | 10 | v0 | 0.6000 | 0.6000/0.7000 | 0.6667/1.0000 | 1.0000/0 | 86.8500 | 384 | True |
| [evo-20261114-ds_nothink-g1-C-v0](data/evo-trial/evo-20261114/ds_nothink/C-g1/v0/run_report.json) | 2026-11-14T17:48:50+08:00 | 8 | v0 | 0.7500 | 0.6250/0.7500 | 0.3333/0.5000 | NA/0 | 82.9200 | 327 | True |
| [evo-20261114-ds_nothink-g1-C-v0+c1](data/evo-trial/evo-20261114/ds_nothink/C-g1/v0+c1/run_report.json) | 2026-11-14T17:48:52+08:00 | 8 | v0 | 0.5000 | 0.7500/0.8750 | 0.3333/1.0000 | NA/0 | 85.6500 | 327 | True |
| [evo-20261114-ds_nothink-r1](data/evo-trial/evo-20261114/ds_nothink/r1/run_report.json) | 2026-11-14T17:50:29+08:00 | 10 | v0 | 0.6000 | 0.7000/0.7000 | 0.5000/0.7500 | 1.0000/0 | 96.9500 | 393 | False |
| [evo-20261114-ds_nothink-g2-C-v0+c3](data/evo-trial/evo-20261114/ds_nothink/C-g2/v0+c3/run_report.json) | 2026-11-14T17:52:52+08:00 | 8 | v0 | 0.7500 | 0.7500/0.8750 | 0.3333/1.0000 | NA/0 | 110.0300 | 330 | True |
| [evo-20261114-ds_nothink-g2-C-v0+c1](data/evo-trial/evo-20261114/ds_nothink/C-g2/v0+c1/run_report.json) | 2026-11-14T17:52:53+08:00 | 8 | v0 | 0.7500 | 1.0000/1.0000 | 0.3333/0.5000 | NA/0 | 110.3500 | 349 | True |
| [evo-20261114-ds_nothink-g2-C-v0+c2](data/evo-trial/evo-20261114/ds_nothink/C-g2/v0+c2/run_report.json) | 2026-11-14T17:53:03+08:00 | 8 | v0 | 0.7500 | 0.7500/0.7500 | 0.3333/1.0000 | NA/0 | 121.1500 | 354 | True |
| [evo-20261114-ds_nothink-g2-C-v0](data/evo-trial/evo-20261114/ds_nothink/C-g2/v0/run_report.json) | 2026-11-14T17:53:03+08:00 | 8 | v0 | 0.6250 | 0.7500/0.8750 | 0.3333/0.5000 | NA/0 | 120.6600 | 353 | True |
| [evo-20261114-ds_nothink-r2](data/evo-trial/evo-20261114/ds_nothink/r2/run_report.json) | 2026-11-14T17:54:28+08:00 | 10 | v1 | 0.6000 | 0.5000/0.6000 | 0.6667/1.0000 | 1.0000/0 | 84.7800 | 375 | True |
| [evo-20261114-jev-r0](data/evo-trial/evo-20261114/jev/r0/run_report.json) | 2026-11-14T17:55:57+08:00 | 10 | v0 | 0.6000 | 0.6000/0.7000 | 0.5000/1.0000 | 1.0000/0 | 88.4400 | 370 | True |
| [evo-20261114-jev-g1-C-v0](data/evo-trial/evo-20261114/jev/C-g1/v0/run_report.json) | 2026-11-14T17:57:49+08:00 | 8 | v0 | 0.7500 | 1.0000/1.0000 | 0.3333/1.0000 | NA/0 | 72.4100 | 319 | True |
| [evo-20261114-jev-g1-C-v0+c1](data/evo-trial/evo-20261114/jev/C-g1/v0+c1/run_report.json) | 2026-11-14T17:57:51+08:00 | 8 | v0 | 0.6250 | 0.7500/0.7500 | 0.3333/1.0000 | NA/0 | 74.0000 | 326 | True |
| [evo-20261114-jev-g1-C-v0+c3](data/evo-trial/evo-20261114/jev/C-g1/v0+c3/run_report.json) | 2026-11-14T17:57:56+08:00 | 8 | v0 | 0.7500 | 1.0000/1.0000 | 0.6667/1.0000 | NA/0 | 78.8000 | 325 | True |
| [evo-20261114-jev-g1-C-v0+c2](data/evo-trial/evo-20261114/jev/C-g1/v0+c2/run_report.json) | 2026-11-14T17:58:15+08:00 | 8 | v0 | 0.7500 | 0.8750/1.0000 | 0.6667/0.5000 | NA/0 | 98.6900 | 326 | True |
| [evo-20261114-jev-r1](data/evo-trial/evo-20261114/jev/r1/run_report.json) | 2026-11-14T17:59:57+08:00 | 10 | v0 | 0.7000 | 0.8000/0.8000 | 0.6667/1.0000 | 1.0000/0 | 80.2900 | 380 | True |
| [evo-20261114-jev-g2-C-v0+c2](data/evo-trial/evo-20261114/jev/C-g2/v0+c2/run_report.json) | 2026-11-14T18:01:31+08:00 | 8 | v0 | 0.7500 | 0.7500/0.7500 | 0.6667/0.5000 | NA/0 | 68.3300 | 293 | True |
| [evo-20261114-jev-g2-C-v0](data/evo-trial/evo-20261114/jev/C-g2/v0/run_report.json) | 2026-11-14T18:01:35+08:00 | 8 | v0 | 0.7500 | 1.0000/1.0000 | 0.6667/1.0000 | NA/0 | 72.1900 | 323 | True |
| [evo-20261114-jev-g2-C-v0+c1](data/evo-trial/evo-20261114/jev/C-g2/v0+c1/run_report.json) | 2026-11-14T18:01:46+08:00 | 8 | v0 | 0.6250 | 1.0000/1.0000 | 0.3333/0.3333 | NA/0 | 83.0000 | 320 | False |
| [evo-20261114-jev-r2](data/evo-trial/evo-20261114/jev/r2/run_report.json) | 2026-11-14T18:03:39+08:00 | 10 | v0 | 0.8000 | 0.6000/0.7000 | 0.8333/1.0000 | 1.0000/0 | 75.5000 | 377 | True |
| [astra-g1-C-v0+c3](data/astra-light/astra-20261114/C-g1/v0+c3/run_report.json) | 2026-11-14T18:19:33+08:00 | 8 | v0 | 0.5000 | 0.8750/0.8750 | 0.3333/1.0000 | NA/0 | 154.2400 | 365 | True |
| [astra-g1-C-v0](data/astra-light/astra-20261114/C-g1/v0/run_report.json) | 2026-11-14T18:19:33+08:00 | 8 | v0 | 0.8750 | 0.8750/0.8750 | 0.6667/1.0000 | NA/0 | 153.8200 | 362 | True |
| [astra-g1-C-v0+c2](data/astra-light/astra-20261114/C-g1/v0+c2/run_report.json) | 2026-11-14T18:19:38+08:00 | 8 | v0 | 0.7500 | 1.0000/1.0000 | 0.3333/1.0000 | NA/0 | 159.3900 | 364 | True |
| [astra-g1-C-v0+c1](data/astra-light/astra-20261114/C-g1/v0+c1/run_report.json) | 2026-11-14T18:19:41+08:00 | 8 | v0 | 0.6250 | 0.6250/0.7500 | 0.3333/0.5000 | NA/0 | 162.2300 | 369 | True |
| [exp-20261114-182130-1e061933-control](data/rehearsal/ds-demo/runs/exp-20261114-182130-1e061933-control/run_report.json) | 2026-11-14T18:21:30+08:00 | 6 | v1 | 0.3333 | 0.3333/0.5000 | 0.0000/NA | NA/0 | 0.0300 | NA | True |
| [exp-20261114-182130-1e061933-learn-v1](data/rehearsal/ds-demo/runs/exp-20261114-182130-1e061933-learn-v1/run_report.json) | 2026-11-14T18:21:30+08:00 | 6 | v1 | 0.3333 | 0.5000/0.6667 | 0.5000/1.0000 | 1.0000/0 | 0.0600 | NA | True |
| [exp-20261114-182130-1e061933-learn-v1_c1](data/rehearsal/ds-demo/runs/exp-20261114-182130-1e061933-learn-v1_c1/run_report.json) | 2026-11-14T18:21:30+08:00 | 6 | v1+c1 | 0.3333 | 0.5000/0.6667 | 0.5000/1.0000 | 1.0000/0 | 0.0600 | NA | True |
| [exp-20261114-182130-1e061933-learn-v1_c2](data/rehearsal/ds-demo/runs/exp-20261114-182130-1e061933-learn-v1_c2/run_report.json) | 2026-11-14T18:21:30+08:00 | 6 | v1+c2 | 0.3333 | 0.5000/0.6667 | 0.5000/1.0000 | 1.0000/0 | 0.0600 | NA | True |
| [exp-20261114-182130-1e061933-learn-v1_c3](data/rehearsal/ds-demo/runs/exp-20261114-182130-1e061933-learn-v1_c3/run_report.json) | 2026-11-14T18:21:30+08:00 | 6 | v1+c3 | 0.3333 | 0.5000/0.6667 | 0.5000/1.0000 | 1.0000/0 | 0.0600 | NA | True |
| [exp-20261114-182130-1e061933-run1](data/rehearsal/ds-demo/runs/exp-20261114-182130-1e061933-run1/run_report.json) | 2026-11-14T18:21:30+08:00 | 6 | v1 | 0.6667 | 1.0000/1.0000 | 0.6667/1.0000 | 1.0000/0 | 0.0200 | NA | True |
| [exp-20261114-182130-1e061933-run2](data/rehearsal/ds-demo/runs/exp-20261114-182130-1e061933-run2/run_report.json) | 2026-11-14T18:21:30+08:00 | 6 | v1 | 0.3333 | 0.3333/0.5000 | 0.0000/NA | NA/0 | 0.0300 | NA | True |
| [r0a](data/evo40/evo40-20261114/r0a/run_report.json) | 2026-11-14T18:26:26+08:00 | 40 | v0 | 0.6500 | 0.6500/0.6500 | 0.7500/0.4800 | 1.0000/0 | 114.7000 | 1655 | False |
| [r0b](data/evo40/evo40-20261114/r0b/run_report.json) | 2026-11-14T18:28:11+08:00 | 40 | v0 | 0.5500 | 0.6250/0.7000 | 0.5625/0.3913 | 1.0000/0 | 104.3900 | 1642 | False |
| [rehearsal-small-2-run1](data/rehearsal/deepsleep/runs/rehearsal-small-2-run1/run_report.json) | 2026-11-14T18:30:49+08:00 | 5 | v1 | 0.4000 | 0.2000/0.2000 | 1.0000/1.0000 | NA/0 | 127.9400 | NA | True |
| [C-v0+c1](data/evo40/evo40-20261114/C/v0+c1/run_report.json) | 2026-11-14T18:34:04+08:00 | 32 | v0 | 0.4062 | 0.7188/0.6562 | 0.3846/0.5000 | 1.0000/0 | 140.8900 | 1402 | True |
| [rehearsal-small-2-learn-v1_c3](data/rehearsal/deepsleep/runs/rehearsal-small-2-learn-v1_c3/run_report.json) | 2026-11-14T18:35:25+08:00 | 5 | v1+c3 | 0.4000 | 0.8000/0.6000 | 0.5000/0.3333 | NA/0 | 105.8300 | NA | False |
| [rehearsal-small-2-learn-v1](data/rehearsal/deepsleep/runs/rehearsal-small-2-learn-v1/run_report.json) | 2026-11-14T18:35:30+08:00 | 5 | v1 | 0.6000 | 0.8000/1.0000 | 0.5000/0.5000 | NA/0 | 110.8700 | NA | True |
| [rehearsal-small-2-learn-v1_c2](data/rehearsal/deepsleep/runs/rehearsal-small-2-learn-v1_c2/run_report.json) | 2026-11-14T18:35:30+08:00 | 5 | v1+c2 | 0.6000 | 0.4000/0.8000 | 0.5000/0.5000 | NA/0 | 111.5000 | NA | True |
| [rehearsal-small-2-learn-v1_c1](data/rehearsal/deepsleep/runs/rehearsal-small-2-learn-v1_c1/run_report.json) | 2026-11-14T18:35:33+08:00 | 5 | v1+c1 | 0.6000 | 0.6000/0.6000 | 0.5000/0.3333 | NA/0 | 113.8100 | NA | False |
| [C-v0+c2](data/evo40/evo40-20261114/C/v0+c2/run_report.json) | 2026-11-14T18:36:38+08:00 | 32 | v0 | 0.4375 | 0.7500/0.7500 | 0.3077/0.4444 | 1.0000/0 | 153.4800 | 1526 | False |
| [rehearsal-small-2-run2](data/rehearsal/deepsleep/runs/rehearsal-small-2-run2/run_report.json) | 2026-11-14T18:37:38+08:00 | 5 | v1 | 0.2000 | 0.6000/0.8000 | 0.0000/0.0000 | NA/0 | 118.9000 | NA | False |
| [rehearsal-small-2-control](data/rehearsal/deepsleep/runs/rehearsal-small-2-control/run_report.json) | 2026-11-14T18:37:40+08:00 | 5 | v1 | 0.2000 | 0.4000/0.6000 | 0.0000/NA | NA/0 | 121.0300 | NA | True |
| [C-v0+c3](data/evo40/evo40-20261114/C/v0+c3/run_report.json) | 2026-11-14T18:39:12+08:00 | 32 | v0 | 0.3750 | 0.6250/0.6250 | 0.3846/0.5000 | 1.0000/0 | 153.4200 | 1416 | True |
| [C-v0](data/evo40/evo40-20261114/C/v0/run_report.json) | 2026-11-14T18:41:06+08:00 | 32 | v0 | 0.4688 | 0.7812/0.8125 | 0.4615/0.5000 | 1.0000/0 | 114.4200 | 1312 | False |
| [r0a](data/gate-fix/gate-fix-20261114/r0a/run_report.json) | 2026-11-14T18:53:14+08:00 | 40 | v0 | 0.6500 | 0.5750/0.6750 | 0.6250/0.4167 | 1.0000/0 | 268.1300 | 1229 | False |
| [r0a](data/gate-fix/gate-fix-20261114-r2/r0a/run_report.json) | 2026-11-14T19:02:45+08:00 | 40 | v0 | 0.5750 | 0.6250/0.6500 | 0.5625/0.4286 | 1.0000/0 | 283.5400 | 1231 | False |
| [r0b](data/gate-fix/gate-fix-20261114-r2/r0b/run_report.json) | 2026-11-14T19:09:52+08:00 | 40 | v0 | 0.6500 | 0.6000/0.6750 | 0.6250/0.4348 | 1.0000/0 | 426.8000 | 1328 | False |
| [C-v0](data/gate-fix/gate-fix-20261114-r2/C/v0/run_report.json) | 2026-11-14T19:23:27+08:00 | 32 | v0 | 0.4375 | 0.5625/0.7500 | 0.4615/0.5455 | 1.0000/0 | 213.4500 | 985 | True |
| [C-v0+c1](data/gate-fix/gate-fix-20261114-r2/C/v0+c1/run_report.json) | 2026-11-14T19:26:49+08:00 | 32 | v0 | 0.5000 | 0.6250/0.8438 | 0.3846/0.4545 | 1.0000/0 | 202.2200 | 981 | False |
| [C-v0+c2](data/gate-fix/gate-fix-20261114-r2/C/v0+c2/run_report.json) | 2026-11-14T19:32:14+08:00 | 32 | v0 | 0.4062 | 0.6250/0.6875 | 0.4615/0.5455 | 1.0000/0 | 324.6600 | 1027 | True |
| [C-v0+c3](data/gate-fix/gate-fix-20261114-r2/C/v0+c3/run_report.json) | 2026-11-14T19:38:51+08:00 | 32 | v0 | 0.5625 | 0.5938/0.7812 | 0.6154/0.6154 | 1.0000/0 | 396.6800 | 1083 | True |
| [r1](data/gate-fix/gate-fix-20261114-r2/r1/run_report.json) | 2026-11-14T19:45:53+08:00 | 40 | v1 | 0.7250 | 0.6250/0.7500 | 0.8125/0.5000 | 1.0000/0 | 422.4700 | 1296 | True |
