"""HTTPS privacy acceptance using only accounts freshly registered by check_live_checkpoint.py."""
import json
import urllib.error
from accounts.models import User,ApiToken
from api.core import issue_token
from profiles.models import Profile,PrivacyReceipt
from assessments.models import Attempt,LessonProgress,PracticeSession
from hiring.models import Company,Need,Invitation


def run(candidate,employer,Actor,Fields,profile,company,offer,attempt,data,emails,password,api_read,passed):
    # Re-publication is explicit through this owned candidate's form, after the prior test of withdrawal.
    data['published']='on';candidate.request('/profile/',data)
    second=Actor();second.register(emails[2],'employer');second.request('/company/')
    second.request('/company/',{'name':'Вторая Тестовая Компания','industry':'Мобильная разработка',
        'description':'Собственная синтетическая компания QA','contact_email':'second-checkpoint@demo.invalid'})
    second.request('/company/needs/')
    second.request('/company/needs/',{'company_name':'Вторая Тестовая Компания','company_email':'second-checkpoint@demo.invalid',
        'title':'Вторая синтетическая iOS роль','grade':'Junior','skills':'Swift','tasks':'Демонстрационная задача',
        'salary_min':'120000','salary_max':'160000','work_format':'office','employment_type':'full_time','task_types':['development'],
        'next_step':'Обсудить встречу'})
    second_company=Company.objects.get(user__username=emails[2]);need=Need.objects.get(company=second_company)
    second.request(f'/candidates/{profile.pk}/?need={need.pk}')
    second.request('/invitations/send/',{'candidate':profile.pk,'need':need.pk,'accepted_attempts':[attempt.pk],
        'discussion':'Синтетическое приватное обсуждение private-checkpoint@demo.invalid'})
    second_offer=Invitation.objects.get(candidate=profile,company=second_company)
    candidate.request(f'/invitations/{second_offer.pk}/accept/',{})
    tokens={name:issue_token(User.objects.get(username=name),'Owned privacy HTTPS checkpoint','cli',contacts=True)[1] for name in emails}
    def denied(path,secret,status=403):
        try:api_read(path,secret)
        except urllib.error.HTTPError as exc:assert exc.code==status
        else:raise AssertionError('Privacy API restriction missing')
    for name in emails[1:]:assert 'private-checkpoint@demo.invalid' in json.dumps(api_read(f'candidates/{profile.pk}/private',tokens[name]))
    passed('two owned companies have independently accepted contact grants')
    # Keep a separately authenticated session for the session-generation check.
    other=Actor();other.login(emails[0],password);assert 'Тестовый Кандидат' in other.request('/profile/')
    def privacy(action,extra=None):
        text=candidate.request('/profile/privacy/')
        candidate.request('/profile/privacy/',{'action':action,'request_id':Fields(text).values['request_id'],
            'acknowledge':'on',**(extra or {})})
    privacy('revoke_company',{'company':company.pk})
    denied(f'candidates/{profile.pk}/private',tokens[emails[1]])
    denied(f'candidates/{profile.pk}/resume.pdf?with_contacts=true',tokens[emails[1]])
    denied(f'invitations/{offer.pk}/contacts',tokens[emails[1]])
    employer.expect_status(f'/candidates/{profile.pk}/resume.pdf',403)
    assert 'private-checkpoint@demo.invalid' not in employer.request(f'/candidates/{profile.pk}/')
    assert 'private-checkpoint@demo.invalid' in json.dumps(api_read(f'candidates/{profile.pk}/private',tokens[emails[2]]))
    candidate.request(f'/invitations/{offer.pk}/accept/',{})
    denied(f'invitations/{offer.pk}/contacts',tokens[emails[1]])
    passed('single-company revoke closes HTML PDF API and old-invitation replay; other grant stays')
    privacy('revoke_all')
    for name in emails[1:]:denied(f'candidates/{profile.pk}/private',tokens[name])
    assert not api_read('me/privacy',tokens[emails[0]])['data']['companies']
    passed('revoke all closes remaining grant and readonly privacy projection confirms no companies')
    profile.refresh_from_db();before=(profile.name,profile.contact_email,Attempt.objects.filter(candidate=profile).count(),PrivacyReceipt.objects.filter(actor=profile.user).count())
    text=candidate.request('/profile/privacy/')
    candidate.expect_status('/profile/privacy/',400,{'action':'clear_profile','request_id':Fields(text).values['request_id'],
        'acknowledge':'on','password':'Incorrect-synthetic-password'})
    profile.refresh_from_db();assert before==(profile.name,profile.contact_email,Attempt.objects.filter(candidate=profile).count(),PrivacyReceipt.objects.filter(actor=profile.user).count())
    passed('wrong clear password cannot change owned profile or receipts over HTTPS')
    privacy('clear_profile',{'password':password})
    denied('me/profile',tokens[emails[0]],401)
    assert 'username' in Fields(other.request('/profile/')).values
    profile.refresh_from_db()
    assert not profile.name and not profile.contact_email and not profile.published and not profile.confirmed_grade
    assert not ApiToken.objects.filter(user=profile.user).exists()
    assert not Attempt.objects.filter(candidate=profile).exists()
    assert not LessonProgress.objects.filter(candidate=profile).exists() and not PracticeSession.objects.filter(candidate=profile).exists()
    assert profile.user.assessment_privacy_holds
    for actor in [employer,second]:
        actor.expect_status(f'/candidates/{profile.pk}/',404)
        archive=actor.request('/invitations/');assert 'обезличенная история' in archive
        assert 'private-checkpoint@demo.invalid' not in archive and 'Тестовый Кандидат' not in archive
        assert f'href="/candidates/{profile.pk}/"' not in archive and 'Подготовиться к разговору' not in archive
    for invitation_id in [offer.pk,second_offer.pk]:
        archived=Invitation.objects.get(pk=invitation_id)
        assert archived.candidate_id is None and archived.candidate_erased_at and archived.snapshot['privacy_redacted']
        assert archived.snapshot['accepted_results']==[]
    passed('clear erases linked data and tokens, logs out another session, keeps anonymous company archives and retry holds')
    candidate.login(emails[0],password)
    assert 'Доступ и удаление данных' in candidate.request('/profile/privacy/')
    privacy('delete_account',{'password':password})
    assert not User.objects.filter(username=emails[0]).exists()
    candidate.login(emails[0],password)
    assert 'username' in Fields(candidate.request('/profile/')).values
    denied('me/privacy',tokens[emails[0]],401)
    assert Invitation.objects.filter(pk__in=[offer.pk,second_offer.pk]).count()==2
    passed('clear preserves login; later explicit delete prevents login and old token access without erasing anonymous outcome')
