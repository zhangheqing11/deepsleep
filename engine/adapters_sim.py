"""Local S2/S3 integration; no contract or safety-policy changes."""
from copy import deepcopy


from .interfaces import VisitorReply
from .topics import tag_topics


class S2VisitorSim:
    """Keep one S2 simulator per session, including deny/reveal state across rounds."""

    def __init__(self, client=None, *, instance=None, factory=None):
        self.factory = factory
        self.client = client
        self.instance = instance
        self.model_name = instance.model_name if instance else (client.model if client else "mock")

    async def reply(self, visitor, round, transcript, memory):
        sim = memory.get("_s2_sim")
        if sim is None:
            factory = self.factory
            if factory is None and self.instance is None:
                from sim.visitor_sim import SimVisitor
                factory = SimVisitor
            sim = self.instance or factory(visitor, self.client)
            if sim.visitor["id"] != visitor["id"]:
                raise ValueError("S2 simulator belongs to another visitor")
            memory["_s2_sim"] = sim
        if not transcript:
            reply = sim.opening()
        else:
            tail = []
            for entry in reversed(transcript):
                if entry["speaker"] == "visitor":
                    break
                if entry["speaker"] in ("agent", "safety"):
                    tail.append(entry["text"])
            prompt = "\n".join(reversed(tail))
            # Use spoken words, never a strategy's unspoken target or hidden labels.
            # S3's frozen tagger also recognises history checks ("这种念头").
            reply = await sim.respond(prompt, asked_topics=tag_topics(prompt))
        memory.setdefault("_s2_replies", []).append({
            "round": round, "renderer": reply.renderer, "fallback_reason": reply.fallback_reason,
            "revealed_clue_ids": reply.revealed_clue_ids, "denied_clue_ids": reply.denied_clue_ids,
            "asked_topics": reply.asked_topics,
        })
        return VisitorReply(reply.text, reply.revealed_clue_ids, reply.asked_topics)


class S2Screening:
    def screen(self, visitor, tool):
        from sim.screening import run_tool
        return run_tool(tool, visitor)


class S2OutcomeModel:
    def __init__(self, simulate=None):
        self._simulate = simulate

    def simulate(self, visitor, plan, context):
        simulate = self._simulate
        if simulate is None:
            from sim.state_model import simulate
        session = deepcopy(context["session"])
        session["plan"] = deepcopy(plan)
        # S3 has already appended the empty round-2 placeholder when invoking f_eval.
        # S2 uses the last referral: only completed round 1 belongs in this evaluation.
        session["rounds"] = [r for r in session["rounds"] if r["round"] == 1]
        result = simulate(visitor, session).to_dict()
        result["isi_change"] = result["isi_week"][-1] - result["isi_week"][0]
        result["responder"] = -result["isi_change"] > 7
        return result


async def run_session(visitor, sim, *, run_id, playbook_version):
    """scoring.smoke --agent engine.adapters_sim:run_session (mock unless sim has a client)."""
    from safety.judges import MockJudge
    from safety.layer import SafetyLayer
    from .run import build_deps
    from .session import SessionRunner

    mock = sim.client is None
    config = {"agent_llm": {"max_retries": 1}}
    if mock:
        config.update(agent_llm={"provider": "mock", "max_retries": 1},
                      path_classifier={"provider": "mock"})
    deps = build_deps(config=config, sim=S2VisitorSim(instance=sim), screening=S2Screening(),
                      outcome=S2OutcomeModel(), playbook_version=playbook_version,
                      safety=SafetyLayer(judge=MockJudge()) if mock else SafetyLayer())
    session, _ = await SessionRunner(deps, visitor, run_id).run()
    return session


class S2RendererClient:
    """Real S2 renderer with thinking disabled; S2 code and its content rules stay untouched."""
    def __init__(self, config, timeout_s=15):
        self.timeout_s = timeout_s
        self.model = config.model
        self.config = config
        self.last_error = None
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(base_url=self.config.base_url, api_key=self.config.api_key,
                                       timeout=self.timeout_s, max_retries=0)
        return self._client

    async def complete(self, system, user, max_tokens=300):
        self.last_error = None
        try:
            response = await self._get_client().chat.completions.create(
                model=self.model, messages=[{'role':'system', 'content':system}, {'role':'user', 'content':user}],
                temperature=0, max_tokens=max_tokens, extra_body={'thinking': {'type':'disabled'}})
            if response.choices[0].finish_reason == 'length':
                self.last_error = 'TruncatedOutput'
                return None
            text = (response.choices[0].message.content or '').strip()
            if not text:
                self.last_error = 'EmptyResponse'
                return None
            return text
        except Exception as exc:
            self.last_error = type(exc).__name__  # never log provider error bodies/credentials
            return None
