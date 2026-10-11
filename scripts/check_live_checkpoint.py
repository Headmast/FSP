#!/usr/bin/env python3
"""Run a real HTTPS journey against the configured deployment; remove only owned synthetic accounts.

Run on the application host from current/ with its FSP_ENV_FILE. This check uses the
server-only keys for its newly created perfect-answer fixture; it is not a grading validation.
"""
import argparse
import http.cookiejar
import json
import os
import secrets
import sys
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--release-config',required=True)
args=parser.parse_args()
base=json.loads(Path(args.release_config).read_text())['url'].rstrip('/')
parsed=urllib.parse.urlsplit(base)
if parsed.scheme!='https' or parsed.username or parsed.password:raise SystemExit('Expected HTTPS deployment URL without credentials')
sys.path.insert(0,str(Path.cwd()/'app'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from accounts.models import User
from profiles.models import Profile,FspLink
from hiring.models import Company,Need,Invitation
from assessments.models import Attempt

class Fields(HTMLParser):
    def __init__(self,text):
        super().__init__();self.values={};self.feed(text)
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='input' and attrs.get('name'):self.values[attrs['name']]=attrs.get('value','')

class Actor:
    def __init__(self):
        self.jar=http.cookiejar.CookieJar()
        self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
    def request(self,path,data=None):
        if data is not None:
            data={**data,'csrfmiddlewaretoken':next(c.value for c in self.jar if c.name=='csrftoken')}
        request=urllib.request.Request(base+path,data=urllib.parse.urlencode(data,doseq=True).encode() if data is not None else None,
            headers={'Referer':base+'/','User-Agent':'FSP synthetic checkpoint','Content-Type':'application/x-www-form-urlencoded'})
        with self.opener.open(request,timeout=15) as response:
            return response.read().decode() if 'application/pdf' not in response.headers.get('Content-Type','') else response.read()
    def register(self,email,role):
        self.request('/accounts/register/')
        text=self.request('/accounts/register/',{'email':email,'role':role,'password1':password,'password2':password,'processing_consent':'on'})
        token=Fields(text).values['token']
        self.request('/accounts/confirm/',{'token':token})
        assert User.objects.get(username=email).has_processing_consent

suffix=uuid.uuid4().hex
emails=[f'checkpoint-{suffix}-{role}@demo.invalid' for role in ['candidate','employer']]
password=secrets.token_urlsafe(24)
checks=[]
def passed(name):
    checks.append(name)
    print(json.dumps({'step':name,'status':'PASS'}),flush=True)

failure=None
try:
    candidate=Actor();employer=Actor()
    version=json.loads(candidate.request('/version/'))['commit']
    assert json.loads(candidate.request('/health/'))['status']=='ok'
    passed('public version and database readiness')
    candidate.register(emails[0],'candidate');employer.register(emails[1],'employer')
    passed('two HTTPS registrations with CSRF, explicit consent and session-bound demo confirmation')
    data={'name':'Тестовый Кандидат','city':'Москва','skills':'Swift, SwiftUI','desired_grade':'Junior','published':'on',
        'specialization':'ios_swift','experience_months':'12','roles':['developer'],'soft_skills':['teamwork'],
        'description':'Приватное описание private-checkpoint@demo.invalid','contact_email':'private-checkpoint@demo.invalid'}
    candidate.request('/profile/');candidate.request('/profile/',data)
    profile=Profile.objects.get(user__username=emails[0]);assert profile.published and profile.publication_consented_at
    assert profile.experience_months==12 and profile.roles==['developer']
    passed('full profile persistence and distinct publication consent')
    occupied=set(FspLink.objects.values_list('external_id',flat=True))
    external_id=next(f'DEMO-{i:03}' for i in range(999,0,-1) if f'DEMO-{i:03}' not in occupied)
    candidate.request('/profile/fsp/link/');candidate.request('/profile/fsp/link/',{'external_id':external_id,'consent':'on'})
    assert FspLink.objects.get(profile=profile).achievements.count()==1
    passed('own mock FSP binding and achievement')
    candidate.request('/assessments/');candidate.request('/assessments/start/',{'grade':'Junior'})
    attempt=Attempt.objects.get(candidate=profile,status='active')
    # Perfect answers for this synthetic fixture only, kept inside this process.
    candidate.request(f'/assessments/{attempt.pk}/finish/',{f"q_{q['id']}":q['correct'] for q in attempt.tasks})
    profile.refresh_from_db();assert profile.confirmed_grade=='Junior'
    assert 'rules-v1' in candidate.request(f'/assessments/{attempt.pk}/proof/')
    passed('assessment completion and versioned safe witness over HTTPS')
    employer.request('/company/');employer.request('/company/',{'name':'Тестовая Компания','industry':'Разработка приложений',
        'description':'Синтетическая компания для проверки','contact_email':'company-checkpoint@demo.invalid'})
    employer.request('/company/needs/');employer.request('/company/needs/',{'company_name':'Тестовая Компания','company_email':'company-checkpoint@demo.invalid',
        'title':'Синтетическая iOS роль','grade':'Junior','skills':'SwiftUI, Combine','tasks':'Демонстрационные задачи',
        'salary_min':'100000','salary_max':'150000','work_format':'remote','next_step':'Знакомство с командой'})
    company=Company.objects.get(user__username=emails[1]);need=Need.objects.get(company=company)
    passed('company profile and concrete paid need')
    page=employer.request(f'/candidates/{profile.pk}/?need={need.pk}&grade=Junior&skill=SwiftUI')
    assert 'private-checkpoint@demo.invalid' not in page and 'Не указаны в навыках кандидата: Combine' in page
    assert 'rules-v1' in page
    passed('employer sees explanation and proof while private text and contacts stay hidden')
    employer.request('/invitations/send/',{'candidate':profile.pk,'need':need.pk,'accepted_attempts':[attempt.pk],'discussion':'Обсудить архитектуру'})
    offer=Invitation.objects.get(candidate=profile,company=company)
    assert offer.snapshot['accepted_results'][0]['attempt_id']==attempt.pk
    inbox=candidate.request('/invitations/');assert 'Обсудить архитектуру' in inbox and 'Синтетическая компания для проверки' in inbox
    passed('selected result and company details visible to candidate before acceptance')
    candidate.request(f'/invitations/{offer.pk}/accept/',{})
    assert 'private-checkpoint@demo.invalid' in employer.request(f'/candidates/{profile.pk}/')
    assert employer.request(f'/candidates/{profile.pk}/resume.pdf').startswith(b'%PDF')
    passed('acceptance opens HTML and PDF access for invitation sender')
    data.pop('published');candidate.request('/profile/',data)
    assert 'Тестовый Кандидат' not in employer.request(f'/candidates/?need={need.pk}&grade=Junior')
    assert 'private-checkpoint@demo.invalid' in employer.request(f'/candidates/{profile.pk}/')
    passed('publication withdrawal removes search while preserving documented prior grant')
except Exception as exc:
    failure=type(exc).__name__
finally:
    # No broad fixture reset: only these two random synthetic accounts and their dependent data.
    Invitation.objects.filter(candidate__user__username=emails[0]).delete()
    Invitation.objects.filter(company__user__username=emails[1]).delete()
    User.objects.filter(username__in=emails).delete()
    cleaned=not User.objects.filter(username__in=emails).exists()
report={'status':'FAIL' if failure else 'PASS','commit':locals().get('version'),'url':base,
    'checked_at':datetime.now(timezone.utc).isoformat(),'checks':checks,'failure_type':failure,
    'synthetic_accounts_removed':cleaned,'scope':'HTTPS journey; no existing account reset; perfect-answer synthetic fixture is not QA-001 validation'}
print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
raise SystemExit(1 if failure or not cleaned else 0)
