.PHONY: venv contracts smoke test

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
