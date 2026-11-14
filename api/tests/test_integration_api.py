"""HTTP lifecycle checks with an explicit offline test double."""
import asyncio
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from api.integration_app import create_integration_app

class TestBackend:
    version = "v0"
    sources = {"test_double": True}
    def __init__(self, *, delay=0.02, outcome="completed"):
        self.delay, self.outcome = delay, outcome
        self.active = self.peak = self.calls = self.reports = 0
    def visitors(self, limit):
        return [{"id": f"sample-{i:03d}", "split": "sample"} for i in range(1, limit + 1)]
    async def run_session(self, visitor, run_id):
        self.active += 1
        self.calls += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(self.delay)
            if self.outcome == "raise":
                raise RuntimeError("test failure")
            return {"visitor_id": visitor["id"], "run_id": run_id, "status": self.outcome}, {}
        finally:
            self.active -= 1
    def validate_session(self, session, visitor):
        if session["status"] == "invalid":
            raise ValueError("invalid fixture")
    def make_report(self, visitors, sessions, run_id, duration_s):
        self.reports += 1
        return {"run_id": run_id, "split": "sample", "n_visitors": len(visitors), "test_double": True}

class IntegrationAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.database = Path(self.temp) / "runs.sqlite3"
    def app(self, backend=None, **kwargs):
        return create_integration_app(backend=backend or TestBackend(), database_path=self.database, **kwargs)
    def create(self, client, limit=1, key="test-key"):
        response = client.post("/api/v1/integration/runs", json={"split": "sample", "limit": limit},
                               headers={"Idempotency-Key": key})
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(response.json()["execution_mode"], "mock")
        self.assertEqual(response.json()["execution_source"], "engine_offline")
        return response.json()["run_id"]
    def wait(self, client, run_id):
        for _ in range(200):
            response = client.get(f"/api/v1/integration/runs/{run_id}")
            self.assertEqual(response.status_code, 200, response.text)
            state = response.json()
            if state["status"] in ("succeeded", "failed"):
                return state
            time.sleep(0.01)
        self.fail("offline task did not finish")
    def test_restart_preserves_results_and_idempotency(self):
        backend = TestBackend()
        with TestClient(self.app(backend)) as client:
            run_id = self.create(client, 3)
            state = self.wait(client, run_id)
            self.assertEqual(state["progress"], {"total": 3, "completed": 3, "failed": 0})
            self.assertTrue(state["report_available"])
            report = client.get(f"/api/v1/integration/runs/{run_id}/report").json()
            items = client.get(f"/api/v1/integration/runs/{run_id}/sessions").json()["items"]
            self.assertEqual(len(items), 3)
            self.assertTrue(all(item["session_available"] for item in items))
            self.assertEqual(client.get("/api/v1/health").json()["execution_mode"], "mock")
        replacement = TestBackend()
        with TestClient(self.app(replacement)) as client:
            self.assertEqual(self.create(client, 3), run_id)
            self.assertEqual(client.get(f"/api/v1/integration/runs/{run_id}/report").json(), report)
            self.assertEqual(replacement.calls, 0)
            conflict = client.post("/api/v1/integration/runs", json={"limit": 2}, headers={"Idempotency-Key": "test-key"})
            self.assertEqual(conflict.status_code, 409)
            self.assertEqual(conflict.json()["error"]["code"], "IDEMPOTENCY_KEY_REUSED")
    def test_global_concurrency_and_capacity(self):
        backend = TestBackend(delay=0.03)
        with TestClient(self.app(backend, concurrency=2, max_runs=2)) as client:
            first = self.create(client, 5, "first")
            second = self.create(client, 5, "second")
            response = client.post("/api/v1/integration/runs", json={}, headers={"Idempotency-Key": "third"})
            self.assertEqual(response.status_code, 429)
            for run_id in (first, second):
                self.assertEqual(self.wait(client, run_id)["status"], "succeeded")
            self.assertLessEqual(backend.peak, 2)
            self.assertEqual(backend.calls, 10)

    def test_pending_idempotency_does_not_start_duplicate_work(self):
        backend = TestBackend(delay=0.1)
        with TestClient(self.app(backend)) as client:
            run_id = self.create(client, 2)
            self.assertEqual(self.create(client, 2), run_id)
            conflict = client.post("/api/v1/integration/runs", json={"limit": 1},
                                   headers={"Idempotency-Key": "test-key"})
            self.assertEqual(conflict.status_code, 409)
            self.assertEqual(self.wait(client, run_id)["status"], "succeeded")
            self.assertEqual(backend.calls, 2)

    def test_mismatched_run_cannot_be_counted_as_completed(self):
        class WrongRunBackend(TestBackend):
            async def run_session(self, visitor, run_id):
                session, trace = await super().run_session(visitor, run_id)
                session["run_id"] = "another-run"
                return session, trace

        with TestClient(self.app(WrongRunBackend())) as client:
            run_id = self.create(client)
            state = self.wait(client, run_id)
            self.assertEqual(state["status"], "failed")
            self.assertEqual(state["progress"], {"total": 1, "completed": 0, "failed": 1})
            item = client.get(f"/api/v1/integration/runs/{run_id}/sessions").json()["items"][0]
            self.assertEqual(item["status"], "failed")
            self.assertFalse(item["session_available"])

    def test_session_save_failure_does_not_leave_successful_progress(self):
        app = self.app()
        with TestClient(app) as client:
            with patch.object(app.state.integration.store, "save_session", side_effect=OSError("save failed")):
                run_id = self.create(client)
                state = self.wait(client, run_id)
            self.assertEqual(state["error"]["code"], "INTEGRATION_ERROR")
            self.assertEqual(state["progress"], {"total": 1, "completed": 0, "failed": 1})
            item = client.get(f"/api/v1/integration/runs/{run_id}/sessions").json()["items"][0]
            self.assertEqual(item["status"], "failed")
            self.assertFalse(item["session_available"])
    def test_error_invalid_and_timeout_do_not_generate_scores(self):
        for outcome, delay, timeout in (("error", 0.01, 1), ("invalid", 0.01, 1), ("raise", 0.01, 1), ("completed", 0.2, 0.01)):
            with self.subTest(outcome=outcome):
                backend = TestBackend(outcome=outcome, delay=delay)
                with TestClient(self.app(backend, timeout_s=timeout)) as client:
                    run_id = self.create(client, key=outcome)
                    state = self.wait(client, run_id)
                    self.assertEqual(state["status"], "failed")
                    self.assertEqual(state["progress"]["failed"], 1)
                    self.assertEqual(state["progress"]["completed"], 0)
                    self.assertFalse(state["report_available"])
                    self.assertEqual(backend.reports, 0)
                    self.assertEqual(client.get(f"/api/v1/integration/runs/{run_id}/report").status_code, 409)
                    item = client.get(f"/api/v1/integration/runs/{run_id}/sessions").json()["items"][0]
                    self.assertFalse(item["session_available"])
                    self.assertIsNone(item["session_status"])
    def test_crisis_exit_is_not_infrastructure_failure(self):
        with TestClient(self.app(TestBackend(outcome="crisis_exit"))) as client:
            run_id = self.create(client)
            self.assertEqual(self.wait(client, run_id)["status"], "succeeded")
            item = client.get(f"/api/v1/integration/runs/{run_id}/sessions").json()["items"][0]
            self.assertEqual(item["session_status"], "crisis_exit")
    def test_shutdown_marks_pending_run_and_does_not_restart(self):
        with TestClient(self.app(TestBackend(delay=10))) as client:
            run_id = self.create(client, 2)
        replacement = TestBackend()
        with TestClient(self.app(replacement)) as client:
            state = self.wait(client, run_id)
            self.assertEqual(state["status"], "failed")
            self.assertEqual(state["error"]["code"], "RUN_INTERRUPTED")
            self.assertEqual(self.create(client, 2), run_id)
            self.assertEqual(replacement.calls, 0)
    def test_invalid_requests_and_unknown_resources_use_error_envelope(self):
        with TestClient(self.app()) as client:
            for body in ({"split": "A"}, {"limit": 0}, {"limit": 19}, {"limit": True}, {"playbook_version": "v1"}, {"unexpected": 1}):
                response = client.post("/api/v1/integration/runs", json=body, headers={"Idempotency-Key": "bad"})
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["error"]["request_id"], response.headers["X-Request-ID"])
            response = client.get("/api/v1/integration/runs/missing")
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["error"]["code"], "RUN_NOT_FOUND")

if __name__ == "__main__":
    unittest.main()
