.PHONY: venv contracts smoke test safety-eval

PROVIDER ?= rules
EVAL_ARGS ?=

venv: .venv/.requirements-installed

.venv/.requirements-installed: requirements.txt
	python3 -m venv .venv
	.venv/bin/python -m pip install -r requirements.txt
	touch $@

contracts: venv
	.venv/bin/python contracts/validate.py

# 后续加入 10 个来访 + mock LLM 的端到端冒烟。
smoke: contracts test

test: venv
	.venv/bin/python -m pytest tests

safety-eval: venv
	.venv/bin/python -m safety.eval --provider $(PROVIDER) $(EVAL_ARGS)

.PHONY: check-keys
check-keys: venv
	.venv/bin/python scripts/check_keys.py
