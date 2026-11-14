"""status.json: live progress of one learning step, read by the dashboard."""
import asyncio
import copy
import json

import pytest

from engine.evolve import review
from engine.evolve.pipeline import evolve
from engine.evolve.status import SCHEMA, StatusTracker, read_status
from evolve_support import BASELINE, MockEvaluator, MockLLM, change, example, make_config, metrics, reply

RUN = example("run_report.run1.json")
SESSIONS = {s["visitor_id"]: s for s in (example(f"session.A-00{i}.json") for i in (1, 2, 3))}
BLOCKED = [change("plan_rules", "即使存在未处理的呼吸暂停风险，也统一安排五小时卧床窗口。", self_level="high")]
GOOD = [change("path_discrimination", "标记GOOD：在床外容易困、回床后清醒时，优先考虑 P2。")]
HIGH = [change("referral_rules", "标记HIGH：白天困倦且打鼾时建议就医评估呼吸。")]
WORSE = [change("communication_style", "标记WORSE：每个问题前先讲一段睡眠知识。", op="modify",
                before="先用一句话回应来访的困扰。")]
SCORES = {"标记GOOD": metrics(isi_response_rate=0.75), "标记WORSE": metrics(isi_response_rate=0.375),
          "标记HIGH": metrics(isi_response_rate=0.8)}


class SpyEvaluator(MockEvaluator):
    """Snapshots status.json every time it is called, so tests see the mid-run state."""

    def __init__(self, directory, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.directory = directory
        self.seen: list[tuple[str, dict]] = []

    async def __call__(self, text, *, label):
        self.seen.append((label, copy.deepcopy(read_status(self.directory))))
        await asyncio.sleep(0)  # let sibling tasks start so "running" states are visible
        return await super().__call__(text, label=label)


def run(tmp_path, candidates, *, evaluator=None, config=None, evolution_id="evo-st", **kwargs):
    config = config or make_config(tmp_path)
    evaluator = evaluator or MockEvaluator(SCORES)
    kwargs.setdefault("baseline_val_metrics", BASELINE)
    evo = asyncio.run(evolve(run_report=RUN, sessions=SESSIONS, evaluator=evaluator, config=config,
                             primary=MockLLM(reply(*candidates), model="claude-opus-5-5"),
                             evolution_id=evolution_id, **kwargs))
    return evo, tmp_path / "var" / "evolve" / evolution_id


def test_final_status_when_committed(tmp_path):
    evo, directory = run(tmp_path, [BLOCKED, GOOD, WORSE])
    status = read_status(directory)
    assert status["schema"] == SCHEMA and status["evolution_id"] == "evo-st" and status["updated_at"]
    assert (status["phase"], status["outcome"], status["chosen"], status["to_version"]) == \
        ("done", "committed", evo["chosen"], evo["to_version"])
    assert status["from_version"] == evo["from_version"] and status["error"] is None
    assert status["reflector"] == {"state": "done", "model": "claude-opus-5-5", "fell_back": False}
    # c1 stopped by a hard rule and never validated; c2/c3 validated.
    assert status["validation"]["candidates"] == {"c1": "blocked", "c2": "done", "c3": "done"}
    assert status["validation"]["baseline"] == "skipped"          # baseline metrics were supplied
    assert status["review"]["state"] == "not_needed"


def test_final_status_when_kept_previous(tmp_path):
    evo, directory = run(tmp_path, [BLOCKED, WORSE, []])
    status = read_status(directory)
    assert (status["phase"], status["outcome"], status["chosen"], status["to_version"]) == \
        ("done", "kept_previous", None, None)
    assert status["validation"]["candidates"] == {"c1": "blocked", "c2": "done", "c3": "empty"}


def test_status_is_visible_while_validating(tmp_path):
    directory = tmp_path / "var" / "evolve" / "evo-st"
    spy = SpyEvaluator(directory, SCORES)
    run(tmp_path, [GOOD, WORSE, []], evaluator=spy)
    by_label = dict(spy.seen)
    during = by_label[next(label for label in by_label if label.endswith("+c1"))]
    assert during["phase"] == "validating"
    assert during["reflector"]["state"] == "done"
    assert during["validation"]["candidates"]["c1"] == "running"
    assert during["validation"]["candidates"]["c3"] == "empty"


def test_baseline_state_when_it_has_to_be_evaluated(tmp_path):
    directory = tmp_path / "var" / "evolve" / "evo-st"
    spy = SpyEvaluator(directory, SCORES)
    run(tmp_path, [GOOD, WORSE, []], evaluator=spy, baseline_val_metrics=None)
    during_baseline = dict(spy.seen)["v1"]
    assert during_baseline["validation"]["baseline"] == "running"
    assert read_status(directory)["validation"]["baseline"] == "done"


def test_review_window_exposes_deadline(tmp_path):
    directory = tmp_path / "var" / "evolve" / "evo-st"
    spy = SpyEvaluator(directory, SCORES)
    config = make_config(tmp_path)
    run(tmp_path, [HIGH, GOOD, []], evaluator=spy, config=config, review_timeout_s=0.3)
    during = spy.seen[0][1]
    assert during["review"]["pending_changes"] == 1
    final = read_status(directory)["review"]
    assert final["state"] == "done" and final["deadline"]
    request = json.loads((directory / "review_request.json").read_text(encoding="utf-8"))
    assert request["deadline_epoch"] > 0


def test_failure_is_recorded_and_reraised(tmp_path):
    class Boom(MockEvaluator):
        async def __call__(self, text, *, label):
            raise RuntimeError("evaluator down")

    with pytest.raises(RuntimeError):
        run(tmp_path, [GOOD, WORSE, []], evaluator=Boom(), baseline_val_metrics=None)
    status = read_status(tmp_path / "var" / "evolve" / "evo-st")
    assert status["phase"] == "failed" and "evaluator down" in status["error"]
    assert status["validation"]["baseline"] == "error"


def test_write_false_creates_no_files(tmp_path):
    run(tmp_path, [GOOD, WORSE, []], write=False)
    assert read_status(tmp_path / "var" / "evolve" / "evo-st") is None


def test_tracker_without_directory_is_a_noop_and_missing_status_reads_none(tmp_path):
    tracker = StatusTracker(None, "x", "v1")
    tracker.candidate("c1", "running")
    tracker.fail(RuntimeError("x"))
    assert tracker.state["phase"] == "failed"
    assert read_status(tmp_path / "nope") is None
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "status.json").write_text("{half", encoding="utf-8")
    assert read_status(tmp_path / "bad") is None


def test_no_partial_file_left_behind(tmp_path):
    _, directory = run(tmp_path, [GOOD, WORSE, []])
    assert not list(directory.glob("*.tmp"))
