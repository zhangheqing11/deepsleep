.PHONY: venv contracts smoke test safety-eval

PROVIDER ?= rules

venv: .venv/.requirements-installed

.venv/.requirements-installed: requirements.txt
	python3 -m venv .venv
	.venv/bin/python -m pip install -r requirements.txt
	touch $@

contracts: venv
	.venv/bin/python contracts/validate.py

# 契约校验 + 全部单元测试 + 10 个样例来访 + mock LLM + stub agent 的端到端冒烟（scoring/smoke.py，全部过契约校验）。
smoke: contracts test
	.venv/bin/python -m scoring.smoke

test: venv
	.venv/bin/python -m pytest -q tests

safety-eval: venv
	.venv/bin/python -m safety.eval --provider $(PROVIDER)

.PHONY: check-keys
check-keys: venv
	.venv/bin/python scripts/check_keys.py
