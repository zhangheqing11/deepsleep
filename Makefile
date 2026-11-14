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

# 路演目标复用已有 Python，不创建 venv 或安装依赖。
DEMO_PYTHON ?= $(firstword $(wildcard .venv/bin/python ../deepsleep/.venv/bin/python))
# 11/15 冻结：三代学习（每代自我练习）+ 模板渲染来访；留出验证即在此配置下完成（docs/handoff-evolve.md）。
DEMO_ARGS ?= --generations 3 --visitor-renderer template
.PHONY: demo-reset demo-run1 demo-run2 demo-all demo-mock
demo-reset:
	$(DEMO_PYTHON) -m engine.demo reset

demo-run1:
	$(DEMO_PYTHON) -m engine.demo run1 $(DEMO_ARGS)
	$(DEMO_PYTHON) -m engine.demo learn $(DEMO_ARGS)

demo-run2:
	$(DEMO_PYTHON) -m engine.demo run2 $(DEMO_ARGS)

demo-all:
	$(DEMO_PYTHON) -m engine.demo all $(DEMO_ARGS)

demo-mock:
	$(DEMO_PYTHON) -m engine.demo all --mock --dev --visitors-dir sim/visitors --reset $(DEMO_ARGS)

# 离线睡眠脱敏数据（privacy/data/）；复用已有 Python，不安装依赖。
DEID_PYTHON ?= $(firstword $(wildcard .venv/bin/python ../deepsleep/.venv/bin/python))
.PHONY: deid-data
deid-data:
	$(DEID_PYTHON) -m privacy.data.tools.build
	$(DEID_PYTHON) -m privacy.data.tools.generate
	$(DEID_PYTHON) -m privacy.data.tools.build_sft
	$(DEID_PYTHON) -m privacy.data.tools.validate --json privacy/data/STATS.json
	PYTHONDONTWRITEBYTECODE=1 $(DEID_PYTHON) -m pytest -q -p no:cacheprovider tests/test_privacy_data.py
	$(DEID_PYTHON) -m privacy.data.tools.evaluate --gold gold/dev.jsonl --baseline rules --json privacy/data/baselines/dev_rules.json
	$(DEID_PYTHON) -m privacy.data.tools.evaluate --gold gold/dev.jsonl --baseline naive --json privacy/data/baselines/dev_naive.json
	$(DEID_PYTHON) -m privacy.data.tools.evaluate --gold gold/test.jsonl --baseline rules --json privacy/data/baselines/test_rules.json
	$(DEID_PYTHON) -m privacy.data.tools.evaluate --gold gold/test.jsonl --baseline naive --json privacy/data/baselines/test_naive.json
	$(DEID_PYTHON) -m privacy.data.tools.evaluate --sessions --baseline rules --json privacy/data/baselines/sessions_rules.json
	$(DEID_PYTHON) -m privacy.data.tools.scan_v03
	$(DEID_PYTHON) -m privacy.data.tools.report
