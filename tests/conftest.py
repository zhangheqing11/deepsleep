"""Offline tests, including when invoked with the pytest executable at repo root."""
from pathlib import Path
import socket
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Windows: asyncio's Proactor loop builds its self-pipe with socket.socketpair(), which on win32
# is a loopback listen + connect. Allow exactly that (connect restored only for the duration of
# the socketpair call); every other connect stays blocked.
_REAL_CONNECT = socket.socket.connect
_REAL_SOCKETPAIR = socket.socketpair


def _loopback_socketpair(*args, **kwargs):
    patched = socket.socket.connect
    socket.socket.connect = _REAL_CONNECT
    try:
        return _REAL_SOCKETPAIR(*args, **kwargs)
    finally:
        socket.socket.connect = patched


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    # CLI subprocesses inherit this too; never open the real repository .env.
    monkeypatch.setenv("SAFETY_EVAL_NO_DOTENV", "1")
    for key in ("DS_API_KEY", "DS_BASE_URL", "DS_MODEL", "TYPESAFE_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "JUDGE_PROVIDER",
                "STARTLUX_API_KEY", "STARTLUX_BASE_URL", "STARTLUX_MODEL"):
        monkeypatch.delenv(key, raising=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("Tests must not access the network")

    # On Windows asyncio implements socket.socketpair() with a localhost
    # connect. Block external network access while allowing that loop
    # bootstrap connection so async tests can run on both platforms.
    def guarded_connect(sock, address):
        host = address[0] if isinstance(address, tuple) else ""
        if host in ("127.0.0.1", "::1", "localhost"):
            return original_connect(sock, address)
        return forbidden(sock, address)

    original_connect = socket.socket.connect
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    if sys.platform == "win32":
        monkeypatch.setattr(socket, "socketpair", _loopback_socketpair)
