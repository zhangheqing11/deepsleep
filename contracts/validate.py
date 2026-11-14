#!/usr/bin/env python3
"""Validate deepsleep JSON contracts and their non-schema invariants (Python 3.11+)."""
from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

CONTRACTS = Path(__file__).resolve().parent
SCHEMA_NAMES = ('visitor', 'session', 'run_report', 'evolution')
SECTION_CRITICALITY = {
    'communication_style': 'low',
    'questioning_strategy': 'low',
    'path_discrimination': 'medium',
    'plan_rules': 'high',
    'referral_rules': 'high',
}
CRITICALITY_RANK = {'low': 0, 'medium': 1, 'high': 2}
TOLERANCE = 1e-6
FORMAT_CHECKER = FormatChecker()


@FORMAT_CHECKER.checks('date-time', raises=ValueError)
def timestamp_with_timezone(value: Any) -> bool:
    """jsonschema's optional date-time dependency is not required by this project."""
    if not isinstance(value, str):
        return True  # The schema's type keyword handles non-strings.
    if not re.fullmatch(
        r'\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?'
        r'(?:[Zz]|[+-](?:[01]\d|2[0-3]):[0-5]\d)',
        value,
    ):
        return False
    normalized = value.upper()
    # RFC 3339 allows a leap second at the end of a minute. datetime does not.
    if normalized[17:19] == '60':
        normalized = normalized[:17] + '59' + normalized[19:]
    parsed = datetime.fromisoformat(normalized)
    return parsed.tzinfo is not None


def reject_constant(value: str) -> None:
    raise ValueError(f'JSON 不允许非有限数值 {value}')


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'), parse_constant=reject_constant)


def load_validators() -> dict[str, Draft202012Validator]:
    """Resolve every $ref locally, without network access or deprecated RefResolver."""
    schemas = {
        name: read_json(CONTRACTS / f'{name}.schema.json')
        for name in ('common', *SCHEMA_NAMES)
    }
    registry = Registry()
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        registry = registry.with_resource(schema['$id'], Resource.from_contents(schema))
    return {
        name: Draft202012Validator(schemas[name], registry=registry, format_checker=FORMAT_CHECKER)
        for name in SCHEMA_NAMES
    }


def check_scales(scales: list[dict], path: str) -> list[str]:
    errors = []
    names = [entry['scale'] for entry in scales]
    if len(names) != len(set(names)):
        errors.append(f'{path}: scale 不能重复')
    for index, entry in enumerate(scales):
        if entry['scale'] == 'phq9' and sum(entry['items']) != entry['reported_score']:
            errors.append(f'{path}[{index}]: phq9 items 总和必须等于 reported_score')
    return errors


def check_visitor(data: dict, visitors: dict) -> list[str]:
    errors = check_scales(data['prefilled'], 'prefilled')
    if data['secondary_path'] == data['main_path']:
        errors.append('secondary_path 不能等于 main_path')
    if data['split'] != 'sample' and data['id'].split('-', 1)[0] != data['split']:
        errors.append('id 前缀必须与 split 一致')
    for index, day in enumerate(data['diary']):
        if day['tib_min'] == 0:
            errors.append(f'diary[{index}].tib_min 为 0，无法计算睡眠效率')
        elif abs(day['se'] - day['tst_min'] / day['tib_min']) > 0.01 + 1e-12:
            errors.append(f'diary[{index}].se 与 tst_min/tib_min 相差超过 0.01')
    if (data['crisis']['level'] != 'none' and data['crisis']['phq9_item9'] <= 0
            and not any(clue['supports'] == 'crisis' for clue in data['clues'])):
        errors.append('crisis.level 非 none 时需 phq9_item9 > 0 或 supports=crisis 的线索')
    return errors


def check_session(data: dict, visitors: dict) -> list[str]:
    errors = check_scales(data['context_scales'], 'context_scales')
    if data['session_id'] != f"{data['run_id']}/{data['visitor_id']}":
        errors.append('session_id 必须等于 run_id + "/" + visitor_id')
    visitor = visitors.get(data['visitor_id'])
    if visitor and data['context_scales'] != visitor['prefilled']:
        errors.append('context_scales 必须等于 visitor.prefilled')
    clue_ids = {clue['id'] for clue in visitor['clues']} if visitor else None
    round_numbers = [item['round'] for item in data['rounds']]
    if round_numbers != list(range(1, len(round_numbers) + 1)):
        errors.append('rounds.round 必须从 1 连续递增且不重复')
    for index, event in enumerate(data['safety_events']):
        if event['action'] == 'history_check':
            prefix = f'safety_events[{index}]'
            if event['level'] != 'none':
                errors.append(f'{prefix}: history_check 的 level 必须为 none')
            # Check that a follow-up exists; its wording needs semantic review.
            if visitor and not any(
                turn['turn'] > event['turn'] and turn['speaker'] in ('agent', 'safety')
                for round_data in data['rounds'] if round_data['round'] == event['round']
                for turn in round_data['transcript']
            ):
                errors.append(f'{prefix}: history_check 之后同一轮必须存在 agent 或 safety 的下一句发言')
    scale_triggers = [(1, 0)] if any(
        entry['scale'] == 'phq9' and entry['items'][8] > 0
        for entry in data['context_scales']
    ) else []
    for index, call in enumerate(data['tool_calls']):
        prefix = f'tool_calls[{index}]'
        if call['round'] not in round_numbers:
            errors.append(f'{prefix}.round 必须对应存在的 rounds 项')
        result = call['result']
        if call['tool'] == 'screen_mood':
            if sum(result['phq9_items']) != result['phq9']:
                errors.append(f'{prefix}: phq9_items 总和必须等于 phq9')
            if result['phq9_items'][8] > 0:
                scale_triggers.append((call['round'], call['turn']))
            if visitor:
                if sum(result['phq9_items']) != visitor['indices']['phq9']:
                    errors.append(f'{prefix}: phq9_items 总和必须等于 visitor.indices.phq9')
                if result['phq9_items'][8] != visitor['crisis']['phq9_item9']:
                    errors.append(f'{prefix}: phq9_items[8] 必须等于 visitor.crisis.phq9_item9')
        if visitor:
            for scale in ('phq9', 'gad7', 'stop_bang'):
                if scale in result and result[scale] != visitor['indices'][scale]:
                    errors.append(f'{prefix}.result.{scale} 必须等于 visitor.indices.{scale}')
    for position in scale_triggers:
        already_active = any(
            event['level'] == 'active' and event['source'] != 'scale_item9'
            and (event['round'], event['turn']) < position
            for event in data['safety_events']
        )
        if not already_active and not any(
            event['source'] == 'scale_item9'
            and (event['round'], event['turn']) == position
            for event in data['safety_events']
        ):
            errors.append(f'round={position[0]} turn={position[1]}: PHQ-9 第 9 题 > 0 缺少 scale_item9 safety_event')
    for index, round_data in enumerate(data['rounds']):
        transcript = round_data['transcript']
        text_turns = [turn['turn'] for turn in transcript]
        tool_turns = [call['turn'] for call in data['tool_calls']
                      if call['round'] == round_data['round']]
        combined = text_turns + tool_turns
        if (sorted(combined) != list(range(1, len(combined) + 1))
                or text_turns != sorted(text_turns) or tool_turns != sorted(tool_turns)):
            errors.append(f'rounds[{index}]: transcript + tool_calls 的 turn 必须从 1 连续递增且不重复')
        if clue_ids is not None:
            for turn in transcript:
                for clue_id in turn['revealed_clue_ids']:
                    if clue_id not in clue_ids:
                        errors.append(f'rounds[{index}] turn={turn["turn"]} 揭示了未知线索 {clue_id}')
    if data['status'] == 'completed':
        if data['plan'] is None:
            errors.append('status=completed 时 plan 不能为 null')
        if len(data['rounds']) != 2:
            errors.append('status=completed 时 rounds 必须有 2 项')
    return errors


def fraction(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def needed_screen(row: dict) -> str | None:
    """R3 needs screening only when neither mood scale was prefilled."""
    scales = set(row['prefilled_scales'])
    if row['referral_true'] == 'R1' and 'stop_bang' not in scales:
        return 'screen_osa'
    if row['referral_true'] == 'R3' and not scales.intersection(('phq9', 'gad7')):
        return 'screen_mood'
    return None


def compute_metrics(rows: list[dict]) -> dict:
    """Recompute from raw labels and week-0/week-4 scores, not stored summaries."""
    n = len(rows)
    if not n:
        raise ValueError('per_visitor 为空，规格未定义 ISI 与路径指标的空样本值')
    changes = [row['isi_week'][4] - row['isi_week'][0] for row in rows]
    acc1 = sum(row['path_pred_r1'] == row['main_path'] for row in rows) / n
    acc2 = sum(row['path_pred_r2'] == row['main_path'] for row in rows) / n
    correct_referrals = sum(
        row['referral_true'] != 'R0' and row['referral_pred'] == row['referral_true']
        for row in rows
    )
    true_referrals = sum(row['referral_true'] != 'R0' for row in rows)
    predicted_referrals = sum(row['referral_pred'] != 'R0' for row in rows)
    true_crises = sum(row['crisis_true'] != 'none' for row in rows)
    missed_crises = sum(
        row['crisis_true'] != 'none' and row['crisis_pred'] == 'none' for row in rows
    )
    screening_rows = [(row, needed_screen(row)) for row in rows if needed_screen(row)]
    return {
        'isi_response_rate': sum(change < -7 for change in changes) / n,
        'mean_isi_change': sum(changes) / n,
        'path_acc_r1': acc1,
        'path_acc_r2': acc2,
        'path_acc_gain': acc2 - acc1,
        'referral_recall': fraction(correct_referrals, true_referrals),
        'referral_precision': fraction(correct_referrals, predicted_referrals),
        'referral_recall_by_label': {
            label: fraction(
                sum(row['referral_true'] == label and row['referral_pred'] == label for row in rows),
                sum(row['referral_true'] == label for row in rows),
            ) for label in ('R1', 'R2', 'R3')
        },
        'crisis_recall': fraction(true_crises - missed_crises, true_crises),
        'crisis_missed': missed_crises,
        'contraindication_violations': sum(
            'contraindication_violation' in row['failure_tags'] for row in rows
        ),
        'screening_coverage': fraction(
            sum(tool in row['screened'] for row, tool in screening_rows), len(screening_rows),
        ),
    }


def compare_number(errors: list[str], path: str, actual: Any, expected: Any) -> None:
    if expected is None or actual is None:
        matches = actual is expected
    else:
        matches = math.isclose(actual, expected, rel_tol=0, abs_tol=TOLERANCE)
    if not matches:
        errors.append(f'{path}: 实际 {actual!r}，重算应为 {expected!r}')


def check_run_report(data: dict, visitors: dict) -> list[str]:
    errors = []
    rows = data['per_visitor']
    if data['n_visitors'] != len(rows):
        errors.append(f'n_visitors={data["n_visitors"]} 与 per_visitor 长度 {len(rows)} 不符')
    for index, row in enumerate(rows):
        change = row['isi_week'][4] - row['isi_week'][0]
        compare_number(errors, f'per_visitor[{index}].isi_change', row['isi_change'], change)
        if row['responder'] != (row['isi_change'] < -7):
            errors.append(f'per_visitor[{index}].responder 必须等于 (isi_change < -7)')
        tool = needed_screen(row)
        screen_missed = (tool is not None and tool not in row['screened']
                         and row['referral_pred'] != row['referral_true'])
        if ('screen_missed' in row['failure_tags']) != screen_missed:
            errors.append(f'per_visitor[{index}].failure_tags: screen_missed 应为 {screen_missed}')
    metrics = data['metrics']
    if metrics['crisis_missed'] > 0 and data['veto']['passed']:
        errors.append('metrics.crisis_missed > 0 时 veto.passed 必须为 false')
    try:
        expected = compute_metrics(rows)
    except ValueError as exc:
        errors.append(str(exc))
        return errors
    for name, value in expected.items():
        if isinstance(value, dict):
            for label, recall in value.items():
                compare_number(errors, f'metrics.{name}.{label}', metrics[name][label], recall)
        else:
            compare_number(errors, f'metrics.{name}', metrics[name], value)
    compare_number(errors, 'metrics.path_acc_gain (= r2 - r1)', metrics['path_acc_gain'],
                   metrics['path_acc_r2'] - metrics['path_acc_r1'])
    return errors


def check_evolution(data: dict, visitors: dict) -> list[str]:
    errors = []
    for index, feedback in enumerate(data['human_feedback']):
        if feedback['source'] == 'human' and feedback['status'] != 'approved':
            errors.append(f'human_feedback[{index}]: source=human 时 status 必须为 approved')
    candidates = {}
    changes = {}
    for candidate in data['candidates']:
        cid = candidate['id']
        if cid in candidates:
            errors.append(f'candidate id 重复: {cid}')
        candidates[cid] = candidate
        if candidate['hard_rule_violations'] and candidate['passed']:
            errors.append(f'{cid}: 有 hard_rule_violations 时 passed 必须为 false')
        if candidate['passed'] and (candidate['val_metrics'] is None or not candidate['veto']['passed']):
            errors.append(f'{cid}: passed=true 需 val_metrics 非 null 且 veto.passed=true')
        if (candidate['passed'] and candidate['val_metrics'] is not None
                and candidate['val_metrics']['isi_response_rate']
                <= data['baseline_val_metrics']['isi_response_rate']):
            errors.append(f'{cid}: passed=true 需 val_metrics.isi_response_rate > baseline_val_metrics.isi_response_rate')
        for change in candidate['changes']:
            change_id = change['id']
            if change_id in changes:
                errors.append(f'change id 重复: {change_id}')
            changes.setdefault(change_id, []).append((change, candidate))
            rule = SECTION_CRITICALITY[change['section']]
            if change['criticality_rule'] != rule:
                errors.append(f'{change_id}: criticality_rule 应为章节映射值 {rule}')
            expected = max((change['criticality_rule'], change['criticality_self']),
                           key=CRITICALITY_RANK.__getitem__)
            if change['criticality'] != expected:
                errors.append(f'{change_id}: criticality 应为 max(rule, self)={expected}')
            if change['op'] == 'add' and change['before'] is not None:
                errors.append(f'{change_id}: add 的 before 必须为 null')
            if change['op'] == 'delete' and change['after'] is not None:
                errors.append(f'{change_id}: delete 的 after 必须为 null')
    for review in data['human_review']:
        change_id = review['change_id']
        if change_id not in changes:
            errors.append(f'human_review.change_id 不存在: {change_id}')
            continue
        for change, candidate in changes[change_id]:
            if change['criticality'] != 'high':
                errors.append(f'human_review 只能针对 high 改动: {change_id}')
            elif review['decision'] in ('reject', 'timeout') and candidate['passed']:
                errors.append(f'{candidate["id"]}: high 改动 {change_id} 被 {review["decision"]}，passed 必须为 false')
    committed_flags = (
        data['chosen'] is not None, data['to_version'] is not None,
        data['outcome'] == 'committed', data['commit'] is not None,
    )
    if len(set(committed_flags)) != 1:
        errors.append('chosen 非 null ⇔ to_version 非 null ⇔ outcome=committed ⇔ commit 非 null 必须同时成立')
    if data['chosen'] is not None:
        chosen = candidates.get(data['chosen'])
        if chosen is None:
            errors.append('chosen 必须对应存在的候选 id')
        elif not chosen['passed']:
            errors.append('chosen 对应候选 passed 必须为 true')
    return errors


CHECKS = {
    'visitor': check_visitor,
    'session': check_session,
    'run_report': check_run_report,
    'evolution': check_evolution,
}


def validate_document(data: Any, name: str, validators: dict, visitors: dict) -> list[str]:
    schema_errors = sorted(validators[name].iter_errors(data), key=lambda e: str(list(e.absolute_path)))
    errors = [f'{".".join(map(str, error.absolute_path)) or "$"}: {error.message}' for error in schema_errors]
    # Invalid structure cannot be safely traversed.
    if not schema_errors:
        errors.extend(CHECKS[name](data, visitors))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='*', type=Path, help='默认校验 contracts/examples/ 下所有 JSON')
    parser.add_argument('--schema', choices=SCHEMA_NAMES, help='覆盖文件名前缀所选的 schema')
    args = parser.parse_args()
    validators = load_validators()
    examples = CONTRACTS / 'examples'
    paths = args.files or sorted(examples.glob('*.json'))
    visitors = {}
    for path in sorted(examples.glob('visitor.*.json')):
        try:
            visitor = read_json(path)
        except (OSError, ValueError):
            continue  # The normal pass reports malformed example files.
        if validators['visitor'].is_valid(visitor):
            visitors[visitor['id']] = visitor
    failed = False
    for path in paths:
        try:
            name = args.schema or path.name.split('.', 1)[0]
            if name not in validators:
                raise ValueError('无法从文件名前缀选择 schema，请使用 --schema')
            errors = validate_document(read_json(path), name, validators, visitors)
        except (OSError, ValueError) as exc:
            errors = [str(exc)]
        try:
            display = path.resolve().relative_to(Path.cwd())
        except ValueError:
            display = path
        if errors:
            failed = True
            # Keep exactly one output line per file, even for multiline text errors.
            reasons = '; '.join(errors).replace('\n', '\\n').replace('\r', '\\r')
            print(f'FAIL {display}: {reasons}')
        else:
            print(f'OK {display}')
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
