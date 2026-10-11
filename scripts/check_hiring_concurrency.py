#!/usr/bin/env python3
"""Exercise concurrent invitation and decisions on the configured file-backed DB."""
import json, os, sys, uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.db import connections
from accounts.models import User
from profiles.models import Profile
from hiring.models import Company,Need,Invitation
from hiring.services import invite,decide
suffix=uuid.uuid4().hex
candidate=User.objects.create_user(username=f'concurrent-c-{suffix}@demo.invalid',role='candidate')
employer=User.objects.create_user(username=f'concurrent-e-{suffix}@demo.invalid',role='employer')
p=Profile.objects.create(user=candidate,published=True,confirmed_grade='Junior')
c=Company.objects.create(user=employer)
n=Need.objects.create(company=c,title='Демо',grade='Junior',salary_min=100,salary_max=200,work_format='remote')
def isolated(fn):
    try:return fn()
    finally:connections.close_all()
try:
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids=list(pool.map(lambda _:isolated(lambda:invite(c,n.pk,p.pk).pk),range(8)))
    assert len(set(ids))==1 and Invitation.objects.filter(candidate=p).count()==1
    def decision(i):
        try:return decide(p,ids[0],'accepted' if i%2 else 'declined').status
        except ValueError:return 'conflict'
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes=list(pool.map(lambda i:isolated(lambda:decision(i)),range(8)))
    final=Invitation.objects.get(pk=ids[0]).status
    assert outcomes.count(final)==4 and outcomes.count('conflict')==4
    print(json.dumps({'status':'PASS','concurrent_calls':8,'invitations_created':1,'final_status':final,'outcomes':outcomes},indent=2))
finally:
    Invitation.objects.filter(candidate=p).delete();n.delete();employer.delete();candidate.delete()
