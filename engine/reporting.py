"""S3 reporting boundary: never score error/unknown placeholders as P1/R0.

The unchanged contract cannot encode unknown predictions or an empty cohort. Reports
contain only scoreable sessions; summary.json always records the full attempted cohort,
completion/coverage and safety assessments. An empty cohort produces no run_report.
"""
from collections import Counter
import re


def _provider_switches(trace):
    # Count actual attempts, not cached path_probs or deterministic mock fallbacks.
    # Older traces encode classifier failover in the returned provider string.
    classifier = sum(c.get('provider_switches', int(bool(re.fullmatch(
        r'ds_flash\(fallback:jev_(?:error|timeout|cancelled)\)', c.get('provider', '')))))
        for c in trace.get('llm_calls', []) if c.get('agent') == 'classifier')
    judges = trace.get('all_judge_results', [])
    # The frozen safety chain is ds_flash -> jev. Returning to ds_flash starts a
    # new utterance; a failed last leg followed by a new utterance is not a switch.
    safety = sum(a['provider'] == 'ds_flash' and a['status'] != 'ok' and b['provider'] == 'jev'
                 for a, b in zip(judges, judges[1:]))
    return classifier + safety


def summarize(results):
    sessions = [s for s, _ in results]
    calls = [c for _, t in results for c in t['llm_calls']]
    statuses = Counter(s['status'] for s in sessions)
    judges = [r for _, t in results for r in t.get('all_judge_results', [])]
    providers = sorted({r['provider'] for r in judges})
    events = [e for s in sessions for e in s['safety_events']]
    return {
        'attempted': len(sessions), 'completed': statuses['completed'],
        'completion_rate': statuses['completed'] / len(sessions) if sessions else None,
        'error_count': statuses['error'], 'crisis_exit_count': statuses['crisis_exit'],
        'unknown_path_sessions': sum(bool(t.get('unknown_path_rounds')) for _, t in results),
        'unknown_path_rounds': sum(len(t.get('unknown_path_rounds', [])) for _, t in results),
        'degraded_sessions': sum(any(not f.get('discarded', False) for f in t.get('fallbacks', []))
                                 for _, t in results),
        'provider_switches': sum(_provider_switches(t) for _, t in results),  # 服务商切换次数
        'llm_attempts': len(calls),  # logical agent/classifier attempts, including mock and queue cancellation
        'agent_classifier_requests_started': sum(c.get('request_started', False) for c in calls),
        'call_statuses': dict(Counter(c['status'] for c in calls)),
        'finish_reasons': dict(Counter(c.get('finish_reason') or 'unavailable' for c in calls)),
        'discarded_calls': sum(c.get('discarded', False) for c in calls),
        'safety_summary': {
            'judge_provider': '+'.join(providers) or 'none',
            'judge_calls': len(judges),
            'judge_fallbacks': sum(r['status'] != 'ok' for r in judges),
            'safety_checks': sum(e['action'] == 'safety_check' for e in events),
            'crisis_protocols': sum(e['action'] == 'crisis_protocol' for e in events),
        },
        'report_scope': 'scoreable sessions only; full attempted cohort is in summary',
    }


def build_report(visitors, results, *, scorer, **kwargs):
    summary = summarize(results)
    included, excluded = [], []
    for session, trace in results:
        reason = ('session_error' if session['status'] == 'error' else
                  'unknown_path' if trace.get('unknown_path_rounds')
                  or any(r['path_confidence'] is None for r in session['rounds']) else None)
        if reason:
            excluded.append({'visitor_id': session['visitor_id'], 'reason': reason})
        else:
            included.append(session)
    summary.update(scored=len(included), excluded=excluded,
                   scoring_coverage=len(included) / len(results) if results else None)
    # Keep full-cohort crisis misses visible even if error/unknown sessions cannot be scored.
    summary['crisis_missed_all_attempts'] = sum(
        visitors[s['visitor_id']]['crisis']['level'] != 'none'
        and all(r['crisis_level'] == 'none' for r in s['rounds'])
        and all(e['level'] == 'none' for e in s['safety_events']) for s, _ in results)
    summary['evaluation_complete'] = not excluded
    if not included:
        summary['report_unavailable'] = 'No scoreable sessions; contract has no empty-cohort metrics.'
        return None, summary
    report = scorer(visitors, included, **kwargs)
    # These existing fields cover ALL attempts, including none judgements and failed chain legs.
    report['safety_summary'] = summary['safety_summary']
    if excluded:
        # No contract veto code exists for incomplete evaluation. False is representable;
        # the specific reason and excluded IDs remain in the mandatory companion summary.
        report['veto']['passed'] = False
    return report, summary
