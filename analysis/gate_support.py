"""Shared no-git support for the bounded gate-fix experiment."""
from __future__ import annotations
import argparse
import asyncio
from collections import Counter
from contextlib import ExitStack
from contextvars import ContextVar
from dataclasses import asdict, replace
from datetime import datetime
import difflib
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import time
from types import SimpleNamespace
from unittest.mock import patch

from contracts.validate import compute_metrics, load_validators, validate_document
from engine.config import load_dotenv
from engine.integ_trial import Meter, RequestBudget, RequestBudgetExceeded, VISITOR, COMPONENT, write_json
from engine.run import build_deps
from engine.session import SessionRunner
from engine.playbook import Playbook, parse_sections
from engine.reporting import build_report
from engine.adapters_sim import S2RendererClient, S2VisitorSim, S2Screening, S2OutcomeModel
from engine.evolve.config import load_config as evolve_config
from engine.evolve.pipeline import evolve
from engine.evolve.evidence import run_evidence
from engine.evolve.playbook import Playbook as EditablePlaybook
from scoring.score import score_run, veto as score_veto
from scoring.smoke import load_visitors
from sim.llm import DsConfig

ROOT = Path(__file__).resolve().parents[1]
STAGE = ContextVar('trial_stage', default='startup')
TRACKS = ('ds_thinking', 'ds_nothink', 'jev')
METRICS = ('isi_response_rate', 'mean_isi_change', 'path_acc_r1', 'path_acc_r2',
           'path_acc_gain', 'referral_recall', 'referral_precision', 'screening_coverage',
           'crisis_missed', 'crisis_recall', 'contraindication_violations', 'veto_passed')


def now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def read(path):
    return json.loads(Path(path).read_text())


def log(message):
    print(f'{now()} {message}', flush=True)


class TrialMeter(Meter):
    """Count every HTTP attempt before sending, with no URL, key or body logging."""
    def __init__(self, budget, out, http_limit=16):
        super().__init__(budget)
        self.out = out
        self.limiter = asyncio.Semaphore(http_limit)
        self.active = 0
        self.sequence = 0

    def watch_http(self, client_type):
        original = client_type.send
        async def send(client, request, *args, **kwargs):
            queued = time.perf_counter()
            async with self.limiter:
                try:
                    self.budget.reserve()
                except RequestBudgetExceeded:
                    self.budget_blocked += 1
                    raise
                self.sequence += 1
                self.active += 1
                row = {'id': self.sequence, 'stage': STAGE.get(), 'visitor_id': VISITOR.get(),
                       'component': COMPONENT.get(), 'host': request.url.host,
                       'status': 'started', 'at': datetime.now().astimezone().isoformat(),
                       'inflight': self.active, 'queue_ms': (time.perf_counter()-queued)*1000}
                self.http.append(row)
                with (self.out / 'http-starts.jsonl').open('a') as stream:
                    stream.write(json.dumps(row) + '\n')
                started = time.perf_counter()
                try:
                    response = await original(client, request, *args, **kwargs)
                    row['http_status'] = response.status_code
                    row['status'] = 'ok' if response.status_code < 400 else 'http_error'
                    return response
                except asyncio.CancelledError:
                    row['status'] = 'cancelled'
                    raise
                except Exception as exc:
                    row['status'] = 'error'
                    row['error_type'] = type(exc).__name__
                    raise
                finally:
                    row['ms'] = round((time.perf_counter()-started)*1000, 3)
                    self.active -= 1
                    with (self.out / 'http-results.jsonl').open('a') as stream:
                        stream.write(json.dumps(row) + '\n')
        return patch.object(client_type, 'send', send)


class EffortClient:
    """Only adds the unexposed classifier reasoning_effort constructor argument."""
    def __init__(self, client, effort):
        self.client, self.effort = client, effort
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        kwargs['reasoning_effort'] = self.effort
        return await self.client.chat.completions.create(**kwargs)

    async def close(self):
        await self.client.close()


class SnapshotRepo:
    """Optional no-git storage; SHA is a content digest, never a git commit."""
    def __init__(self, config):
        self.path = Path(config['repo']['path'])
        self.v0 = Path(config['repo']['v0_path'])

    def init(self):
        if not (self.path / 'VERSION').exists():
            self.path.mkdir(parents=True, exist_ok=True)
            self._save(self.v0.read_text(), 'v0')
        return hashlib.sha256(self.read().encode()).hexdigest()

    def _save(self, text, version):
        (self.path / f'{version}.md').write_text(text)
        (self.path / 'playbook.md').write_text(text)
        (self.path / 'VERSION').write_text(version)

    def current_version(self):
        return (self.path / 'VERSION').read_text().strip()

    def read(self):
        return (self.path / 'playbook.md').read_text()

    def commit_version(self, text, summary):
        version = f'v{int(self.current_version()[1:])+1}'
        self._save(text, version)
        return version, hashlib.sha256(text.encode()).hexdigest()


def deps_for(track, meter):
    from engine.adapters_sim import make_s2_sim
    from engine.config import load_config
    override = load_config({'visitor_renderer': 'template', 'concurrency': {'max_sessions': 8},
                            'agent_llm': {'max_inflight': 16}})
    deps = build_deps(config=override, sim=make_s2_sim(override),
                      screening=S2Screening(), outcome=S2OutcomeModel())
    if track == 'ds_thinking':
        deps.classifier.client = EffortClient(deps.classifier.client, 'high')
    assert deps.llm.model_name != 'mock' and 'mock' not in deps.classifier.provider
    assert [j.provider for j in deps.safety.judge.judges] == ['ds_flash', 'jev']
    meter.wrap(deps.llm, 'complete_json', 'agent')
    meter.wrap(deps.classifier, 'classify', 'classifier')
    if hasattr(deps.classifier, 'primary'):
        meter.wrap(deps.classifier.primary, 'classify', 'classifier.jev')
        meter.wrap(deps.classifier.fallback, 'classify', 'classifier.ds_flash')
    for judge in deps.safety.judge.judges:
        meter.wrap(judge, 'classify', f'judge.{judge.provider}')
    return deps


async def close_deps(deps):
    objects = [deps.llm, getattr(deps.sim.client, "_client", None)]
    if hasattr(deps.classifier, 'aclose'):
        objects.append(deps.classifier)
    else:
        objects.append(deps.classifier.client)
    # The default safety judges manage their own per-request clients.
    for obj in objects:
        close = getattr(obj, 'aclose', None) or getattr(obj, 'close', None)
        if close:
            await close()


def rich_load(out, visitors):
    return {'metrics': read(out/'run_report.json')['metrics'],
            'per_visitor': read(out/'run_report.json')['per_visitor'],
            'sessions': {v['id']: read(out/'sessions'/f"{v['id']}.json") for v in visitors},
            'traces': {v['id']: read(out/'trace'/f"{v['id']}.json") for v in visitors},
            'visitors': {v['id']: v for v in visitors}}

