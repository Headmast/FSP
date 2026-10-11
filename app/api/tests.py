from datetime import timedelta
from django.test import TestCase, Client
from django.utils import timezone
from accounts.models import User, ApiToken
from accounts.consents import record_processing
from profiles.models import Profile
from .core import issue_token, ApiError


class ApiFixture(TestCase):
    def user(self, role='candidate', label='person'):
        user = User.objects.create_user(username=label+'@demo.invalid', email=label+'@demo.invalid',
            role=role, email_confirmed=True, password='Synthetic-2026!')
        record_processing(user)
        if role == 'candidate':
            Profile.objects.create(user=user, name='Иван', city='Москва', skills='Swift', published=True,
                confirmed_grade='Junior', test_score=.875, contact_email='hidden@demo.invalid',
                contact_phone='+70000000000', description='hidden@demo.invalid')
        return user

    def setUp(self):
        self.actor = self.user()
        self.token, self.secret = issue_token(self.actor, 'Test', 'cli')
        self.client.defaults['HTTP_AUTHORIZATION'] = 'Bearer '+self.secret

    def get(self, path, **params):
        return self.client.get('/api/v1/'+path, params)


class TokenTests(ApiFixture):
    def test_token_guards(self):
        self.assertEqual(self.get('me').status_code, 200)
        self.assertNotIn(self.secret, self.token.digest)
        self.token.revoked_at = timezone.now(); self.token.save()
        self.assertEqual(self.get('me').status_code, 401)
        self.token.revoked_at = None; self.token.expires_at = timezone.now()-timedelta(seconds=1); self.token.save()
        self.assertEqual(self.get('me').status_code, 401)

    def test_scope_role_consent_and_rate(self):
        self.actor.processing_consent_version = 'old'; self.actor.save()
        self.assertEqual(self.get('me').json()['error']['code'], 'CONSENT_REQUIRED')
        record_processing(self.actor)
        self.token.window_start=timezone.now(); self.token.request_count=60; self.token.save()
        response=self.get('me'); self.assertEqual(response.status_code,429); self.assertEqual(response['Retry-After'],'60')
        self.token.request_count=0; self.token.save()
        self.actor.role='employer'; self.actor.save()
        self.assertEqual(self.get('me').status_code,403)

    def test_web_secret_once_revoke_owner_and_csrf(self):
        self.client.force_login(self.actor)
        response=self.client.post('/accounts/integrations/', {'action':'create','name':'Desktop','kind':'mcp'})
        self.assertEqual(response.status_code,200)
        secret=response.context['secret']; self.assertTrue(secret.startswith('fsp_'))
        self.assertNotContains(self.client.get('/accounts/integrations/'),secret)
        secure=Client(enforce_csrf_checks=True); secure.force_login(self.actor)
        self.assertEqual(secure.post('/accounts/integrations/',{'action':'revoke','id':self.token.pk}).status_code,403)
        other=self.user(label='other'); other_token,_=issue_token(other,'Other','cli')
        self.assertEqual(self.client.post('/accounts/integrations/',{'action':'revoke','id':other_token.pk}).status_code,404)
        self.client.post('/accounts/integrations/',{'action':'revoke','id':self.token.pk})
        self.assertEqual(self.get('me').status_code,401)

    def test_mcp_never_contacts_and_read_only_method(self):
        with self.assertRaises(ApiError):issue_token(self.actor,'AI','mcp',contacts=True)
        self.assertEqual(self.client.post('/api/v1/me').status_code,405)
        self.assertNotIn('email', self.get('me').json()['data'])


class CandidateTests(ApiFixture):
    def test_read_profile_attempts_and_no_questions(self):
        from assessments.services import start_attempt
        attempt=start_attempt(self.actor.profile,'Junior')
        before=attempt.status
        response=self.get('me/assessments')
        text=response.content.decode()
        for word in ['tasks','answers','options','prompt','correct\"']:
            self.assertNotIn(word,text)
        attempt.refresh_from_db(); self.assertEqual(attempt.status,before)
        self.assertEqual(self.get(f'me/assessments/{attempt.pk}/result').status_code,409)
        self.assertEqual(self.get('me/profile').json()['data']['name'],'Иван')
        self.assertNotIn('hidden@demo.invalid',self.get('me/profile').content.decode())
        self.assertEqual(self.get('me/profile/private').status_code,403)
        self.assertEqual(self.get('me/achievements').json()['data']['source'],'mock')
        other=self.user(label='other')
        foreign=start_attempt(other.profile,'Junior')
        self.assertEqual(self.get(f'me/assessments/{foreign.pk}/result').status_code,404)
        self.assertEqual(self.get('me/assessments/²/result').status_code,404)
        self.assertEqual(self.get('me/assessments',limit=101).status_code,400)

    def test_mcp_projection_and_cli_private_pdf(self):
        _,secret=issue_token(self.actor,'MCP','mcp')
        self.client.defaults['HTTP_AUTHORIZATION']='Bearer '+secret
        self.assertEqual(self.get('me/profile/private').status_code,403)
        self.assertEqual(self.get('me/profile/resume.pdf').status_code,403)
        self.assertNotIn('hidden',self.get('me/profile').content.decode())
        self.assertNotIn('external_id',self.get('me/achievements').content.decode())
        _,secret=issue_token(self.actor,'Private','cli',contacts=True)
        self.client.defaults['HTTP_AUTHORIZATION']='Bearer '+secret
        self.assertEqual(self.get('me/profile/private').json()['data']['contact_email'],'hidden@demo.invalid')
        response=self.get('me/profile/resume.pdf',with_contacts='true')
        self.assertEqual(response.status_code,200)
        self.assertTrue(b''.join(response.streaming_content).startswith(b'%PDF'))


class EmployerTests(ApiFixture):
    def setUp(self):
        super().setUp()
        from hiring.models import Company,Need
        self.employer=self.user('employer','employer')
        self.company=Company.objects.create(user=self.employer,name='Компания',contact_email='company@demo.invalid',description='secret@demo.invalid')
        self.need=Need.objects.create(company=self.company,title='iOS Developer',grade='Junior',skills='Swift',tasks='contact@demo.invalid',salary_min=100,salary_max=200,work_format='remote')
        self.token,self.secret=issue_token(self.employer,'Employer','cli',contacts=True)
        self.client.defaults['HTTP_AUTHORIZATION']='Bearer '+self.secret

    def test_search_matches_and_no_read_side_effects(self):
        from hiring.models import Company
        from hiring.services import search,invite
        expected=search('Junior',self.need)
        response=self.get('candidates',need_id=self.need.pk)
        self.assertEqual(response.status_code,200)
        rows=response.json()['data']
        self.assertEqual([(r['profile']['id'],r['score'],r['parts']) for r in rows],[(r['id'],r['score'],r['parts']) for r in expected])
        invitation=invite(self.company,self.need.pk,self.actor.profile.pk)
        self.client.defaults['HTTP_AUTHORIZATION']='Bearer '+issue_token(self.actor,'Inbox','cli')[1]
        self.get('invitations');self.get(f'invitations/{invitation.pk}')
        invitation.refresh_from_db();self.assertIsNone(invitation.viewed_at)
        fresh=self.user('employer','fresh')
        self.client.defaults['HTTP_AUTHORIZATION']='Bearer '+issue_token(fresh,'New','cli')[1]
        before=Company.objects.count()
        self.assertEqual(self.get('me/company').json()['data']['state'],'company_not_created')
        self.get('needs');self.get('candidates',grade='Junior');self.get('invitations')
        self.assertEqual(Company.objects.count(),before)
        self.assertEqual(self.get('candidates',grade='Bad').status_code,400)
        self.assertEqual(self.get('needs/²').status_code,404)
        self.assertEqual(self.get('needs/'+str(self.need.pk)).status_code,404)

    def test_contacts_isolation_publication_and_mcp_snapshots(self):
        from hiring.services import invite,decide
        invitation=invite(self.company,self.need.pk,self.actor.profile.pk)
        path=f'candidates/{self.actor.profile.pk}/private'
        self.assertEqual(self.get(path).status_code,403)
        decide(self.actor.profile,invitation.pk,'accepted')
        self.assertEqual(self.get(path).json()['data']['contact_email'],'hidden@demo.invalid')
        other=self.user('employer','othercompany')
        self.client.defaults['HTTP_AUTHORIZATION']='Bearer '+issue_token(other,'Other','cli',contacts=True)[1]
        self.assertEqual(self.get(path).status_code,403)
        self.assertEqual(self.get(f'invitations/{invitation.pk}').status_code,404)
        profile=self.actor.profile; profile.published=False;profile.save()
        self.assertEqual(self.get(f'candidates/{profile.pk}').status_code,404)
        self.client.defaults['HTTP_AUTHORIZATION']='Bearer '+self.secret
        self.assertEqual(self.get(path).status_code,200)
        self.assertEqual(self.get('candidates',grade='Junior').json()['data'],[])
        invitation.snapshot['title']='contact@demo.invalid';invitation.snapshot['company']='contact@demo.invalid'
        invitation.snapshot['accepted_results']=[{'tasks':'secret','answers':'secret','contact_email':'hidden@demo.invalid','bank_version':'hidden@demo.invalid'}]
        invitation.save()
        self.client.defaults['HTTP_AUTHORIZATION']='Bearer '+issue_token(self.employer,'AI','mcp')[1]
        for route in ['me/company',f'needs/{self.need.pk}',f'invitations/{invitation.pk}',f'candidates/{profile.pk}']:
            text=self.get(route).content.decode()
            for forbidden in ['@demo.invalid','contact_email','contact_phone','"tasks"','"answers"','"description"','"discussion"','"next_step"']:
                self.assertNotIn(forbidden,text)
        self.assertEqual(self.get(path).status_code,403)


class DraftFixture(ApiFixture):
    def setUp(self):
        super().setUp()
        self.token,self.secret=issue_token(self.actor,'Drafts','cli',contacts=True,drafts=True)
        self.client.defaults['HTTP_AUTHORIZATION']='Bearer '+self.secret

    def prepare(self,kind,payload=None,target=None):
        return self.client.post('/api/v1/drafts',{'kind':kind,'payload':payload or {},'target_id':target},content_type='application/json')


class DraftPreparationTests(DraftFixture):
    def test_prepare_is_immutable_and_does_not_apply(self):
        from .models import ActionDraft
        from django.core.exceptions import ValidationError
        response=self.prepare('profile.update',{'city':'Казань','description':'hidden@demo.invalid'})
        self.assertEqual(response.status_code,201)
        self.actor.profile.refresh_from_db();self.assertEqual(self.actor.profile.city,'Москва')
        obj=ActionDraft.objects.get(pk=response.json()['data']['id'])
        obj.payload={'city':'Самара'}
        with self.assertRaises(ValidationError):obj.save()
        self.assertEqual(self.client.post('/api/v1/drafts/'+str(obj.pk)+'/apply',{},content_type='application/json').status_code,404)
        self.assertEqual(self.get('drafts/invalid').status_code,404)
        other=self.user(label='other-drafts')
        self.client.defaults['HTTP_AUTHORIZATION']='Bearer '+issue_token(other,'Other','cli',drafts=True)[1]
        self.assertEqual(self.get('drafts/'+str(obj.pk)).status_code,404)
        self.assertEqual(self.get('drafts').json()['data'],[])

    def test_scopes_mcp_redaction_and_cancel(self):
        response=self.prepare('profile.update',{'contact_email':'new@demo.invalid','description':'secret@demo.invalid'})
        identifier=response.json()['data']['id']
        self.client.defaults['HTTP_AUTHORIZATION']='Bearer '+issue_token(self.actor,'AI','mcp',drafts=True)[1]
        text=self.get('drafts/'+identifier).content.decode()
        self.assertNotIn('@demo.invalid',text)
        self.assertNotIn('payload',self.get('drafts/'+identifier).json()['data'])
        self.assertEqual(self.prepare('profile.update',{'contact_email':'bad@demo.invalid'}).status_code,400)
        self.assertEqual(self.prepare('profile.update',{'confirmed_grade':'Middle'}).status_code,400)
        self.assertEqual(self.prepare('profile.update',{'city':'Казань'},target=99999).status_code,404)
        cancelled=self.client.post('/api/v1/drafts/'+identifier+'/cancel',{},content_type='application/json')
        self.assertEqual(cancelled.json()['data']['status'],'cancelled')
        self.client.defaults['HTTP_AUTHORIZATION']='Bearer '+issue_token(self.actor,'Read','cli')[1]
        self.assertEqual(self.prepare('profile.publish').status_code,403)
        self.assertNotIn('@demo.invalid',self.get('drafts/'+identifier).content.decode())

    def test_company_need_and_invitation_prepare_only(self):
        from hiring.models import Company,Need,Invitation
        employer=self.user('employer','draft-employer')
        self.client.defaults['HTTP_AUTHORIZATION']='Bearer '+issue_token(employer,'Employer','cli',contacts=True,drafts=True)[1]
        self.assertEqual(self.prepare('company.update',{'name':'Новая компания','contact_email':'new@demo.invalid'}).status_code,201)
        self.assertFalse(Company.objects.filter(user=employer).exists())
        company=Company.objects.create(user=employer,name='Компания',contact_email='company@demo.invalid')
        response=self.prepare('need.create',{'title':'Разработчик','grade':'Junior','skills':'Swift','tasks':'Разработка','salary_min':100,'salary_max':200,'work_format':'remote','next_step':'Знакомство'})
        self.assertEqual(response.status_code,201)
        self.assertFalse(Need.objects.filter(company=company).exists())
        need=Need.objects.create(company=company,title='Разработчик',grade='Junior',skills='Swift',tasks='Разработка',salary_min=100,salary_max=200,work_format='remote')
        response=self.prepare('invitation.send',{'candidate_id':self.actor.profile.pk},target=need.pk)
        self.assertEqual(response.status_code,201)
        self.assertEqual(Invitation.objects.count(),0)
        self.assertEqual(self.prepare('need.update',{'salary_min':300},target=need.pk).status_code,400)


class DraftApprovalTests(DraftFixture):
    def approve(self,identifier,**extra):
        self.client.force_login(self.actor)
        return self.client.post('/drafts/'+identifier+'/',{'action':'apply','acknowledge':'on',**extra})

    def test_session_csrf_ack_and_single_apply(self):
        from .models import ActionDraft
        from accounts.models import ConsentEvent
        response=self.prepare('profile.update',{'city':'Казань'})
        identifier=response.json()['data']['id']
        # A bearer alone cannot grant web approval.
        self.assertEqual(self.client.post('/drafts/'+identifier+'/',{'action':'apply','acknowledge':'on'}).status_code,302)
        self.actor.profile.refresh_from_db();self.assertEqual(self.actor.profile.city,'Москва')
        secure=Client(enforce_csrf_checks=True);secure.force_login(self.actor)
        self.assertEqual(secure.post('/drafts/'+identifier+'/',{'action':'apply','acknowledge':'on'}).status_code,403)
        self.client.force_login(self.actor)
        self.assertEqual(self.client.post('/drafts/'+identifier+'/',{'action':'apply'}).status_code,400)
        self.assertEqual(self.approve(identifier).status_code,302)
        self.actor.profile.refresh_from_db();self.assertEqual(self.actor.profile.city,'Казань')
        self.assertEqual(self.approve(identifier).status_code,302)
        self.assertEqual(ActionDraft.objects.get(pk=identifier).status,'applied')
        self.client.logout()
        unpublished=self.prepare('profile.unpublish').json()['data']['id']
        self.assertEqual(self.approve(unpublished).status_code,302)
        self.client.logout()
        published=self.prepare('profile.publish').json()['data']['id']
        self.assertEqual(self.approve(published).status_code,400)
        self.assertEqual(self.approve(published,publication_consent='on').status_code,302)
        event=ConsentEvent.objects.filter(user=self.actor,purpose='publication').latest('pk')
        self.assertTrue(event.granted);self.assertEqual(event.source,'draft_web_cli')

    def test_stale_expiry_cancel_foreign_and_live_consent(self):
        from .models import ActionDraft
        response=self.prepare('profile.update',{'city':'Казань'});identifier=response.json()['data']['id']
        Profile.objects.filter(user=self.actor).update(city='Самара')
        self.assertEqual(self.approve(identifier).status_code,409)
        self.client.logout()
        identifier=self.prepare('profile.update',{'city':'Казань'}).json()['data']['id']
        ActionDraft.objects.filter(pk=identifier).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.approve(identifier).status_code,410)
        self.client.logout()
        identifier=self.prepare('profile.update',{'city':'Казань'}).json()['data']['id']
        self.client.post('/api/v1/drafts/'+identifier+'/cancel',{},content_type='application/json')
        self.assertEqual(self.approve(identifier).status_code,409)
        other=self.user(label='foreign-browser');self.client.force_login(other)
        self.assertEqual(self.client.get('/drafts/'+identifier+'/').status_code,404)
        self.actor.processing_consent_version='old';self.actor.save()
        self.assertEqual(self.approve(identifier).status_code,302)
        self.actor.profile.refresh_from_db();self.assertEqual(self.actor.profile.city,'Самара')

    def test_company_need_invitation_apply_and_snapshot_replay(self):
        from hiring.models import Company,Need,Invitation
        employer=self.user('employer','approve-employer')
        self.client.defaults['HTTP_AUTHORIZATION']='Bearer '+issue_token(employer,'Employer','cli',contacts=True,drafts=True)[1]
        identifier=self.prepare('company.update',{'name':'Компания','contact_email':'company@demo.invalid'}).json()['data']['id']
        self.client.force_login(employer)
        self.assertEqual(self.client.post('/drafts/'+identifier+'/',{'action':'apply','acknowledge':'on'}).status_code,302)
        company=Company.objects.get(user=employer)
        self.client.logout()
        identifier=self.prepare('need.create',{'title':'Разработчик','grade':'Junior','skills':'Swift','tasks':'Разработка','salary_min':100,'salary_max':200,'work_format':'remote'}).json()['data']['id']
        self.client.force_login(employer)
        self.assertEqual(self.client.post('/drafts/'+identifier+'/',{'action':'apply','acknowledge':'on'}).status_code,302)
        self.assertEqual(self.client.post('/drafts/'+identifier+'/',{'action':'apply','acknowledge':'on'}).status_code,302)
        self.assertEqual(Need.objects.filter(company=company).count(),1)
        need=Need.objects.get(company=company)
        self.client.logout()
        identifier=self.prepare('invitation.send',{'candidate_id':self.actor.profile.pk,'discussion':'Обсудить Swift'},target=need.pk).json()['data']['id']
        self.client.force_login(employer)
        page=self.client.get('/drafts/'+identifier+'/')
        self.assertNotContains(page,'hidden@demo.invalid')
        self.assertEqual(self.client.post('/drafts/'+identifier+'/',{'action':'apply','acknowledge':'on'}).status_code,302)
        self.assertEqual(self.client.post('/drafts/'+identifier+'/',{'action':'apply','acknowledge':'on'}).status_code,302)
        self.assertEqual(Invitation.objects.count(),1)
        invitation=Invitation.objects.get();self.assertEqual(invitation.snapshot['discussion'],'Обсудить Swift')
        self.client.logout()
        self.client.defaults['HTTP_AUTHORIZATION']='Bearer '+self.secret
        identifier=self.prepare('invitation.accept',target=invitation.pk).json()['data']['id']
        self.assertEqual(self.approve(identifier).status_code,302)
        invitation.refresh_from_db();self.assertEqual(invitation.status,'accepted')
        self.client.logout()
        identifier=self.prepare('invitation.decline',target=invitation.pk).json()['data']['id']
        self.assertEqual(self.approve(identifier).status_code,400)
        invitation.refresh_from_db();self.assertEqual(invitation.status,'accepted')
