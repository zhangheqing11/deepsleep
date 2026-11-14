"""Actual upstream engine and scoring with explicitly offline model adapters."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys

from contracts.validate import load_validators, validate_document
from api.prepare_integration import verify_snapshot

PACKAGES = ("engine", "sim", "scoring", "safety", "domain")


class ContractViolation(ValueError):
    def __init__(self, kind, errors):
        self.kind, self.errors = kind, list(errors)
        super().__init__(f"{kind}: " + "; ".join(self.errors))


class _VisitorAdapter:
    model_name = "mock"

    def __init__(self, visitor, simulator_type, reply_type):
        self.simulator = simulator_type(visitor, client=None)
        self.reply_type = reply_type
        self.events = []

    async def reply(self, visitor, round, transcript, memory):
        if not transcript:
            reply = self.simulator.opening()
        else:
            last = max((i for i, t in enumerate(transcript) if t["speaker"] == "visitor"), default=-1)
            text = chr(10).join(t["text"] for t in transcript[last + 1:]
                                if t["speaker"] in ("agent", "safety"))
            reply = await self.simulator.respond(text)
        self.events.append({"round": round, "renderer": reply.renderer,
                            "denied_clue_ids": reply.denied_clue_ids,
                            "revealed_clue_ids": reply.revealed_clue_ids,
                            "fallback_reason": reply.fallback_reason})
        return self.reply_type(text=reply.text, revealed_clue_ids=reply.revealed_clue_ids,
                               asked_topics=reply.asked_topics)


class _ScreeningAdapter:
    def __init__(self, run_tool):
        self.run_tool = run_tool

    def screen(self, visitor, tool):
        return self.run_tool(tool, visitor)


class _OutcomeAdapter:
    def __init__(self, simulate):
        self.simulate_state = simulate

    def simulate(self, visitor, plan, context):
        session = deepcopy(context["session"])
        session["plan"] = deepcopy(plan)
        state = self.simulate_state(visitor, session)
        result = state.to_dict()
        change = state.isi_week[4] - state.isi_week[0]
        result.update(isi_change=change, responder=change < -7)
        return result


class OfflineEngineBackend:
    version = "v0"

    def __init__(self, snapshot_root: Path):
        self.root = Path(snapshot_root).resolve()
        metadata = verify_snapshot(self.root)
        self.sources = deepcopy(metadata["sources"])
        self._check_origins()
        # Dedicated process: all upstream imports must resolve to one pinned tree.
        if str(self.root) not in sys.path:
            sys.path.insert(0, str(self.root))
        self.modules = {name: importlib.import_module(name) for name in (
            "engine.run", "engine.session", "engine.interfaces", "engine.mock_agent",
            "engine.classifier", "safety.layer", "safety.judges", "sim.visitor_sim",
            "sim.screening", "sim.state_model", "scoring.score")}
        self._check_origins()
        self.validators = load_validators()
        self._visitors = []
        for path in sorted((self.root / "sim/visitors").glob("sample-*.json")):
            visitor = json.loads(path.read_text(encoding="utf-8"))
            self._validate(visitor, "visitor", {visitor["id"]: visitor})
            if visitor["split"] != "sample" or visitor["id"] != path.stem:
                raise ValueError("Offline integration accepts unchanged sample visitors only.")
            self._visitors.append(visitor)
        if not self._visitors or len({v["id"] for v in self._visitors}) != len(self._visitors):
            raise ValueError("Pinned sample visitors are missing or duplicated.")

    def _check_origins(self):
        for name, module in list(sys.modules.items()):
            if name.split(".")[0] not in PACKAGES or module is None:
                continue
            locations = list(getattr(module, "__path__", []))
            filename = getattr(module, "__file__", None)
            if filename:
                locations.append(filename)
            if not locations or any(not Path(p).resolve().is_relative_to(self.root) for p in locations):
                raise RuntimeError(f"{name} was loaded outside the pinned snapshot; start a fresh process.")

    def _validate(self, document, kind, visitors):
        errors = validate_document(document, kind, self.validators, visitors)
        if errors:
            raise ContractViolation(kind, errors)

    def visitors(self, limit):
        if type(limit) is not int or not 1 <= limit <= min(18, len(self._visitors)):
            raise ValueError("Visitor limit is outside the pinned sample dataset.")
        return deepcopy(self._visitors[:limit])

    async def run_session(self, visitor, run_id):
        m = self.modules
        sim = _VisitorAdapter(visitor, m["sim.visitor_sim"].SimVisitor, m["engine.interfaces"].VisitorReply)
        # Explicit instances prevent environment credentials from enabling model requests.
        judge = m["safety.judges"].MockJudge()
        deps = m["engine.run"].build_deps(
            llm=m["engine.mock_agent"].MockAgentLLM(),
            classifier=m["engine.classifier"].MockPathClassifier(),
            sim=sim, screening=_ScreeningAdapter(m["sim.screening"].run_tool),
            outcome=_OutcomeAdapter(m["sim.state_model"].simulate),
            safety=m["safety.layer"].SafetyLayer(judge=judge),
            playbook_version=self.version)
        session, trace = await m["engine.session"].SessionRunner(deps, visitor, run_id).run()
        trace["integration"] = {"execution_mode": "mock", "sources": self.sources,
            "visitor_events": sim.events,
            "limitations": ["sample data and placeholder scoring parameters",
                            "S2 visitor does not consume round1_outcome"]}
        return session, trace

    def validate_session(self, session, visitor):
        if session.get("visitor_id") != visitor["id"]:
            raise ContractViolation("session", ["visitor_id does not match the requested visitor"])
        self._validate(session, "session", {visitor["id"]: visitor})

    def make_report(self, visitors, sessions, run_id, duration_s):
        by_id = {v["id"]: v for v in visitors}
        if (len(sessions) != len(visitors) or len(by_id) != len(visitors)
                or {s["visitor_id"] for s in sessions} != set(by_id)):
            raise ValueError("Cannot score missing or duplicate sessions.")
        for session in sessions:
            self.validate_session(session, by_id[session["visitor_id"]])
            if session["run_id"] != run_id or session["status"] not in ("completed", "crisis_exit"):
                raise ValueError("Failed or mismatched sessions cannot be scored as completed work.")
        report = self.modules["scoring.score"].score_run(
            by_id, sessions, run_id=run_id, label="离线引擎联调（Mock 模型、sample 数据）",
            role="offline", split="sample", playbook_version=self.version,
            models={"agent": "mock-agent", "visitor": "mock", "judge": "mock"},
            duration_s=duration_s,
            session_refs={v: f"/api/v1/integration/runs/{run_id}/sessions/{v}" for v in by_id})
        self._validate(report, "run_report", by_id)
        return report
