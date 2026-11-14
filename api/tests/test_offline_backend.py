"""Opt-in actual engine checks; prepare the pinned snapshot before running."""
import asyncio
from copy import deepcopy
import os
from pathlib import Path
import socket
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from api.integration_app import create_integration_app
from api.integration_backend import OfflineEngineBackend, ContractViolation

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "var/integration-deps"


@unittest.skipUnless((SNAPSHOT / "snapshot.json").exists(), "Run python -m api.prepare_integration first")
class OfflineBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backend = OfflineEngineBackend(SNAPSHOT)

    def test_actual_engine_scoring_one_ten_eighteen_without_network(self):
        async def exercise():
            # Patch after asyncio creates its Windows socketpair, and assert calls even if caught upstream.
            with patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")) as connect, \
                    patch.object(socket, "getaddrinfo", side_effect=AssertionError("DNS forbidden")) as dns, \
                    patch.dict(os.environ, {"DS_API_KEY": "test-not-a-key", "JUDGE_PROVIDER": "ds_flash"}):
                visitors = self.backend.visitors(18)
                results = await asyncio.gather(*(self.backend.run_session(v, "offline-check") for v in visitors))
                sessions = [s for s, _ in results]
                for visitor, (session, trace) in zip(visitors, results):
                    self.backend.validate_session(session, visitor)
                    self.assertIn(session["status"], ("completed", "crisis_exit"), session["error"])
                    self.assertEqual(session["models"], {"agent": "mock-agent", "visitor": "mock"})
                    self.assertTrue(trace["integration"]["visitor_events"])
                    if session["status"] == "completed":
                        self.assertEqual(len(session["rounds"]), 2)
                        self.assertIn("isi_week", trace["round1_outcome"])
                for limit in (1, 10, 18):
                    report = self.backend.make_report(visitors[:limit], sessions[:limit], "offline-check", 1.0)
                    self.assertEqual(report["n_visitors"], limit)
                    self.assertEqual(report["split"], "sample")
                    self.assertEqual(report["models"]["judge"], "mock")
                    self.assertTrue(all(row["session_ref"].startswith("/api/v1/integration/runs/")
                                        for row in report["per_visitor"]))
                    if limit >= 10:
                        # Latest main force-screens mood and records PHQ-9 item 9.
                        # This is an offline MockJudge result, not real-model safety approval.
                        self.assertEqual(report["metrics"]["crisis_missed"], 0)
                        self.assertEqual(report["metrics"]["crisis_recall"], 1.0)
                        self.assertTrue(report["veto"]["passed"])
                connect.assert_not_called()
                dns.assert_not_called()
        asyncio.run(exercise())

    def test_same_visitor_has_independent_state_across_concurrent_runs(self):
        async def exercise():
            visitor = self.backend.visitors(18)[15]
            first, second = await asyncio.gather(self.backend.run_session(visitor, "first"),
                                                  self.backend.run_session(visitor, "second"))
            for key in ("rounds", "plan", "behaviors", "tool_calls"):
                self.assertEqual(first[0][key], second[0][key])
            self.assertEqual(first[1]["integration"]["visitor_events"],
                             second[1]["integration"]["visitor_events"])
            self.assertNotEqual(first[0]["run_id"], second[0]["run_id"])
            self.assertNotEqual(first[0]["session_id"], second[0]["session_id"])
        asyncio.run(exercise())

    def test_invalid_contract_and_missing_or_failed_sessions_cannot_be_scored(self):
        visitor = self.backend.visitors(1)[0]
        session, _ = asyncio.run(self.backend.run_session(visitor, "validation"))
        with self.assertRaises(ValueError):
            self.backend.make_report([visitor], [], "validation", 1)
        failed = deepcopy(session)
        failed.update(status="error", error="test", plan=None)
        with self.assertRaises(ValueError):
            self.backend.make_report([visitor], [failed], "validation", 1)
        invalid = deepcopy(session)
        invalid["rounds"][0]["path_pred"] = "INVALID"
        with self.assertRaises(ContractViolation):
            self.backend.validate_session(invalid, visitor)
        with self.assertRaises(ValueError):
            self.backend.make_report([visitor], [session], "another-run", 1)

    def test_actual_engine_http_results_survive_app_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "runs.sqlite3"
            with TestClient(create_integration_app(backend=self.backend, database_path=database)) as client:
                response = client.post("/api/v1/integration/runs", json={"limit": 10},
                                       headers={"Idempotency-Key": "engine-http"})
                self.assertEqual(response.status_code, 202, response.text)
                run_id = response.json()["run_id"]
                base = f"/api/v1/integration/runs/{run_id}"
                for _ in range(300):
                    state = client.get(base).json()
                    if state["status"] in ("succeeded", "failed"):
                        break
                    time.sleep(0.01)
                self.assertEqual(state["status"], "succeeded", state)
                self.assertEqual(state["progress"], {"total": 10, "completed": 10, "failed": 0})
                report = client.get(base + "/report").json()
                self.assertTrue(report["veto"]["passed"])
                items = client.get(base + "/sessions").json()["items"]
                self.assertEqual(len(items), 10)
                for item in items:
                    session = client.get(base + "/sessions/" + item["visitor_id"])
                    self.assertEqual(session.status_code, 200)
                    self.assertEqual(session.json()["run_id"], run_id)
            with TestClient(create_integration_app(backend=self.backend, database_path=database)) as client:
                self.assertEqual(client.get(base + "/report").json(), report)
                repeated = client.post("/api/v1/integration/runs", json={"limit": 10},
                                       headers={"Idempotency-Key": "engine-http"})
                self.assertEqual(repeated.json()["run_id"], run_id)


if __name__ == "__main__":
    unittest.main()
