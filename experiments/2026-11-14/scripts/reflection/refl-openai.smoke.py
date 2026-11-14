"""Final primary-only smoke: one request remains in the authorized budget; no git writes."""
import asyncio
from dataclasses import asdict
import json
import os
from pathlib import Path
import shlex
import sys
import time

ROOT = Path('/Users/zhangheqing/bohack/ds-refl')
sys.path.insert(0, str(ROOT))
from contracts.validate import load_validators
from engine.evolve.config import load_config
from engine.evolve.llm import default_clients
from engine.evolve.reflector import reflect

# Load only required settings in memory; never copy or log keys.
allowed = {'OPENAI_API_KEY', 'OPENAI_BASE_URL', 'REFLECTOR_PROVIDER', 'REFLECTOR_MODEL',
           'REFLECTOR_REASONING_EFFORT', 'REFLECTOR_TIMEOUT_S', 'DS_API_KEY', 'DS_BASE_URL', 'DS_MODEL'}
for line in Path('/Users/zhangheqing/bohack/ds-safety/.env').read_text().splitlines():
    line = line.strip()
    if line.startswith('export '):
        line = line[7:]
    key, sep, value = line.partition('=')
    if sep and key.strip() in allowed:
        parts = shlex.split(value, comments=True)
        os.environ[key.strip()] = ' '.join(parts)


def read(path):
    return json.loads(path.read_text())


async def main():
    config = load_config()
    clients = default_clients(config)
    primary, fallback, error = clients
    report = read(ROOT / 'contracts/examples/run_report.run1.json')
    sessions = {p.stem: read(p) for p in (ROOT / 'engine/fixtures/sessions').glob('*.json')}
    traces = {p.stem: read(p) for p in (ROOT / 'engine/fixtures/trace').glob('*.json')}
    visitors = {v['id']: v for v in (read(p) for p in (ROOT / 'contracts/examples').glob('visitor.*.json'))}
    start = time.perf_counter()
    try:
        result = await reflect(playbook_text=(ROOT / 'engine/playbook_v0.md').read_text(), version='v0',
            run_report=report, sessions=sessions, traces=traces, visitors=visitors, feedback=[],
            config=config, primary=primary, fallback=None, primary_error=error)
    finally:
        for client in (primary, fallback):
            if client is not None:
                await client._client.close()
    elapsed = time.perf_counter() - start
    # Validate only generated fields against the existing candidate schema, without
    # inventing C-validation/gate results or changing the contracts on disk.
    validator = load_validators()['evolution']
    candidate_schema = validator.schema['properties']['candidates']['items']
    fields = ('id', 'summary', 'changes')
    schema = {'type': 'object', 'properties': {k: candidate_schema['properties'][k] for k in fields},
              'required': list(fields), 'additionalProperties': False}
    structure_validator = validator.evolve(schema=schema)
    checks = []
    for candidate in result.candidates:
        contract_candidate = {**candidate, 'changes': [{k: v for k, v in ch.items() if k != 'dimension'}
                                                      for ch in candidate['changes']]}
        errors = [e.message for e in structure_validator.iter_errors(contract_candidate)]
        checks.append({'id': candidate['id'], 'changes': len(candidate['changes']),
                       'structure_valid': not errors and bool(candidate['changes']), 'errors': errors})
    summary = {'elapsed_s': round(elapsed, 3), 'provider': result.provider, 'model': result.model,
               'reasoning_effort': result.reasoning_effort, 'fell_back': result.fell_back,
               'fallback_reason': result.fallback_reason, 'api_requests': len(result.attempts),
               'attempts': result.attempts, 'candidate_checks': checks,
               'dropped_changes': result.dropped_changes,
               'sessions': len(sessions), 'traces': len(traces), 'visitors': len(visitors)}
    out = ROOT / 'var/evolve/openai-smoke'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'reflection.json').write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    assert len(result.candidates) == 3 and all(c['structure_valid'] for c in checks)

asyncio.run(main())
