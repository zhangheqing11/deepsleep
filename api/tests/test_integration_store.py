"""Crash windows and isolation for the local integration store."""
from copy import deepcopy
from pathlib import Path
import tempfile
from time import time
import unittest

from api.integration_store import IntegrationStore, IdempotencyConflict


def state(run_id):
    return {"run_id": run_id, "status": "running", "created_at": time(),
            "finished_at": None, "report_available": False, "error": None,
            "visitor_status": {"sample-001": "running", "sample-002": "queued"},
            "progress": {"total": 2, "completed": 0, "failed": 0}}


class IntegrationStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(self.temp) / "runs.sqlite3"
        self.store = IntegrationStore(self.path)
        self.addCleanup(lambda: self.store.close())
        self.store.create("one", "request-one", state("one"), [])

    def test_crash_between_legacy_session_and_state_commits_preserves_completion(self):
        self.store.save_session("one", "sample-001",
            {"run_id": "one", "visitor_id": "sample-001", "status": "completed"}, {})
        self.store.close()
        self.store = IntegrationStore(self.path)
        self.assertEqual(self.store.recover_interrupted(), 1)
        recovered = self.store.state("one")
        self.assertEqual(recovered["progress"], {"total": 2, "completed": 1, "failed": 1})
        self.assertEqual(recovered["error"]["code"], "RUN_INTERRUPTED")
        self.assertFalse(recovered["report_available"])
        self.assertEqual(self.store.session("one", "sample-001")["status"], "completed")
        self.assertEqual(self.store.recover_interrupted(), 0)
        reused, created = self.store.create("one", "request-one", state("unused"), [])
        self.assertFalse(created)
        self.assertEqual(reused["run_id"], "one")
        with self.assertRaises(IdempotencyConflict):
            self.store.create("one", "changed-request", state("unused"), [])

    def test_completed_report_is_preserved_and_unconfirmed_report_is_cleared(self):
        done = state("done")
        done.update(status="succeeded", report_available=True)
        self.store.create("done", "done", done, [])
        self.store.save_report("done", {"run_id": "done"}, state=done)
        self.store.save_report("one", {"run_id": "one"})
        self.assertEqual(self.store.recover_interrupted(), 1)
        self.assertEqual(self.store.state("done")["status"], "succeeded")
        self.assertEqual(self.store.report("done"), {"run_id": "done"})
        self.assertIsNone(self.store.report("one"))

    def test_wrong_run_and_visitor_cannot_overwrite_other_records(self):
        self.store.create("two", "two", state("two"), [])
        session = {"run_id": "one", "visitor_id": "sample-001", "status": "completed"}
        self.store.save_session("one", "sample-001", session, {})
        with self.assertRaises(ValueError):
            self.store.save_session("two", "sample-001", session, {})
        with self.assertRaises(KeyError):
            self.store.save_session("one", "../invalid", None, {})
        with self.assertRaises(ValueError):
            self.store.save_report("two", {"run_id": "one"})
        with self.assertRaises(KeyError):
            self.store.session("two", "sample-001")
        self.assertEqual(self.store.session("one", "sample-001"), session)

    def test_result_and_state_writes_roll_back_together(self):
        invalid = deepcopy(self.store.state("one"))
        invalid["invalid_number"] = float("nan")
        session = {"run_id": "one", "visitor_id": "sample-001", "status": "completed"}
        with self.assertRaises(ValueError):
            self.store.save_session("one", "sample-001", session, {}, state=invalid)
        with self.assertRaises(KeyError):
            self.store.session("one", "sample-001")
        with self.assertRaises(ValueError):
            self.store.save_report("one", {"run_id": "one"}, state=invalid)
        self.assertIsNone(self.store.report("one"))
        self.assertNotIn("invalid_number", self.store.state("one"))


if __name__ == "__main__":
    unittest.main()
