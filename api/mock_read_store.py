"""In-memory read examples derived exclusively from contracts/examples/."""

from copy import deepcopy
from pathlib import Path

from api.errors import APIError
from api.file_store import FileStore, identifier, VERSION_PATTERN
from contracts.validate import read_json

EXAMPLES = Path(__file__).resolve().parents[1] / "contracts/examples"


class MockReadStore(FileStore):
    """Reuse the read projections with a virtual artifact tree; never create var/."""

    def __init__(self):
        super().__init__(EXAMPLES)
        self.documents = {}
        self.run_ids = []
        plans = {}
        for role in ("run1", "run2", "control"):
            report = read_json(EXAMPLES / f"run_report.{role}.json")
            rid = report["run_id"]
            self.run_ids.append(rid)
            self.documents[f"var/runs/{rid}/run_report.json"] = report
            plans[role] = {k: report[k] for k in ("run_id", "playbook_version", "split", "n_visitors")}
            plans[role]["state"] = "done"
        for path in EXAMPLES.glob("session.*.json"):
            session = read_json(path)
            self.documents[f"var/runs/{session['run_id']}/sessions/{session['visitor_id']}.json"] = session
        evo = read_json(EXAMPLES / "evolution.v1-v2.json")
        self.eid = evo["evolution_id"]
        prefix = f"var/evolve/{self.eid}"
        self.documents[prefix + "/evolution.json"] = evo
        self.documents[prefix + "/status.json"] = {
            "schema": "evolve-status/1", "evolution_id": self.eid, "updated_at": evo["created_at"],
            "from_version": evo["from_version"], "phase": "done",
            "reflector": {"state": "done", **{k: evo["reflector"][k] for k in ("model", "fell_back")}},
            "validation": {"baseline": "done", "candidates": {
                c["id"]: "done" if c["val_metrics"] is not None else "blocked" for c in evo["candidates"]}},
            "review": {"state": "done", "deadline": None, "pending_changes": 0},
            **{k: evo[k] for k in ("outcome", "to_version", "chosen")}, "error": None,
        }
        self.documents[prefix + "/insights.json"] = {
            "contract": False, "execution_mode": "mock", "failures_used": evo["failures_used"],
            "candidates": [{"id": c["id"], "summary": c["summary"]} for c in evo["candidates"]],
        }
        self.documents["var/demo/experiment.json"] = {
            "experiment_id": "exp-mock", "updated_at": evo["created_at"], "stage": "done", **plans,
            "evolution": {"evolution_id": self.eid, "state": "done"}, "error": None,
        }

    def _json(self, *parts, optional=False, schema=None):
        key = "/".join(parts)
        if key in self.documents:
            return deepcopy(self.documents[key])
        if optional:
            return None
        raise APIError(404, "NOT_FOUND", "示例产物不存在。")

    def _directories(self, area):
        return self.run_ids if area == "runs" else [self.eid]

    def _session_docs(self, run_id):
        prefix = f"var/runs/{run_id}/sessions/"
        return {d["visitor_id"]: deepcopy(d) for key, d in self.documents.items() if key.startswith(prefix)}

    def run_item(self, run_id):
        return {**super().run_item(run_id), "execution_mode": "mock"}

    def state(self, run_id):
        return {**super().state(run_id), "execution_mode": "mock"}

    def versions(self):
        evo = self.evolution(self.eid)
        return {"items": [
            {"version": version, "sha": evo["commit"]["sha"] if version == "v2" else None,
             "author": evo["commit"]["author"] if version == "v2" else "deepsleep-team",
             "message": evo["commit"]["message"] if version == "v2" else "初始版本（示例片段）",
             "committed_at": evo["created_at"], "is_head": version == "v2"}
            for version in ("v1", "v2")]}

    def playbook(self, version):
        identifier(version, VERSION_PATTERN)
        if version not in {"v1", "v2"}:
            raise APIError(404, "NOT_FOUND", "示例版本不存在。")
        # The example contains only a diff, not the entire team's playbook.
        lines = self.evolution(self.eid)["diff"].splitlines()
        prefixes = {" ", "-" if version == "v1" else "+"}
        text = "\n".join(line[1:] for line in lines
                         if line[:1] in prefixes and not line.startswith(("---", "+++")))
        return {"version": version, "text": "# Mock：契约 diff 中的 playbook 片段\n" + text + "\n"}
