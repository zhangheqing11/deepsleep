import asyncio
import json

import pytest

from engine.evolve import pipeline
from engine.evolve.lineage import evolve_lineage, generation_id
from engine.evolve.repo import PlaybookRepo
from evolve_support import MockLLM, change, contract_validator, make_config, reply
from test_evolve_pipeline import RUN, SESSIONS, RowsEvaluator, c_rows

VALIDATE = contract_validator()
G1 = [change("path_discrimination", "标记G1：在床外容易困、回床后清醒时，优先考虑 P2。")]
G2 = [change("questioning_strategy", "标记G2：来访提到打鼾且没填 STOP-Bang 时，先调用 screen_osa。")]
G3 = [change("communication_style", "标记G3：用简短的复述确认已经听到的信息。")]


class SeqLLM(MockLLM):
    """One reply per call, in order (one call per generation)."""

    def __init__(self, replies):
        super().__init__(None, model="mock-model")
        self.replies = list(replies)

    async def complete(self, system, user):
        self.calls.append((system, user))
        return json.dumps(self.replies.pop(0), ensure_ascii=False)


def table():
    # Each adopted marker adds two responders on C; the markers stack because the playbook keeps them.
    return RowsEvaluator({"标记G3": [c_rows(responders=set(range(6)))],
                          "标记G2": [c_rows(responders=set(range(4)))],
                          "标记G1": [c_rows(responders=set(range(2)))]},
                         [c_rows(responders=set())])


def run(tmp_path, replies, max_generations, evaluator=None, prefix="exp-learn", continue_after_reject=False,
        **gate):
    config = make_config(tmp_path, gate=gate) if gate else make_config(tmp_path)
    repo = PlaybookRepo(config)
    evaluator = evaluator or table()
    llm = SeqLLM(replies)
    evolutions = asyncio.run(evolve_lineage(
        run_report=RUN, sessions=SESSIONS, traces=None, visitors=None, evaluator=evaluator, config=config,
        repo=repo, max_generations=max_generations, evolution_id_prefix=prefix, primary=llm,
        use_default_clients=False, continue_after_reject=continue_after_reject))
    return evolutions, evaluator, repo, config, llm


def read(tmp_path, *parts):
    return json.loads((tmp_path / "var" / "evolve").joinpath(*parts).read_text(encoding="utf-8"))


def test_single_generation_keeps_prefix_id_and_layout(tmp_path):
    evolutions, evaluator, repo, _, _ = run(tmp_path, [reply(G1, [], [])], 1)
    assert [e["evolution_id"] for e in evolutions] == ["exp-learn"] == [generation_id("exp-learn", 1, 1)]
    assert VALIDATE(evolutions[0]) == [] and evolutions[0]["chosen"] == "c1"
    for name in ("evolution.json", "insights.json", "status.json", "lineage.json"):
        assert (tmp_path / "var/evolve/exp-learn" / name).is_file()
    assert evaluator.labels == ["v1", "v1+c1"] and repo.current_version() == "v2"


def test_two_generations_chain_reuse_baseline_and_history(tmp_path, monkeypatch):
    seen = []
    real = pipeline.reflect

    async def spy(*, history=None, **kwargs):
        seen.append(history)
        return await real(**kwargs)

    monkeypatch.setattr(pipeline, "reflect", spy)
    evolutions, evaluator, repo, _, _ = run(tmp_path, [reply(G1, [], []), reply(G2, [], [])], 2)
    assert [e["evolution_id"] for e in evolutions] == ["exp-learn-g1", "exp-learn-g2"]
    for evo in evolutions:
        assert VALIDATE(evo) == []
        assert evo["outcome"] == "committed"
    assert [(e["from_version"], e["to_version"]) for e in evolutions] == [("v1", "v2"), ("v2", "v3")]
    # Generation 2 reuses the adopted candidate's evaluation as its baseline.
    assert evaluator.labels == ["v1", "v1+c1", "v2+c1"]
    assert evolutions[1]["baseline_val_metrics"] == evolutions[0]["candidates"][0]["val_metrics"]
    text = repo.read()
    assert "标记G1" in text and "标记G2" in text and repo.current_version() == "v3"

    assert seen[0] is None
    (item,) = seen[1]
    assert (item["generation"], item["from_version"], item["to_version"]) == (1, "v1", "v2")
    assert [c["outcome"] for c in item["candidates"]] == ["adopted", "empty", "empty"]
    assert item["candidates"][0]["delta"]["gained"] == 2

    insights = read(tmp_path, "exp-learn-g2", "insights.json")
    assert insights["validation"]["baseline_source"] == "reused"
    assert insights["validation"]["candidates"]["c1"]["paired"]["responder"]["gained"] == ["C-002", "C-003"]
    status = read(tmp_path, "exp-learn-g2", "status.json")
    assert status["phase"] == "done" and status["validation"]["baseline"] == "skipped"

    lineage = read(tmp_path, "exp-learn", "lineage.json")
    assert lineage["state"] == "done" and (lineage["start_version"], lineage["final_version"]) == ("v1", "v3")
    gens = lineage["generations"]
    assert [g["evolution_id"] for g in gens] == ["exp-learn-g1", "exp-learn-g2"]
    assert [g["chosen"] for g in gens] == ["c1", "c1"]
    assert [g["primary_metric"]["chosen"] for g in gens] == [pytest.approx(0.2), pytest.approx(0.4)]
    assert gens[1]["primary_metric"]["baseline"] == pytest.approx(0.2)
    assert gens[1]["paired"]["c1"]["responder"]["net"] == 2


def test_stops_early_when_nothing_adopted(tmp_path):
    # Generation 2 proposes nothing useful (worse than its baseline) → stop; generation 3 never runs.
    evolutions, evaluator, repo, _, llm = run(
        tmp_path, [reply(G1, [], []), reply([change("communication_style", "无标记改动")], [], []),
                   reply(G3, [], [])], 3)
    assert [e["outcome"] for e in evolutions] == ["committed", "kept_previous"]
    assert len(llm.calls) == 2 and repo.current_version() == "v2"
    assert all(VALIDATE(e) == [] for e in evolutions)
    lineage = read(tmp_path, "exp-learn", "lineage.json")
    assert [g["outcome"] for g in lineage["generations"]] == ["committed", "kept_previous"]
    assert lineage["generations"][1]["candidates"][0]["reasons"] == ["主指标未严格提高"]
    assert not (tmp_path / "var/evolve/exp-learn-g3").exists()


def test_stops_when_reflector_yields_no_valid_candidate(tmp_path):
    evolutions, _, repo, _, _ = run(tmp_path, [{"candidates": []}, reply(G1, [], [])], 2)
    assert len(evolutions) == 1 and evolutions[0]["outcome"] == "kept_previous"
    assert VALIDATE(evolutions[0]) == [] and repo.current_version() == "v1"


def test_hard_rule_blocked_candidate_reported_in_history(tmp_path):
    shotgun = [change("plan_rules", "处方包含全部组件。")]
    evolutions, evaluator, _, _, _ = run(tmp_path, [reply(shotgun, G1, [])], 1)
    evo = evolutions[0]
    assert VALIDATE(evo) == [] and evo["chosen"] == "c2"
    assert evo["candidates"][0]["hard_rule_violations"][0]["code"] == "sim_exploit"
    assert "v1+c1" not in evaluator.labels
    item = read(tmp_path, "exp-learn", "insights.json")["history_item"]["candidates"][0]
    assert item["outcome"] == "blocked" and "结局模型" in item["reasons"][0]


def test_rejects_zero_generations(tmp_path):
    with pytest.raises(ValueError):
        run(tmp_path, [], 0)


NOOP1 = [change("communication_style", "无标记改动一：先复述来访的困扰。")]
NOOP2 = [change("communication_style", "无标记改动二：结束前确认来访听懂了。")]


@pytest.mark.parametrize("continue_after_reject", [True, False])
def test_continue_after_reject_reuses_baseline_and_passes_history(tmp_path, monkeypatch, continue_after_reject):
    seen = []
    real = pipeline.reflect

    async def spy(*, history=None, **kwargs):
        seen.append(history)
        return await real(**kwargs)

    monkeypatch.setattr(pipeline, "reflect", spy)
    # Nothing carries a responder marker, so every candidate ties the baseline and is rejected.
    evolutions, evaluator, repo, _, llm = run(
        tmp_path, [reply(NOOP1, [], []), reply(NOOP2, [], [])], 2, continue_after_reject=continue_after_reject)
    assert evolutions[0]["outcome"] == "kept_previous" and repo.current_version() == "v1"
    if not continue_after_reject:
        assert len(evolutions) == 1 and len(llm.calls) == 1 and evaluator.labels == ["v1", "v1+c1"]
        assert not (tmp_path / "var/evolve/exp-learn-g2").exists()
        return
    assert [e["evolution_id"] for e in evolutions] == ["exp-learn-g1", "exp-learn-g2"]
    assert [e["outcome"] for e in evolutions] == ["kept_previous", "kept_previous"]
    assert all(VALIDATE(e) == [] for e in evolutions)
    # Generation 2 reuses generation 1's baseline measurement: "v1" is evaluated only once.
    assert evaluator.labels == ["v1", "v1+c1", "v1+c1"] and evaluator.labels.count("v1") == 1
    assert evolutions[1]["baseline_val_metrics"] == evolutions[0]["baseline_val_metrics"]
    assert seen[0] is None
    (item,) = seen[1]
    assert (item["generation"], item["from_version"]) == (1, "v1")
    assert [c["outcome"] for c in item["candidates"]][0] != "adopted"
    assert read(tmp_path, "exp-learn-g2", "status.json")["validation"]["baseline"] == "skipped"
