"""PathClassifier: uncertainty definition, normalisation, failure fallback, provider adapters (offline)."""
import asyncio
import json
import math
import sys
from types import SimpleNamespace

import pytest

from engine.classifier import (PATHS, DsFlashPathClassifier, JevPathClassifier, MockPathClassifier, make_classifier,
                               make_state, margin, normalise, uncertainty)

DIALOGUE = [{"speaker": "visitor", "text": "我一躺下脑子就反复想明天的事，越担心越睡不着。"},
            {"speaker": "safety", "text": "安全层话术不算证据"}]
WEIGHTS = {"P1": .1, "P2": .2, "P3": .6, "P4": .05, "P5": .05}


def test_uncertainty_is_normalised_entropy():
    assert uncertainty(dict.fromkeys(PATHS, .2)) == 1.0
    assert uncertainty({"P1": 1.0, "P2": 0, "P3": 0, "P4": 0, "P5": 0}) == 0.0
    expected = -sum(w * math.log(w) for w in WEIGHTS.values()) / math.log(5)
    assert uncertainty(WEIGHTS) == round(expected, 4)
    assert margin(WEIGHTS) == 0.4


def test_normalise_and_validation():
    assert normalise({p: 2 for p in PATHS}) == dict.fromkeys(PATHS, .2)
    for bad in ({"P1": 1}, {**WEIGHTS, "P1": -1}, dict.fromkeys(PATHS, 0), {**WEIGHTS, "P1": float("nan")}):
        with pytest.raises(ValueError):
            normalise(bad)
    with pytest.raises(ValueError):
        make_state(WEIGHTS, "angry", "ok", "x", 0)


def test_mock_is_deterministic_and_reads_visitor_only():
    state = asyncio.run(MockPathClassifier().classify(DIALOGUE))
    assert state.status == "ok" and state.top == "P3" and state.attitude == "cooperative"
    resistant = asyncio.run(MockPathClassifier().classify([{"speaker": "visitor", "text": "没有吧，还好。"}]))
    assert resistant.attitude == "resistant" and resistant.uncertainty == 1.0


@pytest.mark.parametrize("mode,expected", [("ok", "ok"), ("invalid", "error"), ("timeout", "timeout"),
                                           ("exception", "error")])
def test_ds_flash_adapter(mode, expected, monkeypatch):
    monkeypatch.setenv("DS_MODEL", "test-model")
    requests = []

    async def create(**kwargs):
        requests.append(kwargs)
        if mode == "timeout":
            await asyncio.Event().wait()
        if mode == "exception":
            raise RuntimeError("down")
        content = "{}" if mode == "invalid" else json.dumps({"weights": WEIGHTS, "attitude": "resistant"})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    state = asyncio.run(DsFlashPathClassifier(.05, client=client).classify(DIALOGUE))
    assert state.status == expected and state.provider == "ds_flash"
    if mode == "ok":
        assert state.weights == pytest.approx(WEIGHTS) and state.attitude == "resistant"
        assert requests[0]["temperature"] == 0 and requests[0]["response_format"] == {"type": "json_object"}
        assert "安全层话术" not in requests[0]["messages"][1]["content"]
    else:
        assert state.uncertainty == 1.0 and state.attitude == "cooperative"


def test_jev_adapter_uses_two_choice_questions(monkeypatch):
    class Choice:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    monkeypatch.setitem(sys.modules, "typesafe_sdk", SimpleNamespace(AsyncTypeSafeClient=object, Choice=Choice))
    seen = {}

    async def system_one(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(choices={"path": SimpleNamespace(choice="P3", probabilities=WEIGHTS),
                                        "attitude": SimpleNamespace(choice="cooperative", probabilities={})})

    state = asyncio.run(JevPathClassifier(1.0, client=SimpleNamespace(system_one=system_one)).classify(DIALOGUE))
    assert state.status == "ok" and state.top == "P3"
    assert list(seen["questions"]["path"].criteria) == list(PATHS)


def test_factory_falls_back_without_keys():
    assert make_classifier({"provider": "ds_flash", "timeout_s": 6}).provider == "mock(fallback)"
    assert make_classifier({"provider": "jev", "timeout_s": 6}).provider == "mock(fallback)"
    assert make_classifier({"provider": "mock", "timeout_s": 6}).provider == "mock"
