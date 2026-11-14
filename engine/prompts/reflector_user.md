# 当前 playbook（{{version}}）
```markdown
{{playbook}}
```

# 上一次运行的指标（{{run_label}}，{{n_visitors}} 个来访）
{{metrics}}

# 运行审计（全部来访的经验统计；k/n 中 n 为该格人数，每个数字都可追溯到具体来访）
{{audit}}

# 门禁规则（候选必须在验证集 C 上同时满足，才可能被采纳）
{{gate_rules}}

# 动作预算与章节可见性
{{budget}}

# 往代尝试（新的在后）
{{history}}

# 分维度指标卡
{{scorecard}}

# 分类器证据汇总（全部来访；by-step 曲线略）
{{evidence_summary}}

# 失败案例（共 {{n_failures}} 个，从审计里最大的几类损失中各挑代表）
{{failures}}

# 人类意见（专家纠正、示范与已确认的批注）
{{feedback}}

# 示范批注（心理学同学写的参考，体现我们希望的临床推理方式）
{{fewshot}}

请先在审计里找出最大的几类可学习损失，再按系统说明输出 3 份增量候选；每条改动的 reason 都要引用审计数字并写出预计修复的来访数。
