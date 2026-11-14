"""Resume only the failed reflector; preserve completed A runs and all billed calls.
The first reflector timed out at 300s without candidates. This continuation raises
only its timeout to 600s. HTTP IDs continue in the existing durable ledger.
"""
import asyncio
from datetime import datetime
import json
from pathlib import Path
import shutil

from analysis import gate_fix as trial


def prepare():
    out = trial.OUT
    assert not (out/'C').exists() and not (out/'evolve/g1/evolution.json').exists()
    failed = trial.read(out/'reflection.json')
    assert failed['fell_back'] and failed['model'] != 'gpt-6-astra'
    archive = out/'reflector-failed-attempt'
    archive.mkdir(exist_ok=False)
    for name in ('reflection.json','config.json','calls-current-process.json','accounting.json',
                 'integrity.json','stopped.json'):
        p = out/name
        if p.exists():
            shutil.copyfile(p, archive/name)
    if (out/'evolve/g1').exists():
        shutil.copytree(out/'evolve/g1',archive/'evolve-g1')
    shutil.copyfile('/tmp/gate-fix-run-r2.log',archive/'process.log')
    (out/'reflection.json').unlink()
    (out/'stopped.json').unlink(missing_ok=True)
    trial.write_json(out/'continuation.json', {
        'at': trial.now(), 'reason': 'reflector timed out; fallback JSON invalid; no C evaluation started',
        'primary_timeout_s_before': 300, 'primary_timeout_s_after': 600,
        'reused_batches': ['r0a','r0b'], 'same_model_effort_prompts_and_inputs': True,
        'budget_used_before': len(trial.BUDGET.read_text().splitlines())})


async def resume():
    original_config = trial.evolve_config
    def config(overrides):
        result = original_config(overrides)
        result['reflector']['primary_timeout_s'] = 600
        return result
    trial.evolve_config = config
    original_meter = trial.TrialMeter
    class ContinuingMeter(original_meter):
        def __init__(self, budget, out):
            super().__init__(budget, out)
            self.sequence = max(json.loads(line)['id'] for line in (out/'http-starts.jsonl').read_text().splitlines())
    trial.TrialMeter = ContinuingMeter
    await trial.experiment40()
    done = trial.read(trial.OUT/'done.json')
    done['continuation_process_wall_s'] = done['wall_s']
    start = datetime.fromisoformat(trial.read(trial.OUT/'manifest.json')['started_at'])
    done['wall_s'] = (datetime.fromisoformat(done['finished_at'])-start).total_seconds()
    trial.write_json(trial.OUT/'done.json', done)


if __name__ == '__main__':
    prepare()
    asyncio.run(resume())
