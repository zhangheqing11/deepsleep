import asyncio
import json

from engine.evolve import review
from evolve_support import make_config

ITEMS = [{"candidate_id": "c1", "change_id": "c1-plan_rules-1"}, {"candidate_id": "c2", "change_id": "c2-referral_rules-1"}]


def test_no_decision_becomes_timeout(tmp_path):
    config = make_config(tmp_path)
    out = asyncio.run(review.collect(config, "evo-1", ITEMS, timeout_s=0))
    assert [r["decision"] for r in out] == ["timeout", "timeout"]
    request = json.loads((review.review_dir(config, "evo-1") / "review_request.json").read_text(encoding="utf-8"))
    assert [c["change_id"] for c in request["changes"]] == ["c1-plan_rules-1", "c2-referral_rules-1"]


def test_empty_items_do_not_wait(tmp_path):
    assert asyncio.run(review.collect(make_config(tmp_path, review={"timeout_s": 60}), "evo-0", [])) == []


def test_veto_submitted_during_window_is_picked_up(tmp_path):
    config = make_config(tmp_path)

    async def scenario():
        async def human():
            await asyncio.sleep(0.05)
            review.submit(config, "evo-2", "c1-plan_rules-1", "reject",
                          {"safety": 1, "clinical": 2, "feasibility": 3}, "不同意")
            review.submit(config, "evo-2", "c2-referral_rules-1", "approve")
        task = asyncio.create_task(human())
        out = await review.collect(config, "evo-2", ITEMS, timeout_s=5)
        await task
        return out

    out = asyncio.run(scenario())
    assert out[0] == {"change_id": "c1-plan_rules-1", "decision": "reject",
                      "scores": {"safety": 1, "clinical": 2, "feasibility": 3}, "comment": "不同意"}
    assert out[1]["decision"] == "approve"


def test_unknown_change_and_bad_scores_ignored(tmp_path):
    config = make_config(tmp_path)
    review.submit(config, "evo-3", "c9-plan_rules-1", "reject")
    review.submit(config, "evo-3", "c1-plan_rules-1", "reject", {"safety": 9, "clinical": 1, "feasibility": 1})
    out = asyncio.run(review.collect(config, "evo-3", ITEMS, timeout_s=0))
    assert out[0]["decision"] == "reject" and out[0]["scores"] is None
    assert out[1]["decision"] == "timeout"


def test_blocking_policy(tmp_path):
    passing = make_config(tmp_path)
    vetoing = make_config(tmp_path, review={"timeout_policy": "veto"})
    assert review.blocks("reject", passing) and review.blocks("reject", vetoing)
    assert not review.blocks("approve", passing) and not review.blocks("approve", vetoing)
    assert not review.blocks("timeout", passing)
    assert review.blocks("timeout", vetoing)
