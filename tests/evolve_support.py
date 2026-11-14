"""Shared helpers for engine/evolve tests: mock LLM, mock evaluator, tmp config."""
from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
from pathlib import Path

from engine.evolve.config import load_config

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "contracts" / "examples"
# Keep the historical fixture filename unchanged.
FIXTURE_INITIAL = Path(__file__).resolve().parent / "fixtures" / "evolve" / "playbook_v0.md"


def example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


BASELINE = example("evolution.v1-v2.json")["baseline_val_metrics"]


# The simple, sequential gate behaviour most tests assume. Pinned here so tests do not depend on the
# shipped defaults (frozen 2026-11-14: replicates 2, baseline_replicates 3, parallel, tolerance 1 ...).
SIMPLE_GATE = {"replicates": 1, "baseline_replicates": 1, "baseline_during_reflection": False,
               "parallel_candidates": False, "referral_recall_tolerance_visitors": 0}
SIMPLE_LINEAGE = {"continue_after_reject": False, "reuse_baseline": True}


def make_config(tmp_path: Path, **overrides) -> dict:
    config = load_config({
        "repo": {"path": str(tmp_path / "var" / "playbook-repo"), "initial_path": str(FIXTURE_INITIAL)},
        "review": {"run_dir": str(tmp_path / "var" / "evolve"), "timeout_s": 0, "poll_interval_s": 0.01},
        "gate": dict(SIMPLE_GATE),
        "lineage": dict(SIMPLE_LINEAGE),
    })
    for section, values in overrides.items():
        config[section].update(values)
    return config


class MockLLM:
    def __init__(self, reply=None, *, model="mock-model", error: Exception | None = None, delay: float = 0.0):
        self.model, self.reply, self.error, self.delay = model, reply, error, delay
        self.calls: list[tuple[str, str]] = []

    async def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply, ensure_ascii=False)


def metrics(**changes) -> dict:
    m = copy.deepcopy(BASELINE)
    m.update(changes)
    return m


class MockEvaluator:
    """Scores a playbook by marker phrases it contains; records every call label."""

    def __init__(self, scores: dict[str, dict] | None = None, fail_on: str | None = None):
        self.scores = scores or {}
        self.fail_on = fail_on
        self.labels: list[str] = []

    async def __call__(self, text: str, *, label: str) -> dict:
        self.labels.append(label)
        if self.fail_on and self.fail_on in text:
            raise RuntimeError("evaluator crashed")
        for marker, result in self.scores.items():
            if marker in text:
                return copy.deepcopy(result)
        return copy.deepcopy(BASELINE)


def change(section, after, op="add", before=None, self_level="low", reason="测试理由"):
    return {"op": op, "section": section, "before": before, "after": after, "reason": reason,
            "criticality_self": self_level}


def reply(*candidates) -> dict:
    return {"candidates": [{"summary": f"候选{i}", "changes": list(chs)} for i, chs in enumerate(candidates, 1)]}


def contract_validator():
    spec = importlib.util.spec_from_file_location("contracts_validate", ROOT / "contracts" / "validate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    validators = module.load_validators()
    return lambda doc: module.validate_document(doc, "evolution", validators, {})
