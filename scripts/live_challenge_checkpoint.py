"""Real HTTPS task lifecycle on check_live_checkpoint.py's own freshly registered accounts."""
from datetime import timedelta
import json
from uuid import uuid4
from django.utils import timezone
from hiring.models import GapChallenge
from hiring.services import rank,contacts_allowed
from api.core import issue_token


def run(candidate,employer,Fields,profile,invitation,api_read,passed):
    baseline=(profile.confirmed_grade,profile.test_score,profile.grade_changed_at,rank(profile,invitation.need))
    path=f'/invitations/{invitation.pk}/challenge/'
    employer.request(path)
    terms={'request_id':str(uuid4()),'skill':'Combine','title':'Проверка отмены подписки',
        'instructions':'Объясните отмену и проверку отсутствия последующих событий.','criteria':'Объяснена отмена\nОбоснована проверка',
        'duration_minutes':15,'pass_points':3,'deadline_at':(timezone.localtime()+timedelta(days=7)).strftime('%Y-%m-%dT%H:%M'),'acknowledge':'on'}
    employer.request(path,terms);employer.request(path,terms)
    obj=GapChallenge.objects.get(invitation=invitation,skill='Combine');assert obj.gap_kind=='missing_declared'
    assert GapChallenge.objects.filter(invitation=invitation,skill='Combine').count()==1
    detail=f'/challenges/{obj.pk}/';rules=candidate.request(detail)
    assert 'Объяснена отмена' in rules and 'Порог: 3' in rules and 'Согласиться и начать' in rules
    passed('HTTPS accepted paid invitation task: immutable rules visible before separate consent, send replay one row')
    candidate.expect_status(detail,400,{'action':'accept','revision':obj.revision})
    candidate.request(detail,{'action':'accept','revision':obj.revision,'acknowledge':'on'});obj.refresh_from_db();started=obj.accepted_at
    candidate.request(detail,{'action':'accept','revision':0,'acknowledge':'on'});obj.refresh_from_db();assert obj.accepted_at==started
    old_revision=obj.revision
    candidate.request(detail,{'action':'save','revision':obj.revision,'answer':'DRAFT_HTTPS_CHALLENGE@demo.invalid'});obj.refresh_from_db()
    assert 'DRAFT_HTTPS_CHALLENGE' in candidate.request(detail) and 'DRAFT_HTTPS_CHALLENGE' not in employer.request(detail)
    candidate.expect_status(detail,409,{'action':'save','revision':old_revision,'answer':'Старый ответ'})
    passed('HTTPS separate consent, stable timer and private saved draft; stale draft rejected')
    submit={'action':'submit','revision':obj.revision,'answer':'ANSWER_HTTPS_CHALLENGE@demo.invalid','acknowledge':'on'}
    candidate.request(detail,submit);candidate.request(detail,submit);obj.refresh_from_db()
    assert 'ANSWER_HTTPS_CHALLENGE' in employer.request(detail)
    review={'action':'review','revision':obj.revision,'score_0':2,'score_1':1,'note':'Отмена описана; проверка частичная.','acknowledge':'on'}
    candidate.expect_status(detail,403,review)
    employer.request(detail,review);employer.request(detail,review);obj.refresh_from_db()
    employer.expect_status(detail,409,{**review,'score_1':2})
    assert obj.review_scores==[2,1] and not obj.credited_at
    employer.request(detail,{'action':'credit','revision':obj.revision,'acknowledge':'on'});obj.refresh_from_db();assert obj.credited_at
    assert '3/4' in candidate.request(detail)
    tokens=[issue_token(user,'Own task HTTPS projection','mcp')[1] for user in [profile.user,invitation.company.user]]
    for token in tokens:
        dto=api_read(f'challenges/{obj.pk}',token)['data']
        assert dto['result']['points']==3 and dto['result']['credited'] and not dto['changes_professional_grade']
        assert 'CHALLENGE@demo.invalid' not in json.dumps(dto)
    passed('HTTPS immutable submission/manual company rubric, separate scoped credit and safe read DTO for both roles')
    candidate.request(detail,{'action':'revoke','revision':0,'acknowledge':'on'});obj.refresh_from_db()
    assert obj.consent_revoked_at and not obj.credited_at
    assert 'ANSWER_HTTPS_CHALLENGE' in candidate.request(detail) and 'ANSWER_HTTPS_CHALLENGE' not in employer.request(detail)
    assert api_read(f'challenges/{obj.pk}',tokens[1])['data']['result'] is None
    assert contacts_allowed(invitation.company,profile)
    profile.refresh_from_db();assert baseline==(profile.confirmed_grade,profile.test_score,profile.grade_changed_at,rank(profile,invitation.need))
    passed('HTTPS answer revoke closes company content/result, preserves owner history and independent contacts; professional grade/rank unchanged')
