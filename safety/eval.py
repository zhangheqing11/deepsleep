"""Offline-capable safety evaluation: python -m safety.eval --provider rules."""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path

from .config import load_config
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


async def evaluate(rows, provider="rules", config=None) -> dict:
    if provider not in ("rules", "mock", "ds_flash", "jev", "gemini_decision"):
        raise ValueError("Unknown evaluation provider")
    config = load_config(config)
    rules = Rules(config["lexicon_path"])
    layer = None
    if provider != "rules":
        # Explicit offline modes cannot be turned into paid calls by the environment.
        judge = MockJudge(config) if provider == "mock" else make_judge({**config, "judge_provider": provider})
        layer = SafetyLayer(config, judge=judge)
    matrix = [[0 for _ in LEVELS] for _ in LEVELS]
    predictions, results, missed = [], [], []
    for row in rows:
        if layer is None:
            hit = rules.match(row["text"])
            predicted = hit.level
        else:
            state = SessionSafetyState()
            event = await layer.assess_text(row["text"], 1, 1, state)
            predicted = event.level if event else "none"
            results.extend(state.judge_results)
        matrix[LEVELS.index(row["label"])][LEVELS.index(predicted)] += 1
        prediction = {"id": row["id"], "text": row["text"], "label": row["label"], "predicted": predicted}
        predictions.append(prediction)
        if row["label"] != "none" and predicted == "none":
            missed.append(prediction)
    true_positive = sum(matrix[i][j] for i in (1, 2) for j in (1, 2))
    risk_actual = sum(sum(matrix[i]) for i in (1, 2))
    risk_predicted = sum(matrix[i][j] for i in range(3) for j in (1, 2))
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
    parser.add_argument("--provider", choices=("rules", "mock", "ds_flash", "jev", "gemini_decision"), required=True)
    parser.add_argument("--testset", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    config = load_config(args.config)
    testset = args.testset or Path(config["testset_path"])
    rows = load_testset(testset)
    report = asyncio.run(evaluate(rows, args.provider, config))
    report["testset"] = str(testset.resolve())
    output_dir = args.output_dir or Path(config["eval_output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = output_dir / f"{args.provider}-{timestamp}.json"
    report["report_path"] = str(output.resolve())
    serialized = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
