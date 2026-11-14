# deepsleep

BoHack 2026 · 日新主题赛道「打造会自我进化的智能」

一个会从自己失败的会谈里改写 playbook、下一次运行分数更高的 CBT-I 睡眠管家 agent。

- 完整方案：[docs/PLAN.md](docs/PLAN.md)
- 上下文同步与分工（AI 和人都先读）：[AGENTS.md](AGENTS.md)

## 提交与贡献说明

开发期间，部分组员因网络连接不稳定，使用其他账号或请他人协助提交。其中，通过 [JiaqiChen-tju](https://github.com/JiaqiChen-tju) 和 [RufusMacintosh](https://github.com/RufusMacintosh) 账号提交的相关改动，由本组其他成员完成。感谢协助提交的同学。

## 协作

main 受保护，所有改动走 worktree + PR，规则见 AGENTS.md 第 7 节。

```bash
git clone https://github.com/zhangheqing11/deepsleep.git && cd deepsleep
git fetch origin && git worktree add ../ds-<任务> -b <缩写>/<目录>-<任务> origin/main
```
