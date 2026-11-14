"""Local persistence and agent-context adapter for schedule personalization."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from domain.schedule import ScheduleProfile, build_schedule_context

_STORE_VERSION = 1
_CONSENT_VERSION = 1


class ScheduleProfileStore:
    """Persist one consented schedule profile to an explicitly chosen local path."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def save(self, profile: ScheduleProfile, *, consent_granted: bool) -> None:
        if consent_granted is not True:
            raise PermissionError("explicit consent is required to save a schedule profile")

        payload = {
            "store_version": _STORE_VERSION,
            "consent_version": _CONSENT_VERSION,
            "profile": profile.as_dict(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temp_path = Path(stream.name)
                json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, self.path)
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()

    def load(self) -> ScheduleProfile | None:
        try:
            with self.path.open("r", encoding="utf-8") as stream:
                payload: Any = json.load(stream)
        except FileNotFoundError:
            return None

        if not isinstance(payload, dict):
            raise ValueError("schedule profile store must contain a JSON object")
        if payload.get("store_version") != _STORE_VERSION:
            raise ValueError("unsupported schedule profile store version")
        if payload.get("consent_version") != _CONSENT_VERSION:
            raise PermissionError("schedule profile has no current consent")
        profile = payload.get("profile")
        if not isinstance(profile, dict):
            raise ValueError("stored schedule profile must be an object")
        return ScheduleProfile.from_dict(profile)

    def delete(self) -> bool:
        try:
            self.path.unlink()
        except FileNotFoundError:
            return False
        return True


def load_schedule_context(store: ScheduleProfileStore) -> dict[str, Any] | None:
    """Load an authorized profile and return its minimized agent context."""
    profile = store.load()
    if profile is None:
        return None
    return build_schedule_context(profile)
