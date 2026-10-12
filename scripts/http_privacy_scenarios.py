"""Real CSRF/session/Bearer privacy scenarios, isolated from the main contract fixture."""
import json
from uuid import uuid4


def privacy_checks(run,user,clients,password):
    from profiles.models import Profile
    from hiring.models import Company,Need,Invitation
    from hiring.services import invite,decide
    from api.core import issue_token
    from django.test import Client
    from accounts.models import User
    candidate=user('http-privacy-candidate','candidate');employer=user('http-privacy-employer','employer')
    profile=Profile.objects.get(user=candidate)
    profile.name='Приватный Кандидат';profile.published=True;profile.confirmed_grade='Junior'
    profile.contact_email='PRIVATE_HTTP_CONTACT@demo.invalid';profile.save()
    company=Company.objects.create(user=employer,name='Компания',contact_email='company@demo.invalid')
    need=Need.objects.create(company=company,title='Роль',grade='Junior',tasks='PRIVATE_HTTP_SNAPSHOT',salary_min=1,salary_max=2,work_format='remote')
    invitation=invite(company,need.pk,profile.pk);decide(profile,invitation.pk,'accepted')
    _,secret=issue_token(employer,'Privacy HTTP','cli',contacts=True)
    anon=Client(enforce_csrf_checks=True)
    _,body=run('privacy-private-before',anon,f'/api/v1/invitations/{invitation.pk}/contacts',template='/api/v1/invitations/{pk}/contacts',bearer=secret)
    assert 'PRIVATE_HTTP_CONTACT' in body.decode()
    key=str(uuid4());data={'action':'revoke_company','company':str(company.pk),'request_id':key,'acknowledge':True}
    run('privacy-revoke-csrf','http-privacy-candidate','/profile/privacy/','POST',data,403,csrf=False)
    run('privacy-revoke-valid','http-privacy-candidate','/profile/privacy/','POST',data,302,location='/profile/privacy/',valid_body='PrivacyAction')
    run('privacy-revoke-repeat','http-privacy-candidate','/profile/privacy/','POST',data,302,location='/profile/privacy/')
    run('privacy-private-denied',anon,f'/api/v1/invitations/{invitation.pk}/contacts',expected=403,template='/api/v1/invitations/{pk}/contacts',bearer=secret)
    _,body=run('privacy-snapshot-redacted',anon,f'/api/v1/invitations/{invitation.pk}',template='/api/v1/invitations/{pk}',bearer=secret)
    assert 'PRIVATE_HTTP' not in body.decode() and json.loads(body)['data']['privacy_redacted']
    clear={'action':'clear_profile','request_id':str(uuid4()),'acknowledge':True,'password':password}
    run('privacy-clear-bad-password','http-privacy-candidate','/profile/privacy/','POST',dict(clear,password='wrong'),400)
    run('privacy-clear-valid','http-privacy-candidate','/profile/privacy/','POST',clear,302,location='/',valid_body='PrivacyAction')
    run('privacy-clear-old-session','http-privacy-candidate','/profile/',expected=302,location='/accounts/login/?next=/profile/')
    _,body=run('privacy-archive-null-candidate',anon,f'/api/v1/invitations/{invitation.pk}',template='/api/v1/invitations/{pk}',bearer=secret)
    assert json.loads(body)['data']['candidate_id'] is None
    run('privacy-old-profile-denied',anon,f'/api/v1/candidates/{profile.pk}',expected=404,template='/api/v1/candidates/{pk}',bearer=secret)
    candidate.refresh_from_db();clients['http-privacy-candidate'].force_login(candidate)
    deletion={'action':'delete_account','request_id':str(uuid4()),'acknowledge':True,'password':password}
    run('privacy-delete-valid','http-privacy-candidate','/profile/privacy/','POST',deletion,302,location='/',valid_body='PrivacyAction')
    assert not User.objects.filter(pk=candidate.pk).exists()
    assert Invitation.objects.get(pk=invitation.pk).candidate_id is None

    from django.conf import settings
    from pathlib import Path
    ledger=Path(settings.PRIVACY_LEDGER_PATH);saved=ledger.read_bytes()
    try:
        ledger.write_text('{corrupt ledger')
        run('privacy-ledger-failure-health',anon,'/health/',expected=503)
        run('privacy-ledger-failure-browser','http-privacy-employer','/candidates/',expected=503)
        run('privacy-ledger-failure-api',anon,'/api/v1/me',expected=503,bearer=secret)
    finally:ledger.write_bytes(saved)
