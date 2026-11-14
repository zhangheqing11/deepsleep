"""Offline-capable safety evaluation: python -m safety.eval --provider rules."""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path

from .config import load_config, load_repo_env
from .judges import LEVELS, JudgeResult, MockJudge, make_judge
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


def _result_record(result, requested_provider):
    attempts = result.attempts or (result,)
    return {
        "requested_provider": requested_provider,
        "actual_provider": result.provider,
        "status": result.status,
        "fallback_used": len(attempts) > 1,
        "attempts": [
            {"provider": attempt.provider, "status": attempt.status,
             "latency_ms": attempt.latency_ms}
            for attempt in attempts
        ],
        "latency_ms": result.latency_ms,
    }


async def evaluate(rows, provider=None, config=None, *, timeout=None, concurrency=None,
                   evaluation_timeout=None) -> dict:
    if provider is not None and provider not in ("rules", "mock", "ds_flash", "jev", "gemini_decision", "startlux", "chain"):
        raise ValueError("Unknown evaluation provider")
    # chain is a routing mode, not a model provider. Keep its primary
    # provider deterministic (ds_flash) even when a stale JUDGE_PROVIDER
    # environment variable is present; the configured fallback list is then
    # constructed and reported explicitly.
    config = load_config(config, provider="mock" if provider == "rules" else
                         "ds_flash" if provider == "chain" else provider)
    provider = provider if provider is not None else config["judge_provider"]
    if timeout is not None:
        config = load_config({**config, "judge_timeout_s": timeout, "judge_timeout_overrides": {}})
    if concurrency is not None and (type(concurrency) is not int or concurrency <= 0):
        raise ValueError("concurrency must be a positive integer")
    if (evaluation_timeout is not None and
            (isinstance(evaluation_timeout, bool) or not isinstance(evaluation_timeout, (int, float))
             or not math.isfinite(evaluation_timeout) or evaluation_timeout <= 0)):
        raise ValueError("evaluation_timeout must be positive and finite")
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
    predictions, results, judgement_records, missed = [], [], [], []
    history_missed, history_over_escalated = [], []
    risk_labels = ("passive", "active")
    async def assess(index, row):
        if layer is None:
            return index, rules.match(row["text"]).level, [], None
        state = SessionSafetyState()
        event = await layer.assess_text(row["text"], 1, 1, state)
        predicted = "history" if event and event.action == "history_check" else event.level if event else "none"
        record = None
        if state.judge_results:
            attempts = tuple(state.judge_results)
            final = attempts[-1]
            # SafetyLayer stores every chain attempt. Rebuild the invocation
            # record even when the final assessment produced no event (none).
            if event is not None:
                final = JudgeResult(event.judge_probs, event.judge_status,
                                    event.judge_provider,
                                    sum(a.latency_ms for a in attempts), attempts)
            else:
                final = JudgeResult(final.probs, final.status, final.provider,
                                    sum(a.latency_ms for a in attempts), attempts)
            record = _result_record(final, provider)
        return index, predicted, list(state.judge_results), record

    evaluation_status = "ok"
    if layer is None:
        assessed = [await assess(index, row) for index, row in enumerate(rows)]
    else:
        limit = concurrency if concurrency is not None else config.get("eval_concurrency", 4)
        semaphore = asyncio.Semaphore(limit)

        async def bounded(index, row):
            async with semaphore:
                return await assess(index, row)

        try:
            if evaluation_timeout is None:
                assessed = await asyncio.gather(*(bounded(index, row) for index, row in enumerate(rows)))
            else:
                tasks = {asyncio.create_task(bounded(index, row)): index
                         for index, row in enumerate(rows)}
                done, pending = await asyncio.wait(tasks, timeout=evaluation_timeout)
                assessed = [None] * len(rows)
                for task in done:
                    assessed[tasks[task]] = task.result()
                if pending:
                    evaluation_status = "timeout"
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                    for task in pending:
                        index = tasks[task]
                        cancelled = JudgeResult(None, "cancelled",
                                                getattr(layer.judge, "provider", provider), 0.)
                        assessed[index] = (index, "none", [cancelled],
                                           _result_record(cancelled, provider))
        finally:
            close = getattr(layer.judge, "aclose", None)
            if close is not None:
                await close()

    for index, row in enumerate(rows):
        _, predicted, row_results, record = assessed[index]
        results.extend(row_results)
        if record is not None:
            judgement_records.append(record)
        matrix[LEVELS.index(row["label"])][LEVELS.index(predicted)] += 1
        prediction = {"id": row["id"], "text": row["text"], "label": row["label"], "predicted": predicted}
        if record is not None:
            prediction["judgement"] = record
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
    fallback_count = sum(record["fallback_used"] for record in judgement_records)
    model_successes = sum(result.status == "ok" for result in results)
    model_failures = sum(result.status != "ok" for result in results)
    # Every failed model invocation is resolved by the fixed SafetyLayer
    # decision (none/passive); count it explicitly rather than presenting it
    # as a model success.
    rule_fallback_count = sum(record["status"] != "ok" for record in judgement_records)
    evidence = {
        "rules-only": {"status": "未测", "note": "规则单独的结果不构成 0 漏报指标"},
        "mock": {"status": "未测", "note": "mock，不代表识别能力"},
        "real_judge": {"status": "未测", "note": "规则 + 真实判断器联合指标；A2/A4 留出集验收未完成"},
    }
    column = "rules-only" if provider == "rules" else "mock" if provider == "mock" else "real_judge"
    evidence[column].update(
        status="本次已测" if column != "real_judge" else "本次已测，A2/A4 留出集未测",
        missed_count=len(missed), risk_recall=_ratio(true_positive, risk_actual),
    )
    return {
        "evidence_columns": evidence,
        "freeze_acceptance": {"status": "未完成", "eligible": False,
                              "reason": "演示前须有真实判断器留出集漏报数；漏报数 > 0 不得冻结，0 也须完成 A2/A4 人工审定"},
        "provider": "rules" if layer is None else layer.judge.provider,
        "requested_provider": provider,
        "evaluation_status": evaluation_status,
        "evaluation_timeout_s": evaluation_timeout,
        "evaluation_concurrency": None if layer is None else (concurrency or config.get("eval_concurrency", 4)),
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
            "timeouts": sum(result.status == "timeout" for result in results),
            "errors": sum(result.status == "error" for result in results),
            "cancelled": sum(result.status == "cancelled" for result in results),
        },
        "judge_fallbacks": fallback_count,
        "rule_fallbacks": rule_fallback_count,
        "model_successes": model_successes,
        "model_failures": model_failures,
        "judge_records": judgement_records,
        "predictions": predictions,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="冻结安全层评测；占位集结果不代表正式安全性能。")
    parser.add_argument("--provider", choices=("rules", "mock", "ds_flash", "jev", "gemini_decision", "startlux", "chain"))
    parser.add_argument("--testset", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout", type=float, help="本次评测判断器超时秒数（覆盖冻结默认值）")
    parser.add_argument("--concurrency", type=int, help="真实判断器并发上限（覆盖配置）")
    parser.add_argument("--evaluation-timeout", type=float,
                        help="整次评测超时秒数；超出的样本标记为 cancelled")
    parser.add_argument("--no-env", action="store_true", help="不读取仓库 .env，仅使用进程环境")
    args = parser.parse_args(argv)
    try:
        if not args.no_env and os.getenv("SAFETY_EVAL_NO_DOTENV") != "1":
            load_repo_env()
    except (OSError, ValueError):
        parser.error("仓库根 .env 读取失败，请检查文件权限和格式。")
    config = load_config(args.config, provider="mock" if args.provider == "rules" else
                         "ds_flash" if args.provider == "chain" else args.provider)
    testset = args.testset or Path(config["testset_path"])
    rows = load_testset(testset)
    try:
        report = asyncio.run(evaluate(rows, args.provider, config,
                                      timeout=args.timeout, concurrency=args.concurrency,
                                      evaluation_timeout=args.evaluation_timeout))
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
