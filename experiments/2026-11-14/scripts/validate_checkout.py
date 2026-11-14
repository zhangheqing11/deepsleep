#!/usr/bin/env python3
"""Prepare ignored SFT test prerequisites outside checkout, test, remove links."""
from pathlib import Path
import contextlib
import io
import os
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / 'experiments/2026-11-14/validation'
sys.path.insert(0, str(REPO))
from privacy.data.tools import build_sft

links = []
env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'SAFETY_EVAL_NO_DOTENV': '1', 'GIT_OPTIONAL_LOCKS': '0'}
with tempfile.TemporaryDirectory(prefix='exp-archive-sft-') as temp:
    root = Path(temp)
    for name in ['synth', 'gold']:
        (root / name).symlink_to(REPO / 'privacy/data' / name, target_is_directory=True)
    build_sft.ROOT = root
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        build_sft.build_sft()
    assert (root / 'sft/dataset_info.json').read_bytes() == (REPO / 'privacy/data/sft/dataset_info.json').read_bytes()
    try:
        for p in sorted((root / 'sft').glob('*.jsonl')):
            dest = REPO / 'privacy/data/sft' / p.name
            if dest.exists() or dest.is_symlink():
                raise RuntimeError('Refusing to replace existing SFT export: ' + str(dest))
            dest.symlink_to(p)
            links.append(dest)
        (OUT / 'sft-prerequisites.txt').write_text(log.getvalue() + f'Temporary exports: {len(links)}; existing dataset_info matched byte-for-byte.\n')
        run = subprocess.run([sys.executable, '-m', 'pytest', '-q', '--ignore=api', '-p', 'no:cacheprovider'], cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        (OUT / 'pytest-with-prerequisites.txt').write_text(run.stdout)
        print(run.stdout)
    finally:
        for link in links:
            link.unlink()
raise SystemExit(run.returncode)
