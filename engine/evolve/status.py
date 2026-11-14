"""Live status of one learning step, for the read-only dashboard.

``<run_dir>/<evolution_id>/status.json`` is rewritten atomically at every phase change
(tmp file + rename, so a reader never sees half a file). It is progress telemetry, not a
contract and not evidence: the final truth stays in ``evolution.json``.

Shape (``schema`` = ``evolve-status/1``)::

    {
      "schema": "evolve-status/1",
      "evolution_id": "...", "updated_at": ISO, "from_version": "v1",
      "phase": "reflecting | validating | committing | done | failed",
      "reflector": {"state": "running | done", "model": str | null, "fell_back": bool | null},
      "validation": {"baseline": "pending | running | done | error | skipped",
                     "candidates": {"c1": "pending | running | done | error | blocked | empty", ...}},
      "review": {"state": "not_needed | waiting | done", "deadline": ISO | null, "pending_changes": int},
      "outcome": null | "committed" | "kept_previous",
      "to_version": str | null, "chosen": str | null, "error": str | null
    }

Validation and human review run concurrently, so they are separate fields rather than one
"stage". ``blocked`` = stopped by a hard rule (never validated); ``empty`` = no applicable changes.
Writes are best-effort: a failing disk must not break a learning step.
"""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path

SCHEMA = "evolve-status/1"
FILE_NAME = "status.json"


def _iso(epoch: float | None) -> str | None:
    return None if epoch is None else datetime.fromtimestamp(epoch).astimezone().isoformat(timespec="seconds")


class StatusTracker:
    """Holds the status dict and persists it. ``directory=None`` makes every call a no-op."""

    def __init__(self, directory: Path | None, evolution_id: str, from_version: str):
        self.directory = directory
        self.state: dict = {
            "schema": SCHEMA,
            "evolution_id": evolution_id,
            "updated_at": None,
            "from_version": from_version,
            "phase": "reflecting",
            "reflector": {"state": "running", "model": None, "fell_back": None},
            "validation": {"baseline": "pending", "candidates": {}},
            "review": {"state": "not_needed", "deadline": None, "pending_changes": 0},
            "outcome": None,
            "to_version": None,
            "chosen": None,
            "error": None,
        }
        self.flush()

    def set(self, **top) -> None:
        self.state.update(top)
        self.flush()

    def reflector(self, **fields) -> None:
        self.state["reflector"].update(fields)
        self.flush()

    def baseline(self, state: str) -> None:
        self.state["validation"]["baseline"] = state
        self.flush()

    def candidate(self, candidate_id: str, state: str) -> None:
        self.state["validation"]["candidates"][candidate_id] = state
        self.flush()

    def review(self, **fields) -> None:
        self.state["review"].update(fields)
        self.flush()

    def review_open(self, deadline_epoch: float) -> None:
        self.review(state="waiting", deadline=_iso(deadline_epoch))

    def fail(self, exc: BaseException) -> None:
        self.set(phase="failed", error=f"{type(exc).__name__}: {exc}")

    def flush(self) -> None:
        if self.directory is None:
            return
        self.state["updated_at"] = _iso(datetime.now().timestamp())
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            target = self.directory / FILE_NAME
            tmp = target.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, target)
        except OSError:
            pass  # progress telemetry only


def read_status(directory: Path) -> dict | None:
    """Latest status of an evolution directory, or None if absent / unreadable."""
    try:
        return json.loads((directory / FILE_NAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
