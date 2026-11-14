"""只读契约示例，不生成分数、不调用模型、不修改 contracts/。"""

from copy import deepcopy
import json
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[1] / "contracts" / "examples"


class FixtureCatalog:
    current_version = "v1"

    def __init__(self):
        self._reports = {}
        for name in ("run1", "run2", "control"):
            report = json.loads((EXAMPLES / f"run_report.{name}.json").read_text(encoding="utf-8"))
            if report["schema_version"] != "0.1.0":
                raise ValueError("Mock 需要 contracts v0.1.0 示例，请先核对契约升级。")
            ids = [row["visitor_id"] for row in report["per_visitor"]]
            if not ids or len(ids) != len(set(ids)) or len(ids) != report["n_visitors"]:
                raise ValueError("报告示例的来访数量或标识不一致。")
            self._reports[(report["split"], report["playbook_version"])] = report
        self._sessions = {}
        for path in sorted(EXAMPLES.glob("session.*.json")):
            session = json.loads(path.read_text(encoding="utf-8"))
            key = (session["run_id"], session["visitor_id"], session["playbook_version"])
            self._sessions[key] = session

    def snapshot(self, split: str, version: str) -> tuple[dict, dict[str, dict]]:
        report = deepcopy(self._reports[(split, version)])
        sessions = {}
        for row in report["per_visitor"]:
            key = (report["run_id"], row["visitor_id"], version)
            if key in self._sessions:
                sessions[row["visitor_id"]] = deepcopy(self._sessions[key])
        return report, sessions
