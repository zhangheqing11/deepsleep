# 当前 playbook（{{version}}）
```markdown
{{playbook}}
```

# 上一次运行的指标（{{run_label}}，{{n_visitors}} 个来访）
{{metrics}}

# 分维度指标卡
{{scorecard}}

# 分类器证据汇总（全部来访；by-step 曲线略）
{{evidence_summary}}

# 失败案例（共 {{n_failures}} 个，按失败类型优先级挑选）
{{failures}}

# 人类意见（专家纠正、示范与已确认的批注）
{{feedback}}

# 示范批注（心理学同学写的参考，体现我们希望的临床推理方式）
{{fewshot}}

请按系统说明输出 3 份增量候选。
