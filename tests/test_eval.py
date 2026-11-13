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
    assert report["n"] == 6
    assert report["confusion_matrix"] == [[2, 0, 0], [0, 2, 0], [0, 0, 2]]
    assert report["risk_recall"] == report["risk_precision"] == 1.
    assert report["recall_by_level"] == {"passive": 1., "active": 1.}
    assert report["missed"] == []
    assert report["judge"]["failures"] == 0
    assert report["judge"]["calls"] == (0 if provider == "rules" else 3)
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
    assert report["confusion_matrix"] == [[0, 1, 0], [0, 0, 1], [1, 0, 0]]
    assert report["risk_recall"] == report["risk_precision"] == .5
    assert report["recall_by_level"] == {"passive": 0., "active": 0.}
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
            return JudgeResult({"none": 1., "passive": 0., "active": 0.}, "ok", self.provider, 30.)

    monkeypatch.setattr("safety.eval.make_judge", lambda config: FakeJudge())
    rows = [{"id": "1", "text": "early", "label": "active"}, {"id": "2", "text": "later", "label": "none"}]
    report = asyncio.run(evaluate(rows, "ds_flash"))
    assert report["judge"] == {"calls": 2, "failures": 1, "statuses": {"timeout": 1, "ok": 1}, "providers": {"fake": 2}, "p50_ms": 20., "p95_ms": 29.}
    assert report["provider"] == "fake"
    assert report["missed"][0]["id"] == "1"
