"""Privacy acceptance: live grants, old endpoints/snapshots, graph erasure and backup fences."""
import json
import tempfile
from datetime import timedelta
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
from django.test import TestCase,Client,override_settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from accounts.models import User,ApiToken
from profiles.models import Profile,Experience,FspLink,PrivacyReceipt
from profiles.privacy import request_action,identity,append_ledger,reconcile,PrivacyUnavailable
from hiring.models import Company,Need,Invitation
from hiring.services import invite,decide,contacts_allowed
from api.core import issue_token
from api.models import ActionDraft
from api.drafts import prepare,apply
from assessments.models import Attempt,PracticeSession,LessonProgress
from assessments.services import start_attempt,finalize


class PrivacyTests(TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.ledger=Path(self.tmp.name)/'privacy.jsonl'
        self.settings_override=override_settings(PRIVACY_LEDGER_PATH=self.ledger)
        self.settings_override.enable();self.addCleanup(self.settings_override.disable)
        self.password='Privacy-Synthetic-2026!'
        def actor(name,role):
            return User.objects.create_user(username=name+'@demo.invalid',email=name+'@demo.invalid',password=self.password,
                role=role,email_confirmed=True,processing_consented_at=timezone.now(),processing_consent_version='processing-v1')
        self.actor=actor('privacy-candidate','candidate');self.other=actor('privacy-other','candidate')
        self.profile=Profile.objects.create(user=self.actor,name='Уникальное Имя',city='Москва',published=True,confirmed_grade='Junior',
            description='PRIVATE_PROFILE_SENTINEL',contact_email='PRIVATE_EMAIL@demo.invalid',contact_phone='PRIVATE_PHONE',skills='Swift',
            preferred_work_formats=['remote'],preferred_employment_types=['full_time'],preferred_task_types=['testing'])
        self.other_profile=Profile.objects.create(user=self.other,name='Другой',contact_email='UNRELATED_CONTACT@demo.invalid')
        self.companies=[];self.employers=[];self.needs=[]
        for index in [1,2]:
            employer=actor('privacy-company'+str(index),'employer');self.employers.append(employer)
            company=Company.objects.create(user=employer,name='Компания',contact_email='company@demo.invalid');self.companies.append(company)
            need=Need.objects.create(company=company,title='Разработчик',grade='Junior',skills='Swift',tasks='PRIVATE_SNAPSHOT_SENTINEL',
                salary_min=100,salary_max=200,work_format='remote',employment_type='full_time',task_types=['testing'])
            self.needs.append(need)
        self.invites=[]
        for company,need in zip(self.companies,self.needs):
            obj=invite(company,need.pk,self.profile.pk,discussion='PRIVATE_DISCUSSION_SENTINEL');obj=decide(self.profile,obj.pk,'accepted');self.invites.append(obj)
        _,secret=issue_token(self.employers[0],'Alpha','cli',contacts=True,drafts=True)
        self.api=Client(HTTP_AUTHORIZATION='Bearer '+secret)
        self.web=Client();self.web.force_login(self.actor)

    def action(self,action,company=None,key=None):
        return request_action(self.actor,action,key or uuid4(),company)

    def test_revoke_company_closes_all_private_paths_but_other_company_stays_open(self):
        company=self.companies[0];profile=self.profile
        second=Need.objects.create(company=company,title='Другая роль',grade='Junior',tasks='Задачи',salary_min=1,salary_max=2,work_format='remote')
        extra=invite(company,second.pk,profile.pk);decide(profile,extra.pk,'accepted')
        self.assertTrue(self.action('revoke_company',company.pk))
        self.assertFalse(contacts_allowed(company,profile));self.assertTrue(contacts_allowed(self.companies[1],profile))
        for path in [f'/api/v1/candidates/{profile.pk}/private',f'/api/v1/candidates/{profile.pk}/resume.pdf?with_contacts=true',f'/api/v1/invitations/{self.invites[0].pk}/contacts']:
            self.assertEqual(self.api.get(path).status_code,403,path)
        employer=Client();employer.force_login(self.employers[0])
        response=employer.get(f'/candidates/{profile.pk}/');self.assertNotContains(response,'PRIVATE_EMAIL');self.assertNotContains(response,'PRIVATE_PROFILE')
        self.assertEqual(response['Cache-Control'],'no-store')
        response=employer.get(f'/candidates/{profile.pk}/resume.pdf');self.assertEqual(response['Cache-Control'],'no-store')
        response=self.api.get(f'/api/v1/invitations/{self.invites[0].pk}');self.assertNotIn('PRIVATE_',json.dumps(response.json()))
        self.assertTrue(response.json()['data']['privacy_redacted']);self.assertIsNotNone(response.json()['data']['contact_revoked_at'])
        self.assertNotContains(employer.get('/invitations/'),'PRIVATE_DISCUSSION')

    def test_old_accept_and_duplicate_send_never_reopen_revoked_grants(self):
        obj=self.invites[0];key=uuid4();self.action('revoke_company',self.companies[0].pk,key)
        receipts=PrivacyReceipt.objects.count()
        self.assertFalse(self.action('revoke_company',self.companies[0].pk,key))
        decide(self.profile,obj.pk,'accepted');duplicate=invite(self.companies[0],self.needs[0].pk,self.profile.pk)
        self.assertEqual(duplicate.pk,obj.pk);self.assertFalse(contacts_allowed(self.companies[0],self.profile))
        self.assertEqual(PrivacyReceipt.objects.count(),receipts)

    def test_new_explicit_accept_can_grant_again_but_old_invitation_contact_url_stays_denied(self):
        self.action('revoke_company',self.companies[0].pk)
        new=Need.objects.create(company=self.companies[0],title='Новая',grade='Junior',tasks='Новые',salary_min=1,salary_max=2,work_format='remote')
        obj=invite(self.companies[0],new.pk,self.profile.pk)
        self.assertFalse(contacts_allowed(self.companies[0],self.profile))
        decide(self.profile,obj.pk,'accepted');self.assertTrue(contacts_allowed(self.companies[0],self.profile))
        self.assertEqual(self.api.get(f'/api/v1/invitations/{self.invites[0].pk}/contacts').status_code,403)
        self.assertEqual(self.api.get(f'/api/v1/invitations/{obj.pk}/contacts').status_code,200)

    def test_foreign_company_and_role_cannot_revoke_another_subject(self):
        company=Company.objects.create(user=User.objects.create_user(username='unrelated-company',role='employer'),name='Чужая')
        response=self.web.post('/profile/privacy/',{'action':'revoke_company','company':company.pk,'request_id':uuid4(),'acknowledge':'on'})
        self.assertEqual(response.status_code,404)
        self.assertTrue(contacts_allowed(self.companies[0],self.profile))
        with self.assertRaises(ValidationError):request_action(self.employers[0],'revoke_all',uuid4())

    def test_password_and_checkbox_are_required_and_bearer_has_no_write_route(self):
        values={'action':'clear_profile','request_id':uuid4(),'password':self.password}
        self.assertEqual(self.web.post('/profile/privacy/',values).status_code,400)
        self.assertEqual(self.web.post('/profile/privacy/',dict(values,acknowledge='on',password='wrong')).status_code,400)
        self.profile.refresh_from_db();self.assertEqual(self.profile.description,'PRIVATE_PROFILE_SENTINEL')
        _,secret=issue_token(self.actor,'Read','mcp')
        api=Client(HTTP_AUTHORIZATION='Bearer '+secret)
        self.assertEqual(api.post('/api/v1/me/privacy',{},content_type='application/json').status_code,405)
        protected=Client(enforce_csrf_checks=True);protected.force_login(self.actor)
        self.assertEqual(protected.post('/profile/privacy/',dict(values,acknowledge='on')).status_code,403)

    def test_lapsed_processing_consent_does_not_force_new_consent_before_erasure(self):
        self.actor.processing_consented_at=None;self.actor.save()
        self.assertEqual(self.web.get('/profile/privacy/').status_code,200)
        response=self.web.post('/profile/privacy/',{'action':'clear_profile','request_id':uuid4(),'acknowledge':'on','password':self.password})
        self.assertEqual(response.status_code,302);self.profile.refresh_from_db();self.assertEqual(self.profile.name,'')

    def populate_private_graph(self):
        Experience.objects.create(profile=self.profile,organization='PRIVATE_EXPERIENCE',role='PRIVATE_ROLE',months=1)
        FspLink.objects.create(profile=self.profile,external_id='PRIVATE_FSP_ID',consented_at=timezone.now(),status='no_history')
        attempt=start_attempt(self.profile,'Junior');attempt.answers={q['id']:q['correct'] for q in attempt.tasks};attempt.save();finalize(attempt,timezone.now())
        from assistant.models import Draft
        Draft.objects.create(user=self.actor,mode='profile',payload={'description':'PRIVATE_DRAFT'},expires_at=timezone.now()+timedelta(hours=1))
        _,self.candidate_secret=issue_token(self.actor,'PRIVATE_TOKEN_NAME','cli',contacts=True,drafts=True)
        token,_=issue_token(self.employers[1],'Draft','cli',drafts=True)
        need=Need.objects.create(company=self.companies[1],title='Новое',grade='Junior',tasks='Новые',salary_min=1,salary_max=2,work_format='remote')
        draft=prepare(self.employers[1],token,'invitation.send',need.pk,{'candidate_id':self.profile.pk,'discussion':'PRIVATE_EMPLOYER_DRAFT'})
        return attempt,draft

    def test_clear_profile_erases_graph_and_snapshots_preserves_account_and_unrelated_person(self):
        attempt,draft=self.populate_private_graph()
        old_id=self.profile.pk;self.action('clear_profile')
        self.profile.refresh_from_db();self.assertFalse(self.profile.published)
        self.assertEqual((self.profile.contact_email,self.profile.name),('',''))
        self.assertEqual(self.profile.preferred_work_formats,[]);self.assertEqual(self.profile.confirmed_grade,'')
        self.assertFalse(Experience.objects.filter(profile=self.profile).exists());self.assertFalse(FspLink.objects.filter(profile=self.profile).exists())
        self.assertFalse(Attempt.objects.filter(candidate=self.profile).exists());self.assertFalse(ApiToken.objects.filter(user=self.actor).exists())
        self.assertFalse(ActionDraft.objects.filter(pk=draft.pk).exists())
        self.assertTrue(User.objects.get(pk=self.actor.pk).check_password(self.password))
        self.other_profile.refresh_from_db();self.assertEqual(self.other_profile.contact_email,'UNRELATED_CONTACT@demo.invalid')
        for invitation in Invitation.objects.filter(company__in=self.companies):
            self.assertIsNone(invitation.candidate_id);self.assertIsNotNone(invitation.candidate_erased_at)
            self.assertNotIn('PRIVATE_',json.dumps(invitation.snapshot))
            self.assertEqual(invitation.snapshot['candidate_preferences']['work_formats'],[])
        for path in [f'/api/v1/candidates/{old_id}',f'/api/v1/candidates/{old_id}/resume.pdf',f'/api/v1/candidates/{old_id}/proofs']:
            self.assertEqual(self.api.get(path).status_code,404)
        self.assertEqual(self.api.get(f'/api/v1/invitations/{self.invites[0].pk}/contacts').status_code,403)
        response=self.api.get(f'/api/v1/invitations/{self.invites[0].pk}')
        self.assertEqual(response.status_code,200);self.assertIsNone(response.json()['data']['candidate_id'])
        employer=Client();employer.force_login(self.employers[0])
        self.assertEqual(employer.get('/invitations/').status_code,200);self.assertNotContains(employer.get('/invitations/'),'Уникальное Имя')
        self.assertEqual(employer.get(f'/assessments/{attempt.pk}/proof/').status_code,404)
        stale=Client(HTTP_AUTHORIZATION='Bearer '+self.candidate_secret)
        self.assertEqual(stale.get('/api/v1/me/profile').status_code,401)

    def test_all_sessions_invalidated_but_password_can_log_in_again_after_clear(self):
        second=Client();second.force_login(self.actor)
        self.action('clear_profile')
        self.assertEqual(second.get('/profile/').status_code,302)
        self.assertNotIn('_auth_user_id',second.session)
        self.assertTrue(second.login(username=self.actor.username,password=self.password))
        self.assertEqual(second.get('/profile/').status_code,200)

    def test_delete_account_removes_login_tokens_and_direct_cascade_scrubs_history(self):
        self.populate_private_graph();pk=self.actor.pk;self.action('delete_account')
        self.assertFalse(User.objects.filter(pk=pk).exists());self.assertFalse(Profile.objects.filter(user_id=pk).exists())
        self.assertTrue(Invitation.objects.filter(company=self.companies[0],candidate__isnull=True).exists())
        self.assertNotIn('PRIVATE_',json.dumps(list(Invitation.objects.filter(company__in=self.companies).values('snapshot'))))
        self.assertFalse(self.web.login(username=self.actor.username,password=self.password))
        self.assertEqual(PrivacyReceipt.objects.get(action='delete_account').actor_id,None)

    def test_model_profile_delete_is_a_redaction_invariant(self):
        self.profile.delete()
        obj=Invitation.objects.get(pk=self.invites[0].pk)
        self.assertIsNone(obj.candidate_id);self.assertTrue(obj.snapshot['privacy_redacted'])
        self.assertNotIn('PRIVATE_',json.dumps(obj.snapshot))

    def test_queued_ledger_applies_before_any_read_and_is_idempotent_after_receipt(self):
        row={'id':str(uuid4()),'user_id':self.actor.pk,'identity':identity(self.actor),'action':'clear_profile','company_id':None,'created_at':timezone.now().isoformat()}
        append_ledger(row)
        self.assertEqual(self.api.get(f'/api/v1/candidates/{self.profile.pk}').status_code,404)
        self.profile.refresh_from_db();self.assertEqual(self.profile.name,'')
        self.profile.name='Новый Профиль';self.profile.save();reconcile();self.profile.refresh_from_db()
        self.assertEqual(self.profile.name,'Новый Профиль')
        text=self.ledger.read_text();self.assertNotIn('PRIVATE_',text);self.assertNotIn('@demo.invalid',text)
        self.assertEqual(self.ledger.stat().st_mode & 0o777,0o600)

    def test_failed_database_action_remains_durable_and_reconciles_next_request(self):
        with patch('profiles.privacy.apply_record',side_effect=RuntimeError('synthetic interruption')):
            with self.assertRaises(RuntimeError):self.action('clear_profile')
        self.profile.refresh_from_db();self.assertEqual(self.profile.name,'Уникальное Имя')
        self.assertTrue(self.ledger.exists());reconcile();self.profile.refresh_from_db();self.assertEqual(self.profile.name,'')

    def test_corrupt_or_unwritable_ledger_fails_closed_without_false_success(self):
        self.ledger.write_text('{broken json')
        self.assertEqual(self.api.get(f'/api/v1/candidates/{self.profile.pk}/private').status_code,503)
        self.assertEqual(self.web.get('/profile/').status_code,503)
        self.profile.refresh_from_db();self.assertEqual(self.profile.contact_email,'PRIVATE_EMAIL@demo.invalid')
        self.ledger.unlink()
        with patch('profiles.privacy.os.open',side_effect=OSError('synthetic disk failure')):
            with self.assertRaises(PrivacyUnavailable):self.action('clear_profile')
        self.profile.refresh_from_db();self.assertEqual(self.profile.name,'Уникальное Имя')

    def test_nonce_cannot_be_reused_for_another_action_or_actor(self):
        key=uuid4();self.action('revoke_company',self.companies[0].pk,key)
        with self.assertRaises(ValidationError):self.action('clear_profile',key=key)
        self.profile.refresh_from_db();self.assertEqual(self.profile.name,'Уникальное Имя')

    def test_clear_preserves_seven_and_thirty_day_limits_without_retaining_answers(self):
        now=timezone.now();self.profile.grade_changed_at=now-timedelta(days=2);self.profile.save()
        attempt=start_attempt(self.profile,'Junior');attempt.answers={q['id']:q['correct'] for q in attempt.tasks};attempt.save();finalize(attempt,now)
        self.action('clear_profile');self.profile.refresh_from_db()
        with self.assertRaises(ValueError):start_attempt(self.profile,'Junior')
        with self.assertRaises(ValueError):start_attempt(self.profile,'Middle')
        self.actor.refresh_from_db();holds=self.actor.assessment_privacy_holds
        self.assertEqual(holds['change_from'],'Junior');self.assertNotIn('answers',json.dumps(holds))
        with patch('assessments.services.timezone.now',return_value=now+timedelta(days=8)):
            next_attempt=start_attempt(self.profile,'Junior')
            self.assertEqual(next_attempt.grade,'Junior');self.assertNotEqual(next_attempt.variant,attempt.variant)

    def test_readonly_privacy_status_is_owned_and_no_contact_or_destructive_api(self):
        _,secret=issue_token(self.actor,'Read','mcp');api=Client(HTTP_AUTHORIZATION='Bearer '+secret)
        response=api.get('/api/v1/me/privacy');self.assertEqual(response.status_code,200)
        data=response.json()['data'];self.assertEqual(len(data['companies']),2)
        self.assertTrue(data['actions_in_browser_only']);self.assertFalse(data['saved_copies_revocable'])
        self.assertNotIn('PRIVATE_',json.dumps(data));self.assertEqual(api.post('/api/v1/me/privacy').status_code,405)

    def test_restored_revocation_does_not_override_a_later_explicit_acceptance(self):
        now=timezone.now();row={'id':str(uuid4()),'user_id':self.actor.pk,'identity':identity(self.actor),
            'action':'revoke_company','company_id':self.companies[0].pk,'created_at':(now-timedelta(days=1)).isoformat()}
        obj=self.invites[0];obj.created_at=now-timedelta(days=2);obj.responded_at=now;obj.save();self.assertTrue(contacts_allowed(self.companies[0],self.profile))
        append_ledger(row);reconcile();self.assertTrue(contacts_allowed(self.companies[0],self.profile))


    def test_all_company_revocation_and_format_floor_are_permanent(self):
        self.action('revoke_all')
        for company in self.companies:self.assertFalse(contacts_allowed(company,self.profile))
        self.assertTrue((self.ledger.parent/'privacy-floor-v1').exists())
        self.ledger.write_text('')
        (self.ledger.parent/'privacy-floor-v1').write_text('2\n')
        self.assertEqual(self.api.get('/api/v1/me').status_code,503)

    def test_identity_mismatch_does_not_erase_a_reused_numeric_identifier(self):
        row={'id':str(uuid4()),'user_id':self.actor.pk,'identity':'0'*64,'action':'delete_account','company_id':None,'created_at':timezone.now().isoformat()}
        append_ledger(row);reconcile()
        self.assertTrue(User.objects.filter(pk=self.actor.pk).exists())
        self.profile.refresh_from_db();self.assertEqual(self.profile.name,'Уникальное Имя')

    def test_erasing_active_exam_cannot_bypass_retry_limit(self):
        start_attempt(self.profile,'Junior');self.action('clear_profile');self.profile.refresh_from_db()
        self.assertFalse(Attempt.objects.filter(candidate=self.profile).exists())
        with self.assertRaises(ValueError):start_attempt(self.profile,'Junior')
