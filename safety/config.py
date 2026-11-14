"""Load frozen settings and resolve data paths independently of working directory."""
from collections.abc import Mapping
import math
import os
import re
from pathlib import Path

import yaml

DEFAULT_CONFIG = Path(__file__).with_name("config.yaml")
PATH_KEYS = ("lexicon_path", "scripts_path", "judge_prompt_path", "testset_path", "eval_output_dir", "veto_rules_path")


def load_config(config=None, *, provider=None) -> dict:
    """Resolve explicit overrides > JUDGE_PROVIDER > YAML."""
    path = DEFAULT_CONFIG if config is None or isinstance(config, Mapping) else Path(config).resolve()
    with path.open(encoding="utf-8") as stream:
        values = yaml.safe_load(stream)
    env_provider = os.getenv("JUDGE_PROVIDER", "").strip()
    if env_provider:
        values["judge_provider"] = env_provider
    if isinstance(config, Mapping):
        values.update(config)
    if provider is not None:
        values["judge_provider"] = provider
    if values["judge_provider"] not in ("ds_flash", "jev", "gemini_decision", "startlux", "mock"):
        raise ValueError("judge_provider must be ds_flash, jev, gemini_decision, startlux or mock")
    for key in ("tau_flag", "tau_active", "probability_sum_tolerance"):
        value = values[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise ValueError(f"{key} must be between 0 and 1")
    values.setdefault("judge_fallback_timeout_s", 3.0)
    for key in ("judge_timeout_s", "judge_fallback_timeout_s", "min_tib_minutes"):
        value = values[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{key} must be positive and finite")
    concurrency = values.setdefault("eval_concurrency", 4)
    if type(concurrency) is not int or concurrency <= 0:
        raise ValueError("eval_concurrency must be a positive integer")
    fallbacks = values.setdefault("judge_fallbacks", [])
    if (not isinstance(fallbacks, list) or any(
            not isinstance(item, str) or item not in
            ("ds_flash", "jev", "gemini_decision", "startlux") for item in fallbacks)):
        raise ValueError("judge_fallbacks must be a list of real judge providers")
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


def read_env(path):
    if not path.exists():
        return {}
    try:
        from dotenv import dotenv_values
    except ImportError:
        # Single-line KEY=value, optional export, quotes and inline comments.
        result = {}
        for line in path.read_text(encoding='utf-8').splitlines():
            match = re.match(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.*)$', line)
            if not match:
                continue
            key, value = match.groups()
            if value.startswith(('"', "'")):
                quote = value[0]
                end = value.find(quote, 1)
                if end < 0:
                    raise ValueError('Invalid dotenv quoting')
                value = value[1:end]
            else:
                value = re.split(r'\s+#', value, maxsplit=1)[0].strip()
                if value.startswith('#'):
                    value = ''
            result[key] = value
        return result
    # Do not expand values from the shell; report only this file's configuration.
    values = dict(dotenv_values(path, interpolate=False))
    # python-dotenv retains a bare inline comment after an empty assignment
    # (KEY= # comment) on some versions; normalize that harmless case so
    # loading a repository .env has the same semantics as our fallback parser.
    return {key: "" if isinstance(value, str) and value.lstrip().startswith("#") else value
            for key, value in values.items()}


def load_repo_env(path=None):
    """Load root dotenv without replacing existing process environment values."""
    path = Path(path) if path is not None else DEFAULT_CONFIG.parent.parent / ".env"
    for key, value in read_env(path).items():
        if value is not None:
            os.environ.setdefault(key, value)
