#!/usr/bin/env python3
"""Offline recursive content scan and provenance verification, including gzip members."""
from pathlib import Path
import hashlib
import json
import re
import tarfile

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    'provider_prefix': b's' + b'k-',
    'google_prefix': b'AI' + b'za',
    'bearer_header': b'Bear' + rb'er\s+',
    'key_assignment': rb'\b[A-Za-z_][A-Za-z0-9_]*_' + rb'API_KEY\s*=',
    'auth_header': b'Author' + b'ization',
}
RX = {k: re.compile(v, re.I) for k, v in PATTERNS.items()}
issues = []
contents = {}
counts = {'files': 0, 'archive_members': 0, 'content_bytes': 0}


def scan(name, data):
    counts['content_bytes'] += len(data)
    p = Path(name)
    if any(x.startswith('.env') for x in p.parts) or '.git' in p.parts:
        issues.append({'path': name, 'reason': 'forbidden path'})
    for kind, pattern in RX.items():
        if pattern.search(data):
            issues.append({'path': name, 'reason': kind})
    if len(data) > 20 * 1024 * 1024:
        issues.append({'path': name, 'reason': 'over 20 MiB'})
    if p.suffix == '.json':
        try:
            json.loads(data)
        except (ValueError, UnicodeDecodeError):
            issues.append({'path': name, 'reason': 'invalid JSON'})


for p in sorted(ROOT.rglob('*')):
    if p.is_symlink():
        issues.append({'path': str(p.relative_to(ROOT)), 'reason': 'symlink'})
        continue
    if not p.is_file():
        continue
    name = p.relative_to(ROOT).as_posix()
    counts['files'] += 1
    if p.name.endswith('.tar.gz'):
        if p.stat().st_size > 20 * 1024 * 1024:
            issues.append({'path': name, 'reason': 'archive over 20 MiB'})
        with tarfile.open(p, 'r:gz') as archive:
            for member in archive:
                if not member.isfile() or Path(member.name).is_absolute() or '..' in Path(member.name).parts:
                    issues.append({'path': name, 'reason': 'unsafe archive member'})
                    continue
                data = archive.extractfile(member).read()
                counts['archive_members'] += 1
                contents[(name, member.name)] = hashlib.sha256(data).hexdigest()
                scan(name + '::' + member.name, data)
    else:
        data = p.read_bytes()
        contents[(name, None)] = hashlib.sha256(data).hexdigest()
        scan(name, data)

manifest = json.loads((ROOT / 'MANIFEST.json').read_text())
for row in manifest['files']:
    key = (row['destination'], row.get('member'))
    if contents.get(key) != row['archived_sha256']:
        issues.append({'path': str(key), 'reason': 'manifest hash mismatch'})
result = {'offline': True, 'counts': counts, 'source_records_verified': len(manifest['files']),
          'hits': len(issues), 'issues': issues}
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(bool(issues))
