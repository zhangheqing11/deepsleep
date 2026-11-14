"""File artifacts, live progress, contract fidelity and read-only HTTP boundaries."""

from copy import deepcopy
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from api.config import Settings
from api.main import create_app
from contracts.validate import load_validators, read_json, validate_document
from engine.evolve.config import load_config
from engine.evolve.repo import PlaybookRepo
from engine.evolve.status import StatusTracker

EXAMPLES = Path(__file__).resolve().parents[2] / "contracts/examples"
PREFIX = "/api/v1"


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def artifacts(tmp_path):
    reports = [read_json(EXAMPLES / f"run_report.{role}.json") for role in ("run1", "run2", "control")]
    for report in reports:
        write(tmp_path / "var/runs" / report["run_id"] / "run_report.json", report)
    for path in EXAMPLES.glob("session.*.json"):
        session = read_json(path)
        write(tmp_path / "var/runs" / session["run_id"] / "sessions" / f"{session['visitor_id']}.json", session)
    running = deepcopy(read_json(EXAMPLES / "session.A-001.json"))
    running.update(run_id="running", session_id="running/A-001", models={"agent": "mock-agent", "visitor": "mock"})
    write(tmp_path / "var/runs/running/sessions/A-001.json", running)
    evo = read_json(EXAMPLES / "evolution.v1-v2.json")
    evolution_dir = tmp_path / "var/evolve" / evo["evolution_id"]
    write(evolution_dir / "evolution.json", evo)
    write(evolution_dir / "insights.json", {"contract": False, "summary": "测试洞察"})
    tracker = StatusTracker(evolution_dir, evo["evolution_id"], "v1")
    tracker.set(phase="done", outcome="committed", to_version="v2", chosen=evo["chosen"])
    StatusTracker(tmp_path / "var/evolve/learning", "learning", "v1")
    experiment = {"experiment_id": "exp-test", "updated_at": "2026-11-15T10:00:00+08:00", "stage": "run2",
                  "run1": {"run_id": reports[0]["run_id"], "playbook_version": "v1", "split": "A", "state": "done"},
                  "run2": {"run_id": "running", "playbook_version": "v2", "split": "B", "state": "running", "n_visitors": 40},
                  "control": {"run_id": reports[2]["run_id"], "playbook_version": "v1", "split": "B", "state": "pending"},
                  "evolution": {"evolution_id": "learning", "state": "running"}, "error": None}
    write(tmp_path / "var/demo/experiment.json", experiment)
    repo = PlaybookRepo(load_config(), path=tmp_path / "var/playbook-repo")
    repo.init("# 初始 playbook\n")
    repo.commit_version("# 初始 playbook\n新增提问策略\n", "测试候选通过门禁")
    return tmp_path, reports, evo, repo


@pytest.fixture
def client(artifacts):
    with TestClient(create_app(Settings(data_root=artifacts[0]))) as client:
        yield client


def get(client, path):
    response = client.get(PREFIX + path)
    assert response.status_code == 200, response.text
    assert response.headers["X-Request-ID"].startswith("req_")
    return response.json()


def error(response, status, code=None):
    assert response.status_code == status, response.text
    detail = response.json()["error"]
    assert set(detail) == {"code", "message", "request_id"}
    assert detail["request_id"] == response.headers["X-Request-ID"]
    if code:
        assert detail["code"] == code


def test_files_routes_and_contracts(client, artifacts):
    root, reports, evo, repo = artifacts
    validators = load_validators()
    visitors = {d["id"]: d for d in map(read_json, EXAMPLES.glob("visitor.*.json"))}
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert get(client, "/health") == {"status": "ok", "data_source": "files", "execution_mode": "real"}
    assert get(client, "/demo/experiment") == read_json(root / "var/demo/experiment.json")
    items = get(client, "/runs")["items"]
    assert len(items) == 4
    from datetime import datetime
    dates = [datetime.fromisoformat(i["created_at"]) for i in items]
    assert dates == sorted(dates, reverse=True)
    assert get(client, "/runs?limit=1")["items"] == items[:1]
    for source in reports:
        base = "/runs/" + source["run_id"]
        report = get(client, base + "/report")
        assert report == source
        assert validate_document(report, "run_report", validators, visitors) == []
        state = get(client, base)
        assert state["status"] == "succeeded" and state["report_available"]
        assert state["execution_mode"] == "real"
        sessions = get(client, base + "/sessions")["items"]
        assert len(sessions) == source["n_visitors"]
        for item in sessions:
            response = client.get(PREFIX + base + "/sessions/" + item["visitor_id"])
            if item["session_available"]:
                assert response.status_code == 200
                assert validate_document(response.json(), "session", validators, visitors) == []
            else:
                error(response, 404)
        assert get(client, base + "/evidence") == {"available": False}
    base = "/evolutions/" + evo["evolution_id"]
    assert get(client, base) == evo
    assert validate_document(get(client, base), "evolution", validators, visitors) == []
    assert get(client, base + "/status")["phase"] == "done"
    assert get(client, base + "/insights") == {"contract": False, "summary": "测试洞察"}
    versions = get(client, "/playbook/versions")["items"]
    assert [v["version"] for v in versions] == ["v1", "v2"]
    assert [v["is_head"] for v in versions] == [False, True]
    assert versions[1]["sha"] == repo.head()
    assert versions[1]["author"] == "deepsleep-agent"
    assert get(client, "/playbook/v1") == {"version": "v1", "text": "# 初始 playbook\n"}
    assert get(client, "/playbook/v2")["text"] == repo.read("v2")
    diff = get(client, "/playbook/diff?from=v1&to=v2")
    assert diff["from"] == "v1" and diff["to"] == "v2"
    assert "+新增提问策略" in diff["diff"]
    assert get(client, "/playbook/diff?from=v1&to=v1")["diff"] == ""
    assert {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()} == before


def test_live_progress_and_not_ready(client, artifacts):
    root = artifacts[0]
    state = get(client, "/runs/running")
    assert state["status"] == "running" and not state["report_available"]
    assert state["progress"] == {"completed": 1, "failed": 0, "total": 40}
    assert state["execution_mode"] == "mock"
    error(client.get(PREFIX + "/runs/running/report"), 404, "NOT_READY")
    error(client.get(PREFIX + "/evolutions/learning"), 404, "NOT_READY")
    assert get(client, "/evolutions/learning/status")["phase"] == "reflecting"
    items = get(client, "/evolutions")["items"]
    assert len(items) == 2
    assert next(i for i in items if i["evolution_id"] == "learning")["outcome"] is None
    assert len(get(client, "/evolutions?limit=1")["items"]) == 1
    experiment = read_json(root / "var/demo/experiment.json")
    del experiment["run2"]["n_visitors"]
    write(root / "var/demo/experiment.json", experiment)
    assert get(client, "/runs/running")["progress"]["total"] is None
    write(root / "var/runs/running/summary.json", {"attempted": 5})
    assert get(client, "/runs/running")["progress"]["total"] == 5
    session = read_json(root / "var/runs/running/sessions/A-001.json")
    session.update(visitor_id="A-002", session_id="running/A-002", status="error", error="test", plan=None)
    write(root / "var/runs/running/sessions/A-002.json", session)
    assert get(client, "/runs/running")["progress"] == {"total": 5, "completed": 1, "failed": 1}


def test_evidence_projects_only_classifier_data(client, artifacts):
    root, reports, _, _ = artifacts
    rid = reports[0]["run_id"]
    trace = {"path_probs": [{"round": 1, "turn": 2, "status": "ok",
                              "weights": {"P1": .1, "P2": .6, "P3": .1, "P4": .1, "P5": .1}}],
             "llm_calls": [{"secret": "must-not-be-exposed"}]}
    write(root / "var/runs" / rid / "trace/A-001.json", trace)
    response = get(client, f"/runs/{rid}/evidence")
    assert response["contract"] is False
    assert response["summary"]["n_with_path_probs"] == 1
    assert response["visitors"]["A-001"]["curve"][0]["p_true"] == .6
    assert "must-not-be-exposed" not in json.dumps(response)


@pytest.mark.parametrize("route", [
    "/runs/missing", "/runs/missing/report", "/runs/missing/sessions", "/runs/missing/sessions/A-001",
    "/runs/missing/evidence", "/evolutions/missing", "/evolutions/missing/status",
    "/evolutions/missing/insights", "/playbook/v9999", "/playbook/diff?from=v1&to=v9999",
])
def test_missing_resources(client, route):
    error(client.get(PREFIX + route), 404)


def test_empty_root_does_not_create_artifacts(tmp_path):
    root = tmp_path / "nonexistent"
    with TestClient(create_app(Settings(data_root=root))) as client:
        assert get(client, "/runs") == {"items": []}
        assert get(client, "/evolutions") == {"items": []}
        assert get(client, "/demo/experiment") == {"available": False}
        for route in ("/playbook/versions", "/playbook/v1", "/playbook/diff?from=v1&to=v2"):
            error(client.get(PREFIX + route), 404, "NOT_FOUND")
    assert not root.exists()


@pytest.mark.parametrize("route", [
    "/runs/%2e%2e", "/runs/%2e%2e%2f.env/report", "/runs/a%5cb", "/runs/" + "x" * 81,
    "/runs/running/sessions/%2e%2e", "/runs/running/sessions/" + "x" * 65,
    "/evolutions/%2e%2e/status", "/evolutions/a%2fb", "/evolutions/" + "x" * 81,
    "/playbook/HEAD", "/playbook/v12345", "/playbook/diff?from=--help&to=v2",
    "/playbook/diff?from=v1&to=../.env", "/runs?limit=0", "/evolutions?limit=no",
    "/runs/running/calls.json", "/runs/running/trace/A-001.json", "/.env", "/var/demo/experiment.json",
])
def test_invalid_ids_and_private_paths(client, route):
    response = client.get(PREFIX + route)
    assert response.status_code in {404, 422}, response.text
    error(response, response.status_code)


def test_symlinks_and_unreadable_data_are_not_exposed(client, artifacts):
    root = artifacts[0]
    secret = root / ".env"
    secret.write_text('{"private":"do-not-expose"}')
    path = root / "var/demo/experiment.json"
    path.unlink()
    path.symlink_to(secret)
    response = client.get(PREFIX + "/demo/experiment")
    error(response, 404)
    assert "do-not-expose" not in response.text
    path.unlink()
    for bad in ('{partial', '[]', '{"value":NaN}', '{"value":1e999}', '\xff'):
        path.write_bytes(bad.encode("latin1"))
        error(client.get(PREFIX + "/demo/experiment"), 404, "DATA_UNAVAILABLE")
    path.unlink()
    (root / "var/runs/escape").symlink_to(root, target_is_directory=True)
    error(client.get(PREFIX + "/runs/escape/report"), 404)
    assert "escape" not in [i["run_id"] for i in get(client, "/runs")["items"]]


@pytest.mark.parametrize("relative,route", [
    ("var/runs/run-20261115-01/run_report.json", "/runs/run-20261115-01/report"),
    ("var/runs/run-20261115-01/sessions/A-001.json", "/runs/run-20261115-01/sessions/A-001"),
    ("var/runs/running/summary.json", "/runs/running"),
    ("var/evolve/evolution-20261115-01/evolution.json", "/evolutions/evolution-20261115-01"),
    ("var/evolve/learning/status.json", "/evolutions/learning/status"),
    ("var/evolve/evolution-20261115-01/insights.json", "/evolutions/evolution-20261115-01/insights"),
    ("var/runs/run-20261115-01/trace/A-001.json", "/runs/run-20261115-01/evidence"),
])
def test_corrupt_artifacts_are_safe_404(client, artifacts, relative, route):
    path = artifacts[0] / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"partial":')
    error(client.get(PREFIX + route), 404, "DATA_UNAVAILABLE")


def test_missing_companions_and_malformed_metadata(client, artifacts, monkeypatch):
    root, reports, evo, repo = artifacts
    for name in ("status", "insights"):
        (root / "var/evolve" / evo["evolution_id"] / (name + ".json")).unlink()
        error(client.get(PREFIX + f"/evolutions/{evo['evolution_id']}/{name}"), 404, "NOT_FOUND")
    assert get(client, "/evolutions/" + evo["evolution_id"]) == evo
    manifest = read_json(root / "var/demo/experiment.json")
    manifest["run2"]["split"] = "bad-split"
    write(root / "var/demo/experiment.json", manifest)
    error(client.get(PREFIX + "/runs/running"), 404, "DATA_UNAVAILABLE")
    with monkeypatch.context() as patch:
        patch.setattr(PlaybookRepo, "head", lambda self: (_ for _ in ()).throw(RuntimeError("private git error")))
        response = client.get(PREFIX + "/playbook/versions")
        error(response, 404, "DATA_UNAVAILABLE")
        assert "private git error" not in response.text
    with monkeypatch.context() as patch:
        patch.setattr("api.file_store.read_json", lambda path: (_ for _ in ()).throw(PermissionError("private path")))
        error(client.get(PREFIX + "/demo/experiment"), 404, "DATA_UNAVAILABLE")


def test_files_post_always_returns_cli_instruction(client):
    for kwargs in ({}, {"json": {"split": "A"}}, {"content": "{invalid"}):
        response = client.post(PREFIX + "/runs", **kwargs)
        error(response, 501, "RUNS_VIA_CLI")
        assert "真实运行请在操作员终端执行 make demo-run1 / make demo-run2" in response.text


def test_mock_read_routes_are_examples(tmp_path):
    with TestClient(create_app(Settings(data_source="mock", data_root=tmp_path))) as client:
        assert get(client, "/health")["data_source"] == "mock"
        experiment = get(client, "/demo/experiment")
        assert experiment["stage"] == "done"
        reports = get(client, "/runs")["items"]
        assert len(reports) == 3 and all(i["execution_mode"] == "mock" for i in reports)
        validators = load_validators()
        for item in reports:
            base = "/runs/" + item["run_id"]
            assert get(client, base)["execution_mode"] == "mock"
            assert validate_document(get(client, base + "/report"), "run_report", validators, {}) == []
            assert get(client, base + "/evidence") == {"available": False}
            for session in get(client, base + "/sessions")["items"]:
                if session["session_available"]:
                    assert validate_document(get(client, base + "/sessions/" + session["visitor_id"]),
                                             "session", validators, {}) == []
        eid = get(client, "/evolutions")["items"][0]["evolution_id"]
        evo = get(client, "/evolutions/" + eid)
        assert evo == read_json(EXAMPLES / "evolution.v1-v2.json")
        assert validate_document(evo, "evolution", validators, {}) == []
        assert get(client, f"/evolutions/{eid}/status")["phase"] == "done"
        assert get(client, f"/evolutions/{eid}/insights")["execution_mode"] == "mock"
        assert len(get(client, "/playbook/versions")["items"]) == 2
        assert "Mock" in get(client, "/playbook/v1")["text"]
        assert get(client, "/playbook/diff?from=v1&to=v2")["diff"]
    assert not list(tmp_path.iterdir())


def test_env_and_optional_static_hosting(tmp_path, monkeypatch):
    monkeypatch.delenv("API_EXECUTION_MODE", raising=False)
    monkeypatch.delenv("API_DATA_SOURCE", raising=False)
    monkeypatch.setenv("API_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("API_SERVE_WEB", "1")
    monkeypatch.setattr("api.main.WEB_DIST", tmp_path / "dist")
    assert Settings.from_env().data_source == "files"
    assert Settings.from_env().data_root == tmp_path
    with TestClient(create_app()) as client:
        error(client.get("/"), 404)
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist/index.html").write_text("<h1>Read API</h1>")
    with TestClient(create_app()) as client:
        response = client.get("/")
        assert response.status_code == 200 and "Read API" in response.text
        assert "X-Frame-Options" not in response.headers
        assert get(client, "/health")["data_source"] == "files"
        error(client.get(PREFIX + "/not-an-api"), 404)
    monkeypatch.setenv("API_SERVE_WEB", "0")
    with TestClient(create_app()) as client:
        error(client.get("/"), 404)
