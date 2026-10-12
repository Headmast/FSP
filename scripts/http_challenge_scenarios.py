"""Independent real CSRF/session/Bearer expectations for company-scoped gap tasks."""
from datetime import timedelta
import json
from uuid import uuid4


def challenge_scenarios(run,user,clients,password):
    from django.test import Client
    from django.utils import timezone
    from profiles.models import Profile
    from hiring.models import Company,Need,GapChallenge
    from hiring.services import invite,decide,rank
    from api.core import issue_token
    key='http-challenge-candidate';ekey='http-challenge-employer'
    candidate=user(key,'candidate');employer=user(ekey,'employer');other=user('http-challenge-other','employer')
    profile=Profile.objects.get(user=candidate);profile.name='Тестовый Кандидат';profile.confirmed_grade='Junior';profile.published=True;profile.skills='Swift';profile.test_score=.75;profile.save()
    company=Company.objects.create(user=employer,name='Тестовая Компания',contact_email='company@demo.invalid')
    need=Need.objects.create(company=company,title='iOS',grade='Junior',skills='Swift, Combine, XCTest',tasks='Экран',salary_min=1,salary_max=2,work_format='remote')
    invitation=invite(company,need.pk,profile.pk);decide(profile,invitation.pk,'accepted')
    before=(profile.confirmed_grade,profile.test_score,rank(profile,need))
    offer_path=f'/invitations/{invitation.pk}/challenge/';offer_template='/invitations/{pk}/challenge/'
    run('challenge-offer-form',ekey,offer_path,template=offer_template)
    run('challenge-offer-wrong-role',key,offer_path,expected=403,template=offer_template)
    run('challenge-offer-foreign','http-challenge-other',offer_path,expected=404,template=offer_template)
    values={'request_id':str(uuid4()),'skill':'Combine','title':'Проверка отмены запроса',
        'instructions':'INSTRUCTION_HTTP_PRIVATE@demo.invalid','criteria':'Объяснена отмена\nПоказана проверка',
        'duration_minutes':15,'pass_points':3,'deadline_at':(timezone.localtime()+timedelta(days=7)).strftime('%Y-%m-%dT%H:%M'),'acknowledge':True}
    run('challenge-offer-csrf',ekey,offer_path,'POST',values,403,template=offer_template,csrf=False)
    _,body=run('challenge-offer-invalid-skill',ekey,offer_path,'POST',{**values,'skill':'UIKit'},400,template=offer_template)
    assert not GapChallenge.objects.exists()
    run('challenge-offer-valid',ekey,offer_path,'POST',values,302,template=offer_template,valid_body='ChallengeOffer')
    obj=GapChallenge.objects.get(invitation=invitation,skill='Combine');path=f'/challenges/{obj.pk}/';template='/challenges/{pk}/'
    run('challenge-offer-repeat',ekey,offer_path,'POST',values,302,template=offer_template,location=path)
    run('challenge-offer-immutable',ekey,offer_path,'POST',{**values,'title':'Изменить условия'},409,template=offer_template)
    _,body=run('challenge-rules-before-consent',key,path,template=template)
    assert 'Объяснена отмена' in body.decode() and '15 минут' in body.decode()
    run('challenge-foreign-detail','http-challenge-other',path,expected=404,template=template)
    accept={'action':'accept','revision':0,'acknowledge':True}
    run('challenge-accept-csrf',key,path,'POST',accept,403,template=template,csrf=False)
    run('challenge-accept-no-ack',key,path,'POST',{'action':'accept','revision':0},400,template=template)
    run('challenge-accept',key,path,'POST',accept,302,template=template,location=path,valid_body='ChallengeMutation')
    obj.refresh_from_db();start=obj.accepted_at
    run('challenge-accept-repeat',key,path,'POST',accept,302,template=template,location=path);obj.refresh_from_db();assert obj.accepted_at==start
    draft={'action':'save','revision':obj.revision,'answer':'DRAFT_HTTP_PRIVATE@demo.invalid'}
    run('challenge-save-draft',key,path,'POST',draft,302,template=template,valid_body='ChallengeMutation')
    _,body=run('challenge-draft-company-hidden',ekey,path,template=template);assert 'DRAFT_HTTP_PRIVATE' not in body.decode()
    obj.refresh_from_db()
    run('challenge-stale-draft',key,path,'POST',{**draft,'answer':'Старое значение'},409,template=template)
    submit={'action':'submit','revision':obj.revision,'answer':'ANSWER_HTTP_PRIVATE@demo.invalid','acknowledge':True}
    run('challenge-submit',key,path,'POST',submit,302,template=template,valid_body='ChallengeMutation')
    run('challenge-submit-repeat',key,path,'POST',submit,302,template=template)
    _,body=run('challenge-company-reads-submitted',ekey,path,template=template);assert 'ANSWER_HTTP_PRIVATE' in body.decode()
    obj.refresh_from_db();review={'action':'review','revision':obj.revision,'score_0':2,'score_1':1,'note':'REVIEW_HTTP_PRIVATE@demo.invalid','acknowledge':True}
    run('challenge-review-wrong-role',key,path,'POST',review,403,template=template)
    run('challenge-review-bad-score',ekey,path,'POST',{**review,'score_0':3},400,template=template)
    run('challenge-review',ekey,path,'POST',review,302,template=template,valid_body='ChallengeMutation')
    run('challenge-review-repeat',ekey,path,'POST',review,302,template=template)
    run('challenge-review-immutable',ekey,path,'POST',{**review,'score_1':2},409,template=template)
    obj.refresh_from_db();assert obj.review_scores==[2,1] and not obj.credited_at
    credit={'action':'credit','revision':obj.revision,'acknowledge':True}
    run('challenge-credit',ekey,path,'POST',credit,302,template=template,valid_body='ChallengeMutation')
    run('challenge-credit-repeat',ekey,path,'POST',credit,302,template=template)
    anon=Client(enforce_csrf_checks=True);tokens={name:issue_token(actor,'HTTP task projection','mcp')[1] for name,actor in [(key,candidate),(ekey,employer),('other',other)]}
    for name in [key,ekey]:
        _,body=run('challenge-api-'+name,anon,f'/api/v1/challenges/{obj.pk}',template='/api/v1/challenges/{pk}',bearer=tokens[name])
        dto=json.loads(body)['data'];assert dto['result']['points']==3 and dto['result']['credited'] and 'PRIVATE' not in body.decode()
        run('challenge-api-list-'+name,anon,'/api/v1/challenges',bearer=tokens[name])
    run('challenge-api-foreign',anon,f'/api/v1/challenges/{obj.pk}',expected=404,template='/api/v1/challenges/{pk}',bearer=tokens['other'])
    run('challenge-api-write-forbidden',anon,f'/api/v1/challenges/{obj.pk}','POST',{},405,template='/api/v1/challenges/{pk}',bearer=tokens[key])
    # A separate offered task is backdated only to exercise the exact deadline guard, not as a claimed elapsed-time run.
    values.update(request_id=str(uuid4()),skill='XCTest',title='Проверка тестирования')
    run('challenge-expiry-fixture-offer',ekey,offer_path,'POST',values,302,template=offer_template)
    expired=GapChallenge.objects.get(invitation=invitation,skill='XCTest');GapChallenge.objects.filter(pk=expired.pk).update(deadline_at=timezone.now()-timedelta(seconds=1))
    run('challenge-expired-accept',key,f'/challenges/{expired.pk}/','POST',accept,409,template=template)
    values.update(request_id=str(uuid4()),skill='Swift',title='Проверка заявленного навыка')
    run('challenge-decline-fixture-offer',ekey,offer_path,'POST',values,302,template=offer_template)
    declined=GapChallenge.objects.get(invitation=invitation,skill='Swift')
    decline={'action':'decline','revision':0}
    run('challenge-decline',key,f'/challenges/{declined.pk}/','POST',decline,302,template=template)
    run('challenge-decline-repeat',key,f'/challenges/{declined.pk}/','POST',decline,302,template=template)
    profile.refresh_from_db();assert before==(profile.confirmed_grade,profile.test_score,rank(profile,need))
    return obj,key,ekey
