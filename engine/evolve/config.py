"""Frozen evolve-engine configuration."""
from __future__ import annotations

import copy
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(__file__).with_name("config.yaml")

SECTIONS = ("communication_style", "questioning_strategy", "path_discrimination", "plan_rules", "referral_rules")
SECTION_CRITICALITY = {
    "communication_style": "low",
    "questioning_strategy": "low",
    "path_discrimination": "medium",
    "plan_rules": "high",
    "referral_rules": "high",
}
CRITICALITY_RANK = {"low": 0, "medium": 1, "high": 2}


@lru_cache(maxsize=1)
def _load_default() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def load_config(overrides: dict | None = None) -> dict:
    """Return a deep copy of the frozen config, optionally merged with test overrides."""
    config = copy.deepcopy(_load_default())
    for key, value in (overrides or {}).items():
        if isinstance(value, dict) and isinstance(config.get(key), dict):
            config[key].update(value)
        else:
            config[key] = value
    return config


def resolve(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def max_criticality(*levels: str) -> str:
    return max(levels, key=CRITICALITY_RANK.__getitem__)
