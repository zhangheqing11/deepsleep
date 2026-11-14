"""Offline diagnosis; old timestamps have one-second precision and no host field."""
import bisect
from collections import Counter
from datetime import datetime
import json
from pathlib import Path

OLD = Path('/Users/zhangheqing/bohack/ds-accept/var/evo40/evo40-20261114')


def diagnose(out):
    rows = [json.loads(line) for line in (OLD/'http-results.jsonl').read_text().splitlines()]
    starts = sorted(datetime.fromisoformat(r['at']).timestamp() for r in rows)
    ends = sorted(datetime.fromisoformat(r['at']).timestamp()+r['ms']/1000 for r in rows)
    # Point approximation only: all starts in a second assigned to its beginning.
    for row in rows:
        t = datetime.fromisoformat(row['at']).timestamp()
        row['approx_inflight'] = bisect.bisect_right(starts, t)-bisect.bisect_right(ends, t)
    stages = []
    for stage in dict.fromkeys(r['stage'] for r in rows):
        subset = [r for r in rows if r['stage'] == stage]
        values = sorted(r['approx_inflight'] for r in subset)
        errors = [r for r in subset if r['status'] == 'error']
        stages.append({'stage': stage, 'attempts': len(subset), 'errors': len(errors),
                       'approx_inflight_median': values[len(values)//2], 'approx_inflight_max': max(values),
                       'errors_by_component': dict(Counter(r['component'] for r in errors))})
    bins = []
    for lo, hi in ((0,16), (17,32), (33,48), (49,64), (65,1000)):
        subset = [r for r in rows if lo <= r['approx_inflight'] <= hi]
        bins.append({'range': f'{lo}-{hi}', 'attempts': len(subset),
                     'errors': sum(r['status'] == 'error' for r in subset)})
    data = {'source': str(OLD), 'host_recorded': False, 'timestamp_precision_s': 1,
            'inflight_method': 'floor-start-time point approximation, not measured concurrency',
            'errors': [{'component': c, 'error': e, 'count': n} for (c,e),n in
                       Counter((r['component'],r.get('error_type')) for r in rows if r['status']=='error').items()],
            'stages': stages, 'bins': bins}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
    return data
