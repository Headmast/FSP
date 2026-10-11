#!/usr/bin/env python3
"""Measure search against predeclared synthetic gold labels. Use a fresh isolated database."""
import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from profiles.models import Profile
from profiles.skills import normalized
from hiring.models import Need
from hiring.services import search
fixture=json.loads((ROOT/'doc/qa/matching-fixture.json').read_text())
assert Profile.objects.count()==24,'Benchmark requires exactly the fresh 24-candidate fixture cohort'
cases=[]
for case in fixture['cases']:
    need=Need.objects.get(title=case['need']);gold=set(case['expected_top_5'])
    rows=search(case['grade'],need)
    actual=[p['name'] for p in rows[:5]]
    precision=len(set(actual)&gold)/5
    violations=sum(p['grade']!=case['grade'] for p in rows)
    assert len(rows)==10 and violations==0
    assert not any(p['name'].startswith('Неподтверждённый') for p in rows)
    pool=Profile.objects.filter(published=True,confirmed_grade=case['grade'])
    baseline=sorted(pool,key=lambda p:(-len(normalized(p.skills)&normalized(need.skills)),p.pk))[:5]
    baseline_names=[p.name for p in baseline]
    cases.append({'need':case['need'],'expected':case['expected_top_5'],'actual':actual,'precision_at_5':precision,
        'hard_filter_violations':violations,'keyword_baseline':baseline_names,'baseline_precision_at_5':len(set(baseline_names)&gold)/5})
    assert precision>=.8,(case,actual)
result={'status':'PASS','cases':cases,'mean_precision_at_5':sum(c['precision_at_5'] for c in cases)/3,
    'mean_baseline_precision_at_5':sum(c['baseline_precision_at_5'] for c in cases)/3,'population':fixture['population']}
output=ROOT/'.runtime/qa/matching.json';output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
