import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from safety.eval import evaluate, load_testset
from safety.judges import JudgeResult

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("provider", ["rules", "mock"])
def test_eval_cli_runs_from_root_and_writes_report(provider, tmp_path):
    result = subprocess.run([sys.executable, "-m", "safety.eval", "--provider", provider, "--output-dir", str(tmp_path)], cwd=ROOT, env={**os.environ, "JUDGE_PROVIDER": "mock"}, capture_output=True, text=True, check=True)
    report = json.loads(result.stdout)
    assert report["provider"] == provider
    assert report["n"] == 48
    assert [sum(row) for row in report["confusion_matrix"]] == [21, 3, 14, 10]
    assert report["judge"]["failures"] == 0
    assert report["judge"]["calls"] == (0 if provider == "rules" else 46)
    if provider == "rules":
        assert report["confusion_matrix"] == [[12, 0, 9, 0], [1, 0, 2, 0], [4, 0, 10, 0], [3, 0, 5, 2]]
        assert report["risk_recall"] == 17 / 24
        assert report["risk_precision"] == 17 / 28
        assert [row["id"] for row in report["history_missed"]] == ["NEG-20"]
        assert [row["id"] for row in report["history_over_escalated"]] == ["NEG-18", "NEG-19"]
        assert [row["id"] for row in report["missed"]] == ["POS-03", "POS-08", "POS-12", "POS-13", "POS-15", "POS-19", "POS-24"]
    saved = list(tmp_path.glob(f"{provider}-*.json"))
    assert len(saved) == 1
    assert json.loads(saved[0].read_text()) == report


def test_eval_metrics_expose_misses_and_false_alarms():
    rows = [
        {"id": "1", "text": "普通文本", "label": "active"},
        {"id": "2", "text": "我现在想自杀", "label": "passive"},
        {"id": "3", "text": "撑不下去", "label": "none"},
    ]
    report = asyncio.run(evaluate(rows, "rules"))
    assert report["confusion_matrix"] == [[0, 0, 1, 0], [0, 0, 0, 0], [0, 0, 0, 1], [1, 0, 0, 0]]
    assert report["risk_recall"] == report["risk_precision"] == .5
    assert report["recall_by_level"] == {"history": None, "passive": 0., "active": 0.}
    assert [row["id"] for row in report["missed"]] == ["1"]
    assert report["judge"]["p50_ms"] is None
    assert report["judge"]["p95_ms"] is None


def test_expanded_jsonl_and_empty_denominators(tmp_path):
    path = tmp_path / "large.jsonl"
    path.write_text("# 占位，待心理学同学审定后替换\n" + "\n".join(json.dumps({"id": str(i), "text": "普通文本", "label": "none", "cssrs": 0, "difficulty": "easy"}) for i in range(150)))
    rows = load_testset(path)
    assert len(rows) == 150
    report = asyncio.run(evaluate(rows, "rules"))
    assert report["risk_recall"] is None
    assert report["risk_precision"] is None


def test_bad_testset_is_rejected_with_line_number(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('# comment\n{"id":"x","text":"test","label":"oops"}\n')
    with pytest.raises(ValueError, match="line 2"):
        load_testset(path)


def test_failure_count_and_percentiles_include_no_event(monkeypatch):
    class FakeJudge:
        provider = "fake"

        async def classify(self, text):
            if text == "early":
                return JudgeResult(None, "timeout", self.provider, 10.)
            return JudgeResult({"none": 1., "history": 0., "passive": 0., "active": 0.}, "ok", self.provider, 30.)

    monkeypatch.setattr("safety.eval.make_judge", lambda config, **kwargs: FakeJudge())
    rows = [{"id": "1", "text": "early", "label": "active"}, {"id": "2", "text": "later", "label": "none"}]
    report = asyncio.run(evaluate(rows, "ds_flash"))
    assert report["judge"] == {"calls": 2, "failures": 1, "statuses": {"timeout": 1, "ok": 1}, "providers": {"fake": 2}, "p50_ms": 20., "p95_ms": 29.}
    assert report["provider"] == "fake"
    assert report["missed"][0]["id"] == "1"


def test_history_metrics_separate_missed_verification_and_over_escalation(monkeypatch):
    class FakeJudge:
        provider = "fake"

        async def classify(self, text):
            return JudgeResult({label: float(label == text) for label in ("none", "history", "passive", "active")}, "ok", self.provider, 0.)

    monkeypatch.setattr("safety.eval.make_judge", lambda config, **kwargs: FakeJudge())
    rows = [{"id": label, "text": label, "label": "history"} for label in ("none", "history", "passive", "active")]
    rows += [{"id": "current-risk", "text": "history", "label": "active"}]
    report = asyncio.run(evaluate(rows, "ds_flash"))
    assert report["labels"] == ["none", "history", "passive", "active"]
    assert report["confusion_matrix"] == [[0, 0, 0, 0], [1, 1, 1, 1], [0, 0, 0, 0], [0, 1, 0, 0]]
    assert report["history_recall"] == report["recall_by_level"]["history"] == .25
    assert [row["id"] for row in report["history_missed"]] == ["none"]
    assert [row["id"] for row in report["history_over_escalated"]] == ["passive", "active"]
    assert [row["id"] for row in report["missed"]] == ["current-risk"]
    assert report["risk_precision"] == report["risk_recall"] == 0.


@pytest.mark.parametrize("provider,key", [
    ("ds_flash", "DS_API_KEY"), ("jev", "TYPESAFE_API_KEY"),
    ("gemini_decision", "GEMINI_API_KEY"), ("startlux", "STARTLUX_API_KEY"),
])
def test_explicit_real_provider_requires_key_and_engine_keeps_fallback(provider, key, monkeypatch, tmp_path):
    from safety.judges import make_judge
    monkeypatch.setenv("JUDGE_PROVIDER", "mock")
    monkeypatch.setenv(key, "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    with pytest.raises(ValueError, match=f"评测 {provider} 缺少 API key"):
        asyncio.run(evaluate([], provider))
    assert make_judge({"judge_provider": provider}).provider == "mock(fallback)"
    result = subprocess.run(
        [sys.executable, "-m", "safety.eval", "--provider", provider,
         "--output-dir", str(tmp_path)], cwd=ROOT, env=os.environ.copy(),
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert f"评测 {provider} 缺少 API key" in result.stderr
    assert not list(tmp_path.iterdir())


def test_provider_precedence(monkeypatch):
    from safety.config import load_config
    monkeypatch.delenv("JUDGE_PROVIDER", raising=False)
    assert load_config()["judge_provider"] == "ds_flash"
    monkeypatch.setenv("JUDGE_PROVIDER", "jev")
    assert load_config()["judge_provider"] == "jev"
    assert load_config({"judge_provider": "mock"})["judge_provider"] == "mock"
    monkeypatch.setenv("JUDGE_PROVIDER", "invalid")
    assert asyncio.run(evaluate([], "mock"))["provider"] == "mock"
    assert asyncio.run(evaluate([], "rules"))["provider"] == "rules"


def test_explicit_provider_and_timeout_reach_actual_judge(monkeypatch):
    from safety.judges import DsFlashJudge, StartLuxJudge
    monkeypatch.setenv("JUDGE_PROVIDER", "mock")
    monkeypatch.setenv("DS_API_KEY", "test-placeholder")
    monkeypatch.setenv("DS_MODEL", "test-model")
    monkeypatch.setenv("DS_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("STARTLUX_API_KEY", "test-placeholder")
    seen = []

    async def predict(self, text):
        seen.append((self.provider, self.timeout))
        return {"none": 1., "history": 0., "passive": 0., "active": 0.}

    monkeypatch.setattr(DsFlashJudge, "_predict", predict)
    monkeypatch.setattr(StartLuxJudge, "_predict", predict)
    rows = [{"id": "1", "text": "普通文本", "label": "none"}]
    for provider, timeout, expected in [("ds_flash", None, 6.0), ("startlux", None, 8.), ("startlux", 12., 12.)]:
        report = asyncio.run(evaluate(rows, provider, timeout=timeout))
        assert report["provider"] == provider
        assert seen[-1] == (provider, expected)
    assert asyncio.run(evaluate([]))["provider"] == "mock"


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_eval_rejects_invalid_timeout(timeout):
    with pytest.raises(ValueError, match="positive and finite"):
        asyncio.run(evaluate([], "rules", timeout=timeout))


@pytest.mark.parametrize("manual", [False, True])
def test_dotenv_preserves_environment_and_parses_check_keys_syntax(monkeypatch, tmp_path, manual):
    from safety.config import load_repo_env
    if manual:
        monkeypatch.setitem(sys.modules, "dotenv", None)
    path = tmp_path / ".env"
    path.write_text('export EVAL_TEST_A="file value"\nEVAL_TEST_B=plain # comment\nEVAL_TEST_C=\'quoted#value\'\nEVAL_TEST_D= # empty\n')
    monkeypatch.setenv("EVAL_TEST_A", "existing")
    for key in ("EVAL_TEST_B", "EVAL_TEST_C", "EVAL_TEST_D"):
        monkeypatch.delenv(key, raising=False)
    load_repo_env(path)
    assert os.environ["EVAL_TEST_A"] == "existing"
    assert os.environ["EVAL_TEST_B"] == "plain"
    assert os.environ["EVAL_TEST_C"] == "quoted#value"
    assert os.environ["EVAL_TEST_D"] == ""


def test_cli_loads_root_env_before_config_and_accepts_timeout(monkeypatch, tmp_path, capsys):
    import safety.config as config_module
    from safety.eval import main
    root = tmp_path / "repo"
    (root / "safety").mkdir(parents=True)
    (root / "safety/config.yaml").write_text((ROOT / "safety/config.yaml").read_text())
    (root / ".env").write_text("JUDGE_PROVIDER=mock\n")
    monkeypatch.delenv("JUDGE_PROVIDER", raising=False)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG", root / "safety" / "config.yaml")
    monkeypatch.chdir(tmp_path)
    main(["--config", str(ROOT / "safety/config.yaml"), "--timeout", "9", "--output-dir", str(tmp_path / "out")])
    assert json.loads(capsys.readouterr().out)["provider"] == "mock"
