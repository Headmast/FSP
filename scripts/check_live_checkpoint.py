#!/usr/bin/env python3
"""Run a real HTTPS journey against the configured deployment; remove only owned synthetic accounts.

Run on the application host from current/ with its FSP_ENV_FILE. This check uses the
server-only keys for its newly created perfect-answer fixture; it is not a grading validation.
"""
import argparse
import hashlib
import http.cookiejar
import json
import os
import secrets
import sys
import urllib.parse
import urllib.request
import urllib.error
import uuid
import traceback
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--release-config',required=True)
parser.add_argument('--privacy',action='store_true',help='Accept privacy with only this run\'s candidate and two owned companies')
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
from assistant.models import Draft
from api.core import issue_token

def api_read(path,secret):
    request=urllib.request.Request(base+'/api/v1/'+path,headers={'Authorization':'Bearer '+secret,'User-Agent':'FSP synthetic conditions checkpoint'})
    with urllib.request.urlopen(request,timeout=15) as response:return json.load(response)

def api_denied(path,secret):
    try:api_read(path,secret)
    except urllib.error.HTTPError as exc:assert exc.code==403
    else:raise AssertionError('MCP private access unexpectedly allowed')

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
    def login(self,email,secret):
        self.request('/accounts/login/')
        self.request('/accounts/login/',{'username':email,'password':secret})
    def expect_status(self,path,status,data=None):
        try:self.request(path,data)
        except urllib.error.HTTPError as exc:
            assert exc.code==status
        else:raise AssertionError('Expected negative HTTP response')

suffix=uuid.uuid4().hex
emails=[f'checkpoint-{suffix}-{role}@demo.invalid' for role in ['candidate','employer']]
if args.privacy:emails.append(f'checkpoint-{suffix}-privacy-employer@demo.invalid')
password=secrets.token_urlsafe(24)
checks=[]
privacy_artifacts=[]
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
        'preferred_work_formats':['remote'],'preferred_employment_types':['full_time'],'preferred_task_types':['development','testing'],
        'description':'Приватное описание private-checkpoint@demo.invalid','contact_email':'private-checkpoint@demo.invalid'}
    candidate.request('/profile/');candidate.request('/profile/',data)
    profile=Profile.objects.get(user__username=emails[0]);assert profile.published and profile.publication_consented_at
    assert profile.experience_months==12 and profile.roles==['developer']
    passed('full profile persistence and distinct publication consent')
    assert profile.preferred_work_formats==['remote'] and profile.preferred_task_types==['development','testing']
    candidate_secret=issue_token(profile.user,'Owned conditions checkpoint','mcp')[1]
    profile_dto=api_read('me/profile',candidate_secret)['data']
    assert profile_dto['preferred_employment_types']==['full_time'] and 'private-checkpoint@demo.invalid' not in json.dumps(profile_dto)
    passed('optional candidate preferences persist and safe token projection excludes contacts')
    helper=candidate.request('/assistant/',{'mode':'profile'})
    assert 'Проверил черновик' in helper and 'Мок' in helper
    draft=Draft.objects.get(user=profile.user,mode='profile')
    assert profile.description==data['description']
    data['description']='Проверенное описание private-checkpoint@demo.invalid'
    candidate.request(f'/assistant/drafts/{draft.pk}/',{'description':data['description']})
    profile.refresh_from_db();assert profile.description==data['description'] and profile.published
    candidate.request(f'/assistant/drafts/{draft.pk}/',{'description':'Повтор не применяется'})
    profile.refresh_from_db();assert profile.description==data['description']
    employer.expect_status(f'/assistant/drafts/{draft.pk}/',404)
    passed('candidate edits and applies private draft; replay and foreign draft protected')
    occupied=set(FspLink.objects.values_list('external_id',flat=True))
    external_id=next(f'DEMO-{i:03}' for i in range(999,0,-1) if f'DEMO-{i:03}' not in occupied)
    candidate.request('/profile/fsp/link/');candidate.request('/profile/fsp/link/',{'external_id':external_id,'consent':'on'})
    assert FspLink.objects.get(profile=profile).achievements.count()==1
    passed('own mock FSP binding and achievement')
    candidate.request('/assessments/');candidate.request('/assessments/start/',{'grade':'Junior'})
    attempt=Attempt.objects.get(candidate=profile,status='active')
    candidate.expect_status('/assistant/',409,{'mode':'profile'})
    # Perfect answers for this synthetic fixture only, kept inside this process.
    candidate.request(f'/assessments/{attempt.pk}/finish/',{f"q_{q['id']}":q['correct'] for q in attempt.tasks})
    profile.refresh_from_db();assert profile.confirmed_grade=='Junior'
    assert 'rules-v1' in candidate.request(f'/assessments/{attempt.pk}/proof/')
    passed('assessment completion and versioned safe witness over HTTPS')
    assert not Company.objects.filter(user__username=emails[1]).exists()
    employer.request('/assistant/');employer.request('/assistant/',{'mode':'need','new_need':'on','grade':'Junior','skills':'SwiftUI, Combine'})
    need_draft=Draft.objects.get(user__username=emails[1],mode='need')
    assert not Company.objects.filter(user__username=emails[1]).exists()
    assert not Need.objects.filter(company__user__username=emails[1]).exists()
    need_data={'company_name':'Тестовая Компания','company_email':'company-checkpoint@demo.invalid',
        'title':'Синтетическая iOS роль','grade':'Junior','skills':'SwiftUI, Combine','tasks':'Демонстрационные задачи',
        'salary_min':'100000','salary_max':'150000','work_format':'remote','employment_type':'full_time','task_types':['development','testing'],'next_step':'Знакомство с командой'}
    employer.request(f'/assistant/drafts/{need_draft.pk}/',need_data)
    employer.request(f'/assistant/drafts/{need_draft.pk}/',{})
    company=Company.objects.get(user__username=emails[1]);need=Need.objects.get(company=company)
    passed('fresh employer reviews draft before company/need exists; one paid need on replay')
    employer.request('/company/');employer.request('/company/',{'name':'Тестовая Компания','industry':'Разработка приложений',
        'description':'Синтетическая компания для проверки','contact_email':'company-checkpoint@demo.invalid'})
    passed('company profile and concrete paid need')
    page=employer.request(f'/candidates/{profile.pk}/?need={need.pk}&grade=Junior&skill=SwiftUI')
    assert 'private-checkpoint@demo.invalid' not in page and 'Не указаны в навыках кандидата: Combine' in page
    assert 'rules-v1' in page
    passed('employer sees explanation and proof while private text and contacts stay hidden')
    assert 'Все три условия указаны обеими сторонами' in page
    matched=employer.request(f'/candidates/?need={need.pk}&conditions=matched')
    assert 'Тестовый Кандидат' in matched
    employer_secret=issue_token(company.user,'Owned conditions checkpoint','mcp')[1]
    dto=api_read(f'candidates/{profile.pk}?need_id={need.pk}',employer_secret)['data']
    assert len(dto['explanation']['conditions']['matches'])==3 and not dto['contacts_allowed']
    assert 'private-checkpoint@demo.invalid' not in json.dumps(dto)
    api_denied(f'candidates/{profile.pk}/resume.pdf?need_id={need.pk}',employer_secret)
    api_denied(f'candidates/{profile.pk}/private',employer_secret)
    passed('matching condition filter and safe MCP DTO over HTTPS before contact')
    helper=employer.request('/assistant/',{'mode':'matching','need':need.pk,'candidate':profile.pk})
    assert 'Пробелы самоописания: Combine' in helper and 'private-checkpoint@demo.invalid' not in helper
    helper=employer.request('/assistant/',{'mode':'invitation','need':need.pk,'candidate':profile.pk})
    assert 'Проверил текст и условия' in helper and not Invitation.objects.filter(candidate=profile,company=company).exists()
    passed('safe mock matching and invitation preview do not send automatically')
    employer.request('/invitations/send/',{'candidate':profile.pk,'need':need.pk,'accepted_attempts':[attempt.pk],'discussion':'Обсудить архитектуру'})
    offer=Invitation.objects.get(candidate=profile,company=company)
    assert offer.snapshot['accepted_results'][0]['attempt_id']==attempt.pk
    inbox=candidate.request('/invitations/');assert 'Обсудить архитектуру' in inbox and 'Синтетическая компания для проверки' in inbox
    passed('selected result and company details visible to candidate before acceptance')
    helper=candidate.request('/assistant/',{'mode':'conversation','invitation':offer.pk})
    assert 'Работодатель зачёл результатов: 1' in helper
    offer.refresh_from_db();assert offer.status=='sent'
    passed('candidate conversation uses snapshot and preserves pending decision')
    initial=offer.snapshot.copy();data['preferred_work_formats']=['office'];candidate.request('/profile/',data)
    profile.refresh_from_db();assert profile.preferred_work_formats==['office']
    assert 'Тестовый Кандидат' not in employer.request(f'/candidates/?need={need.pk}&conditions=matched')
    assert 'требуется уточнение' in employer.request(f'/candidates/{profile.pk}/?need={need.pk}')
    snapshot_dto=api_read(f'invitations/{offer.pk}',employer_secret)['data']
    assert len(snapshot_dto['conditions']['matches'])==3
    offer.refresh_from_db();assert offer.snapshot==initial
    passed('changed preferences create a current conflict while the sent invitation snapshot stays matched')
    candidate.request(f'/invitations/{offer.pk}/accept/',{})
    assert 'private-checkpoint@demo.invalid' in employer.request(f'/candidates/{profile.pk}/')
    assert employer.request(f'/candidates/{profile.pk}/resume.pdf').startswith(b'%PDF')
    passed('acceptance opens HTML and PDF access for invitation sender')
    helper=employer.request('/assistant/',{'mode':'conversation','invitation':offer.pk})
    assert 'Согласуйте время встречи' in helper
    passed('employer conversation after explicit acceptance')
    data.pop('published');candidate.request('/profile/',data)
    assert 'Тестовый Кандидат' not in employer.request(f'/candidates/?need={need.pk}&grade=Junior')
    assert 'private-checkpoint@demo.invalid' in employer.request(f'/candidates/{profile.pk}/')
    passed('publication withdrawal removes search while preserving documented prior grant')
    if args.privacy:
        from live_privacy_checkpoint import run as privacy_acceptance
        privacy_acceptance(candidate,employer,Actor,Fields,profile,company,offer,attempt,data,emails,password,api_read,passed,privacy_artifacts)
except Exception as exc:
    failure=type(exc).__name__
    failure_location=[{'file':Path(frame.filename).name,'line':frame.lineno} for frame in traceback.extract_tb(exc.__traceback__)]
finally:
    # Only this run's random synthetic accounts; erased invitations remain scoped by their owned companies.
    Invitation.objects.filter(candidate__user__username=emails[0]).delete()
    Invitation.objects.filter(company__user__username__in=emails[1:]).delete()
    User.objects.filter(username__in=emails).delete()
    cleaned=not User.objects.filter(username__in=emails).exists()
report={'status':'FAIL' if failure else 'PASS','commit':locals().get('version'),'url':base,
    'checked_at':datetime.now(timezone.utc).isoformat(),'checks':checks,'failure_type':failure,
    'failure_location':locals().get('failure_location',[]),'privacy':args.privacy,
    'privacy_artifacts':privacy_artifacts,
    'driver_sha256':{name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()
        for name in ['check_live_checkpoint.py']+(['live_privacy_checkpoint.py'] if args.privacy else [])},
    'synthetic_accounts_removed':cleaned,'scope':'HTTPS journey; no existing account reset; perfect-answer synthetic fixture is not QA-001 validation'}
print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
raise SystemExit(1 if failure or not cleaned else 0)
