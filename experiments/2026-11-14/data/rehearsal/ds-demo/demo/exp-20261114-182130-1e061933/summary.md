实验 exp-20261114-182130-1e061933（mock；ISI 为规则模型模拟值）

| 运行 | 版本 | isi_response_rate | path_acc_r2 | referral_recall | referral_precision | crisis_missed | veto.passed |
|---|---|---|---|---|---|---|---|
| 运行 1 | v1 | 0.6667 | 1.0000 | 0.6667 | 1.0000 | 0 | True |
| 对照 | v1 | 0.3333 | 0.5000 | 0.0000 | N/A | 0 | True |
| 运行 2 | v1 | 0.3333 | 0.5000 | 0.0000 | N/A | 0 | True |

学习结果：kept_previous；v1 → v1；evolution_id=exp-20261114-182130-1e061933-learn
未采纳候选；运行 2 与对照使用同一版本。

回退命令：python -m engine.evolve rollback v1
