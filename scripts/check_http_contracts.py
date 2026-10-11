#!/usr/bin/env python3
"""Validate saved OpenAPI and exercise independent browser HTTP expectations on a disposable DB."""
import argparse
import ast
import copy
import datetime
import hashlib
import inspect
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import textwrap
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
HTTP_METHODS = {'get','post','head','options','put','patch','delete','trace'}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def actual_routes():
    from config.urls import urlpatterns
    from django.urls import URLResolver
    result = {}
    def flattened(routes,prefix=''):
        for route in routes:
            if isinstance(route,URLResolver):yield from flattened(route.url_patterns,prefix+str(route.pattern))
            else:yield prefix+str(route.pattern),route
    for raw_path,route in flattened(urlpatterns):
        path = '/' + re.sub(r'<(?:int|str|path|slug|uuid):([^>]+)>', r'{\1}', raw_path)
        callback = route.callback
        cls = getattr(callback, 'view_class', None)
        if cls:
            names = callback.view_initkwargs.get('http_method_names', cls.http_method_names)
            methods = {m for m in names if hasattr(cls, m) or m == 'head' and hasattr(cls, 'get')}
        else:
            tree = ast.parse(textwrap.dedent(inspect.getsource(inspect.unwrap(callback))))
            decorators = tree.body[0].decorator_list
            methods = None
            for decorator in decorators:
                if isinstance(decorator, ast.Name) and decorator.id == 'require_safe':methods = {'get','head'}
                if isinstance(decorator, ast.Name) and decorator.id == 'require_POST':methods = {'post'}
                if isinstance(decorator, ast.Name) and decorator.id == 'require_GET':methods = {'get'}
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name) and decorator.func.id == 'require_http_methods':
                    methods = {m.lower() for m in ast.literal_eval(decorator.args[0])}
                if isinstance(decorator,ast.Call) and isinstance(decorator.func,ast.Name) and decorator.func.id=='endpoint':
                    value=next((kw.value for kw in decorator.keywords if kw.arg=='methods'),None)
                    methods={m.lower() for m in ast.literal_eval(value)} if value is not None else {'get'}
            require(methods is not None, f'{path}: missing explicit HTTP method guard')
        result[path] = (route.name, methods)
    return result


def check_coverage(spec):
    routes = actual_routes()
    require(set(routes) == set(spec['paths']), 'URL coverage differs: ' + str(set(routes) ^ set(spec['paths'])))
    for path, (name, methods) in routes.items():
        ops = spec['paths'][path]
        require({k for k in ops if k in HTTP_METHODS} == methods, f'{path}: method coverage mismatch')
        for method in methods:
            require(ops[method].get('x-django-url-name') == name, f'{path}: wrong Django name')
            require('default' not in ops[method]['responses'], f'{path}: permissive default hides errors')
    return len(routes), sum(len(v[1]) for v in routes.values())


def schema_check(spec, schema, value):
    from jsonschema import Draft202012Validator, FormatChecker
    def rewrite(obj):
        if isinstance(obj, list):return [rewrite(x) for x in obj]
        if isinstance(obj, dict):return {k: v.replace('#/components/schemas/', '#/$defs/') if k == '$ref' else rewrite(v) for k,v in obj.items()}
        return obj
    root = rewrite(copy.deepcopy(schema))
    root['$defs'] = rewrite(spec['components']['schemas'])
    Draft202012Validator(root, format_checker=FormatChecker()).validate(value)


def check_examples(spec):
    count = 0
    for operations in spec['paths'].values():
        for method, op in operations.items():
            if method not in HTTP_METHODS:continue
            containers = [op.get('requestBody', {})] + list(op['responses'].values())
            for container in containers:
                for media in container.get('content', {}).values():
                    for example in media.get('examples', {}).values():
                        schema_check(spec, media['schema'], example['value']);count += 1
    from http_contracts import FORM_CLASSES
    for name,cls in FORM_CLASSES.items():
        documented = set(spec['components']['schemas'][name]['properties'])
        instance=cls(company=None) if name=='Assignment' else cls()
        require(set(instance.fields) <= documented, f'{name}: field missing in schema')
    from profiles.forms import ExperienceFormSet
    fields = set(ExperienceFormSet().empty_form.fields)
    require(fields == {'organization','role','months','description','id','DELETE','profile'}, 'Experience formset changed: review dynamic schema')
    return count


def check_response(spec, path, method, response, body):
    operations = spec['paths'][path]
    op = operations.get(method.lower()) or next(iter(operations.values()))
    status = str(response.status_code)
    require(status in op['responses'], f'{method} {path}: undocumented HTTP {status}')
    contract = op['responses'][status]
    for name,header in contract.get('headers',{}).items():
        if header.get('required'):require(name in response, f'{path}: missing {name}')
        if name in response and header.get('schema'):schema_check(spec,header['schema'],response[name])
    if method == 'HEAD':
        require(body == b'', f'{path}: HEAD returned a body');return
    content = contract.get('content', {})
    if content:
        media = response.get('Content-Type','').split(';',1)[0]
        require(media in content, f'{path}: undocumented response media {media}')
        if media == 'application/json':schema_check(spec, content[media]['schema'], json.loads(body))
        elif media == 'application/pdf':require(body.startswith(b'%PDF-'), f'{path}: PDF bytes missing signature')
        elif media == 'application/octet-stream':require(body.startswith(b'PK\x03\x04'),f'{path}: wheel ZIP signature missing')
        elif media == 'application/gzip':require(body.startswith(b'\x1f\x8b'),f'{path}: archive gzip signature missing')
        else:schema_check(spec, content[media]['schema'], body.decode())


def runtime_checks(spec, report):
    from django.core.management import call_command
    from django.test import Client, override_settings
    from django.utils import timezone
    from django.db import DatabaseError
    from datetime import timedelta
    from unittest.mock import patch
    from accounts.models import User, ConsentEvent
    from profiles.models import Profile
    from hiring.models import Company, Need, Invitation
    from assessments.models import Attempt
    from assistant.models import Draft, Usage
    call_command('migrate', verbosity=0)
    clients, users, seen = {}, {}, set()
    checks = report['runtime']
    now = timezone.now()
    password = 'Demo-Contract-934!'
    def user(key, role, confirmed=True, consent=True):
        obj = User.objects.create_user(username=f'{key}@demo.invalid',email=f'{key}@demo.invalid',password=password,
            role=role,email_confirmed=confirmed,processing_consented_at=now if consent else None,
            processing_consent_version='processing-v1' if consent else '')
        if role == 'candidate':Profile.objects.create(user=obj)
        users[key]=obj
        client=Client(enforce_csrf_checks=True);client.force_login(obj);client.get('/accounts/login/')
        clients[key]=client
        return obj
    candidate=user('candidate','candidate');other=user('other','candidate')
    employer=user('employer','employer');other_employer=user('otheremployer','employer')
    user('unconfirmed','candidate',confirmed=False);user('unconsented','candidate',consent=False)
    profile=Profile.objects.get(user=candidate);other_profile=Profile.objects.get(user=other)
    company=Company.objects.create(user=employer,name='Company',contact_email='company@demo.invalid')
    foreign_company=Company.objects.create(user=other_employer,name='Other',contact_email='other@demo.invalid')
    need_data={'title':'iOS разработчик','grade':'Junior','skills':'Swift, Core Data','tasks':'Сделать экран',
        'salary_min':90000,'salary_max':120000,'work_format':'remote','next_step':'Встреча','company_name':'Компания','company_email':'company@demo.invalid'}
    def run(label, key, path, method='GET', data=None, expected=200, template=None, location=None, csrf=True, raw_json=False, valid_body=None,bearer=None):
        client=clients[key] if isinstance(key,str) else key
        if valid_body:
            schema_check(spec, {'$ref':'#/components/schemas/'+valid_body}, data)
        headers={}
        if bearer:headers['HTTP_AUTHORIZATION']='Bearer '+bearer
        if method not in {'GET','HEAD','OPTIONS'} and csrf:
            token=client.cookies.get('csrftoken')
            if token:headers['HTTP_X_CSRFTOKEN']=token.value
        if method in {'GET','HEAD','OPTIONS'}:response=client.generic(method,path,**headers)
        elif raw_json:response=client.generic(method,path,json.dumps(data or {}),content_type='application/json',**headers)
        else:
            payload={k: ('true' if v is True else 'false' if v is False else v) for k,v in (data or {}).items()}
            response=client.generic(method,path,urlencode(payload,doseq=True),content_type='application/x-www-form-urlencoded',**headers)
        body=b''.join(response.streaming_content) if response.streaming else response.content
        require(response.status_code == expected, f'{label}: expected {expected}, got {response.status_code}')
        route=template or path.split('?',1)[0]
        check_response(spec,route,method,response,body)
        if location:require(response.get('Location')==location, f'{label}: wrong Location {response.get("Location")}')
        if method.lower() in spec['paths'][route]:seen.add((route,method.lower()))
        checks.append({'id':label,'method':method,'route':route,'expected_status':expected,'actual_status':response.status_code,
            'content_type':response.get('Content-Type'),'location':response.get('Location'),'status':'PASS'})
        response.close()
        return response,body
    def rendered_path(path,pk=1):
        if path=='/drafts/{pk}/' and isinstance(pk,int):pk='00000000-0000-0000-0000-000000000001'
        return path.replace('{pk}',str(pk)).replace('{track}','ios').replace('{grade}','Junior').replace('{topic}','swift').replace('{filename}','manifest.json')
    anonymous=Client(enforce_csrf_checks=True)
    run('welcome',anonymous,'/')
    run('privacy',anonymous,'/accounts/privacy/')
    # Independent auth expectations; do not obtain expected statuses from the spec.
    for path,operations in spec['paths'].items():
        if path.startswith('/api/v1'):continue
        role=next(iter(operations.values()))['x-role']
        if role not in {'candidate','employer','both','authenticated'}:continue
        rendered=rendered_path(path,9223372036854775807)
        method='GET' if 'get' in operations else 'POST'
        anonymous.get('/accounts/login/')
        response,_=run('auth-'+path,anonymous,rendered,method,expected=302,template=path)
        require(response['Location'].startswith('/accounts/login/?next='),'Anonymous access does not redirect to login')
        if role in {'candidate','employer','both'}:
            # Correct role but no consent. Wrong role is checked before consent.
            if role in {'candidate','both'}:
                run('consent-guard-'+path,'unconsented',rendered,method,expected=302,template=path,location='/accounts/consent/')
                run('email-guard-'+path,'unconfirmed',rendered,method,expected=403,template=path)
            if role=='employer':run('role-'+path,'candidate',rendered,method,expected=403,template=path)
            if role=='candidate':run('role-'+path,'employer',rendered,method,expected=403,template=path)
    public=Client(enforce_csrf_checks=True)
    run('register-form',public,'/accounts/register/')
    run('register-csrf',public,'/accounts/register/','POST',{},403,csrf=False)
    run('register-invalid',public,'/accounts/register/','POST',{},200)
    registration={'email':'registered@demo.invalid','role':'candidate','password1':password,'password2':password,'processing_consent':True}
    run('register-valid',public,'/accounts/register/','POST',registration,302,location='/accounts/confirm/',valid_body='Registration')
    require(User.objects.filter(username='registered@demo.invalid',is_active=False).exists(),'Registration activated before confirmation')
    run('confirm-form',public,'/accounts/confirm/')
    run('confirm-invalid',public,'/accounts/confirm/','POST',{'token':'invalid'},400)
    token=public.session['pending_registration']['token']
    run('confirm-valid',public,'/accounts/confirm/','POST',{'token':token},302,location='/',valid_body='Confirmation')
    run('confirm-repeat',public,'/accounts/confirm/','POST',{'token':token},404)
    run('register-duplicate',public,'/accounts/register/','POST',registration,200)
    run('consent-form','unconsented','/accounts/consent/')
    run('consent-invalid','unconsented','/accounts/consent/','POST',{},200)
    run('consent-valid','unconsented','/accounts/consent/','POST',{'processing_consent':True},302,location='/',valid_body='Consent')
    before=ConsentEvent.objects.filter(user=users['unconsented']).count()
    run('consent-repeat','unconsented','/accounts/consent/','POST',{'processing_consent':True},302,location='/')
    require(ConsentEvent.objects.filter(user=users['unconsented']).count()==before,'Repeated consent event duplicated')
    login_client=Client(enforce_csrf_checks=True)
    run('login-get',login_client,'/accounts/login/')
    run('login-invalid',login_client,'/accounts/login/','POST',{'username':'missing','password':'bad'},200)
    run('login-valid-safe-next',login_client,'/accounts/login/','POST',{'username':candidate.username,'password':password,'next':'https://foreign.invalid/'},302,location='/')
    run('login-head',login_client,'/accounts/login/','HEAD')
    run('login-options',login_client,'/accounts/login/','OPTIONS')
    run('logout-options',login_client,'/accounts/logout/','OPTIONS')
    run('logout-csrf',login_client,'/accounts/logout/','POST',{},403,csrf=False)
    run('logout-valid',login_client,'/accounts/logout/','POST',{},302,location='/',valid_body='CsrfOnly')
    require('_auth_user_id' not in login_client.session,'Logout did not clear session')
    run('logout-repeat',login_client,'/accounts/logout/','POST',{},302,location='/')
    profile_data={'name':'Анна','city':'Москва','skills':'Swift, Core Data','desired_grade':'Junior','published':True,
        'contact_email':'private@demo.invalid','description':'Приватный текст','roles':['developer','reviewer'],'soft_skills':['teamwork'],
        'specialization':'ios_swift','experience_months':12,'confirmed_grade':'Middle',
        'experience-TOTAL_FORMS':1,'experience-INITIAL_FORMS':0,'experience-0-organization':'Проект','experience-0-role':'Разработчик','experience-0-months':12,'experience-0-description':'Описание опыта'}
    run('profile-invalid','candidate','/profile/','POST',{},200)
    run('profile-valid','candidate','/profile/','POST',profile_data,302,location='/profile/',valid_body='Profile')
    profile.refresh_from_db();require(profile.confirmed_grade=='' and profile.experiences.count()==1,'Profile write accepted grade or lost experience')
    run('profile-json-ignored','candidate','/profile/','POST',{'desired_grade':'Middle','published':False},200,raw_json=True)
    profile.refresh_from_db();require(profile.published and profile.desired_grade=='Junior','JSON parsed as writable form')
    run('fsp-connect-invalid','candidate','/profile/fsp/link/','POST',{'external_id':'DEMO-000','consent':True},200)
    for external, status in [('DEMO-001','demo_history'),('DEMO-EMPTY','no_history'),('DEMO-DOWN','unavailable')]:
        run('fsp-connect-'+external,'candidate','/profile/fsp/link/','POST',{'external_id':external,'consent':True},302,location='/profile/fsp/link/',valid_body='FspAction')
        _,body=run('fsp-json-'+status,'candidate','/profile/fsp/')
        require(json.loads(body)['status']==status,'FSP state response mismatch')
    run('fsp-unlink','candidate','/profile/fsp/link/','POST',{'action':'unlink'},302,location='/profile/fsp/link/',valid_body='FspAction')
    _,body=run('fsp-json-disconnected','candidate','/profile/fsp/')
    require(json.loads(body)['status']=='not_connected','Unlink failed')
    run('company-invalid','employer','/company/','POST',{},200)
    run('company-valid','employer','/company/','POST',{'name':'Компания','industry':'Разработка','description':'Продукт','contact_email':'company@demo.invalid'},302,location='/company/',valid_body='Company')
    run('need-invalid','employer','/company/needs/','POST',{**need_data,'salary_min':150000},200)
    run('need-valid','employer','/company/needs/','POST',need_data,302,location='/candidates/',valid_body='Need')
    need=Need.objects.get(company=company)
    foreign_need=Need.objects.create(company=foreign_company,**{k:v for k,v in need_data.items() if k not in {'company_name','company_email'}})
    run('team-add','employer','/company/team/','POST',{'action':'add','name':'Рекрутер'},302,location='/company/dashboard/',valid_body='TeamAction')
    from hiring.models import Recruiter
    recruiter=Recruiter.objects.get(company=company)
    run('team-assign','employer','/company/team/','POST',{'action':'assign','need':need.pk,'recruiter':recruiter.pk},302,location='/company/dashboard/',valid_body='TeamAction')
    run('team-invalid','employer','/company/team/','POST',{'action':'assign','need':foreign_need.pk},302,location='/company/dashboard/')
    run('team-unknown','employer','/company/team/','POST',{'action':'unknown'},404)
    run('dashboard-filter','employer',f'/company/dashboard/?period=7&hr={recruiter.pk}&need={need.pk}',template='/company/dashboard/')
    run('dashboard-invalid-period','employer','/company/dashboard/?period=wrong',expected=404,template='/company/dashboard/')
    run('token-invalid','candidate','/accounts/integrations/','POST',{'action':'create','name':'MCP','kind':'mcp','contacts':True},400)
    run('token-create','candidate','/accounts/integrations/','POST',{'action':'create','name':'CLI','kind':'cli'},200,valid_body='TokenAction')
    from accounts.models import ApiToken
    token=ApiToken.objects.get(user=candidate)
    run('token-revoke','candidate','/accounts/integrations/','POST',{'action':'revoke','id':token.pk},302,location='/accounts/integrations/',valid_body='TokenAction')
    run('token-revoke-repeat','candidate','/accounts/integrations/','POST',{'action':'revoke','id':token.pk},302,location='/accounts/integrations/')
    run('token-revoke-foreign','other','/accounts/integrations/','POST',{'action':'revoke','id':token.pk},404)
    run('start-invalid','candidate','/assessments/start/','POST',{'grade':'Unknown'},302,location='/assessments/')
    run('start-valid','candidate','/assessments/start/','POST',{'grade':'Junior'},302,valid_body='StartAttempt')
    attempt=Attempt.objects.get(candidate=profile,status='active');attempt_path=f'/assessments/{attempt.pk}/'
    run('start-reuse','candidate','/assessments/start/','POST',{'grade':'Middle'},302,location=attempt_path)
    require(Attempt.objects.filter(candidate=profile).count()==1,'Active start created duplicate')
    run('attempt-active','candidate',attempt_path,template='/assessments/{pk}/')
    run('assistant-active','candidate','/assistant/','POST',{'mode':'profile'},409)
    run('proof-active','candidate',f'/assessments/{attempt.pk}/proof/',expected=404,template='/assessments/{pk}/proof/')
    run('answer-invalid','candidate',attempt_path+'answer/','POST',{'q_foreign':1},302,template='/assessments/{pk}/answer/',location=attempt_path)
    attempt.refresh_from_db();require(attempt.answers=={},'Invalid question partially saved')
    answers={'q_'+task['id']:task['correct'] for task in attempt.tasks}  # Test fixture only; never output keys.
    run('answer-valid','candidate',attempt_path+'answer/','POST',answers,302,template='/assessments/{pk}/answer/',location=attempt_path,valid_body='Answers')
    run('finish-valid','candidate',attempt_path+'finish/','POST',{},302,template='/assessments/{pk}/finish/',location=attempt_path,valid_body='Answers')
    attempt.refresh_from_db();require(attempt.passed and attempt.correct_count==8,'Finished score mismatch')
    run('finish-repeat','candidate',attempt_path+'finish/','POST',{'q_foreign':'bad','score':0},302,template='/assessments/{pk}/finish/',location=attempt_path)
    attempt.refresh_from_db();require(attempt.correct_count==8,'Repeated finish rewrote score')
    run('start-cooldown','candidate','/assessments/start/','POST',{'grade':'Junior'},302,location='/assessments/')
    run('filter-invalid','employer','/candidates/?grade=Unknown',template='/candidates/')
    for value in ['²','-1','9'*30,str(foreign_need.pk)]:
        run('need-id-'+value[:10],'employer','/candidates/?'+urlencode({'need':value}),expected=404,template='/candidates/')
    run('assistant-profile','candidate','/assistant/','POST',{'mode':'profile'},200,valid_body='Assistant')
    draft=Draft.objects.filter(user=candidate).latest('pk');draft_path=f'/assistant/drafts/{draft.pk}/'
    run('draft-get','candidate',draft_path,template='/assistant/drafts/{pk}/')
    run('draft-invalid','candidate',draft_path,'POST',{},400,template='/assistant/drafts/{pk}/')
    run('draft-apply-profile','candidate',draft_path,'POST',{'description':'Проверенный текст','published':False,'confirmed_grade':'Middle'},302,template='/assistant/drafts/{pk}/',location='/profile/',valid_body='DraftApply')
    run('draft-repeat-profile','candidate',draft_path,'POST',{},302,template='/assistant/drafts/{pk}/',location='/profile/')
    profile.refresh_from_db();require(profile.description=='Проверенный текст' and profile.published and profile.confirmed_grade=='Junior','Draft wrote protected profile fields')
    for label in ['stale','expired']:
        run('generate-'+label,'candidate','/assistant/','POST',{'mode':'profile'})
        item=Draft.objects.filter(user=candidate).latest('pk')
        if label=='stale':Profile.objects.filter(pk=profile.pk).update(description='Ручная правка')
        else:Draft.objects.filter(pk=item.pk).update(expires_at=now-timedelta(seconds=1))
        run('draft-'+label,'candidate',f'/assistant/drafts/{item.pk}/','POST',{'description':'Новый текст'},409 if label=='stale' else 410,template='/assistant/drafts/{pk}/')
    run('draft-foreign','other',draft_path,expected=404,template='/assistant/drafts/{pk}/')
    run('assistant-result','candidate','/assistant/','POST',{'mode':'result','identifier':attempt.pk})
    run('assistant-result-empty','other','/assistant/','POST',{'mode':'result'},400)
    run('assistant-role','candidate','/assistant/','POST',{'mode':'need'},403)
    run('assistant-need','employer','/assistant/','POST',{'mode':'need','new_need':'on','grade':'Junior','skills':'Swift'},200,valid_body='Assistant')
    ndraft=Draft.objects.filter(user=employer).latest('pk');ndraft_path=f'/assistant/drafts/{ndraft.pk}/'
    run('draft-apply-need','employer',ndraft_path,'POST',need_data,302,template='/assistant/drafts/{pk}/',location='/company/needs/',valid_body='DraftApply')
    count=Need.objects.filter(company=company).count()
    run('draft-repeat-need','employer',ndraft_path,'POST',{},302,template='/assistant/drafts/{pk}/',location='/company/needs/')
    require(Need.objects.filter(company=company).count()==count==2,'Draft repeat created second Need')
    for mode in ['matching','invitation']:
        run('assistant-'+mode,'employer','/assistant/','POST',{'mode':mode,'need':need.pk,'candidate':profile.pk})
        run('assistant-'+mode+'-missing','employer','/assistant/','POST',{'mode':mode},400)
    send_data={'need':need.pk,'candidate':profile.pk,'accepted_attempts':[attempt.pk],'discussion':'Обсудим условия'}
    run('send-valid','employer','/invitations/send/','POST',send_data,302,location='/invitations/',valid_body='Invitation')
    invitation=Invitation.objects.get(need=need,candidate=profile);snapshot=copy.deepcopy(invitation.snapshot)
    run('send-repeat','employer','/invitations/send/','POST',{**send_data,'discussion':'Новое'},302,location='/invitations/')
    invitation.refresh_from_db();require(invitation.snapshot==snapshot and Invitation.objects.count()==1,'Duplicate rewrote snapshot')
    for key in ['candidate','employer']:
        run('assistant-conversation-'+key,key,'/assistant/','POST',{'mode':'conversation','invitation':invitation.pk})
    run('stage-partial-get','employer',f'/assistant/?mode=matching&need={foreign_need.pk}',template='/assistant/')
    run('stage-complete-foreign','employer',f'/assistant/?mode=matching&need={foreign_need.pk}&candidate={profile.pk}',expected=404,template='/assistant/')
    run('conversation-foreign','otheremployer','/assistant/','POST',{'mode':'conversation','invitation':invitation.pk},404)
    _,body=run('candidate-before-contact','employer',f'/candidates/{profile.pk}/',template='/candidates/{pk}/')
    require(b'private@demo.invalid' not in body and 'Ручная правка'.encode() not in body,'Private data visible before acceptance')
    run('accept-foreign','other',f'/invitations/{invitation.pk}/accept/','POST',{},404,template='/invitations/{pk}/accept/')
    run('accept-valid','candidate',f'/invitations/{invitation.pk}/accept/','POST',{},302,template='/invitations/{pk}/accept/',location='/invitations/')
    run('accept-repeat','candidate',f'/invitations/{invitation.pk}/accept/','POST',{},302,template='/invitations/{pk}/accept/',location='/invitations/')
    run('decline-conflict','candidate',f'/invitations/{invitation.pk}/decline/','POST',{},302,template='/invitations/{pk}/decline/',location='/invitations/')
    invitation.refresh_from_db();require(invitation.status=='accepted','Opposite decision changed final status')
    _,body=run('candidate-after-contact','employer',f'/candidates/{profile.pk}/',template='/candidates/{pk}/')
    require(b'private@demo.invalid' in body,'Acceptance did not open sender contact')
    _,body=run('candidate-other-company','otheremployer',f'/candidates/{profile.pk}/',template='/candidates/{pk}/')
    require(b'private@demo.invalid' not in body,'Another company obtained contact grant')
    run('proof-employer','employer',f'/assessments/{attempt.pk}/proof/',template='/assessments/{pk}/proof/')
    other_profile.confirmed_grade='Junior';other_profile.published=True;other_profile.save()
    run('send-for-decline','otheremployer','/invitations/send/','POST',{'need':foreign_need.pk,'candidate':other_profile.pk},302,location='/invitations/')
    declined=Invitation.objects.get(candidate=other_profile,need=foreign_need)
    run('decline-valid','other',f'/invitations/{declined.pk}/decline/','POST',{},302,template='/invitations/{pk}/decline/',location='/invitations/')
    run('decline-repeat','other',f'/invitations/{declined.pk}/decline/','POST',{},302,template='/invitations/{pk}/decline/',location='/invitations/')
    declined.refresh_from_db();require(declined.status=='declined','Decline/repeat did not preserve decision')
    expired=Attempt.objects.create(candidate=profile,grade='Junior',bank_version=attempt.bank_version,variant=attempt.variant,
        tasks=attempt.tasks,started_at=now-timedelta(minutes=20),expires_at=now-timedelta(minutes=5))
    expired_path=f'/assessments/{expired.pk}/'
    run('answer-expired','candidate',expired_path+'answer/','POST',answers,302,template='/assessments/{pk}/answer/',location=expired_path)
    run('finish-expired','candidate',expired_path+'finish/','POST',answers,302,template='/assessments/{pk}/finish/',location=expired_path)
    expired.refresh_from_db();require(expired.expired and expired.answers=={} and expired.correct_count==0,'Late answers affected expired score')
    company.refresh_from_db();company.contact_email='';company.save(update_fields=['contact_email'])
    another_need=Need.objects.exclude(pk=need.pk).get(company=company)
    run('send-email-missing','employer','/invitations/send/','POST',{'need':another_need.pk,'candidate':profile.pk},302,location='/company/')
    company.contact_email='company@demo.invalid';company.save(update_fields=['contact_email'])
    run('send-proof-invalid','employer','/invitations/send/','POST',{'need':another_need.pk,'candidate':profile.pk,'accepted_attempts':[9223372036854775807]},302,location=f'/candidates/{profile.pk}/')
    run('send-id-invalid','employer','/invitations/send/','POST',{'need':'²','candidate':profile.pk},404)
    # Real failure shapes: no fake success/fallback response.
    with patch('assistant.provider.generate',side_effect=RuntimeError('fixture failure')):
        run('provider-failure','employer','/assistant/','POST',{'mode':'need','new_need':'on'},503)
    Usage.objects.filter(user=employer).update(count=10)
    run('provider-limit','employer','/assistant/','POST',{'mode':'need','new_need':'on'},429)
    with patch('accounts.models.User.objects.exists',side_effect=DatabaseError('fixture unavailable')):
        run('health-unavailable',anonymous,'/health/',expected=503)
    # Token API DTOs are exercised independently through the same Django handler.
    from api.core import issue_token
    token_pairs={key:issue_token(users[key],'contract-'+key,'cli',contacts=True,drafts=True) for key in ['candidate','employer','otheremployer']}
    mcp_token,mcp_secret=issue_token(candidate,'contract-mcp','mcp')
    from http_contract_scenarios import learning_scenarios, action_scenarios
    learning_session=learning_scenarios(run,require,profile,other_profile)
    action_draft=action_scenarios(run,require,anonymous,users,profile,company,need,token_pairs)
    api_pk={'/api/v1/drafts/{pk}':action_draft.pk,'/api/v1/me/assessments/{pk}/result':attempt.pk,'/api/v1/needs/{pk}':need.pk,
        '/api/v1/invitations/{pk}':invitation.pk,'/api/v1/invitations/{pk}/contacts':invitation.pk}
    for path,operations in spec['paths'].items():
        if not path.startswith('/api/v1'):continue
        if 'get' not in operations:continue
        op=operations['get'];scopes=' '.join(op.get('x-required-scopes',[]))
        key='employer' if 'employer.read' in scopes and ' OR ' not in scopes else 'candidate'
        pk=api_pk.get(path,profile.pk);rendered=path.replace('{pk}',str(pk)).replace('{unknown}','not-a-route')
        query='?need_id='+str(need.pk) if path=='/api/v1/candidates' else ''
        expected=404 if path in {'/api/v1/','/api/v1/{unknown}'} else 200
        # Keep each response test below the separate rate-limit fixture.
        ApiToken.objects.filter(pk=token_pairs[key][0].pk).update(request_count=0)
        run('api-read-'+path,anonymous,rendered+query,expected=expected,template=path,bearer=token_pairs[key][1])
        run('api-no-token-'+path,anonymous,rendered,expected=401,template=path)
        run('api-put-'+path,anonymous,rendered,'PUT',{},404 if path in {'/api/v1/','/api/v1/{unknown}'} else 405,template=path,bearer=token_pairs[key][1])
        if path in {'/api/v1/','/api/v1/{unknown}'}:
            for method in ['POST','PATCH','DELETE','HEAD','OPTIONS']:
                run('api-fallback-'+method+path,anonymous,rendered,method,{},404,template=path,bearer=token_pairs[key][1])
            run('api-fallback-trace-'+path,anonymous,rendered,'TRACE',{},405,template=path,bearer=token_pairs[key][1])
    run('api-mcp-private',anonymous,'/api/v1/me/profile/private',expected=403,bearer=mcp_secret)
    run('api-mcp-pdf',anonymous,'/api/v1/me/profile/resume.pdf',expected=403,bearer=mcp_secret)
    run('api-other-company-contacts',anonymous,f'/api/v1/candidates/{profile.pk}/private',expected=403,template='/api/v1/candidates/{pk}/private',bearer=token_pairs['otheremployer'][1])
    run('api-invalid-id',anonymous,'/api/v1/needs/²',expected=404,template='/api/v1/needs/{pk}',bearer=token_pairs['employer'][1])
    run('api-invalid-pagination',anonymous,'/api/v1/needs?limit=0',expected=400,template='/api/v1/needs',bearer=token_pairs['employer'][1])
    ApiToken.objects.filter(pk=mcp_token.pk).update(request_count=60,window_start=timezone.now())
    run('api-rate-limit',anonymous,'/api/v1/me',expected=429,bearer=mcp_secret)
    ApiToken.objects.filter(pk=mcp_token.pk).update(revoked_at=timezone.now())
    run('api-revoked',anonymous,'/api/v1/me',expected=401,bearer=mcp_secret)
    # Every supported read/HEAD operation with valid context, and every method guard.
    pk_map={'/drafts/{pk}/':action_draft.pk,'/learning/sessions/{pk}/':learning_session.pk,'/learning/sessions/{pk}/answer/':learning_session.pk,'/candidates/{pk}/':profile.pk,'/candidates/{pk}/resume.pdf':profile.pk,
        '/assessments/{pk}/':attempt.pk,'/assessments/{pk}/proof/':attempt.pk,
        '/assessments/{pk}/answer/':attempt.pk,'/assessments/{pk}/finish/':attempt.pk,
        '/assistant/drafts/{pk}/':draft.pk,'/invitations/{pk}/accept/':invitation.pk,'/invitations/{pk}/decline/':invitation.pk}
    for path, operations in spec['paths'].items():
        if path.startswith('/api/v1'):continue
        role=next(iter(operations.values()))['x-role'];key='employer' if role=='employer' else 'candidate'
        if role in {'public','pending-session'}:key=anonymous
        rendered=rendered_path(path,pk_map.get(path,1))
        if path=='/accounts/confirm/':
            # Create a fresh pending registration for read coverage.
            pending=Client(enforce_csrf_checks=True);pending.get('/accounts/register/')
            run('pending-create',pending,'/accounts/register/','POST',{**registration,'email':'pending@demo.invalid'},302)
            key=pending
        for method in ['GET','HEAD']:
            if method.lower() not in operations:continue
            expected=302 if path=='/' and isinstance(key,str) else 200
            run('read-'+method+'-'+path,key,rendered,method,expected=expected,template=path)
        response,_=run('method-PUT-'+path,key,rendered,'PUT',{},405,template=path)
        require(set(response['Allow'].replace(' ','').lower().split(','))=={m for m in operations if m in HTTP_METHODS},f'{path}: Allow mismatch')
        if '{pk}' in path:
            method='GET' if 'get' in operations else 'POST'
            run('foreign-object-'+path,key,rendered_path(path,9223372036854775807),method,{},404,template=path)
    from api.views import client_version
    for filename in [f'fsp_client-{client_version()}-py3-none-any.whl',f'fsp_client-{client_version()}.tar.gz']:
        run('download-'+filename,anonymous,'/downloads/'+filename,template='/downloads/{filename}')
    _,body=run('download-manifest-integrity',anonymous,'/downloads/manifest.json',template='/downloads/{filename}')
    manifest=json.loads(body)
    for artifact in manifest['files']:
        payload=(ROOT/'.runtime/downloads'/artifact['filename']).read_bytes()
        require(len(payload)==artifact['bytes'] and hashlib.sha256(payload).hexdigest()==artifact['sha256'],'Download manifest mismatch')
    from zipfile import ZipFile
    wheel=ROOT/'.runtime/downloads'/f'fsp_client-{client_version()}-py3-none-any.whl'
    with ZipFile(wheel) as archive:
        source_dir=ROOT/'clients/python/src/fsp_client'
        for source in source_dir.rglob('*.py'):
            require(archive.read('fsp_client/'+source.relative_to(source_dir).as_posix())==source.read_bytes(),'Client download is stale: '+source.name)
    report['download_source_match']={'status':'PASS','format':'wheel','scope':'all current fsp_client Python sources match packaged bytes'}
    run('download-unknown',anonymous,'/downloads/not-allowed',expected=404,template='/downloads/{filename}')
    expected_ops={(p,m) for p,ops in spec['paths'].items() for m in ops if m in HTTP_METHODS}
    require(seen==expected_ops,'Runtime operations missing: '+str(expected_ops-seen))
    report['runtime_operation_coverage']={'status':'PASS','covered':len(seen),'total':len(expected_ops)}
    # Independent counterfactuals prove that the verifier can reject a plausible bad contract.
    bad=copy.deepcopy(spec);del bad['paths']['/accounts/privacy/']
    try:check_coverage(bad)
    except AssertionError:report['counterfactuals'].append({'id':'removed-route','status':'PASS','meaning':'Rejected'})
    else:raise AssertionError('Verifier accepted missing route')
    response,body=run('counterfactual-health-baseline',anonymous,'/health/')
    bad=copy.deepcopy(spec);bad['paths']['/health/']['get']['responses'].pop('200')
    try:check_response(bad,'/health/','GET',response,body)
    except AssertionError:report['counterfactuals'].append({'id':'wrong-success-status','status':'PASS','meaning':'Rejected'})
    else:raise AssertionError('Verifier accepted missing success response')
    bad=copy.deepcopy(spec);bad['components']['schemas']['HealthOk']['properties']['status']['const']='ready'
    try:check_response(bad,'/health/','GET',response,body)
    except Exception as exc:
        from jsonschema import ValidationError
        require(isinstance(exc,ValidationError),'Unexpected counterfactual exception');report['counterfactuals'].append({'id':'wrong-json-field','status':'PASS','meaning':'Rejected'})
    else:raise AssertionError('Verifier accepted false JSON schema')
    bad=copy.deepcopy(spec)
    variant=next(v for v in bad['components']['schemas']['ActionPrepare']['oneOf'] if v['properties']['kind']['const']=='profile.update')
    variant['properties']['payload']['properties']['city']={'const':'Wrong city'}
    try:schema_check(bad,{'$ref':'#/components/schemas/ActionPrepare'},{'kind':'profile.update','payload':{'city':'Казань'}})
    except Exception as exc:
        from jsonschema import ValidationError
        require(isinstance(exc,ValidationError),'Unexpected request counterfactual exception');report['counterfactuals'].append({'id':'wrong-v2-request-field','status':'PASS','meaning':'Rejected'})
    else:raise AssertionError('Verifier accepted false V2 request schema')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec',type=Path,default=ROOT/'doc/api/openapi.json')
    parser.add_argument('--output',type=Path,default=ROOT/'.runtime/qa/http-contracts.json');args=parser.parse_args()
    report={'task':'DOC-003','checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'source_hashes':{},'runtime':[],'counterfactuals':[],'status':'FAIL'}
    try:
        with tempfile.TemporaryDirectory(prefix='fsp-http-contracts-') as tmp:
            # These precede Django setup, even if parent env or worktree had a production path.
            os.environ.update(FSP_ENV_FILE='/dev/null',DATABASE_PATH=str(Path(tmp)/'contract.sqlite3'),DEBUG='1',
                ALLOWED_HOSTS='testserver,localhost,127.0.0.1',DJANGO_SETTINGS_MODULE='config.settings')
            import django
            django.setup()
            # Expected negative cases are captured in evidence, not emitted as hundreds of tracebacks.
            logging.getLogger('django.request').setLevel(logging.CRITICAL)
            logging.getLogger('django.security.csrf').setLevel(logging.CRITICAL)
            logging.getLogger('fsp.api').setLevel(logging.CRITICAL)
            from django.test import override_settings
            from openapi_spec_validator import validate
            spec=json.loads(args.spec.read_text());validate(spec)
            paths, operations=check_coverage(spec)
            report['structure']={'status':'PASS','paths':paths,'operations':operations,'validated_examples':check_examples(spec),'openapi':'3.1.1'}
            with override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}}):
                runtime_checks(spec,report)
            from django.db import connections
            connections.close_all()
        source_names=['app/config/urls.py','app/accounts/views.py','app/profiles/views.py','app/assessments/views.py','app/hiring/views.py','app/assistant/views.py',
            'app/accounts/forms.py','app/profiles/forms.py','app/profiles/models.py','app/assessments/models.py','app/assessments/learning_tracks.py','app/accounts/integrations.py','app/api/tests.py','app/api/drafts.py','app/api/web.py','app/api/models.py','app/assessments/learning_views.py','app/assessments/learning.py','app/assessments/learning_urls.py','app/hiring/dashboard.py','app/hiring/forms.py','app/api/urls.py','app/api/core.py','app/api/schema.py','app/api/views.py','app/api/serializers.py',
            'scripts/http_contracts.py','scripts/http_contract_scenarios.py','scripts/build_http_spec.py','scripts/check_http_contracts.py','doc/api/openapi.json']
        report['source_hashes']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in source_names}
        report['status']='PASS';report['completed_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    except Exception as exc:
        report['error']=type(exc).__name__+': '+str(exc)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(f"{report['status']}: {len(report['runtime'])} runtime checks; {report.get('structure',{})}; {report.get('error','')}")
    print('Evidence: '+str(args.output))
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
