# deepsleep

BoHack 2026 · 日新主题赛道「打造会自我进化的智能」

一个会从自己失败的会谈里改写 playbook、下一次运行分数更高的 CBT-I 睡眠管家 agent。

- 完整方案：[docs/PLAN.md](docs/PLAN.md)
- 上下文同步与分工（AI 和人都先读）：[AGENTS.md](AGENTS.md)

## 协作

main 受保护，所有改动走 worktree + PR，规则见 AGENTS.md 第 7 节。

```bash
git clone https://github.com/zhangheqing11/deepsleep.git && cd deepsleep
git fetch origin && git worktree add ../ds-<任务> -b <缩写>/<目录>-<任务> origin/main
```
