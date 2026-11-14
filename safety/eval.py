"""Offline-capable safety evaluation: python -m safety.eval --provider rules."""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path

from .config import load_config, load_repo_env
from .judges import LEVELS, MockJudge, make_judge
from .layer import SafetyLayer, SessionSafetyState
from .rules import Rules


def load_testset(path) -> list[dict]:
    """Read any size JSONL; permit blank lines and the required # header comment."""
    rows = []
    seen = set()
    with open(path, encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, dict) or not {"id", "text", "label", "cssrs", "difficulty"} <= row.keys():
                    raise ValueError("missing required fields")
                if not isinstance(row["id"], str) or not isinstance(row["text"], str) or row["label"] not in LEVELS:
                    raise ValueError("invalid id, text or label")
                if row["id"] in seen:
                    raise ValueError("duplicate id")
                seen.add(row["id"])
            except (ValueError, TypeError) as exc:
                raise ValueError(f"{path}: line {number}: {exc}") from exc
            rows.append(row)
    return rows


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def _percentile(values, percentile):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


async def evaluate(rows, provider=None, config=None, *, timeout=None) -> dict:
    if provider is not None and provider not in ("rules", "mock", "ds_flash", "jev", "gemini_decision", "startlux", "chain"):
        raise ValueError("Unknown evaluation provider")
    config = load_config(config, provider="mock" if provider == "rules" else None if provider == "chain" else provider)
    provider = provider if provider is not None else config["judge_provider"]
    if timeout is not None:
        config = load_config({**config, "judge_timeout_s": timeout, "judge_timeout_overrides": {}})
    rules = Rules(config["lexicon_path"])
    layer = None
    if provider != "rules":
        # Explicit offline modes cannot be turned into paid calls by the environment.
        if provider == "chain":
            judge = make_judge(config, allow_fallback=False, chain=True)
        else:
            judge = MockJudge(config) if provider == "mock" else make_judge({**config, "judge_provider": provider}, allow_fallback=False)
        layer = SafetyLayer(config, judge=judge)
    matrix = [[0 for _ in LEVELS] for _ in LEVELS]
    predictions, results, missed = [], [], []
    history_missed, history_over_escalated = [], []
    risk_labels = ("passive", "active")
    for row in rows:
        if layer is None:
            hit = rules.match(row["text"])
            predicted = hit.level
        else:
            state = SessionSafetyState()
            event = await layer.assess_text(row["text"], 1, 1, state)
            predicted = "history" if event and event.action == "history_check" else event.level if event else "none"
            results.extend(state.judge_results)
        matrix[LEVELS.index(row["label"])][LEVELS.index(predicted)] += 1
        prediction = {"id": row["id"], "text": row["text"], "label": row["label"], "predicted": predicted}
        predictions.append(prediction)
        if row["label"] in risk_labels and predicted not in risk_labels:
            missed.append(prediction)
        if row["label"] == "history":
            if predicted == "none":
                history_missed.append(prediction)
            elif predicted in risk_labels:
                history_over_escalated.append(prediction)
    risk_indices = [LEVELS.index(label) for label in risk_labels]
    history_index = LEVELS.index("history")
    true_positive = sum(matrix[i][j] for i in risk_indices for j in risk_indices)
    risk_actual = sum(sum(matrix[i]) for i in risk_indices)
    risk_predicted = sum(matrix[i][j] for i in range(len(LEVELS)) for j in risk_indices)
    latencies = [result.latency_ms for result in results]
    return {
        "provider": "rules" if layer is None else layer.judge.provider,
        "requested_provider": provider,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "n": len(predictions),
        "labels": list(LEVELS),
        "matrix_axes": {"rows": "actual", "columns": "predicted"},
        "confusion_matrix": matrix,
        "risk_recall": _ratio(true_positive, risk_actual),
        "risk_precision": _ratio(true_positive, risk_predicted),
        "recall_by_level": {level: _ratio(matrix[i][i], sum(matrix[i])) for i, level in enumerate(LEVELS) if i},
        "missed": missed,
        "history_recall": _ratio(matrix[history_index][history_index], sum(matrix[history_index])),
        "history_missed": history_missed,
        "history_over_escalated": history_over_escalated,
        "judge": {
            "calls": len(results),
            "failures": sum(result.status != "ok" for result in results),
            "statuses": dict(Counter(result.status for result in results)),
            "providers": dict(Counter(result.provider for result in results)),
            "p50_ms": _percentile(latencies, .50),
            "p95_ms": _percentile(latencies, .95),
        },
        "predictions": predictions,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="冻结安全层评测；占位集结果不代表正式安全性能。")
    parser.add_argument("--provider", choices=("rules", "mock", "ds_flash", "jev", "gemini_decision", "startlux", "chain"))
    parser.add_argument("--testset", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout", type=float, help="本次评测判断器超时秒数（覆盖冻结默认值）")
    args = parser.parse_args(argv)
    try:
        load_repo_env()
    except (OSError, ValueError):
        parser.error("仓库根 .env 读取失败，请检查文件权限和格式。")
    config = load_config(args.config, provider="mock" if args.provider == "rules" else None if args.provider == "chain" else args.provider)
    testset = args.testset or Path(config["testset_path"])
    rows = load_testset(testset)
    try:
        report = asyncio.run(evaluate(rows, args.provider, config, timeout=args.timeout))
    except ValueError as exc:
        parser.error(str(exc))
    report["testset"] = str(testset.resolve())
    output_dir = args.output_dir or Path(config["eval_output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = output_dir / f"{report['provider']}-{timestamp}.json"
    report["report_path"] = str(output.resolve())
    serialized = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
