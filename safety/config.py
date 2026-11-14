"""Load frozen settings and resolve data paths independently of working directory."""
from collections.abc import Mapping
import math
import os
from pathlib import Path

import yaml

DEFAULT_CONFIG = Path(__file__).with_name("config.yaml")
PATH_KEYS = ("lexicon_path", "scripts_path", "judge_prompt_path", "testset_path", "eval_output_dir", "veto_rules_path")


def load_config(config=None) -> dict:
    """Accept a YAML path or overrides; JUDGE_PROVIDER wins over YAML/overrides."""
    path = DEFAULT_CONFIG if config is None or isinstance(config, Mapping) else Path(config).resolve()
    with path.open(encoding="utf-8") as stream:
        values = yaml.safe_load(stream)
    if isinstance(config, Mapping):
        values.update(config)
    provider = os.getenv("JUDGE_PROVIDER", "").strip()
    if provider:
        values["judge_provider"] = provider
    if values["judge_provider"] not in ("ds_flash", "jev", "gemini_decision", "startlux", "mock"):
        raise ValueError("judge_provider must be ds_flash, jev, gemini_decision, startlux or mock")
    for key in ("tau_flag", "tau_active", "probability_sum_tolerance"):
        value = values[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise ValueError(f"{key} must be between 0 and 1")
    for key in ("judge_timeout_s", "min_tib_minutes"):
        value = values[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{key} must be positive and finite")
    overrides = values.setdefault("judge_timeout_overrides", {})
    if not isinstance(overrides, Mapping):
        raise ValueError("judge_timeout_overrides must be a provider-to-timeout mapping")
    for provider, value in overrides.items():
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value <= 0):
            raise ValueError(f"judge_timeout_overrides[{provider}] must be positive and finite")
    # The scale criterion is fixed by the specification, not an evolution knob.
    if values["phq9_item9_threshold"] != 0:
        raise ValueError("PHQ-9 item 9 threshold must remain 0")
    for key in PATH_KEYS:
        values[key] = str((path.parent / values[key]).resolve())
    return values
