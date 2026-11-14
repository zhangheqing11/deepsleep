"""Offline tests, including when invoked with the pytest executable at repo root."""
from pathlib import Path
import socket
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for key in ("DS_API_KEY", "DS_BASE_URL", "DS_MODEL", "TYPESAFE_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "JUDGE_PROVIDER",
                "STARTLUX_API_KEY", "STARTLUX_BASE_URL", "STARTLUX_MODEL"):
        monkeypatch.delenv(key, raising=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("Tests must not access the network")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
