"""GET /demo/pipeline aggregation and the demo launcher (the child process is always faked)."""

from datetime import datetime, timedelta
import json
import os
import sys

from fastapi.testclient import TestClient
import pytest

from api import pipeline
from api.auth import password_digest
from api.config import Settings
from api.main import create_app
from engine.file_lock import file_lock

PREFIX = "/api/v1/demo"
EID = "exp-test"


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def ago(seconds):
    return (datetime.now().astimezone() - timedelta(seconds=seconds)).isoformat(timespec="seconds")


def sessions(root, run_id, ok, errors=0):
    for i in range(ok + errors):
        write(root / "var/runs" / run_id / "sessions" / f"v-{i:03d}.json",
              {"run_id": run_id, "visitor_id": f"v-{i:03d}", "status": "error" if i >= ok else "ok"})


def report(root, run_id, isi, n=3, version="v1", **metrics):
    write(root / "var/runs" / run_id / "run_report.json",
          {"run_id": run_id, "n_visitors": n, "playbook_version": version,
           "metrics": {"isi_response_rate": isi, "referral_recall": 1.0, "referral_precision": 0.5, **metrics}})


def batch(run_id, role, version, split, state, started, finished=None, generation=None, candidate=None,
          replicate=1, total=3):
    return {"run_id": run_id, "role": role, "version": version, "split": split, "total": total, "state": state,
            "started_at": started, "finished_at": finished, "generation": generation, "candidate": candidate,
            "replicate": replicate}


def manifest(stage, **states):
    doc = {"experiment_id": EID, "updated_at": ago(1), "stage": stage, "error": None,
           "evolution": {"evolution_id": f"{EID}-learn", "state": states.get("evolution", "pending")}}
    for key, split in (("run1", "A"), ("run2", "B"), ("control", "B")):
        doc[key] = {"run_id": f"{EID}-{key}", "playbook_version": "v1", "split": split,
                    "state": states.get(key, "pending")}
    return doc


@pytest.fixture
def running(tmp_path):
    """Run 1 done; generation 1 of 2 validating: baseline x2 and c1 x2 done, c2 running."""
    root = tmp_path
    write(root / "var/demo/experiment.json", manifest("learning", run1="done", evolution="running"))
    write(root / f"var/demo/{EID}/options.json", {"generations": 2, "mock": False})
    sessions(root, f"{EID}-run1", 3)
    report(root, f"{EID}-run1", 0.4)
    learn = f"{EID}-learn"
    batches = [batch(f"{EID}-run1", "run1", "v1", "A", "done", ago(300), ago(240))]
    for label, cand, rep, isi in (("v1", None, 1, 0.5), ("v1-r2", None, 2, 0.6),
                                  ("v1_c1", "c1", 1, 0.6), ("v1_c1-r2", "c1", 2, 0.7)):
        run_id = f"{learn}-{label}"
        sessions(root, run_id, 3)
        report(root, run_id, isi)
        batches.append(batch(run_id, "validation", f"v1+{cand}" if cand else "v1", "C", "done",
                             ago(200), ago(150), generation=1, candidate=cand, replicate=rep))
    sessions(root, f"{learn}-v1_c2", 1, errors=1)
    batches.append(batch(f"{learn}-v1_c2", "validation", "v1+c2", "C", "running", ago(30),
                         generation=1, candidate="c2"))
    write(root / f"var/demo/{EID}/progress.json", {
        "schema": "demo-progress/1", "experiment_id": EID, "started_at": ago(300), "updated_at": ago(1),
        "commands": ["run1", "learn", "run2"], "generations_planned": 2, "mock": False, "batches": batches,
        "generations": [{"index": 1, "evolution_id": f"{learn}-g1", "from_version": "v1", "state": "running",
                         "started_at": ago(240), "finished_at": None, "outcome": None, "to_version": None}]})
    write(root / f"var/evolve/{learn}-g1/status.json", {
        "schema": "evolve-status/1", "evolution_id": f"{learn}-g1", "from_version": "v1", "phase": "validating",
        "reflector": {"state": "done", "model": "gpt-6-astra", "fell_back": False},
        "validation": {"baseline": "done", "candidates": {"c1": "done", "c2": "running", "c3": "pending"}},
        "outcome": None, "to_version": None, "chosen": None, "error": None})
    return root


def client_for(root, **settings):
    return TestClient(create_app(Settings(data_root=root, **settings)))


def get_pipeline(client):
    response = client.get(PREFIX + "/pipeline")
    assert response.status_code == 200, response.text
    return response.json()


def test_no_experiment(tmp_path):
    with client_for(tmp_path) as client:
        body = get_pipeline(client)
    assert set(body) == {"available", "launcher"} and body["available"] is False
    launcher = body["launcher"]
    assert launcher["enabled"] is False and launcher["state"] == "idle" and launcher["log_tail"] == []
    assert [p["key"] for p in launcher["presets"]] == ["live", "full", "next"]
    assert [p["generations"] for p in launcher["presets"]] == [1, 3, 1]
    assert [p["reset"] for p in launcher["presets"]] == [True, True, False]
    assert [p["expected_s"] for p in launcher["presets"]] == [400, 1480, 480]
    assert launcher["current_version"] is None and launcher["lineage_mode"] is None


def test_running_experiment(running):
    with client_for(running) as client:
        body = get_pipeline(client)
    assert body["available"] and body["experiment_id"] == EID and body["mode"] == "real"
    assert body["state"] == "running" and body["error"] is None and body["finished_at"] is None
    assert body["progress_available"] is True and body["generations_planned"] == 2
    assert body["eta_s"] is not None and body["eta_s"] > 0 and body["elapsed_s"] >= 290
    assert body["playbook"] == {"from_version": "v1", "current_version": "v1"}
    steps = {s["key"]: s for s in body["steps"]}
    assert [s["key"] for s in body["steps"]] == ["run1", "gen1", "practice1", "gen2", "final"]
    assert {k: s["state"] for k, s in steps.items()} == {
        "run1": "done", "gen1": "running", "practice1": "pending", "gen2": "pending", "final": "pending"}
    run1 = steps["run1"]
    assert run1["expected_s"] == 60 and run1["eta_s"] is None and run1["elapsed_s"] == 60
    b = run1["batches"][0]
    assert (b["label"], b["completed"], b["failed"], b["isi_response_rate"], b["duration_s"], b["split"]) \
        == ("运行 1", 3, 0, 0.4, 60.0, "A")
    gen1 = steps["gen1"]
    assert gen1["eta_s"] is not None and gen1["expected_s"] == 400 and gen1["finished_at"] is None
    assert [b["label"] for b in gen1["batches"]] == ["基线 · 第 1 次", "基线 · 第 2 次", "候选 1 · 第 1 次",
                                                     "候选 1 · 第 2 次", "候选 2 · 第 1 次"]
    c2 = gen1["batches"][-1]
    assert (c2["state"], c2["completed"], c2["failed"], c2["total"], c2["isi_response_rate"], c2["duration_s"]) \
        == ("running", 1, 1, 3, None, None)
    generation = gen1["generation"]
    assert generation["phase"] == "validating" and generation["reflector"]["model"] == "gpt-6-astra"
    assert generation["baseline_isi"] == pytest.approx(0.55)
    cands = {c["id"]: c for c in generation["candidates"]}
    assert cands["c1"]["isi"] == pytest.approx(0.65) and cands["c1"]["state"] == "done"
    assert (cands["c2"]["state"], cands["c2"]["isi"]) == ("running", None)
    assert (cands["c3"]["state"], cands["c3"]["isi"], cands["c3"]["passed"]) == ("pending", None, None)
    assert generation["outcome"] is None and generation["chosen"] is None
    # Planned 2 generations (not launched here) → the "full" preset defaults until a generation is measured.
    assert steps["gen2"]["generation"] is None and steps["gen2"]["expected_s"] == 400
    assert steps["practice1"]["expected_s"] == 60          # measured run 1 duration
    assert body["result"] == {"run1": {"isi_response_rate": 0.4, "referral_recall": 1.0, "referral_precision": 0.5,
                                       "n": 3, "playbook_version": "v1"},
                              "control": None, "run2": None, "delta_pp": None}


def finish(root):
    """Turn the running fixture into a finished experiment: g1 committed v2, g2 kept, practice, B runs."""
    learn = f"{EID}-learn"
    doc = manifest("done", run1="done", evolution="done", run2="done", control="done")
    doc["run2"]["playbook_version"] = "v2"
    doc["evolution"].update(evolution_id=f"{learn}-g1", generations=[f"{learn}-g1", f"{learn}-g2"])
    write(root / "var/demo/experiment.json", doc)
    progress = json.loads((root / f"var/demo/{EID}/progress.json").read_text(encoding="utf-8"))
    for b in progress["batches"]:
        b.update(state="done", finished_at=b["finished_at"] or ago(140))
    report(root, f"{learn}-v1_c2", 0.5)
    progress["generations"][0].update(state="done", finished_at=ago(140), outcome="committed", to_version="v2")
    progress["batches"].append(batch(f"{EID}-practice-v2", "practice", "v2", "A", "done", ago(140), ago(100),
                                     generation=1))
    progress["generations"].append({"index": 2, "evolution_id": f"{learn}-g2", "from_version": "v2",
                                    "state": "done", "started_at": ago(100), "finished_at": ago(60),
                                    "outcome": "kept_previous", "to_version": None})
    progress["batches"].append(batch(f"{learn}-v2_c1", "validation", "v2+c1", "C", "done", ago(80), ago(70),
                                     generation=2, candidate="c1"))
    for key, isi, version in (("run2", 0.7, "v2"), ("control", 0.5, "v1")):
        progress["batches"].append(batch(f"{EID}-{key}", key, version, "B", "done", ago(50), ago(5)))
        sessions(root, f"{EID}-{key}", 3)
        report(root, f"{EID}-{key}", isi, version=version)
    write(root / f"var/demo/{EID}/progress.json", progress)
    write(root / f"var/evolve/{learn}-g1/status.json", {
        "evolution_id": f"{learn}-g1", "from_version": "v1", "phase": "done",
        "reflector": {"state": "done", "model": "gpt-6-astra", "fell_back": False},
        "validation": {"baseline": "done", "candidates": {"c1": "done", "c2": "done", "c3": "blocked"}},
        "outcome": "committed", "to_version": "v2", "chosen": "c1"})
    write(root / f"var/evolve/{learn}-g1/evolution.json", {
        "evolution_id": f"{learn}-g1", "outcome": "committed", "chosen": "c1",
        "baseline_val_metrics": {"isi_response_rate": 0.55},
        "candidates": [{"id": "c1", "passed": True}, {"id": "c2", "passed": False}, {"id": "c3", "passed": False}]})
    write(root / f"var/evolve/{learn}-g2/status.json", {
        "evolution_id": f"{learn}-g2", "from_version": "v2", "phase": "done",
        "reflector": {"state": "done", "model": "gpt-6-astra", "fell_back": True},
        "validation": {"baseline": "skipped", "candidates": {"c1": "done"}},
        "outcome": "kept_previous", "to_version": None, "chosen": None})
    write(root / f"var/evolve/{learn}-g2/evolution.json", {
        "evolution_id": f"{learn}-g2", "outcome": "kept_previous", "chosen": None,
        "baseline_val_metrics": {"isi_response_rate": 0.65}, "candidates": [{"id": "c1", "passed": False}]})
    return root


def test_finished_experiment(running):
    root = finish(running)
    with client_for(root) as client:
        body = get_pipeline(client)
    assert body["state"] == "done" and body["eta_s"] is None and body["finished_at"]
    assert body["playbook"] == {"from_version": "v1", "current_version": "v2"}
    assert {s["key"]: s["state"] for s in body["steps"]} == {
        "run1": "done", "gen1": "done", "practice1": "done", "gen2": "done", "final": "done"}
    assert all(s["eta_s"] is None for s in body["steps"])
    gen1 = body["steps"][1]["generation"]
    assert (gen1["outcome"], gen1["to_version"], gen1["chosen"], gen1["phase"]) == ("committed", "v2", "c1", "done")
    assert [(c["id"], c["state"], c["passed"]) for c in gen1["candidates"]] == [
        ("c1", "done", True), ("c2", "done", False), ("c3", "done", False)]
    assert gen1["candidates"][1]["isi"] == 0.5 and gen1["candidates"][2]["status"] == "blocked"
    gen2 = body["steps"][3]["generation"]
    assert gen2["baseline_isi"] == 0.65 and gen2["outcome"] == "kept_previous"   # reused baseline
    assert body["steps"][2]["batches"][0]["label"] == "练习（v2）"
    assert [b["label"] for b in body["steps"][4]["batches"]] == ["运行 2", "对照"]
    result = body["result"]
    assert result["run2"]["isi_response_rate"] == 0.7 and result["control"]["playbook_version"] == "v1"
    assert result["delta_pp"] == pytest.approx(20.0)


def test_failed_experiment_marks_open_steps(running):
    doc = manifest("failed", run1="done", evolution="failed")
    doc["error"] = "RuntimeError: boom"
    write(running / "var/demo/experiment.json", doc)
    with client_for(running) as client:
        body = get_pipeline(client)
    assert body["state"] == "failed" and body["error"] == "RuntimeError: boom" and body["eta_s"] is None
    assert {s["key"]: s["state"] for s in body["steps"]} == {
        "run1": "done", "gen1": "failed", "practice1": "skipped", "gen2": "skipped", "final": "skipped"}
    assert body["steps"][1]["batches"][-1]["state"] == "failed"


def test_old_experiment_without_progress(tmp_path):
    root = tmp_path
    doc = manifest("done", run1="done", evolution="done", run2="done", control="done")
    doc["evolution"]["generations"] = [f"{EID}-learn"]
    write(root / "var/demo/experiment.json", doc)
    for key, isi in (("run1", 0.4), ("run2", 0.5), ("control", 0.45)):
        sessions(root, f"{EID}-{key}", 2)
        report(root, f"{EID}-{key}", isi, n=2)
    write(root / f"var/evolve/{EID}-learn/status.json", {"evolution_id": f"{EID}-learn", "from_version": "v1",
                                                         "phase": "done", "outcome": "kept_previous"})
    with client_for(root) as client:
        body = get_pipeline(client)
    assert body["progress_available"] is False and body["state"] == "done"
    assert [(s["key"], s["state"]) for s in body["steps"]] == [
        ("run1", "done"), ("gen1", "done"), ("final", "done")]
    assert body["steps"][0]["batches"][0]["completed"] == 2 and body["steps"][0]["batches"][0]["total"] == 2
    assert body["steps"][1]["generation"]["outcome"] == "kept_previous"
    assert body["result"]["delta_pp"] == pytest.approx(5.0)
    # A bare manifest (nothing else on disk) must not crash either.
    write(root / "var/demo/experiment.json", manifest("run1", run1="running"))
    with client_for(root) as client:
        body = get_pipeline(client)
    assert body["state"] == "running" and [s["state"] for s in body["steps"]] == ["running", "pending", "pending"]
    assert body["eta_s"] is not None


def test_mock_data_source():
    with TestClient(create_app(Settings(data_source="mock"))) as client:
        body = get_pipeline(client)
        assert body["available"] is False and body["launcher"]["enabled"] is False
        response = client.post(PREFIX + "/launch", json={"preset": "live"})
        assert response.status_code == 501 and response.json()["error"]["code"] == "RUNS_VIA_CLI"


def test_auth_required_when_enabled(tmp_path):
    settings = dict(auth_mode="demo", auth_password_sha256=password_digest("pw-for-test"))
    with client_for(tmp_path, **settings) as client:
        assert client.get(PREFIX + "/pipeline").status_code == 401
        assert client.post(PREFIX + "/launch", json={"preset": "live"}).status_code == 401
        assert client.post(PREFIX + "/stop").status_code == 401


def test_launch_disabled(tmp_path):
    with client_for(tmp_path) as client:
        for path, body in (("/launch", {"preset": "live"}), ("/stop", None)):
            response = client.post(PREFIX + path, json=body)
            assert response.status_code == 403 and response.json()["error"]["code"] == "LAUNCH_DISABLED"


class FakeProcess:
    instances = []
    eid = EID

    def __init__(self, command, **kwargs):
        self.command, self.kwargs, self.pid, self.returncode = command, kwargs, 4242, None
        kwargs["stdout"].write(f"experiment_id={self.eid}\nworking with secret-value-for-test-123\n".encode())
        FakeProcess.instances.append(self)

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.returncode = -9


@pytest.fixture
def fake_popen(monkeypatch):
    FakeProcess.instances = []
    killed = []
    monkeypatch.setattr(pipeline.subprocess, "Popen", FakeProcess)

    def fake_run(command, **kwargs):  # Windows taskkill
        killed.append(command)
        FakeProcess.instances[-1].returncode = 1

    def fake_killpg(pid, sig):  # POSIX
        killed.append(("killpg", pid, sig))
        FakeProcess.instances[-1].returncode = -15

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)
    monkeypatch.setattr(pipeline.os, "killpg", fake_killpg, raising=False)
    monkeypatch.setenv("FAKE_SERVICE_API_KEY", "secret-value-for-test-123")
    monkeypatch.setenv("REFLECTOR_REASONING_EFFORT", "xhigh")
    return killed


def test_unknown_preset(tmp_path, fake_popen):
    with client_for(tmp_path, demo_launch=True) as client:
        for body in ({"preset": "turbo"}, {}, {"preset": "live", "extra": 1}):
            response = client.post(PREFIX + "/launch", json=body)
            assert response.status_code == 422 and response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert FakeProcess.instances == []


def test_launch_poll_and_stop(running, fake_popen):
    with client_for(running, demo_launch=True) as client:
        response = client.post(PREFIX + "/launch", json={"preset": "live", "mock": True})
        assert response.status_code == 202 and response.json() == {"pid": 4242, "preset": "live", "mock": True}
        proc = FakeProcess.instances[0]
        assert proc.command == [sys.executable, "-m", "engine.demo", "all", "--reset", "--generations", "1",
                                "--visitor-renderer", "template", "--mock"]
        assert proc.kwargs["env"]["REFLECTOR_REASONING_EFFORT"] == "low"
        assert proc.kwargs["cwd"] == str(pipeline.REPO_ROOT)
        assert ("creationflags" in proc.kwargs) if os.name == "nt" else proc.kwargs["start_new_session"]
        assert os.environ["REFLECTOR_REASONING_EFFORT"] == "xhigh"        # server env untouched
        response = client.post(PREFIX + "/launch", json={"preset": "full"})
        assert response.status_code == 409 and response.json()["error"]["code"] == "ALREADY_RUNNING"
        body = get_pipeline(client)
        launcher = body["launcher"]
        assert (launcher["enabled"], launcher["state"], launcher["pid"], launcher["preset"]) == (True, "running", 4242,
                                                                                                "live")
        assert launcher["log_tail"] == [f"experiment_id={EID}", "working with ***"]
        assert "secret-value-for-test-123" not in json.dumps(body)
        assert body["state"] == "running"
        response = client.post(PREFIX + "/stop")
        assert response.status_code == 200 and response.json() == {"stopped": True}
        if os.name == "nt":
            assert fake_popen == [["taskkill", "/PID", "4242", "/T", "/F"]]
        else:
            assert fake_popen[0][:2] == ("killpg", 4242)
        body = get_pipeline(client)
        assert body["launcher"]["state"] == "exited" and body["launcher"]["exit_code"] is not None
        assert body["state"] == "failed" and body["error"] == "已手动停止" and body["eta_s"] is None
        response = client.post(PREFIX + "/stop")
        assert response.status_code == 409 and response.json()["error"]["code"] == "NOT_RUNNING"
        # A second launch after exit is allowed and uses the full preset's settings.
        FakeProcess.eid = "exp-next"
        try:
            assert client.post(PREFIX + "/launch", json={"preset": "full"}).status_code == 202
        finally:
            FakeProcess.eid = EID
        proc = FakeProcess.instances[1]
        assert proc.command[5:7] == ["--generations", "3"] and "--mock" not in proc.command
        assert proc.kwargs["env"]["REFLECTOR_REASONING_EFFORT"] == "high"
        # The stopped experiment stays failed although the new child truncated the log.
        body = get_pipeline(client)
        assert body["launcher"]["state"] == "running" and body["launcher"]["log_tail"][0] == "experiment_id=exp-next"
        assert (body["experiment_id"], body["state"], body["error"]) == (EID, "failed", "已手动停止")


def test_child_exit_without_final_stage_is_failed(running, fake_popen):
    with client_for(running, demo_launch=True) as client:
        assert client.post(PREFIX + "/launch", json={"preset": "live"}).status_code == 202
        assert get_pipeline(client)["state"] == "running"
        FakeProcess.instances[0].returncode = 1
        body = get_pipeline(client)
        assert body["state"] == "failed" and "退出码 1" in body["error"] and body["launcher"]["exit_code"] == 1


def test_launch_refused_while_cli_holds_lock(tmp_path, fake_popen):
    with client_for(tmp_path, demo_launch=True) as client:
        with file_lock(tmp_path / "var/demo/.lock", blocking=False):
            response = client.post(PREFIX + "/launch", json={"preset": "live"})
            assert response.status_code == 409 and response.json()["error"]["code"] == "ALREADY_RUNNING"
        assert FakeProcess.instances == []
        assert client.post(PREFIX + "/launch", json={"preset": "live"}).status_code == 202


# --------------------------------------------------------------------------------------------
# Evolution chain: curve on cohort B, the "next" preset
# --------------------------------------------------------------------------------------------

LIN = "lin-20261115-093000-ab12cd34"


def chain_experiment(root, eid, started, from_version, runs, generation, lineage=LIN, mock=False, summary=None,
                     finished=True):
    """One experiment of a chain. ``runs``: {role: (version, isi, state)}; isi None → no report yet."""
    batches = [batch(f"{eid}-run1", "run1", from_version, "A", "done", started, started)]
    for role, (version, isi, state) in runs.items():
        batches.append(batch(f"{eid}-{role}", role, version, "B", state, started,
                             started if state != "running" else None))
        if isi is not None:
            report(root, f"{eid}-{role}", isi, n=3, version=version, referral_recall=isi, referral_precision=1 - isi)
    outcome, to_version = generation
    evolution_id = f"{eid}-learn"
    write(root / f"var/demo/{eid}/progress.json", {
        "schema": "demo-progress/1", "experiment_id": eid, "started_at": started, "updated_at": started,
        "commands": ["run1", "learn", "run2"], "generations_planned": 1, "mock": mock, "lineage_id": lineage,
        "from_version": from_version, "batches": batches,
        "generations": [{"index": 1, "evolution_id": evolution_id, "from_version": from_version, "state": "done",
                         "started_at": started, "finished_at": started, "outcome": outcome,
                         "to_version": to_version}]})
    chosen = "c2" if outcome == "committed" else None
    write(root / f"var/evolve/{evolution_id}/evolution.json", {
        "evolution_id": evolution_id, "from_version": from_version, "to_version": to_version, "outcome": outcome,
        "chosen": chosen, "candidates": [{"id": "c1", "summary": "未采纳的候选", "passed": False},
                                         {"id": "c2", "summary": summary, "passed": outcome == "committed"}]})
    doc = {"experiment_id": eid, "updated_at": started, "stage": "done" if finished else "run2", "error": None,
           "evolution": {"evolution_id": evolution_id, "state": "done", "generations": [evolution_id]}}
    for key, split in (("run1", "A"), ("run2", "B"), ("control", "B")):
        version = from_version if key == "run1" else runs.get(key, (from_version,))[0]
        state = "done" if finished or key == "run1" else runs.get(key, (None, None, "running"))[2]
        doc[key] = {"run_id": f"{eid}-{key}", "playbook_version": version, "split": split, "state": state}
    write(root / f"var/demo/experiment.{eid}.json", doc)
    return doc


@pytest.fixture
def chain(tmp_path):
    """v1 control + v2 run 2; v2 control + v3 run 2; v3 control + v3 run 2 (kept_previous)."""
    root = tmp_path
    write(root / "var/demo/lineage.json", {"lineage_id": LIN, "reset_at": ago(400)})
    chain_experiment(root, "exp-a", ago(300), "v1", {"control": ("v1", 0.5, "done"), "run2": ("v2", 0.6, "done")},
                     ("committed", "v2"), summary="补问作息")
    chain_experiment(root, "exp-b", ago(200), "v2", {"control": ("v2", 0.7, "done"), "run2": ("v3", 0.8, "done")},
                     ("committed", "v3"), summary="先筛转介")
    current = chain_experiment(root, "exp-c", ago(100), "v3",
                               {"control": ("v3", 0.9, "done"), "run2": ("v3", 0.7, "done")},
                               ("kept_previous", None))
    write(root / "var/demo/experiment.json", current)
    # Excluded: another chain, the same chain in mock mode, an unreadable file, a foreign experiment id.
    chain_experiment(root, "exp-other", ago(250), "v1", {"control": ("v1", 0.0, "done")}, ("kept_previous", None),
                     lineage="lin-other")
    chain_experiment(root, "exp-mock", ago(150), "v1", {"control": ("v1", 0.0, "done"), "run2": ("v2", 0.0, "done")},
                     ("committed", "v2"), mock=True, summary="mock")
    (root / "var/demo/exp-broken").mkdir(parents=True)
    (root / "var/demo/exp-broken/progress.json").write_text("{not json", encoding="utf-8")
    write(root / "var/demo/exp-alias/progress.json", {"experiment_id": "exp-a", "lineage_id": LIN, "mock": False,
                                                      "started_at": ago(50), "batches": [], "generations": []})
    (root / "var/playbook-repo/.git").mkdir(parents=True)
    (root / "var/playbook-repo/VERSION").write_text("v3\n", encoding="utf-8")
    return root


def test_curve_over_chain(chain):
    with client_for(chain) as client:
        body = get_pipeline(client)
    assert body["experiment_id"] == "exp-c" and body["state"] == "done"
    curve = body["curve"]
    assert (curve["lineage_id"], curve["mode"], curve["cohort"], curve["experiments"]) == (LIN, "real", "B", 3)
    points = curve["points"]
    assert [p["version"] for p in points] == ["v1", "v2", "v3"]
    assert [p["n_runs"] for p in points] == [1, 2, 3]
    assert [p["mean"] for p in points] == [pytest.approx(0.5), pytest.approx(0.65), pytest.approx(0.8)]
    assert points[0]["delta_pp"] is None
    assert points[1]["delta_pp"] == pytest.approx(15.0) and points[2]["delta_pp"] == pytest.approx(15.0)
    assert [p["learned"] for p in points] == [None, "补问作息", "先筛转介"]
    assert [p["evolution_id"] for p in points] == [None, "exp-a-learn", "exp-b-learn"]
    assert points[1]["referral_recall"] == pytest.approx(0.65)
    assert points[1]["referral_precision"] == pytest.approx(0.35)
    assert [(r["experiment_id"], r["role"]) for r in points[1]["runs"]] == [("exp-a", "run2"), ("exp-b", "control")]
    assert [(r["experiment_id"], r["role"]) for r in points[2]["runs"]] == [
        ("exp-b", "run2"), ("exp-c", "control"), ("exp-c", "run2")]
    assert points[0]["runs"] == [{"run_id": "exp-a-control", "role": "control", "experiment_id": "exp-a",
                                  "isi_response_rate": 0.5, "n": 3}]
    rejected = curve["rejected"]
    assert [(r["experiment_id"], r["evolution_id"], r["from_version"]) for r in rejected] == [
        ("exp-c", "exp-c-learn", "v3")]
    assert rejected[0]["finished_at"]
    # Step texts name the actual versions; the existing fields are unchanged.
    steps = {s["key"]: s for s in body["steps"]}
    assert steps["run1"]["detail"] == "用当前 playbook（v3）跑 A 组来访"
    assert steps["final"]["detail"] == "学习后的版本与 v3 并行跑 B 组来访"
    assert body["playbook"] == {"from_version": "v3", "current_version": "v3"}
    assert body["result"]["delta_pp"] == pytest.approx(-20.0)
    assert (body["launcher"]["current_version"], body["launcher"]["lineage_mode"]) == ("v3", "real")


def test_curve_while_current_experiment_runs(chain):
    (chain / "var/runs/exp-c-run2/run_report.json").unlink()                # run 2 still in progress
    current = chain_experiment(chain, "exp-c", ago(100), "v3",
                               {"control": ("v3", 0.9, "done"), "run2": ("v4", None, "running")},
                               ("committed", "v4"), summary="新学到的", finished=False)
    write(chain / "var/demo/experiment.json", current)
    with client_for(chain) as client:
        body = get_pipeline(client)
    assert body["state"] == "running"
    points = body["curve"]["points"]
    assert [p["version"] for p in points] == ["v1", "v2", "v3"]             # v4 has no B report yet
    assert points[2]["n_runs"] == 2 and points[2]["mean"] == pytest.approx(0.85)
    assert body["curve"]["rejected"] == []
    report(chain, "exp-c-run2", 0.95, version="v4")                          # report written → counted
    with client_for(chain) as client:
        points = get_pipeline(client)["curve"]["points"]
    assert [p["version"] for p in points] == ["v1", "v2", "v3", "v4"]
    assert points[3]["learned"] == "新学到的" and points[3]["delta_pp"] == pytest.approx(10.0)


def test_curve_in_mock_mode_only_counts_mock_experiments(chain):
    mock = json.loads((chain / "var/demo/experiment.exp-mock.json").read_text(encoding="utf-8"))
    write(chain / "var/demo/experiment.json", mock)
    with client_for(chain) as client:
        curve = get_pipeline(client)["curve"]
    assert (curve["mode"], curve["experiments"]) == ("mock", 1)
    assert [(p["version"], p["learned"]) for p in curve["points"]] == [("v1", None), ("v2", "mock")]


def test_old_experiment_has_empty_curve(running):
    with client_for(running) as client:
        body = get_pipeline(client)
    assert body["curve"] == {"lineage_id": None, "mode": "real", "cohort": "B", "experiments": 0,
                             "points": [], "rejected": []}
    assert body["steps"][0]["detail"] == "用初始 playbook（v1）跑 A 组来访"
    assert body["steps"][-1]["detail"] == "学习后的版本与 v1 并行跑 B 组来访"


def test_next_preset_without_repo_uses_low_effort_and_no_reset(tmp_path, fake_popen):
    with client_for(tmp_path, demo_launch=True) as client:
        body = get_pipeline(client)
        assert (body["launcher"]["current_version"], body["launcher"]["lineage_mode"]) == (None, None)
        response = client.post(PREFIX + "/launch", json={"preset": "next", "mock": True})
        assert response.status_code == 202 and response.json() == {"pid": 4242, "preset": "next", "mock": True}
    proc = FakeProcess.instances[0]
    assert proc.command == [sys.executable, "-m", "engine.demo", "all", "--generations", "1",
                            "--visitor-renderer", "template", "--mock"]
    assert proc.kwargs["env"]["REFLECTOR_REASONING_EFFORT"] == "low"


def test_next_preset_effort_by_current_version(tmp_path, fake_popen):
    (tmp_path / "var/playbook-repo/.git").mkdir(parents=True)
    (tmp_path / "var/playbook-repo/VERSION").write_text("v1\n", encoding="utf-8")
    with client_for(tmp_path, demo_launch=True) as client:
        assert client.post(PREFIX + "/launch", json={"preset": "next"}).status_code == 202
        FakeProcess.instances[-1].returncode = 0
        (tmp_path / "var/playbook-repo/VERSION").write_text("v2\n", encoding="utf-8")
        assert get_pipeline(client)["launcher"]["current_version"] == "v2"
        assert client.post(PREFIX + "/launch", json={"preset": "next"}).status_code == 202
        FakeProcess.instances[-1].returncode = 0
        assert client.post(PREFIX + "/launch", json={"preset": "live"}).status_code == 202
    efforts = [p.kwargs["env"]["REFLECTOR_REASONING_EFFORT"] for p in FakeProcess.instances]
    assert efforts == ["low", "high", "low"]                                # live stays low at any version
    assert "--reset" not in FakeProcess.instances[1].command and "--reset" in FakeProcess.instances[2].command
    assert "--mock" not in FakeProcess.instances[1].command


def test_next_refused_when_mode_differs_from_chain(chain, fake_popen):
    with client_for(chain, demo_launch=True) as client:
        response = client.post(PREFIX + "/launch", json={"preset": "next", "mock": True})
        assert response.status_code == 409 and response.json()["error"]["code"] == "LINEAGE_MODE_MISMATCH"
        assert "v1" in response.json()["error"]["message"]
        assert FakeProcess.instances == []
        # Resetting presets start a new chain, so any mode is fine; so is "next" in the chain's own mode.
        assert client.post(PREFIX + "/launch", json={"preset": "live", "mock": True}).status_code == 202
        FakeProcess.instances[-1].returncode = 0
        assert client.post(PREFIX + "/launch", json={"preset": "next", "mock": False}).status_code == 202
    assert FakeProcess.instances[-1].kwargs["env"]["REFLECTOR_REASONING_EFFORT"] == "high"   # repo at v3
