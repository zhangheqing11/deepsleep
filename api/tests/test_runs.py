"""验证前端约定、真实后台推进、幂等竞争和契约示例的一致性。"""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import time
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from api.config import Settings
from api.main import create_app
from contracts.validate import load_validators, validate_document

EXAMPLES = Path(__file__).resolve().parents[2] / "contracts" / "examples"


class RunAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validators = load_validators()
        cls.visitors = {}
        for path in EXAMPLES.glob("visitor.*.json"):
            visitor = json.loads(path.read_text(encoding="utf-8"))
            cls.visitors[visitor["id"]] = visitor

    def setUp(self):
        self.app = create_app(Settings(mock_step_delay_s=0.03, mock_report_delay_s=0.3))
        self.client = self.enterContext(TestClient(self.app))

    def create(self, body=None, key=None, scenario="normal"):
        response = self.client.post(
            "/api/v1/runs", json={"split": "A"} if body is None else body,
            headers={"Idempotency-Key": key or str(uuid4()), "X-Mock-Scenario": scenario},
        )
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(set(response.json()), {"run_id", "status", "execution_mode"})
        self.assertEqual(response.json()["status"], "queued")
        self.assertEqual(response.json()["execution_mode"], "mock")
        self.assertNotIn("/", response.json()["run_id"])
        return response.json()["run_id"]

    def wait_for(self, run_id, predicate):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            response = self.client.get(f"/api/v1/runs/{run_id}")
            self.assertEqual(response.status_code, 200, response.text)
            state = response.json()
            if predicate(state):
                return state
            time.sleep(0.01)
        self.fail(f"任务未按预期结束: {state}")

    def assert_error(self, response, status, code):
        self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(set(response.json()), {"error"})
        error = response.json()["error"]
        self.assertEqual(set(error), {"code", "message", "request_id"})
        self.assertEqual(error["code"], code)
        self.assertEqual(error["request_id"], response.headers["X-Request-ID"])
        self.assertTrue(error["message"])

    def test_reports_match_contract_examples_and_do_not_mutate_templates(self):
        for body, fixture in [
            ({"split": "A"}, "run_report.run1.json"),
            ({"split": "B"}, "run_report.control.json"),
            ({"split": "B", "playbook_version": "v2"}, "run_report.run2.json"),
        ]:
            with self.subTest(body=body):
                source = EXAMPLES / fixture
                original = source.read_bytes()
                expected = json.loads(original)
                run_id = self.create(body)
                state = self.wait_for(run_id, lambda s: s["status"] == "succeeded")
                self.assertTrue(state["report_available"])
                self.assertEqual(state["progress"], {"total": 8, "completed": 8, "failed": 0})
                self.assertIsNone(state["error"])
                self.assertEqual(state["playbook_version"], expected["playbook_version"])
                report = self.client.get(f"/api/v1/runs/{run_id}/report")
                self.assertEqual(report.status_code, 200)
                expected["run_id"] = run_id
                self.assertEqual(report.json(), expected)
                self.assertEqual(validate_document(report.json(), "run_report", self.validators, self.visitors), [])
                self.assertEqual(source.read_bytes(), original)
                # GET 得到的数据被调用方改变，也不能污染服务中的快照。
                changed = report.json()
                changed["metrics"]["isi_response_rate"] = -1
                self.assertEqual(self.client.get(f"/api/v1/runs/{run_id}/report").json(), expected)
                next_run = self.create(body)
                self.assertNotEqual(run_id, next_run)
                self.assertEqual(self.app.state.runs._runs[next_run].template["metrics"], expected["metrics"])

    def test_idempotency_reuses_task_before_and_after_completion(self):
        key = str(uuid4())
        body = {"split": "A", "playbook_version": "v1"}
        run_id = self.create(body, key)
        reordered = {"playbook_version": "v1", "split": "A"}
        self.assertEqual(self.create(reordered, key), run_id)
        state = self.wait_for(run_id, lambda s: s["status"] == "succeeded")
        self.assertEqual(self.create(body, key), run_id)
        self.assertEqual(self.client.get(f"/api/v1/runs/{run_id}").json(), state)
        self.assertEqual(len(self.app.state.runs._runs), 1)

    def test_concurrent_same_key_creates_exactly_one_task(self):
        key = str(uuid4())
        def post(_):
            return self.client.post(
                "/api/v1/runs", json={"split": "A"}, headers={"Idempotency-Key": key}
            )
        with ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(post, range(16)))
        self.assertTrue(all(response.status_code == 202 for response in responses))
        self.assertEqual(len({response.json()["run_id"] for response in responses}), 1)
        self.assertEqual(len(self.app.state.runs._runs), 1)

    def test_key_reuse_with_different_body_or_scenario_is_conflict(self):
        key = str(uuid4())
        self.create(key=key)
        for body, scenario in [
            ({"split": "B"}, "normal"),
            ({"split": "A", "playbook_version": "v1"}, "normal"),
            ({"split": "A"}, "fail"),
        ]:
            with self.subTest(body=body, scenario=scenario):
                response = self.client.post(
                    "/api/v1/runs", json=body,
                    headers={"Idempotency-Key": key, "X-Mock-Scenario": scenario},
                )
                self.assert_error(response, 409, "IDEMPOTENCY_KEY_REUSED")

    def test_omitted_and_null_version_are_equivalent(self):
        key = str(uuid4())
        run_id = self.create(key=key)
        self.assertEqual(self.create({"split": "A", "playbook_version": None}, key), run_id)

    def test_invalid_inputs_return_uniform_422_without_creating_tasks(self):
        for body in [
            {}, {"split": "C"}, {"split": "a"}, {"split": 1},
            {"split": "A", "unknown": True}, {"split": "A", "playbook_version": 1},
            {"split": "A", "playbook_version": "v2"},
            {"split": "A", "playbook_version": ""},
        ]:
            with self.subTest(body=body):
                response = self.client.post(
                    "/api/v1/runs", json=body, headers={"Idempotency-Key": str(uuid4())}
                )
                self.assert_error(response, 422, "VALIDATION_ERROR")
        for headers in [
            {}, {"Idempotency-Key": ""}, {"Idempotency-Key": "a b"},
            {"Idempotency-Key": "a" * 129},
            {"Idempotency-Key": str(uuid4()), "X-Mock-Scenario": "unknown"},
        ]:
            with self.subTest(headers=headers):
                response = self.client.post("/api/v1/runs", json={"split": "A"}, headers=headers)
                self.assert_error(response, 422, "VALIDATION_ERROR")
        response = self.client.post(
            "/api/v1/runs", content="{invalid-json",
            headers={"Content-Type": "application/json", "Idempotency-Key": str(uuid4())},
        )
        self.assert_error(response, 422, "VALIDATION_ERROR")
        self.assertEqual(len(self.app.state.runs._runs), 0)

    def test_unknown_run_returns_404_for_all_resources(self):
        for suffix in ("", "/report", "/sessions", "/sessions/A-001"):
            with self.subTest(suffix=suffix):
                response = self.client.get(f"/api/v1/runs/missing{suffix}")
                self.assert_error(response, 404, "RUN_NOT_FOUND")

    def test_progress_is_monotonic_and_completion_time_is_stable(self):
        run_id = self.create()
        self.assert_error(self.client.get(f"/api/v1/runs/{run_id}/report"), 409, "REPORT_NOT_READY")
        last_completed, last_elapsed = 0, 0
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = self.client.get(f"/api/v1/runs/{run_id}").json()
            progress = state["progress"]
            self.assertGreaterEqual(progress["completed"], last_completed)
            self.assertGreaterEqual(state["elapsed_ms"], last_elapsed)
            self.assertLessEqual(progress["completed"] + progress["failed"], progress["total"])
            last_completed, last_elapsed = progress["completed"], state["elapsed_ms"]
            if state["status"] == "succeeded":
                self.assertTrue(state["report_available"])
                break
            time.sleep(0.01)
        else:
            self.fail("Mock 运行没有结束")
        time.sleep(0.05)
        self.assertEqual(self.client.get(f"/api/v1/runs/{run_id}").json()["elapsed_ms"], last_elapsed)

    def test_background_work_completes_without_polling(self):
        run_id = self.create()
        time.sleep(0.6)
        state = self.client.get(f"/api/v1/runs/{run_id}").json()
        self.assertEqual(state["status"], "succeeded")
        self.assertTrue(state["report_available"])

    def test_failure_has_error_and_no_success_report(self):
        run_id = self.create(scenario="fail")
        state = self.wait_for(run_id, lambda s: s["status"] == "failed")
        self.assertEqual(state["error"]["code"], "MOCK_RUN_FAILED")
        self.assertEqual(state["progress"], {"total": 8, "completed": 0, "failed": 8})
        self.assertFalse(state["report_available"])
        self.assert_error(self.client.get(f"/api/v1/runs/{run_id}/report"), 409, "REPORT_NOT_READY")

    def test_report_delay_finishes_then_makes_report_available(self):
        run_id = self.create(scenario="report_delay")
        state = self.wait_for(run_id, lambda s: s["status"] == "succeeded")
        self.assertFalse(state["report_available"])
        self.assertIsNone(state["error"])
        self.assert_error(self.client.get(f"/api/v1/runs/{run_id}/report"), 409, "REPORT_NOT_READY")
        ready = self.wait_for(run_id, lambda s: s["report_available"])
        self.assertEqual(ready["status"], "succeeded")
        self.assertEqual(ready["elapsed_ms"], state["elapsed_ms"])
        self.assertEqual(self.client.get(f"/api/v1/runs/{run_id}/report").status_code, 200)

    def test_sessions_preserve_contract_and_missing_records_are_honest(self):
        run_id = self.create()
        self.wait_for(run_id, lambda s: s["status"] == "succeeded")
        items = self.client.get(f"/api/v1/runs/{run_id}/sessions").json()["items"]
        self.assertEqual([item["visitor_id"] for item in items], [f"A-{i:03d}" for i in range(1, 9)])
        self.assertEqual(sum(item["session_available"] for item in items), 3)
        for item in items:
            self.assertEqual(item["status"], "succeeded")
            self.assertEqual(item["session_status"], "completed" if item["session_available"] else None)
            response = self.client.get(f"/api/v1/runs/{run_id}/sessions/{item['visitor_id']}")
            if not item["session_available"]:
                self.assert_error(response, 404, "SESSION_NOT_FOUND")
                continue
            original = json.loads((EXAMPLES / f"session.{item['visitor_id']}.json").read_text(encoding="utf-8"))
            expected = deepcopy(original)
            expected["run_id"] = run_id
            expected["session_id"] = f"{run_id}/{item['visitor_id']}"
            self.assertEqual(response.json(), expected)
            self.assertEqual(validate_document(response.json(), "session", self.validators, self.visitors), [])
        b_id = self.create({"split": "B", "playbook_version": "v2"})
        self.wait_for(b_id, lambda s: s["status"] == "succeeded")
        b_items = self.client.get(f"/api/v1/runs/{b_id}/sessions").json()["items"]
        self.assertEqual(len(b_items), 8)
        self.assertTrue(all(not item["session_available"] and item["session_status"] is None for item in b_items))
        self.assert_error(self.client.get(f"/api/v1/runs/{b_id}/sessions/B-001"), 404, "SESSION_NOT_FOUND")

    def test_shutdown_cancels_pending_tasks(self):
        app = create_app(Settings(mock_step_delay_s=0.5))
        with TestClient(app) as client:
            response = client.post("/api/v1/runs", json={"split": "A"}, headers={"Idempotency-Key": str(uuid4())})
            run_id = response.json()["run_id"]
        self.assertEqual(app.state.runs.state(run_id).status, "failed")
        self.assertEqual(app.state.runs.state(run_id).error.code, "RUN_INTERRUPTED")
        self.assertFalse(app.state.runs._tasks)


if __name__ == "__main__":
    unittest.main()
