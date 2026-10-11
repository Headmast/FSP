#!/usr/bin/env python3
"""Check real file-backed SQLite attempts under simultaneous calls; clean up own synthetic user."""
import json
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.db import connections
from accounts.models import User
from profiles.models import Profile
from assessments.models import Attempt
from assessments.services import start_attempt,save_answers
from collections import Counter

user=User.objects.create_user(username=f'concurrency-{uuid.uuid4().hex}@demo.invalid',role='candidate',email_confirmed=True)
profile=Profile.objects.create(user=user)
cohort_users=[]
def isolated(fn):
    try:return fn()
    finally:connections.close_all()
try:
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids=list(pool.map(lambda _:isolated(lambda:start_attempt(profile,'Junior').pk),range(8)))
    assert len(set(ids))==1
    obj=Attempt.objects.get(pk=ids[0]);answers={q['id']:q['correct'] for q in obj.tasks}
    with ThreadPoolExecutor(max_workers=8) as pool:
        counts=list(pool.map(lambda _:isolated(lambda:save_answers(profile,obj.pk,answers,finish=True).correct_count),range(8)))
    assert counts==[8]*8
    assert Attempt.objects.filter(candidate=profile).count()==1
    profile.refresh_from_db();assert profile.confirmed_grade=='Junior' and profile.test_score==1
    cohort=[]
    for index in range(8):
        member=User.objects.create_user(username=f'new-cohort-{uuid.uuid4().hex}@demo.invalid',role='candidate')
        cohort_users.append(member);cohort.append(Profile.objects.create(user=member))
    with ThreadPoolExecutor(max_workers=8) as pool:
        variants=list(pool.map(lambda candidate:isolated(lambda:start_attempt(candidate,'Junior').variant),cohort))
    assert Counter(variants)=={'A':4,'B':4}
    print(json.dumps({'status':'PASS','concurrent_calls':8,'attempts_created':1,'final_results':counts,
        'distinct_new_candidates':8,'new_candidate_variants':dict(Counter(variants))},indent=2))
finally:
    for member in cohort_users:member.delete()
    user.delete()
