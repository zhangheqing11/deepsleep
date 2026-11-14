"""Frozen engine settings and a minimal .env loader (no extra dependency)."""
from collections.abc import Mapping
import copy
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = Path(__file__).with_name("config.yaml")
PATH_KEYS = ("playbook_path", "prompts_dir")


def load_dotenv(path: Path | str = ROOT / ".env") -> None:
    """Fill os.environ from KEY=VALUE lines; existing variables win."""
    path = Path(path)
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


def _merge(base: dict, extra: Mapping) -> dict:
    for key, value in extra.items():
        if isinstance(value, Mapping) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
    return base


def load_config(config=None) -> dict:
    """Accept None, a YAML path, or a mapping of overrides (tests only)."""
    path = DEFAULT_CONFIG if config is None or isinstance(config, Mapping) else Path(config).resolve()
    with path.open(encoding="utf-8") as stream:
        values = yaml.safe_load(stream)
    if isinstance(config, Mapping):
        _merge(values, config)
    caps = {int(k): int(v) for k, v in values["round_turn_cap"].items()}
    if set(caps) != {1, 2} or any(v < 1 for v in caps.values()):
        raise ValueError("round_turn_cap must define positive caps for rounds 1 and 2")
    values["round_turn_cap"] = caps
    if values["path_classifier"]["provider"] not in ("ds_flash", "jev", "mock"):
        raise ValueError("path_classifier.provider must be ds_flash, jev or mock")
    for key in ("merge_strategy_response", "merge_memory_plan"):
        if not isinstance(values["pipeline"][key], bool):
            raise ValueError(f"pipeline.{key} must be boolean")
    if values["agent_llm"]["provider"] not in ("ds_flash", "mock"):
        raise ValueError("agent_llm.provider must be ds_flash or mock")
    if values["visitor_renderer"] not in ("llm", "template"):
        raise ValueError("visitor_renderer must be llm or template")
    retry = values["agent_llm"]["network_retry"]
    if type(retry["max_retries"]) is not int or not 0 <= retry["max_retries"] <= 5:
        raise ValueError("network_retry.max_retries must be an integer between 0 and 5")
    if any(not isinstance(retry[k], (int, float)) or not 0 <= retry[k] <= 60
           for k in ("backoff_s", "max_backoff_s")):
        raise ValueError("network retry delays must be between 0 and 60 seconds")
    share = values["quality"]["max_degraded_share"]
    if isinstance(share, bool) or not isinstance(share, (int, float)) or not 0 <= share <= 1:
        raise ValueError("quality.max_degraded_share must be a number between 0 and 1")
    for key in PATH_KEYS:
        values[key] = str((path.parent / values[key]).resolve())
    return values
