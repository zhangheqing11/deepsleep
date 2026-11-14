"""Interfaces between engine/ and sim/ (S2). Keep these stable; sim implements them.

VisitorSim.reply(visitor, round, transcript, memory) -> VisitorReply
  visitor     : contract visitor dict (hidden labels allowed; the agent never sees it)
  round       : 1 or 2
  transcript  : every entry so far in this session, oldest first:
                {round, turn, speaker: agent|visitor|safety, text, revealed_clue_ids}
                The entries after the visitor's last utterance are what it answers.
                In round 1 with no prior entries, the reply is the opening complaint.
  memory      : per-session scratch dict owned by the simulator (deny_first state, caches)
  The reply goes through the safety layer like any visitor utterance.

ScreeningProvider.screen(visitor, tool) -> dict  (pure code, no LLM; BACKLOG D2)
  screen_mood -> {"phq9", "phq9_items"[9], "gad7"};  screen_osa -> {"stop_bang"}
  Values must equal visitor.indices and phq9_items[8] == visitor.crisis.phq9_item9.

PlanOutcomeModel.simulate(visitor, plan, context) -> dict  (loop 2 f_eval; S2's frozen 4-week state model)
  plan    : the round-1 plan (contract plan shape)
  context : {"session": partial session-like dict so far (rounds, tool_calls, behaviors, safety_events)}
  returns : {"isi_week": [5 numbers, weeks 0-4], "isi_change": number, "adherence": 0-1, "responder": bool}
            extra keys are passed through to the trace. The agent sees isi_week / isi_change / adherence;
            the engine also stores the dict in the simulator's memory as memory["round1_outcome"] so the
            simulated visitor can talk about how the 4 weeks went.
"""
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class VisitorReply:
    text: str
    revealed_clue_ids: list[str] = field(default_factory=list)
    # Topics the simulator judged the preceding agent message to ask about;
    # None lets the engine fall back to engine.topics.tag_topics.
    asked_topics: list[str] | None = None


@runtime_checkable
class VisitorSim(Protocol):
    model_name: str

    async def reply(self, visitor: dict, round: int, transcript: list[dict], memory: dict) -> VisitorReply: ...


@runtime_checkable
class ScreeningProvider(Protocol):
    def screen(self, visitor: dict, tool: str) -> dict: ...


@runtime_checkable
class PlanOutcomeModel(Protocol):
    def simulate(self, visitor: dict, plan: dict, context: dict) -> dict: ...
