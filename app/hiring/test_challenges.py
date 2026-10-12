from datetime import timedelta
import json,tempfile
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
from django.test import TestCase,Client,override_settings
from django.core.exceptions import ValidationError,PermissionDenied
from django.http import Http404
from django.utils import timezone
from accounts.models import User
from profiles.models import Profile
from profiles.privacy import request_action
from .models import Company,Need,Invitation,GapChallenge
from .services import invite,decide,rank,contacts_allowed
from . import challenges as service
from .challenge_projection import data as projection


class ChallengeTests(TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        override=override_settings(PRIVACY_LEDGER_PATH=Path(temp.name)/'privacy.jsonl');override.enable();self.addCleanup(override.disable)
        self.now=timezone.now();self.password='Own-Challenge-2026!'
        def user(name,role):return User.objects.create_user(username=name+'@demo.invalid',password=self.password,role=role,
            email_confirmed=True,processing_consented_at=self.now,processing_consent_version='processing-v1')
        self.candidate=user('challenge-candidate','candidate');self.other_candidate=user('challenge-other','candidate')
        self.employer=user('challenge-employer','employer');self.other_employer=user('challenge-company-other','employer')
        self.profile=Profile.objects.create(user=self.candidate,name='Тестовый Кандидат',published=True,confirmed_grade='Junior',test_score=.75,skills='Swift',contact_email='PRIVATE_CONTACT@demo.invalid')
        Profile.objects.create(user=self.other_candidate)
        self.company=Company.objects.create(user=self.employer,name='Тестовая Компания',contact_email='company@demo.invalid')
        self.other_company=Company.objects.create(user=self.other_employer,name='Другая Компания',contact_email='other@demo.invalid')
        self.need=Need.objects.create(company=self.company,title='iOS',grade='Junior',skills='Swift, Combine, XCTest',tasks='Экран',salary_min=1,salary_max=2,work_format='remote')
        self.invitation=invite(self.company,self.need.pk,self.profile.pk);decide(self.profile,self.invitation.pk,'accepted');self.invitation.refresh_from_db()
        self.before=(self.profile.confirmed_grade,self.profile.test_score,self.profile.grade_changed_at,rank(self.profile,self.need))
        self.cclient=Client();self.cclient.force_login(self.candidate);self.eclient=Client();self.eclient.force_login(self.employer)

    def terms(self,**changes):
        return {'request_id':uuid4(),'skill':'Combine','title':'Проверка отмены запроса','instructions':'INSTRUCTION_PRIVATE@demo.invalid',
            'criteria':['Объяснена отмена','Показана проверка'],'duration_minutes':15,'deadline_at':self.now+timedelta(days=7),'pass_points':3,**changes}

    def offer(self,**changes):return service.send(self.employer,self.invitation.pk,**self.terms(**changes))[0]
    def act(self,obj,kind,**kwargs):
        obj.refresh_from_db();user=self.employer if kind in {'withdraw','credit'} else self.candidate
        result=service.action(user,obj.pk,kind,revision=obj.revision,acknowledge=True,**kwargs)[0];obj.refresh_from_db();return result
    def submitted(self):
        obj=self.offer();self.act(obj,'accept');self.act(obj,'save',answer='DRAFT_PRIVATE@demo.invalid');self.act(obj,'submit',answer='ANSWER_PRIVATE@demo.invalid');return obj
    def reviewed(self):
        obj=self.submitted();service.review(self.employer,obj.pk,revision=obj.revision,scores=[2,2],note='REVIEW_PRIVATE@demo.invalid',acknowledge=True);obj.refresh_from_db();return obj
    def unchanged_grade(self):
        self.profile.refresh_from_db();self.assertEqual((self.profile.confirmed_grade,self.profile.test_score,self.profile.grade_changed_at,rank(self.profile,self.need)),self.before)

    def test_paid_accepted_own_invitation_required(self):
        self.invitation.status='sent';self.invitation.save()
        with self.assertRaises(service.ChallengeConflict):self.offer()
        self.invitation.status='declined';self.invitation.save()
        with self.assertRaises(service.ChallengeConflict):self.offer()
        with self.assertRaises(Http404):service.send(self.other_employer,self.invitation.pk,**self.terms())
        with self.assertRaises(PermissionDenied):service.send(self.candidate,self.invitation.pk,**self.terms())
        self.assertEqual(GapChallenge.objects.count(),0)

    def test_real_skill_gap_label_and_single_immutable_offer(self):
        terms=self.terms();obj,created=service.send(self.employer,self.invitation.pk,**terms);self.assertTrue(created)
        duplicate,created=service.send(self.employer,self.invitation.pk,**terms);self.assertFalse(created);self.assertEqual(duplicate.pk,obj.pk)
        self.assertEqual(obj.gap_kind,'missing_declared');self.assertEqual(self.offer(skill='Swift').gap_kind,'unverified_skill')
        with self.assertRaises(service.ChallengeConflict):service.send(self.employer,self.invitation.pk,**{**terms,'title':'Заменить правила'})
        self.need.tasks='Изменённая потребность';self.need.skills='Swift';self.need.save();obj.refresh_from_db()
        self.assertEqual(obj.instructions,terms['instructions']);self.assertEqual(obj.criteria,terms['criteria'])

    def test_send_validation_cannot_be_bypassed_by_service_call(self):
        bad=[{'skill':'UIKit'},{'skill':None},{'duration_minutes':4},{'duration_minutes':61},{'duration_minutes':True},
            {'criteria':[]},{'criteria':['Один']*2},{'criteria':['x'*181]},{'criteria':['x']*6},{'pass_points':5},{'pass_points':0},
            {'deadline_at':self.now},{'deadline_at':self.now+timedelta(days=31)},{'deadline_at':self.now.replace(tzinfo=None)},
            {'deadline_at':'bad'},{'request_id':'bad'},{'instructions':''},{'title':'x'*121}]
        for values in bad:
            with self.subTest(values=values),self.assertRaises(ValidationError):self.offer(**values)
        self.assertFalse(GapChallenge.objects.exists())

    def test_accept_requires_explicit_ack_and_replay_does_not_extend_timer(self):
        obj=self.offer()
        with self.assertRaises(ValidationError):service.action(self.candidate,obj.pk,'accept',revision=0)
        with patch('hiring.challenges.timezone.now',return_value=self.now):self.act(obj,'accept')
        start=obj.accepted_at
        with patch('hiring.challenges.timezone.now',return_value=self.now+timedelta(minutes=1)):
            _,changed=service.action(self.candidate,obj.pk,'accept',revision=0,acknowledge=True)
        self.assertFalse(changed);obj.refresh_from_db();self.assertEqual(obj.accepted_at,start)
        self.assertEqual(service.due_at(obj),self.now+timedelta(minutes=15));self.unchanged_grade()

    def test_absolute_deadline_caps_budget_and_exact_boundary_denies(self):
        obj=self.offer(deadline_at=self.now+timedelta(minutes=5))
        with patch('hiring.challenges.timezone.now',return_value=self.now):self.act(obj,'accept')
        self.assertEqual(service.due_at(obj),obj.deadline_at)
        with patch('hiring.challenges.timezone.now',return_value=obj.deadline_at):
            self.assertEqual(service.effective_state(obj),'expired')
            for kind in ['save','submit']:
                with self.assertRaises(service.ChallengeConflict):self.act(obj,kind,answer='Не должен сохраниться')
        obj.refresh_from_db();self.assertEqual(obj.answer,'');self.assertIsNone(obj.submitted_at)

    def test_expired_get_and_api_projection_do_not_write_state(self):
        obj=self.offer();self.act(obj,'accept');before=(obj.state,obj.revision,obj.accepted_at)
        with patch('hiring.challenges.timezone.now',return_value=service.due_at(obj)+timedelta(seconds=1)):
            self.assertEqual(projection(obj,self.candidate)['state'],'expired');self.assertContains(self.cclient.get(f'/challenges/{obj.pk}/'),'Срок истёк')
        obj.refresh_from_db();self.assertEqual((obj.state,obj.revision,obj.accepted_at),before)

    def test_decline_and_withdraw_are_idempotent_and_do_not_change_invitation(self):
        obj=self.offer();self.act(obj,'decline');self.act(obj,'decline')
        with self.assertRaises(service.ChallengeConflict):self.act(obj,'accept')
        other=self.offer(skill='XCTest');self.act(other,'withdraw');self.act(other,'withdraw')
        self.invitation.refresh_from_db();self.assertEqual(self.invitation.status,'accepted');self.assertTrue(contacts_allowed(self.company,self.profile))

    def test_draft_hidden_until_submission_and_safe_wire_omits_all_free_text(self):
        obj=self.offer();self.act(obj,'accept');self.act(obj,'save',answer='DRAFT_PRIVATE@demo.invalid')
        self.assertNotContains(self.eclient.get(f'/challenges/{obj.pk}/'),'DRAFT_PRIVATE')
        self.assertContains(self.cclient.get(f'/challenges/{obj.pk}/'),'DRAFT_PRIVATE')
        for user in [self.candidate,self.employer]:self.assertNotIn('PRIVATE',json.dumps(projection(obj,user)))
        self.act(obj,'submit',answer='ANSWER_PRIVATE@demo.invalid');self.assertContains(self.eclient.get(f'/challenges/{obj.pk}/'),'ANSWER_PRIVATE')
        self.unchanged_grade()

    def test_stale_draft_cannot_replace_newer_answer_or_submitted_response(self):
        obj=self.offer();self.act(obj,'accept');old=obj.revision;self.act(obj,'save',answer='Новый черновик')
        with self.assertRaises(service.ChallengeConflict):service.action(self.candidate,obj.pk,'save',revision=old,answer='Старый черновик')
        self.act(obj,'submit',answer='Финальный ответ');submitted=obj.submitted_at
        _,changed=service.action(self.candidate,obj.pk,'submit',revision=old,answer='Финальный ответ',acknowledge=True);self.assertFalse(changed)
        with self.assertRaises(service.ChallengeConflict):service.action(self.candidate,obj.pk,'submit',revision=old,answer='Заменить финальный',acknowledge=True)
        obj.refresh_from_db();self.assertEqual(obj.answer,'Финальный ответ');self.assertEqual(obj.submitted_at,submitted)

    def test_review_scale_and_immutable_result_and_explicit_credit(self):
        obj=self.submitted()
        for scores in [[2],[3,2],[True,2]]:
            with self.assertRaises(ValidationError):service.review(self.employer,obj.pk,revision=obj.revision,scores=scores,note='Оценка',acknowledge=True)
        with self.assertRaises(service.ChallengeConflict):service.review(self.employer,obj.pk,revision=obj.revision-1,scores=[2,2],note='Оценка',acknowledge=True)
        service.review(self.employer,obj.pk,revision=obj.revision,scores=[2,1],note='Достаточно, но проверка частичная',acknowledge=True)
        obj.refresh_from_db();self.assertEqual(service.result(obj)['points'],3);self.assertTrue(service.result(obj)['sufficient']);self.assertIsNone(obj.credited_at)
        _,changed=service.review(self.employer,obj.pk,revision=0,scores=[2,1],note='Достаточно, но проверка частичная',acknowledge=True);self.assertFalse(changed)
        with self.assertRaises(service.ChallengeConflict):service.review(self.employer,obj.pk,revision=obj.revision,scores=[2,2],note='Заменить оценку',acknowledge=True)
        self.act(obj,'credit');credited=obj.credited_at;self.act(obj,'credit');self.assertEqual(obj.credited_at,credited);self.unchanged_grade()

    def test_insufficient_review_cannot_be_credited(self):
        obj=self.submitted()
        with self.assertRaises(ValidationError):service.review(self.employer,obj.pk,revision=obj.revision,scores=[1,1],note='Порог не достигнут',acknowledge=True,credit=True)
        obj.refresh_from_db();self.assertEqual(obj.state,'submitted')
        service.review(self.employer,obj.pk,revision=obj.revision,scores=[1,1],note='Порог не достигнут',acknowledge=True)
        with self.assertRaises(service.ChallengeConflict):self.act(obj,'credit')
        self.unchanged_grade()

    def test_wrong_actor_and_other_company_have_no_task_or_result_access(self):
        obj=self.submitted()
        for user in [self.other_candidate,self.other_employer]:
            with self.assertRaises(Http404):service.owned(user,obj.pk)
        with self.assertRaises(PermissionDenied):service.review(self.candidate,obj.pk,revision=obj.revision,scores=[2,2],note='Себе оценка',acknowledge=True)
        self.assertEqual(self.eclient.post(f'/challenges/{obj.pk}/',{'action':'submit','revision':obj.revision,'answer':'fake','acknowledge':'on'}).status_code,403)
        self.assertEqual(self.cclient.post(f'/challenges/{obj.pk}/',{'action':'review'}).status_code,403)

    def test_explicit_answer_revoke_wins_over_stale_revision_and_retains_owner_history(self):
        obj=self.reviewed();_,changed=service.action(self.candidate,obj.pk,'revoke',revision=0,acknowledge=True);self.assertTrue(changed);obj.refresh_from_db()
        self.assertEqual(obj.state,'revoked');self.assertEqual(service.result(obj)['points'],4)
        self.assertContains(self.cclient.get(f'/challenges/{obj.pk}/'),'ANSWER_PRIVATE');self.assertNotContains(self.eclient.get(f'/challenges/{obj.pk}/'),'ANSWER_PRIVATE')
        self.assertIsNone(projection(obj,self.employer)['result']);self.assertIsNone(projection(obj,self.employer)['candidate_id'])
        self.assertEqual(projection(obj,self.candidate)['result']['points'],4);self.assertTrue(contacts_allowed(self.company,self.profile))
        with self.assertRaises(service.ChallengeConflict):self.act(obj,'credit')

    def test_global_contact_revoke_closes_task_and_new_grant_never_reopens_old_link(self):
        obj=self.reviewed();request_action(self.candidate,'revoke_company',uuid4(),self.company.pk);obj.refresh_from_db()
        self.assertEqual(obj.state,'revoked');self.assertFalse(service.share_open(obj));self.assertNotContains(self.eclient.get(f'/challenges/{obj.pk}/'),'ANSWER_PRIVATE')
        new_need=Need.objects.create(company=self.company,title='Новая роль',grade='Junior',skills='Combine',tasks='Новая задача',salary_min=1,salary_max=2,work_format='remote')
        invitation=invite(self.company,new_need.pk,self.profile.pk);decide(self.profile,invitation.pk,'accepted')
        self.assertTrue(contacts_allowed(self.company,self.profile));self.assertFalse(service.share_open(obj))
        with self.assertRaises(service.ChallengeConflict):service.review(self.employer,obj.pk,revision=obj.revision,scores=[2,2],note='Старый ответ',acknowledge=True)

    def test_clear_and_direct_profile_delete_erase_all_task_personal_content(self):
        obj=self.reviewed();request_action(self.candidate,'clear_profile',uuid4());obj.refresh_from_db()
        self.assertIsNone(obj.candidate_id);self.assertEqual(obj.state,'erased');self.assertEqual(obj.criteria,[]);self.assertEqual(obj.review_scores,[])
        self.assertEqual(obj.answer,obj.instructions);self.assertEqual(obj.review_note,'');self.assertIsNone(obj.reviewed_by_id)
        self.assertNotIn('PRIVATE',json.dumps(projection(obj,self.employer)));self.assertNotContains(self.eclient.get(f'/challenges/{obj.pk}/'),'PRIVATE')
        with self.assertRaises(Http404):service.owned(self.candidate,obj.pk)

    def test_orm_profile_delete_invariant_without_web_action(self):
        obj=self.reviewed();self.profile.delete();obj.refresh_from_db();self.assertIsNone(obj.candidate_id);self.assertEqual(obj.answer,'');self.assertEqual(obj.state,'erased')

    def test_browser_csrf_and_unchecked_consent_and_full_review_route(self):
        obj=self.offer();client=Client(enforce_csrf_checks=True);client.force_login(self.candidate)
        url=f'/challenges/{obj.pk}/';client.get(url);base={'action':'accept','revision':0,'acknowledge':'on'}
        self.assertEqual(client.post(url,base).status_code,403)
        csrf=client.cookies['csrftoken'].value
        self.assertEqual(client.post(url,{'action':'accept','revision':0,'csrfmiddlewaretoken':csrf}).status_code,400)
        self.assertEqual(client.post(url,{**base,'csrfmiddlewaretoken':csrf}).status_code,302)
        obj.refresh_from_db();self.assertEqual(self.cclient.post(url,{'action':'submit','revision':obj.revision,'answer':'Ответ','acknowledge':'on'}).status_code,302)
        obj.refresh_from_db();self.assertEqual(self.eclient.post(url,{'action':'review','revision':obj.revision,'score_0':2,'score_1':2,'note':'Решение обосновано','acknowledge':'on','credit':'on'}).status_code,302)
        obj.refresh_from_db();self.assertEqual(obj.state,'reviewed');self.assertIsNotNone(obj.credited_at);self.unchanged_grade()

    def test_token_projection_readonly_and_no_raw_fields_even_for_cli(self):
        from api.core import issue_token
        obj=self.reviewed()
        for user in [self.candidate,self.employer]:
            secret=issue_token(user,'Own safe tasks','mcp')[1];headers={'HTTP_AUTHORIZATION':'Bearer '+secret}
            response=self.client.get(f'/api/v1/challenges/{obj.pk}',**headers);self.assertEqual(response.status_code,200)
            self.assertNotIn('PRIVATE',response.content.decode());self.assertFalse(response.json()['data']['changes_professional_grade'])
            self.assertEqual(self.client.post(f'/api/v1/challenges/{obj.pk}',{},**headers).status_code,405)
        obj.refresh_from_db();self.assertEqual(obj.state,'reviewed');self.assertEqual(obj.revision,4)

    def test_http_offer_fields_and_duplicate_conflict(self):
        payload=self.terms();payload['deadline_at']=timezone.localtime(payload['deadline_at']).strftime('%Y-%m-%dT%H:%M');payload['criteria']='\n'.join(payload['criteria']);payload['acknowledge']='on'
        url=f'/invitations/{self.invitation.pk}/challenge/'
        self.assertEqual(self.eclient.post(url,payload).status_code,302);self.assertEqual(self.eclient.post(url,payload).status_code,302)
        self.assertEqual(self.eclient.post(url,{**payload,'title':'Изменить отправленное'}).status_code,409)
        self.assertEqual(GapChallenge.objects.count(),1)

    def test_task_revoke_fence_matches_immutable_nonce_not_only_numeric_id(self):
        from profiles.privacy import append_ledger,reconcile,identity
        obj=self.reviewed()
        row={'id':str(uuid4()),'user_id':self.candidate.pk,'identity':identity(self.candidate),'action':'revoke_challenge','company_id':None,
            'challenge_id':obj.pk,'challenge_nonce':str(uuid4()),'created_at':timezone.now().isoformat()}
        append_ledger(row);reconcile();obj.refresh_from_db();self.assertIsNone(obj.consent_revoked_at);self.assertTrue(service.share_open(obj))
        row.update(id=str(uuid4()),challenge_nonce=str(obj.request_id));append_ledger(row);reconcile();obj.refresh_from_db()
        self.assertIsNotNone(obj.consent_revoked_at);self.assertFalse(service.share_open(obj))

    def test_declined_task_terms_remain_owned_but_no_answer_share(self):
        obj=self.offer();self.act(obj,'decline')
        self.assertContains(self.eclient.get(f'/challenges/{obj.pk}/'),'INSTRUCTION_PRIVATE')
        self.assertFalse(service.share_open(obj));self.assertTrue(service.contents_open(obj));self.assertIsNone(projection(obj,self.employer)['result'])
