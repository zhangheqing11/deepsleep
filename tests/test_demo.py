"""Offline orchestration checks; model/network access is forbidden even with keys set."""
import asyncio
from copy import deepcopy
import json
import socket

import pytest

from contracts.validate import load_validators, validate_document
from engine import demo

MOCK = ["--mock", "--dev", "--visitors-dir", "sim/visitors"]


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "VAR_DIR", tmp_path / "var")
    monkeypatch.setattr(demo, "PLAYBOOK_REPO", tmp_path / "var/playbook-repo")
    monkeypatch.setattr(demo, "load_dotenv", lambda *a, **k: None)  # never read the repo-root .env
    # Pin the simple gate/lineage behaviour so these orchestration tests do not depend on shipped defaults.
    real_evolve_config = demo.evolve_config

    def simple_evolve_config(overrides=None):
        overrides = dict(overrides or {})
        overrides["gate"] = {"replicates": 1, "baseline_replicates": 1, "baseline_during_reflection": False,
                             "parallel_candidates": False, "referral_recall_tolerance_visitors": 0,
                             **overrides.get("gate", {})}
        overrides["lineage"] = {"continue_after_reject": False, "reuse_baseline": True, **overrides.get("lineage", {})}
        return real_evolve_config(overrides)

    monkeypatch.setattr(demo, "evolve_config", simple_evolve_config)
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("network access in mock mode")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    for key in ("DS_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "TYPESAFE_API_KEY"):
        monkeypatch.setenv(key, "mock-mode-must-ignore-credentials")
    monkeypatch.setenv("DS_BASE_URL", "https://invalid.example")
    monkeypatch.setenv("DS_MODEL", "must-not-call")
    snapshots = []
    save = demo.save_manifest

    def capture(manifest):
        save(manifest)
        snapshots.append(deepcopy(demo.read_json(demo.VAR_DIR / "demo/experiment.json")))

    monkeypatch.setattr(demo, "save_manifest", capture)
    yield snapshots
    assert not attempts


def manifest():
    return demo.read_json(demo.VAR_DIR / "demo/experiment.json")


def report(m, key):
    return demo.read_json(demo.VAR_DIR / "runs" / m[key]["run_id"] / "run_report.json")


def assert_reports(m):
    validators = load_validators()
    groups = demo.read_json(demo.VAR_DIR / "demo" / m["experiment_id"] / "cohorts.json")
    visitors = {v["id"]: v for group in groups.values() for v in group}
    for key in ("run1", "run2", "control"):
        r = report(m, key)
        assert validate_document(r, "run_report", validators, visitors) == []
        assert r["role"] == key
        out = demo.VAR_DIR / "runs" / m[key]["run_id"]
        assert (out / "summary.json").is_file()
        for row in r["per_visitor"]:
            session = demo.read_json(out / row["session_ref"])
            assert validate_document(session, "session", validators, visitors) == []
            assert (out / "trace" / f"{row['visitor_id']}.json").is_file()
    ids = lambda key: {v["visitor_id"] for v in report(m, key)["per_visitor"]}
    assert ids("run2") == ids("control")
    assert ids("run1").isdisjoint(ids("run2"))
    assert ids("run1").isdisjoint(v["id"] for v in groups["C"])


def test_all_kept_previous_contracts_and_states(sandbox, capsys):
    assert demo.main(["all", *MOCK, "--reset", "--experiment", "complete"]) == 0
    m = manifest()
    assert set(m) == {"experiment_id", "updated_at", "stage", "run1", "evolution", "run2", "control", "error"}
    assert m["stage"] == "done" and m["error"] is None
    for key in ("run1", "evolution", "run2", "control"):
        states = [s[key]["state"] for s in sandbox]
        assert list(dict.fromkeys(states)) == ["pending", "running", "done"]
        assert all(s[key].get("run_id", s[key].get("evolution_id")) for s in sandbox)
    assert any(s["run2"]["state"] == s["control"]["state"] == "running" and s["stage"] == "run2" for s in sandbox)
    assert_reports(m)
    evo = demo.read_json(demo.VAR_DIR / "evolve" / m["evolution"]["evolution_id"] / "evolution.json")
    assert evo["outcome"] == "kept_previous"
    assert len(evo["candidates"]) == 3 and all(c["val_metrics"] for c in evo["candidates"])
    assert evo["baseline_val_metrics"] is not None
    assert m["run2"]["playbook_version"] == m["control"]["playbook_version"]
    assert report(m, "run2")["metrics"] == report(m, "control")["metrics"]
    assert demo.read_json(demo.VAR_DIR / "demo/experiment.complete.json") == m
    summary = (demo.VAR_DIR / "demo/complete/summary.md").read_text()
    assert summary in capsys.readouterr().out
    assert "kept_previous" in summary and "rollback v1" in summary


def test_split_commands_reuse_frozen_options_and_visitors(sandbox, monkeypatch):
    assert demo.main(["run1", *MOCK, "--experiment", "split", "--n-b", "2"]) == 0
    assert manifest()["stage"] == "learning"
    # Later commands must not re-read the source cohort or require mock flags again.
    monkeypatch.setattr(demo, "cohorts", lambda _: pytest.fail("reloaded visitors"))
    assert demo.main(["learn", "--experiment", "split"]) == 0
    assert manifest()["stage"] == "run2"
    assert demo.main(["run2"]) == 0
    assert_reports(manifest())
    assert report(manifest(), "run2")["n_visitors"] == 2
    before = manifest()
    assert demo.main(["run2"]) == 1  # no duplicate paid evaluation
    assert manifest() == before


def test_committed_branch_keeps_original_control(sandbox, monkeypatch):
    real_evolve = demo.evolve

    async def committed(**kwargs):
        evaluator = kwargs["evaluator"]

        async def with_test_metrics(text, *, label):
            rich = await evaluator(text, label=label)
            # Synthetic validation metrics exercise orchestration after a real gate commit.
            # Actual A/B session reports are untouched and validated below.
            rich["metrics"] = dict(rich["metrics"], isi_response_rate=0.8 if "+c" in label else 0.1,
                                   referral_recall=1.0, referral_precision=1.0,
                                   crisis_missed=0, contraindication_violations=0)
            return rich

        return await real_evolve(**dict(kwargs, evaluator=with_test_metrics))

    monkeypatch.setattr(demo, "evolve", committed)
    assert demo.main(["all", *MOCK, "--experiment", "adopted"]) == 0
    m = manifest()
    assert m["run2"]["playbook_version"] == "v2"
    assert m["control"]["playbook_version"] == m["run1"]["playbook_version"] == "v1"
    assert demo.PlaybookRepo(demo.config_for_repo()).current_version() == "v2"
    assert_reports(m)
    text = (demo.VAR_DIR / "demo/adopted/summary.md").read_text()
    assert "committed；v1 → v2" in text
    assert 1 <= sum(line.startswith("- ") for line in text.splitlines()) <= 3


def test_two_generations_chain_and_manifest(sandbox, monkeypatch):
    real_evolve = demo.evolve

    async def committed(**kwargs):
        evaluator = kwargs["evaluator"]

        async def with_test_metrics(text, *, label):
            rich = await evaluator(text, label=label)
            # Synthetic C metrics: every candidate beats v1, nothing beats the adopted v2.
            rich["metrics"] = dict(rich["metrics"], isi_response_rate=0.8 if "+c" in label else 0.1,
                                   referral_recall=1.0, referral_precision=1.0,
                                   crisis_missed=0, contraindication_violations=0)
            return rich

        return await real_evolve(**dict(kwargs, evaluator=with_test_metrics))

    monkeypatch.setattr(demo, "evolve", committed)
    assert demo.main(["all", *MOCK, "--experiment", "chain", "--generations", "2"]) == 0
    m = manifest()
    assert m["evolution"]["generations"] == ["chain-learn-g1", "chain-learn-g2"]
    assert m["evolution"]["evolution_id"] == "chain-learn-g1"           # last committed generation
    assert m["run2"]["playbook_version"] == "v2" and m["control"]["playbook_version"] == "v1"
    assert demo.read_json(demo.VAR_DIR / "demo/chain/options.json")["generations"] == 2
    validators = load_validators()
    evolutions = [demo.read_json(demo.VAR_DIR / "evolve" / eid / "evolution.json") for eid in m["evolution"]["generations"]]
    assert [validate_document(e, "evolution", validators, {}) for e in evolutions] == [[], []]
    assert [e["outcome"] for e in evolutions] == ["committed", "kept_previous"]
    chosen = next(c for c in evolutions[0]["candidates"] if c["id"] == evolutions[0]["chosen"])
    assert evolutions[1]["baseline_val_metrics"] == chosen["val_metrics"]   # reused, not re-run
    runs = {p.name for p in (demo.VAR_DIR / "runs").iterdir()}
    assert "chain-learn-v2" not in runs                                  # generation 2 baseline was reused
    lineage = demo.read_json(demo.VAR_DIR / "evolve/chain-learn/lineage.json")
    assert [g["outcome"] for g in lineage["generations"]] == ["committed", "kept_previous"]
    text = (demo.VAR_DIR / "demo/chain/summary.md").read_text(encoding="utf-8")
    assert "学习结果（第 1 代）：committed；v1 → v2" in text
    assert "学习结果（第 2 代）：kept_previous；v2 → v2" in text and "rollback v1" in text
    assert_reports(m)


def test_old_options_without_generations_still_load(sandbox):
    assert demo.main(["run1", *MOCK, "--experiment", "legacy"]) == 0
    path = demo.VAR_DIR / "demo/legacy/options.json"
    options = demo.read_json(path)
    del options["generations"]
    demo.atomic_json(path, options)
    assert demo.main(["learn", "--experiment", "legacy", "--generations", "2"]) == 1   # frozen at default 1
    assert demo.main(["learn", "--experiment", "legacy"]) == 0
    m = manifest()
    assert m["evolution"]["generations"] == ["legacy-learn"] and m["evolution"]["evolution_id"] == "legacy-learn"


@pytest.mark.parametrize("failure", ["run1", "learn", "run2", "control"])
def test_failure_written_and_sibling_finishes(sandbox, monkeypatch, failure):
    original_batch = demo.batch
    original_evolve = demo.evolve

    async def broken_batch(*args):
        if args[5] == failure:
            raise RuntimeError("injected stage failure")
        return await original_batch(*args)

    async def broken_evolve(**kwargs):
        if failure == "learn":
            raise RuntimeError("injected stage failure")
        return await original_evolve(**kwargs)

    monkeypatch.setattr(demo, "batch", broken_batch)
    monkeypatch.setattr(demo, "evolve", broken_evolve)
    assert demo.main(["all", *MOCK]) == 1
    m = manifest()
    assert m["stage"] == "failed" and "injected stage failure" in m["error"]
    assert m["evolution" if failure == "learn" else failure]["state"] == "failed"
    if failure in ("run2", "control"):
        assert m["control" if failure == "run2" else "run2"]["state"] == "done"
    assert demo.read_json(demo.VAR_DIR / "demo" / f"experiment.{m['experiment_id']}.json") == m


def test_missing_cohorts_and_reset_preserve_history(sandbox, capsys):
    assert demo.main(["run1", "--mock", "--visitors-dir", "missing-visitors", "--experiment", "missing"]) == 1
    m = manifest()
    assert m["stage"] == "failed"
    assert "--visitors-dir sim/visitors --dev" in capsys.readouterr().err
    assert demo.main(["reset"]) == 0
    assert not (demo.VAR_DIR / "demo/experiment.json").exists()
    assert demo.read_json(demo.VAR_DIR / "demo/experiment.missing.json") == m
    assert demo.PlaybookRepo(demo.config_for_repo()).current_version() == "v1"


def test_refuse_options_change_and_foreign_paths(sandbox):
    assert demo.main(["run1", *MOCK]) == 0
    before = manifest()
    assert demo.main(["learn", "--max-sessions", "1"]) == 1
    assert manifest() == before
    assert demo.main(["all", "--mock", "--dev", "--visitors-dir", "/tmp"]) == 1
    assert manifest()["stage"] == "failed"
    with pytest.raises(SystemExit) as exc:
        demo.main(["all", *MOCK, "--experiment", "../escape"])
    assert exc.value.code == 2


def test_session_limit_is_per_batch_across_parallel_batches(sandbox, monkeypatch):
    # One semaphore per batch (2026-11-14): overlapping batches no longer queue behind each other,
    # so --max-sessions bounds each batch's concurrency, not the global total.
    active, peak, total = {}, {}, 0
    total_peak = 0
    run = demo.SessionRunner.run

    async def measured(self):
        nonlocal total, total_peak
        rid = self.run_id
        active[rid] = active.get(rid, 0) + 1
        total += 1
        peak[rid] = max(peak.get(rid, 0), active[rid])
        total_peak = max(total_peak, total)
        await asyncio.sleep(0)
        try:
            return await run(self)
        finally:
            active[rid] -= 1
            total -= 1

    monkeypatch.setattr(demo.SessionRunner, "run", measured)
    assert demo.main(["all", *MOCK, "--max-sessions", "2"]) == 0
    assert peak and all(v == 2 for v in peak.values()) and not any(active.values()) and total == 0
    assert total_peak >= 2


def test_manifest_atomically_replaced(sandbox, monkeypatch):
    real_replace = demo.os.replace
    replaced = []

    def observe(source, target):
        json.loads(demo.Path(source).read_text())
        assert demo.Path(source).parent == target.parent
        real_replace(source, target)
        replaced.append(target.name)

    monkeypatch.setattr(demo.os, "replace", observe)
    assert demo.main(["all", *MOCK, "--experiment", "atomic"]) == 0
    assert replaced.count("experiment.json") == len(sandbox)
    assert replaced.count("experiment.atomic.json") == len(sandbox)


def test_b_runs_overlap(sandbox, monkeypatch):
    original = demo.batch
    entered = set()
    barrier = None

    async def overlap(*args):
        nonlocal barrier
        if args[5] in ("run2", "control"):
            if barrier is None:
                barrier = asyncio.Event()
            entered.add(args[5])
            if len(entered) == 2:
                barrier.set()
            await asyncio.wait_for(barrier.wait(), timeout=2)
        return await original(*args)

    monkeypatch.setattr(demo, "batch", overlap)
    assert demo.main(["all", *MOCK]) == 0
    assert entered == {"run2", "control"}


def test_incomplete_scoring_is_failed_with_artifacts(sandbox, monkeypatch):
    original = demo.SessionRunner.run

    async def one_error(self):
        session, trace = await original(self)
        if self.visitor["id"] == "sample-001":
            session["status"] = "error"
            session["error"] = "injected session error"
        return session, trace

    monkeypatch.setattr(demo.SessionRunner, "run", one_error)
    assert demo.main(["run1", *MOCK]) == 1
    m = manifest()
    assert m["stage"] == "failed" and m["run1"]["state"] == "failed"
    out = demo.VAR_DIR / "runs" / m["run1"]["run_id"]
    summary = demo.read_json(out / "summary.json")
    assert not summary["evaluation_complete"] and summary["error_count"] == 1
    assert len(list((out / "sessions").glob("*.json"))) == 6
    assert not report(m, "run1")["veto"]["passed"]


def test_real_mode_requires_configuration_before_any_requests(sandbox, monkeypatch):
    monkeypatch.delenv("DS_API_KEY")
    assert demo.main(["run1", "--dev", "--visitors-dir", "sim/visitors"]) == 1
    assert manifest()["stage"] == "failed"
    assert "DS_API_KEY" in manifest()["error"]


def committed_evolve(monkeypatch, calls):
    """Patch demo.evolve so candidates beat v1 on C (forces a commit) and record each call's kwargs."""
    real_evolve = demo.evolve

    async def committed(**kwargs):
        calls.append(kwargs)
        evaluator = kwargs["evaluator"]

        async def with_test_metrics(text, *, label):
            rich = await evaluator(text, label=label)
            rich["metrics"] = dict(rich["metrics"], isi_response_rate=0.8 if "+c" in label else 0.1,
                                   referral_recall=1.0, referral_precision=1.0,
                                   crisis_missed=0, contraindication_violations=0)
            return rich

        return await real_evolve(**dict(kwargs, evaluator=with_test_metrics))

    monkeypatch.setattr(demo, "evolve", committed)


def record_batches(monkeypatch, batches):
    original = demo.batch

    async def recorded(*args):
        batches.append(args)
        return await original(*args)

    monkeypatch.setattr(demo, "batch", recorded)


def test_two_generations_practice_on_new_playbook(sandbox, monkeypatch):
    calls, batches = [], []
    committed_evolve(monkeypatch, calls)
    record_batches(monkeypatch, batches)
    assert demo.main(["all", *MOCK, "--experiment", "prac", "--generations", "2"]) == 0
    m = manifest()
    assert m["practice"] == [{"run_id": "prac-practice-v2", "playbook_version": "v2", "state": "done"}]
    practice = [args for args in batches if args[5] == "practice"]
    assert len(practice) == 1
    _, visitors, text, version, run_id, _, split = practice[0][:7]
    learned = (demo.VAR_DIR / "demo/prac/learned.md").read_text(encoding="utf-8")
    original = (demo.VAR_DIR / "demo/prac/original.md").read_text(encoding="utf-8")
    assert text == learned != original and version == "v2" and run_id == "prac-practice-v2" and split == "A"
    groups = demo.read_json(demo.VAR_DIR / "demo/prac/cohorts.json")
    assert [v["id"] for v in visitors] == [v["id"] for v in groups["A"]]
    # Generation 1 reflects on run 1; generation 2 on the fresh practice report and its sessions.
    assert [c["run_report"]["run_id"] for c in calls] == ["prac-run1", "prac-practice-v2"]
    fresh = demo.read_json(demo.VAR_DIR / "runs/prac-practice-v2/run_report.json")
    assert calls[1]["run_report"] == fresh
    assert set(calls[1]["sessions"]) == {v["id"] for v in groups["A"]}
    assert all(s["run_id"] == "prac-practice-v2" for s in calls[1]["sessions"].values())
    validators = load_validators()
    visitors_by_id = {v["id"]: v for group in groups.values() for v in group}
    assert validate_document(fresh, "run_report", validators, visitors_by_id) == []
    assert (fresh["role"], fresh["split"], fresh["label"], fresh["playbook_version"]) == ("run1", "A", "自我练习", "v2")
    lineage = demo.read_json(demo.VAR_DIR / "evolve/prac-learn/lineage.json")
    assert lineage["generations"][0]["next_source_run_id"] == "prac-practice-v2"
    states = [[p["state"] for p in s.get("practice", [])] for s in sandbox]
    assert ["running"] in states and ["done"] in states
    text = (demo.VAR_DIR / "demo/prac/summary.md").read_text(encoding="utf-8")
    line = next(l for l in text.splitlines() if l.startswith("自我练习"))
    assert "（A 组，v2）" in line and "isi_response_rate=" in line and "prac-practice-v2" in line
    assert_reports(m)


def test_single_generation_has_no_practice(sandbox, monkeypatch):
    calls, batches = [], []
    committed_evolve(monkeypatch, calls)
    record_batches(monkeypatch, batches)
    assert demo.main(["all", *MOCK, "--experiment", "single"]) == 0
    m = manifest()
    assert m["run2"]["playbook_version"] == "v2"                      # committed, still no practice
    assert set(m) == {"experiment_id", "updated_at", "stage", "run1", "evolution", "run2", "control", "error"}
    assert all("practice" not in s for s in sandbox)
    assert sorted(args[5] for args in batches if args[5] != "validation") == ["control", "run1", "run2"]
    assert len(calls) == 1 and calls[0]["run_report"]["run_id"] == "single-run1"
    assert not any("practice" in p.name for p in (demo.VAR_DIR / "runs").iterdir())
    assert "自我练习" not in (demo.VAR_DIR / "demo/single/summary.md").read_text(encoding="utf-8")


def inject_degraded(monkeypatch, n):
    original = demo.build_report

    def degraded(*args, **kwargs):
        report, summary = original(*args, **kwargs)
        summary["degraded_sessions"] = n
        return report, summary

    monkeypatch.setattr(demo, "build_report", degraded)


def test_degraded_batch_above_threshold_is_invalid(sandbox, monkeypatch):
    inject_degraded(monkeypatch, 1)                                     # 1/6 > 0.10
    assert demo.main(["run1", *MOCK, "--experiment", "degraded"]) == 1
    m = manifest()
    assert m["stage"] == "failed" and m["run1"]["state"] == "failed" and "批次无效" in m["error"]
    out = demo.VAR_DIR / "runs" / m["run1"]["run_id"]
    summary = demo.read_json(out / "summary.json")
    assert summary["attempted"] == 6 and summary["degraded_sessions"] == 1
    assert "max_degraded_share" in summary["invalid_reason"]
    assert (out / "run_report.json").is_file()                          # kept for inspection


def test_degraded_batch_below_threshold_passes(sandbox, monkeypatch):
    real = demo.load_config
    monkeypatch.setattr(demo, "load_config", lambda config=None: real({**(config or {}),
                                                                       "quality": {"max_degraded_share": 0.2}}))
    inject_degraded(monkeypatch, 1)                                     # 1/6 <= 0.2
    assert demo.main(["run1", *MOCK, "--experiment", "tolerated"]) == 0
    m = manifest()
    assert m["run1"]["state"] == "done"
    assert "invalid_reason" not in demo.read_json(demo.VAR_DIR / "runs" / m["run1"]["run_id"] / "summary.json")


def test_mock_batches_are_never_degraded(sandbox):
    assert demo.main(["run1", *MOCK, "--experiment", "clean"]) == 0
    summary = demo.read_json(demo.VAR_DIR / "runs/clean-run1/summary.json")
    assert summary["degraded_sessions"] == 0 and "invalid_reason" not in summary


@pytest.mark.parametrize("value", [-0.01, 1.01, True, "0.1", None])
def test_config_rejects_bad_degraded_share(value):
    from engine.config import load_config
    with pytest.raises(ValueError, match="max_degraded_share"):
        load_config({"quality": {"max_degraded_share": value}})


def test_config_degraded_share_default_and_bounds():
    from engine.config import load_config
    assert load_config()["quality"]["max_degraded_share"] == 0.10
    for value in (0, 1, 0.5):
        assert load_config({"quality": {"max_degraded_share": value}})["quality"]["max_degraded_share"] == value
