#!/usr/bin/env python3
"""Evaluate production scoring against frozen semantic responses in isolated temporary SQLite."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
import random
import sys
import tempfile
from collections import Counter
from datetime import datetime,timedelta,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--output',default='doc/qa/validation-results.json')
p.add_argument('--annotations')
p.add_argument('--bank-source')
a=p.parse_args()
fixture_path=ROOT/'doc/qa/validation-fixture.json'
fixture=json.loads(fixture_path.read_text())
items=dict(fixture['items'])
if a.annotations:items.update(json.loads(Path(a.annotations).read_text())['items'])
os.environ.update(FSP_ENV_FILE='/dev/null',DEBUG='1')
sys.path.insert(0,str(ROOT/'app'));os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
rows=[];oracle=[]
with tempfile.TemporaryDirectory(prefix='fsp-validation-') as temp:
    os.environ['DATABASE_PATH']=str(Path(temp)/'validation.sqlite3')
    import django
    django.setup()
    from django.core.management import call_command
    from django.db import connections
    from django.utils import timezone as django_timezone
    from accounts.models import User
    from profiles.models import Profile
    from assessments.models import Attempt
    from assessments.services import save_answers
    from assessments.bank import BANK,VERSION
    if a.bank_source:
        spec=importlib.util.spec_from_file_location('validation_bank',a.bank_source)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        BANK,VERSION=module.BANK,module.VERSION
    call_command('migrate',verbosity=0)
    serial=0
    def trial(subject,grade,variant,occasion,all_known=False):
        global serial
        serial+=1
        user=User.objects.create_user(username=f'validation-{serial}@demo.invalid',role='candidate')
        profile=Profile.objects.create(user=user)
        tasks=copy.deepcopy(BANK[(grade,variant)])
        # Permutation is independent of answer correctness; response uses annotated text only.
        answers={}
        for position,task in enumerate(tasks,1):
            random.Random(f'{subject["id"]}:{grade}:{variant}:{occasion}:{position}').shuffle(task['options'])
            # Re-index the key after permutation without using it to construct submitted answers.
            original=BANK[(grade,variant)][position-1]
            key_text=original['options'][original['correct']]
            task['correct']=task['options'].index(key_text)
            annotation=items[task['id']]
            known=all_known or (annotation['topic'] in subject['mastered_topics'] and position not in subject['lapse_positions'][occasion])
            text=annotation['answer_text' if known else 'misconception_text']
            answers[task['id']]=task['options'].index(text)
        now=django_timezone.now()
        obj=Attempt.objects.create(candidate=profile,grade=grade,variant=variant,bank_version=VERSION,
            tasks=tasks,started_at=now,expires_at=now+timedelta(minutes=15))
        result=save_answers(profile,obj.pk,answers,finish=True)
        return {'subject':subject['id'],'split':subject['split'],'expected':subject['expected'],
            'grade':grade,'variant':variant,'occasion':occasion,'correct_count':result.correct_count,
            'passed':result.passed,'area_scores':result.area_scores}
    oracle_subject={'id':'semantic-oracle','split':'oracle','expected':None,'mastered_topics':[],'lapse_positions':[[],[]]}
    for grade,variant in BANK:
        result=trial(oracle_subject,grade,variant,0,all_known=True)
        oracle.append({'grade':grade,'variant':variant,'semantic_answer_mismatches':8-result['correct_count']})
    for subject in fixture['profiles']:
        for grade in ['Junior','Middle']:
            for variant in 'AB':
                for occasion in [0,1]:rows.append(trial(subject,grade,variant,occasion))
    connections.close_all()

def summary(split):
    subjects=[s for s in fixture['profiles'] if s['split']==split]
    index={(r['subject'],r['grade'],r['variant'],r['occasion']):r for r in rows}
    predicted={}
    matrix=Counter();mistakes=[]
    for s in subjects:
        for variant in 'AB':
            for occasion in [0,1]:
                level='Middle' if index[(s['id'],'Middle',variant,occasion)]['passed'] else 'Junior' if index[(s['id'],'Junior',variant,occasion)]['passed'] else 'unconfirmed'
                predicted[s['id'],variant,occasion]=level
                if s['expected'] is not None:
                    matrix[s['expected'],level]+=1
                    if s['expected']!=level:mistakes.append({'subject':s['id'],'variant':variant,'occasion':occasion,'expected':s['expected'],'actual':level})
    retest=sum(predicted[s['id'],v,0]==predicted[s['id'],v,1] for s in subjects for v in 'AB')/(len(subjects)*2)
    ab=sum(predicted[s['id'],'A',o]==predicted[s['id'],'B',o] for s in subjects for o in [0,1])/(len(subjects)*2)
    gap=sum(abs(index[(s['id'],g,'A',o)]['correct_count']-index[(s['id'],g,'B',o)]['correct_count']) for s in subjects for g in ['Junior','Middle'] for o in [0,1])/(len(subjects)*4)
    metrics={'subjects':len(subjects),'grade_decisions':len(subjects)*4,'label_accuracy':1-len(mistakes)/(len(subjects)*4) if split!='boundary' else None,
        'test_retest_agreement':retest,'ab_grade_agreement':ab,'mean_abs_ab_score_gap':gap,
        'confusion_matrix':[{"expected":expected,"actual":actual,"count":count} for (expected,actual),count in sorted(matrix.items())],
        'misclassifications':mistakes,'score_separation':[]}
    for expected in ['unconfirmed','Junior','Middle']:
        for grade in ['Junior','Middle']:
            group=[r for r in rows if r['split']==split and r['expected']==expected and r['grade']==grade]
            if group:metrics['score_separation'].append({'expected':expected,'test':grade,'mean_correct':sum(r['correct_count'] for r in group)/len(group),'pass_rate':sum(r['passed'] for r in group)/len(group)})
    return metrics
metrics={s:summary(s) for s in ['anchors','holdout','boundary']}
limits=fixture['criteria']
violations=[]
for split in ['anchors','holdout']:
    m=metrics[split]
    for name in ['label_accuracy','test_retest_agreement','ab_grade_agreement']:
        if m[name]<limits[name+'_min']:violations.append(f'{split}:{name}')
    if m['mean_abs_ab_score_gap']>limits['mean_abs_ab_score_gap_max']:violations.append(f'{split}:mean_abs_ab_score_gap')
if sum(o['semantic_answer_mismatches'] for o in oracle)>limits['oracle_mismatches_max']:violations.append('semantic_oracle_mismatch')
result={'status':'FAIL' if violations else 'PASS','bank_version':VERSION,'checked_at':datetime.now(timezone.utc).isoformat(),
    'fixture_sha256':hashlib.sha256(fixture_path.read_bytes()).hexdigest(),'protocol_sha256':hashlib.sha256((ROOT/'doc/qa/validation-protocol.md').read_bytes()).hexdigest(),
    'annotations_sha256':hashlib.sha256(Path(a.annotations).read_bytes()).hexdigest() if a.annotations else None,
    'grader_sha256':hashlib.sha256((ROOT/'app/assessments/services.py').read_bytes()).hexdigest(),
    'bank_sha256':hashlib.sha256(Path(a.bank_source).read_bytes() if a.bank_source else (ROOT/'app/assessments/bank.py').read_bytes()).hexdigest(),
    'checker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'criteria':limits,'isolation':'temporary SQLite; independent Profile for each trial; no production DB',
    'synthetic_profiles':40,'attempts':len(rows),'oracle_attempts':4,'oracle':oracle,'metrics':metrics,'violations':violations,'rows':rows,
    'limits':'Synthetic knowledge model, Codex authored. Not human psychometric evidence. Boundary instability reported separately. Highest passed level is an analysis label from two independent grade tests, not an automatic production upgrade.'}
output=Path(a.output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ['status','bank_version','synthetic_profiles','attempts','oracle_attempts','metrics','violations']},ensure_ascii=False,indent=2))
raise SystemExit(1 if violations else 0)
