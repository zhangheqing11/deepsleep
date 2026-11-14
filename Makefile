.PHONY: venv contracts smoke test safety-eval engine-mock

PROVIDER ?= rules
EVAL_ARGS ?=

venv: .venv/.requirements-installed

.venv/.requirements-installed: requirements.txt
	python3 -m venv .venv
	.venv/bin/python -m pip install -r requirements.txt
	touch $@

contracts: venv
	.venv/bin/python contracts/validate.py

# 10 个样例来访 + mock LLM + stub agent → session + run_report，全部过契约校验（scoring/smoke.py）。
smoke: contracts
	.venv/bin/python -m scoring.smoke

test: venv
	.venv/bin/python -m pytest -q tests

safety-eval: venv
	.venv/bin/python -m safety.eval --provider $(PROVIDER) $(EVAL_ARGS)

.PHONY: check-keys
check-keys: venv
	.venv/bin/python scripts/check_keys.py

# 会谈引擎：契约示例来访 + mock agent，输出到 var/runs/<run-id>/
engine-mock: venv
	.venv/bin/python -m engine.run --mock --run-id dev-mock
