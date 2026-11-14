"""Finish local validation after the orchestration's validation-call signature mismatch."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
from analysis.evo_trial import *
OUT=ROOT/'var/astra-light/astra-20261114'
visitors={v['id']:v for v in load_visitors(n=18)}
e=read(OUT/'evolve/g1/evolution.json')
write_json(OUT/'evolution-validation.json',validate_document(e,'evolution',load_validators(),visitors))
assert not e['chosen'], 'Adopted candidate requires r1 continuation with shared budget'
write_json(OUT/'done.json',{'finished_at':now(),'r1_run':False,'recovered_local_validation':True,'note':'C gate completed; corrected local validator invocation, no additional API calls'})
print({'outcome':e['outcome'],'chosen':e['chosen'],'validation_errors':read(OUT/'evolution-validation.json')})
