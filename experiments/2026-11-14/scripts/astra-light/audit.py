import sys,hashlib,json,os
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from analysis.evo_trial import read,write_json,compute_metrics,score_veto,load_visitors,load_validators,validate_document
from engine.evolve.gate import val_veto,improves_primary,choose
from engine.evolve.hard_rules import check_candidate
OUT=ROOT/'var/astra-light/astra-20261114'; OLD=ROOT/'var/evo-trial/evo-20261114/jev';cfg=read(OUT/'evolve-config.json');e=read(OUT/'evolve/g1/evolution.json')
errors=[];vis={v['id']:v for v in load_visitors(n=18)};val=load_validators()
for p in sorted(OUT.glob('C-g1/*/run_report.json'))+list(OUT.glob('r1/run_report.json')):
 r=read(p); computed=compute_metrics(r['per_visitor'])
 for k,x in computed.items():
  if r['metrics'][k]!=x: errors.append(str(p)+': metric '+k)
 ve=validate_document(r,'run_report',val,vis)
 if ve:errors.append({'path':str(p),'errors':ve})
 for sp in p.parent.glob('sessions/*.json'):
  ve=validate_document(read(sp),'session',val,vis)
  if ve:errors.append({'path':str(sp),'errors':ve})
base=(OLD/'r0/playbook.md').read_text()
for c in e['candidates']:
 assert check_candidate(c['changes'],base,cfg)==c['hard_rule_violations']
 if c['val_metrics']:
  assert val_veto(c['val_metrics'],e['baseline_val_metrics'],cfg)==c['veto']
  assert c['passed']==(not c['hard_rule_violations'] and c['veto']['passed'] and improves_primary(c['val_metrics'],e['baseline_val_metrics'],cfg))
assert choose(e['candidates'])==e['chosen']
starts=[json.loads(x) for x in (OUT/'http-starts.jsonl').read_text().splitlines()];results=[json.loads(x) for x in (OUT/'http-results.jsonl').read_text().splitlines()]
count=len((OUT/'request-budget.log').read_text().splitlines());assert count==len(starts)==len(results)<=1500
# Inspect values only in memory, report counts only.
secrets=[]
for line in Path('/Users/zhangheqing/bohack/ds-safety/.env').read_text().splitlines():
 if '=' in line and not line.lstrip().startswith('#'):
  k,v=line.split('=',1);v=v.strip().strip('"').strip("'")
  if any(t in k.upper() for t in ('KEY','TOKEN','SECRET','PASSWORD')) and len(v)>8:secrets.append(v.encode())
report=Path('/Users/zhangheqing/bohack/research/codex-tasks/astra-light.md')
files=[p for p in OUT.rglob('*') if p.is_file()]+([report] if report.exists() else [])
hits=sum(any(s in p.read_bytes() for s in secrets) for p in files)
audit={'ledger_starts_results':[count,len(starts),len(results)],'http_statuses':dict(Counter(x['status'] for x in results)), 'http_components':dict(Counter(x['component'] for x in results)), 'metric_session_report_validation_errors':errors,'hard_rules_and_gate_recomputed':True,'secret_value_matching_files':hits,'runtime_git_dirs':list(map(str,OUT.rglob('.git')))}
write_json(OUT/'audit.json',audit);print(json.dumps(audit,ensure_ascii=False))
