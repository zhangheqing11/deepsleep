"""Replay existing visitor-turn prefixes through the frozen path classifiers.

No dialogue generation, hidden-label prompting, provider fallback or automatic retry.
Dry run needs neither credentials nor optional SDKs. --resume only fills unattempted
pairs; an interrupted request remains charged to the budget and is not retried.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from contextvars import ContextVar
from datetime import datetime, timezone
from difflib import SequenceMatcher
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import statistics
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.classifier import (  # noqa: E402
    PATHS, PROMPT_PATH, DsFlashPathClassifier, JevPathClassifier,
    make_state, render_dialogue,
)
from engine.telemetry import CURRENT_CALL  # noqa: E402

CONFIGS = ("ds_flash_thinking", "ds_flash_nothink", "jev")
DEFAULT_SOURCES = [
    Path('/Users/zhangheqing/bohack/ds-integ/var/integ/integ-real-split/sessions'),
    Path('/Users/zhangheqing/bohack/ds-integ/var/integ/integ-real-merged/sessions'),
    Path('/Users/zhangheqing/bohack/deepsleep/.claude/worktrees/engine-session-b8fd78/var'),
]
CAPTURE = ContextVar('classifier_compare_capture', default=None)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def normal_text(text):
    return re.sub(r'[^\w]', '', text).lower()


def match_clue(text, clue):
    """Conservative lexical match, not a semantic or clinically validated label."""
    actual, expected = normal_text(text), normal_text(clue)
    if not expected:
        return None
    match = SequenceMatcher(None, expected, actual, autojunk=False).find_longest_match()
    coverage = match.size / len(expected)
    if expected in actual or (match.size >= 12 and coverage >= .45):
        return dict(method='exact' if expected in actual else 'contiguous_substring',
                    matched_text=expected[match.a:match.a + match.size],
                    match_chars=match.size, clue_coverage=coverage)
    return None


def session_prefixes(session, card):
    dialogue, prefixes, events = [], [], []
    seen_clues = set()
    for rnd in session['rounds']:
        for entry in rnd['transcript']:
            if entry['speaker'] in ('agent', 'visitor'):
                dialogue.append({k: entry[k] for k in ('speaker', 'text')})
            if entry['speaker'] != 'visitor':
                continue
            k = len(prefixes) + 1
            for clue in card['clues']:
                if clue['supports'] != card['main_path'] or clue['id'] in seen_clues:
                    continue
                evidence = match_clue(entry['text'], clue['content'])
                if evidence:
                    events.append(dict(k=k, round=rnd['round'], clue_id=clue['id'],
                                       clue_text=clue['content'], visitor_text=entry['text'],
                                       revealed_id_agrees=clue['id'] in entry.get('revealed_clue_ids', []),
                                       **evidence))
                    seen_clues.add(clue['id'])
            # Hash exactly what all classifiers receive, not labels or run identifiers.
            prefixes.append(dict(sample_id=digest(render_dialogue(dialogue)), k=k,
                                 round=rnd['round'], turn=entry['turn'], dialogue=list(dialogue)))
    return prefixes, events


def collect_dataset(sources, cards_dir, target=150, seed=20261114):
    sessions, samples, excluded = [], {}, []
    seen_files, seen_sessions = set(), {}
    raw_prefixes = 0
    for source in sources:
        dirs = [source] if source.name == 'sessions' else sorted(source.rglob('sessions'))
        if not dirs:
            raise ValueError(f'No sessions directories: {source}')
        for directory in dirs:
            manifest_path = directory.parent / 'manifest.json'
            manifest = read_json(manifest_path) if manifest_path.exists() else {}
            for path in sorted(directory.glob('*.json')):
                if path.resolve() in seen_files:
                    continue
                seen_files.add(path.resolve())
                session = read_json(path)
                model = session.get('models', {}).get('agent', '')
                if not model or 'mock' in model.lower() or manifest.get('mock') is True:
                    excluded.append(dict(source=str(path), reason='mock_or_unknown_agent'))
                    continue
                card_path = cards_dir / (session['visitor_id'] + '.json')
                card = read_json(card_path)
                # Verify the source checkout's card when available; never silently relabel.
                source_card = next((p / 'sim/visitors' / card_path.name for p in path.parents
                                    if (p / 'sim/visitors' / card_path.name).exists()), None)
                if source_card and read_json(source_card) != card:
                    raise ValueError(f'Visitor card mismatch: {source_card}')
                prefixes, clues = session_prefixes(session, card)
                raw_prefixes += len(prefixes)
                if not prefixes:
                    excluded.append(dict(source=str(path), reason='no_visitor_utterance'))
                    continue
                fingerprint = digest([card['id'], [p['sample_id'] for p in prefixes]])
                if fingerprint in seen_sessions:
                    seen_sessions[fingerprint]['duplicate_sources'].append(str(path))
                    continue
                sid = session['session_id']
                if any(s['session_id'] == sid for s in sessions):
                    sid += ':' + fingerprint[:8]
                row = dict(session_id=sid, source=str(path), source_sha256=digest(session),
                           duplicate_sources=[], run_id=session['run_id'], visitor_id=card['id'],
                           models=session['models'], status=session['status'],
                           main_path=card['main_path'], secondary_path=card.get('secondary_path'),
                           defensiveness=card['persona']['defensiveness'],
                           card_source=str(card_path), card_sha256=digest(card),
                           first_clue_k=min((c['k'] for c in clues), default=None),
                           clue_matches=clues, prefixes=[])
                for p in prefixes:
                    samples.setdefault(p['sample_id'], dict(sample_id=p['sample_id'], dialogue=p['dialogue']))
                    row['prefixes'].append({k: v for k, v in p.items() if k != 'dialogue'})
                sessions.append(row)
                seen_sessions[fingerprint] = row
    if not sessions:
        raise ValueError('No real-agent sessions found')
    # Each session is a sampling stratum. Retain endpoints and immediate clue pairs.
    selected = {s['prefixes'][-1]['sample_id'] for s in sessions}
    for s in sessions:
        k = s['first_clue_k']
        if k is not None:
            selected.add(s['prefixes'][k - 1]['sample_id'])
            if k > 1:
                selected.add(s['prefixes'][k - 2]['sample_id'])
    if len(selected) > target:
        raise ValueError('Target too small to retain all session finals and clue pairs')
    rng = random.Random(seed)
    queues = []
    for s in sessions:
        pool = [p['sample_id'] for p in s['prefixes'] if p['sample_id'] not in selected]
        rng.shuffle(pool)
        queues.append(pool)
    while len(selected) < min(target, len(samples)):
        order = list(range(len(queues)))
        rng.shuffle(order)
        for i in order:
            while queues[i] and queues[i][-1] in selected:
                queues[i].pop()
            if queues[i] and len(selected) < target:
                selected.add(queues[i].pop())
    for s in sessions:
        for p in s['prefixes']:
            p['selected'] = p['sample_id'] in selected
    return dict(sessions=sessions, samples=[samples[k] for k in sorted(selected)],
                excluded=excluded, counts=dict(files_seen=len(seen_files), raw_prefixes=raw_prefixes,
                    sessions=len(sessions), unique_prefixes=len(samples), selected_unique_prefixes=len(selected),
                    selected_occurrences=sum(p['selected'] for s in sessions for p in s['prefixes'])),
                seed=seed, target=target,
                sampling='session-stratified round-robin; final and immediate clue pair mandatory; global input dedup')


def load_env(path):
    """Read only needed fields; no shell execution, logging, or environment dump."""
    wanted = {'DS_API_KEY', 'DS_BASE_URL', 'DS_MODEL', 'TYPESAFE_API_KEY'}
    for line in path.read_text().splitlines():
        match = re.match(r'^\s*(?:export\s+)?([A-Z_]+)\s*=\s*(.*?)\s*$', line)
        if match and match[1] in wanted:
            value = match[2]
            if value[:1] in ('"', "'") and value[-1:] == value[:1]:
                value = value[1:-1]
            else:
                value = re.split(r'\s+#', value, maxsplit=1)[0]
            os.environ[match[1]] = value
    if any(not os.environ.get(k, '').strip() for k in wanted):
        raise ValueError('Missing required classifier credentials/configuration')


class DSRecorder:
    """Transparent SDK proxy: only add explicit high effort and capture response evidence."""
    def __init__(self, client, high):
        self.client, self.high = client, high
        self.chat = SimpleNamespace(completions=self)

    async def create(self, **kwargs):
        if self.high:
            kwargs['reasoning_effort'] = 'high'
        response = await self.client.chat.completions.create(**kwargs)
        row = CAPTURE.get()
        row['response_model'] = response.model
        row['raw_output'] = response.choices[0].message.content
        usage = response.usage
        row['usage'] = usage.model_dump() if usage else None
        row['reasoning_chars'] = len(getattr(response.choices[0].message, 'reasoning_content', '') or '')
        return response


class JevRecorder:
    def __init__(self, client):
        self.client = client

    async def system_one(self, **kwargs):
        response = await self.client.system_one(**kwargs)
        row = CAPTURE.get()
        row['response_model'] = response.model
        row['usage'] = response.usage.model_dump() if response.usage else None
        row['raw_output'] = response.model_dump()
        return response


async def run_calls(document, output, concurrency=16, budget=520):
    from openai import AsyncOpenAI
    from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy
    if not 1 <= concurrency <= 16 or not 1 <= budget <= 520:
        raise ValueError('Concurrency must be 1..16, total budget 1..520')
    timeout = 15.0
    ds = AsyncOpenAI(api_key=os.environ['DS_API_KEY'], base_url=os.environ['DS_BASE_URL'],
                     timeout=timeout, max_retries=0)
    jev = AsyncTypeSafeClient(api_key=os.environ['TYPESAFE_API_KEY'], timeout=timeout,
                             retry=RetryPolicy(max_retries=0))
    classifiers = {
        CONFIGS[0]: DsFlashPathClassifier(timeout, thinking='enabled', client=DSRecorder(ds, True)),
        CONFIGS[1]: DsFlashPathClassifier(timeout, thinking='disabled', client=DSRecorder(ds, False)),
        'jev': JevPathClassifier(timeout, client=JevRecorder(jev)),
    }
    document['request_config'] = dict(ds_model=os.environ['DS_MODEL'], timeout_s=timeout,
        concurrency=concurrency, max_retries=0, provider_fallback=False,
        ds_flash_thinking={'thinking': {'type': 'enabled'}, 'reasoning_effort': 'high'},
        ds_flash_nothink={'thinking': {'type': 'disabled'}})
    existing = {(r['config'], r['sample_id']) for r in document['results']}
    jobs = [(c, s) for s in document['dataset']['samples'] for c in CONFIGS
            if (c, s['sample_id']) not in existing]
    if len(document['results']) + len(jobs) > budget:
        raise ValueError('Required calls exceed total budget')
    random.Random(document['dataset']['seed']).shuffle(jobs)
    semaphore = asyncio.Semaphore(concurrency)

    async def one(config, sample):
        async with semaphore:
            row = dict(config=config, sample_id=sample['sample_id'], status='inflight',
                       started_at=datetime.now(timezone.utc).isoformat(), usage=None)
            document['results'].append(row)
            # Reserve budget before request; crash-safe resume never reissues this pair.
            write_json(output, document)
            token = CAPTURE.set(row)
            telemetry = {}
            telemetry_token = CURRENT_CALL.set(telemetry)
            started = time.perf_counter()
            try:
                # Same _predict + make_state as _Bounded.classify, retaining safe error types.
                weights, attitude = await asyncio.wait_for(
                    classifiers[config]._predict(render_dialogue(sample['dialogue'])), timeout)
                state = make_state(weights, attitude, 'ok', config, (time.perf_counter()-started)*1000)
                row.update(state.to_dict(), top=state.top)
            except Exception as exc:
                is_timeout = isinstance(exc, TimeoutError) or 'timeout' in type(exc).__name__.lower()
                row.update(status='timeout' if is_timeout else 'error', error_type=type(exc).__name__,
                           http_status=getattr(exc, 'status_code', None),
                           latency_ms=round((time.perf_counter()-started)*1000, 1), top=None,
                           weights=None, attitude=None, uncertainty=None)
            finally:
                CAPTURE.reset(token)
                CURRENT_CALL.reset(telemetry_token)
                row['telemetry'] = {k: v for k, v in telemetry.items() if k != 'usage'}
                write_json(output, document)
            completed = sum(r['status'] != 'inflight' for r in document['results'])
            if completed % 30 == 0:
                print(f'Completed {completed}/{len(document["dataset"]["samples"])*3} requests', flush=True)

    try:
        await asyncio.gather(*(one(*job) for job in jobs))
    finally:
        await ds.close()
        await jev.aclose()


def mean(values):
    return statistics.fmean(values) if values else None


def usage_tokens(row):
    usage = row.get('usage') or {}
    if usage.get('total_tokens') is not None:
        return usage['total_tokens']
    if usage.get('input_tokens') is not None and usage.get('output_tokens') is not None:
        return usage['input_tokens'] + usage['output_tokens']
    return None


def quantile(values, q):
    if not values:
        return None
    v = sorted(values)
    pos = (len(v)-1)*q
    lo, hi = math.floor(pos), math.ceil(pos)
    return v[lo] + (v[hi]-v[lo])*(pos-lo)


def bootstrap(groups, statistic=mean, repetitions=2000, seed=20261114):
    """Resample whole sessions; retain multiplicity (never dedup bootstrap draws)."""
    groups = [g for g in groups if g]
    flat = [x for group in groups for x in group]
    estimate = statistic(flat)
    if not groups:
        return dict(value=None, ci95=None, n=0, sessions=0)
    rng = random.Random(seed)
    draws = [statistic([x for g in rng.choices(groups, k=len(groups)) for x in g])
             for _ in range(repetitions)]
    return dict(value=estimate, ci95=[quantile(draws, .025), quantile(draws, .975)],
                n=len(flat), sessions=len(groups))


def summarize(document, repetitions=2000):
    sessions = document['dataset']['sessions']
    results = {(r['config'], r['sample_id']): r for r in document['results']}
    metrics = {}
    for config in CONFIGS:
        groups = defaultdict(lambda: defaultdict(list))
        curve = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        clue_rows, attitude_table = [], Counter()
        for session in sessions:
            sid, truth = session['session_id'], session['main_path']
            for p in session['prefixes']:
                r = results.get((config, p['sample_id']))
                if r is None:
                    continue
                ok = r['status'] == 'ok'
                correct = int(ok and r['top'] == truth)
                groups['accuracy_all'][sid].append(correct)
                groups['timeout_rate'][sid].append(int(r['status'] == 'timeout'))
                groups['error_rate'][sid].append(int(r['status'] not in ('ok', 'timeout')))
                curve[p['k']]['accuracy_all'][sid].append(correct)
                if 'latency_ms' in r:
                    groups['latency_ms'][sid].append(r['latency_ms'])
                    groups['over_6s_rate'][sid].append(int(r['latency_ms'] > 6000))
                if p['k'] == len(session['prefixes']):
                    groups['final_accuracy_all'][sid].append(correct)
                    if ok:
                        groups['final_accuracy_valid'][sid].append(correct)
                    groups['final_accuracy_' + truth][sid].append(correct)
                if not ok:
                    continue
                groups['accuracy_valid'][sid].append(correct)
                groups['brier'][sid].append(sum((r['weights'][p] - int(p == truth))**2 for p in PATHS))
                entropy = r['uncertainty']
                groups['entropy'][sid].append(entropy)
                groups['entropy_correct' if correct else 'entropy_wrong'][sid].append(entropy)
                band = 'low' if entropy < 1/3 else 'mid' if entropy < 2/3 else 'high'
                groups['error_entropy_' + band][sid].append(1-correct)
                curve[p['k']]['entropy'][sid].append(entropy)
                curve[p['k']]['true_weight'][sid].append(r['weights'][truth])
                attitude_table[(session['defensiveness'], r['attitude'])] += 1
                if session['defensiveness'] in ('high', 'low'):
                    expected = 'resistant' if session['defensiveness'] == 'high' else 'cooperative'
                    groups['attitude_agreement'][sid].append(int(r['attitude'] == expected))
                groups['resistant_' + session['defensiveness']][sid].append(int(r['attitude'] == 'resistant'))
                total = usage_tokens(r)
                if total is not None:
                    groups['tokens'][sid].append(total)
            k = session['first_clue_k']
            if k is not None and k > 1:
                before, after = [results.get((config, session['prefixes'][i-1]['sample_id'])) for i in (k-1, k)]
                if before and after and before['status'] == after['status'] == 'ok':
                    delta = after['weights'][truth] - before['weights'][truth]
                    groups['clue_weight_delta'][sid].append(delta)
                    groups['clue_pre_accuracy'][sid].append(int(before['top'] == truth))
                    groups['clue_post_accuracy'][sid].append(int(after['top'] == truth))
                    if before['top'] != truth:
                        groups['clue_immediate_correction'][sid].append(int(after['top'] == truth))
                    clue_rows.append(dict(session_id=sid, k=k, delta=delta,
                                          before=before['top'], after=after['top']))
        stats = {key: bootstrap(list(g.values()), repetitions=repetitions)
                 for key, g in groups.items()}
        # Call-level point estimates use unique requests; session-cluster CIs use occurrences.
        calls = [r for r in document['results'] if r['config'] == config]
        latencies = [r['latency_ms'] for r in calls if 'latency_ms' in r]
        tokens = [usage_tokens(r) for r in calls if usage_tokens(r) is not None]
        stats['calls'] = dict(n=len(calls), statuses=dict(Counter(r['status'] for r in calls)),
                             tokens=dict(n=len(tokens), total=sum(tokens), mean=mean(tokens),
                                         p50=quantile(tokens, .5), p95=quantile(tokens, .95),
                                         max=max(tokens, default=None)),
                             over_6s=sum(v > 6000 for v in latencies),
                             latency_ms={k: fn(latencies) for k, fn in
                                 [('mean', mean), ('p50', lambda a: quantile(a,.5)),
                                  ('p95', lambda a: quantile(a,.95)), ('max', lambda a: max(a, default=None))]})
        stats['latency_cluster'] = {key: bootstrap(list(groups['latency_ms'].values()), fn, repetitions)
            for key, fn in [('p50', lambda a: quantile(a,.5)), ('p95', lambda a: quantile(a,.95)),
                            ('max', lambda a: max(a, default=None))]}
        stats['curve'] = {str(k): {name: bootstrap(list(g.values()), repetitions=repetitions)
                                  for name, g in metrics_k.items()} for k, metrics_k in sorted(curve.items())}
        stats['clue_pairs'] = clue_rows
        stats['attitude_counts'] = [{'defensiveness': d, 'attitude': a, 'n': n}
                                   for (d, a), n in sorted(attitude_table.items())]
        metrics[config] = stats
    return metrics


def fmt(metric, percent=False):
    if not metric or metric['value'] is None:
        return 'NA'
    scale, suffix = (100, '%') if percent else (1, '')
    lo, hi = metric['ci95']
    return f"{metric['value']*scale:.3f}{suffix} [{lo*scale:.3f}, {hi*scale:.3f}]"


def write_report(document, path):
    dataset, metrics = document['dataset'], document.get('metrics', {})
    counts = dataset['counts']
    sessions = dataset['sessions']
    lines = ['# 路径分类器三方对比', '', f"生成时间：{document['created_at']}。仅陈述本次观测，不作选型推荐。", '',
        '## 样本与方法', '',
        f"扫描 {counts['files_seen']} 份会谈文件；真实 agent 会谈去重后 {len(sessions)} 场，"
        f"{len({s['visitor_id'] for s in sessions})} 张不同来访卡。原始来访发言位置 {counts['raw_prefixes']} 个，"
        f"按分类器实际输入全文去重后 {counts['unique_prefixes']} 个前缀，选取 {counts['selected_unique_prefixes']} 个唯一前缀，"
        f"对应 {counts['selected_occurrences']} 个会谈内位置。三方使用完全相同的输入。", '',
        '按会谈分层，固定 seed=20261114；保留每场最后前缀及首次线索前后相邻前缀，其余位置在各会谈间轮转随机抽样。'
        '跨轮累计对话；k 表示整场第 k 个来访发言，不在第二轮重新计数。相同输入只调用一次，结果映射回所有对应会谈位置。', '',
        '只发送 agent/visitor 的原文，不发送隐藏标签、量表、线索 ID 或原分类结果；与现有 render_dialogue 一致，排除 safety/tool 文本。'
        '以卡片 main_path 为主路径真值，secondary_path 另存，不计为主路径正确。'
        '最高权重并列时沿用现有 PathState.top 的 P1→P5 顺序打破并列；完全均匀的有效响应因此预测为 P1。', '',
        '| 来源 run | 会谈数 | 状态 | agent 模型 | 来访模型 |', '|---|---:|---|---|---|']
    for run in sorted({s['run_id'] for s in sessions}):
        ss = [s for s in sessions if s['run_id'] == run]
        lines.append(f"| {run} | {len(ss)} | {dict(Counter(s['status'] for s in ss))} | "
                     f"{dict(Counter(s['models']['agent'] for s in ss))} | {dict(Counter(s['models']['visitor'] for s in ss))} |")
    lines += ['', f"主路径分布（会谈）：{dict(sorted(Counter(s['main_path'] for s in sessions).items()))}。"
              f"defensiveness：{dict(Counter(s['defensiveness'] for s in sessions))}。", '',
        f"文本匹配到主路径线索的会谈 {sum(s['first_clue_k'] is not None for s in sessions)} 场；"
        f"其中首条发言即出现 {sum(s['first_clue_k'] == 1 for s in sessions)} 场（无前测，不估计增量）。"
        '匹配去标点后使用完整包含，或最长连续公共片段 ≥12 字且覆盖卡片线索 ≥45%。只匹配来访发言，'
        '每条匹配的文本证据与 revealed_clue_ids 一致性均保存在 JSON；该规则可能漏掉改述或误解否定。', '',
        '95% CI：固定 seed，按整场会谈有放回抽样 2,000 次，取 2.5%/97.5% 分位数。'
        '超时/错误按主路径不正确计入准确率；Brier、熵、态度及线索增量仅使用有效响应。'
        'Brier 为五类平方误差之和（0–2，均匀预测为 0.8）；熵 H/ln(5) 在 0–1。'
        '这些区间为会谈抽样的不确定性，不覆盖同一输入重复调用的随机性。', '',
        f"原 prompt SHA-256：`{document['prompt_sha256']}`；代码版本：`{document['git_commit']}`。", '']
    if not metrics:
        lines += ['本文件为 dry-run 样本审计；未调用 API，没有模型成绩。']
    else:
        lines += ['## 三方数据', '',
            f"请求参数：`{json.dumps(document['request_config'], ensure_ascii=False)}`。"
            f"累计预留请求 {len(document['results'])}/520；无重试、无跨模型兜底。", '',
            '所有方括号为会谈 bootstrap 95% CI。准确率与校准按会谈内抽到的位置统计；调用数按唯一输入统计。', '',
            '| 指标 | ds flash 思考开 | ds flash 思考关 | Jev |', '|---|---|---|---|']
        fields = [('最终前缀主路径准确率', 'final_accuracy_all', True),
                  ('有效最终响应准确率', 'final_accuracy_valid', True),
                  ('所有所选回合准确率', 'accuracy_all', True), ('Brier', 'brier', False),
                  ('平均归一化熵', 'entropy', False), ('线索前后主路径权重增量', 'clue_weight_delta', False),
                  ('线索前准确率', 'clue_pre_accuracy', True), ('线索后即时准确率', 'clue_post_accuracy', True),
                  ('线索前错误者即时纠正率', 'clue_immediate_correction', True),
                  ('态度与 high/low 卡片粗标签一致率', 'attitude_agreement', True),
                  ('平均 token/位置（有 usage）', 'tokens', False)]
        for label, key, percent in fields:
            lines.append('| ' + label + ' | ' + ' | '.join(fmt(metrics[c].get(key), percent) for c in CONFIGS) + ' |')
        for label, accessor in [
            ('唯一调用数', lambda m: str(m['calls']['n'])),
            ('状态计数', lambda m: str(m['calls']['statuses'])),
            ('若 6 秒截止：超过 6 秒的调用数', lambda m: str(m['calls']['over_6s'])),
            ('实际调用延迟 mean / p50 / p95 / max（ms）', lambda m: ' / '.join(
                f"{m['calls']['latency_ms'][k]:.1f}" for k in ('mean','p50','p95','max'))),
            ('有效线索前后对数', lambda m: str(len(m['clue_pairs']))),
            ('唯一调用 token：总计 / 均值 / p50 / p95 / max', lambda m: ' / '.join(
                'NA' if m['calls']['tokens'][k] is None else f"{m['calls']['tokens'][k]:.1f}"
                for k in ('total', 'mean', 'p50', 'p95', 'max'))),
        ]:
            lines.append('| ' + label + ' | ' + ' | '.join(accessor(metrics[c]) for c in CONFIGS) + ' |')
        lines += ['', '延迟从取得并发槽后计时，排除本地排队；若有 15 秒未完成的请求，将按右删失处理，'
                  '该条延迟只代表等到截止的时间。6 秒计数是本次请求的反事实截止统计，早于 6 秒的错误另计。'
                  '共享输入只请求一次；下面的延迟 CI 则将请求映射回会谈位置后按会谈重抽样，因此与唯一调用分位数可不同。', '',
                  '| 延迟（ms，按会谈位置） | 思考开 | 思考关 | Jev |', '|---|---|---|---|']
        for k in ('p50', 'p95', 'max'):
            lines.append('| ' + k + ' | ' + ' | '.join(fmt(metrics[c]['latency_cluster'][k]) for c in CONFIGS) + ' |')
        lines += ['', '## 逐回合曲线', '',
            '各 k 的样本来自该回合被抽中的会谈，分母随 k 改变；下表不是固定完整队列的纵向曲线。'
            '括号 n 为会谈位置数，熵和正确路径权重只统计有效响应。', '',
            '| k | 思考开准确率；熵；真值权重 | 思考关准确率；熵；真值权重 | Jev准确率；熵；真值权重 |',
            '|---|---|---|---|']
        ks = sorted({int(k) for c in CONFIGS for k in metrics[c]['curve']})
        for k in ks:
            cells = []
            for c in CONFIGS:
                item = metrics[c]['curve'][str(k)]
                cells.append(f"{fmt(item['accuracy_all'], True)} (n={item['accuracy_all']['n']})；"
                             f"{fmt(item.get('entropy'))}；{fmt(item.get('true_weight'))}")
            lines.append(f"| {k} | " + ' | '.join(cells) + ' |')
        for c in CONFIGS:
            cv = metrics[c]['curve']
            lines += ['', f"{c}：按 k 对齐的准确率依次为 " + ' → '.join(
                f"k{k}={cv[str(k)]['accuracy_all']['value']:.1%}" for k in ks) + '。']
        lines += ['', '## 熵、错误与态度', '',
            '| 指标 | 思考开 | 思考关 | Jev |', '|---|---|---|---|']
        for label, key, percent in [('预测正确时的熵', 'entropy_correct', False),
                ('预测错误时的熵', 'entropy_wrong', False), ('低熵 <1/3 的错误率', 'error_entropy_low', True),
                ('中熵 [1/3,2/3) 的错误率', 'error_entropy_mid', True),
                ('高熵 ≥2/3 的错误率', 'error_entropy_high', True)]:
            lines.append('| '+label+' | '+' | '.join(fmt(metrics[c].get(key), percent) +
                f" (n={metrics[c].get(key, {}).get('n', 0)})" for c in CONFIGS)+' |')
        for c in CONFIGS:
            correct = metrics[c].get('entropy_correct', {}).get('value')
            wrong = metrics[c].get('entropy_wrong', {}).get('value')
            if correct is not None and wrong is not None:
                relation = '高于' if wrong > correct else '低于' if wrong < correct else '等于'
                lines += ['', f"{c}：错误样本的平均熵 {wrong:.3f} {relation}正确样本的 {correct:.3f}。"
                          '各熵区间的样本数见上表，空区间无法比较错误率。']
        lines += ['', '态度粗标签：high→resistant，low→cooperative；mid 不算一致率。'
                  '人格倾向与最近一条发言的态度不是同一目标，该数值不能解释为态度识别准确率。']
        for c in CONFIGS:
            lines += ['', f"{c} 分布：`{json.dumps(metrics[c]['attitude_counts'], ensure_ascii=False)}`。"]
        lines += ['', '## 按会谈的典型错例（描述性选取）', '']
        lookup = {(r['config'], r['sample_id']): r for r in document['results']}
        sample_lookup = {s['sample_id']: s for s in dataset['samples']}
        candidates = []
        for s in sessions:
            final = s['prefixes'][-1]
            wrong = sum(lookup[(c, final['sample_id'])].get('top') not in (None, s['main_path']) for c in CONFIGS)
            if wrong:
                candidates.append((s['first_clue_k'] is not None, wrong, s['session_id'], s))
        chosen, visitors = [], set()
        for _, _, _, s in sorted(candidates, key=lambda x: x[:3], reverse=True):
            if s['visitor_id'] not in visitors:
                chosen.append(s)
                visitors.add(s['visitor_id'])
            if len(chosen) == 3:
                break
        for i, s in enumerate(chosen, 1):
            final = s['prefixes'][-1]
            lines += [f"{i}. **{s['session_id']}**：主路径 {s['main_path']}，次路径 {s['secondary_path']}，"
                      f"首次文本线索 k={s['first_clue_k']}，会谈状态 {s['status']}。"]
            if s['clue_matches']:
                clue = s['clue_matches'][0]
                lines += [f"   卡片：{clue['clue_text']} 实际来访：{clue['visitor_text']}"]
            else:
                lines += ['   未匹配到主路径鉴别线索；隐藏标签不代表对话已经可辨认。']
            lines += [f"   最后发言：{sample_lookup[final['sample_id']]['dialogue'][-1]['text']}"]
            for c in CONFIGS:
                r = lookup[(c, final['sample_id'])]
                trajectory = ' → '.join(f"k{p['k']}:{lookup[(c,p['sample_id'])].get('top') or lookup[(c,p['sample_id'])]['status']}"
                                        for p in s['prefixes'] if p['selected'])
                lines += [f"   {c}：{trajectory}；最终权重 `{r.get('weights')}`。"]
            lines += ['']
    lines += ['', '## 局限与复跑', '',
        '- 这是现有运行记录的回放；包含错误结束、局部 fallback 和规则模拟来访。最终前缀是日志的最后来访发言，并非都完成了两轮会谈。',
        '- 相同来访卡跨运行重复，前缀可能共享开场文本；按会谈 bootstrap 未进一步处理跨会谈同卡相关性，区间可能偏窄。',
        '- 某个小分组若观测全对或全错，经验 bootstrap 区间会退化到单点；这不代表总体错误率已确定为 0% 或 100%。',
        '- 少量会谈、少量卡片及不均衡路径不能代表独立临床人群。隐藏主路径在早期可能尚不可辨认；准确率下降不必然等于忽略已出现的证据。',
        '- 文本匹配不是人工语义标注，线索增量只限匹配到且前后响应有效的会谈；因果关系不能由该前后差推断。',
        '- Jev 沿用现有实现的 Choice 问题和 criteria，DS 使用 JSON chat；系统指令相同，但 API 输出机制不同。',
        '- 仅一次交错回放，没有测同输入多次调用的方差。高熵分组是预定固定区间，空组记 NA。',
        '- raw JSON 保留全部入选输入、出处哈希、卡片标签、线索证据、每次结果/usage 和 CI；不包含凭证。', '',
        '```bash',
        'cd /Users/zhangheqing/bohack/ds-eval',
        '/Users/zhangheqing/bohack/ds-safety/.venv/bin/python analysis/classifier_compare.py --dry-run',
        '/Users/zhangheqing/bohack/ds-safety/.venv/bin/python analysis/classifier_compare.py --resume',
        '/Users/zhangheqing/bohack/ds-safety/.venv/bin/python analysis/classifier_compare.py --analyze-only',
        '```', '',
        '`--dry-run` 写单独的 `.dry-run.json`，不读取 key、不调用 API；首次实测去掉该开关。'
        '`--resume` 使用已有 JSON 中冻结的样本，只补未尝试的配置/前缀；不会重试已失败或中断的请求。'
        '`--analyze-only` 离线重算统计与报告，不调用 API。已有输出不会被普通实测命令覆盖。']
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--analyze-only', action='store_true')
    parser.add_argument('--source', type=Path, action='append')
    parser.add_argument('--cards', type=Path, default=ROOT/'sim/visitors')
    parser.add_argument('--env', type=Path, default=Path('/Users/zhangheqing/bohack/ds-safety/.env'))
    parser.add_argument('--output', type=Path, default=ROOT/'analysis/out/classifier_compare.json')
    parser.add_argument('--report', type=Path, default=Path('/Users/zhangheqing/bohack/research/codex-tasks/clf-compare.md'))
    parser.add_argument('--target', type=int, default=150)
    parser.add_argument('--concurrency', type=int, default=16)
    parser.add_argument('--budget', type=int, default=520)
    args = parser.parse_args(argv)
    if sum((args.dry_run, args.resume, args.analyze_only)) > 1:
        parser.error('Choose only one mode')
    prompt_hash = hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest()
    if args.resume or args.analyze_only:
        document = read_json(args.output)
        if args.resume and document['prompt_sha256'] != prompt_hash:
            parser.error('Prompt changed since experiment started')
        if args.resume and document['classifier_sha256'] != hashlib.sha256((ROOT/'engine/classifier.py').read_bytes()).hexdigest():
            parser.error('Classifier implementation changed since experiment started')
    else:
        if args.output.exists() and not args.dry_run:
            parser.error('Output exists; use --resume or --analyze-only')
        import subprocess
        document = dict(created_at=datetime.now(timezone.utc).isoformat(), prompt_sha256=prompt_hash,
                        git_commit=subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
                        classifier_sha256=hashlib.sha256((ROOT/'engine/classifier.py').read_bytes()).hexdigest(),
                        dataset=collect_dataset(args.source or DEFAULT_SOURCES, args.cards, args.target), results=[])
    if args.dry_run:
        output = args.output.with_name(args.output.stem + '.dry-run.json')
        write_json(output, document)
        print(json.dumps(document['dataset']['counts'], ensure_ascii=False))
        print(f'Dry run only; planned calls={len(document["dataset"]["samples"])*3}; output={output}')
        return
    if not args.analyze_only:
        load_env(args.env)
        if args.resume and document.get('request_config', {}).get('ds_model', os.environ['DS_MODEL']) != os.environ['DS_MODEL']:
            parser.error('DS model changed since experiment started')
        asyncio.run(run_calls(document, args.output, args.concurrency, args.budget))
    import importlib.metadata
    document['runtime'] = dict(python=sys.version.split()[0], packages={
        name: importlib.metadata.version(name) for name in ('openai', 'typesafe-sdk')})
    document['metrics'] = summarize(document)
    write_json(args.output, document)
    write_report(document, args.report)
    print(f'Results: {args.output}\nReport: {args.report}')


if __name__ == '__main__':
    main()
