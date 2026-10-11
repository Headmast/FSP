from datetime import timedelta
from django.test import TestCase, Client
from django.utils import timezone
from accounts.models import User
from profiles.models import Profile
from .models import Company, Recruiter, Need, Invitation
from .forms import NeedForm
from .services import invite, decide


class OwnerDashboardTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.owner = self.user('owner', 'employer')
        self.other = self.user('other', 'employer')
        self.company = Company.objects.create(user=self.owner, name='Своя компания', contact_email='owner@demo.invalid')
        self.foreign_company = Company.objects.create(user=self.other, name='Чужая компания')
        self.hr = Recruiter.objects.create(company=self.company, name='Анна HR')
        self.second_hr = Recruiter.objects.create(company=self.company, name='Борис HR')
        self.foreign_hr = Recruiter.objects.create(company=self.foreign_company, name='Чужой HR')
        self.need = self.make_need(self.company, self.hr)
        self.foreign_need = self.make_need(self.foreign_company, self.foreign_hr)
        self.candidate = self.user('candidate', 'candidate')
        self.profile = Profile.objects.create(user=self.candidate, name='Алексей', confirmed_grade='Junior', published=True,
                                              contact_email='secret@demo.invalid', contact_phone='+79999999999')
        self.client.force_login(self.owner)

    def user(self, name, role):
        return User.objects.create_user(username=name+'@demo.invalid', role=role, email_confirmed=True,
                                        processing_consented_at=self.now, processing_consent_version='processing-v1')

    def make_need(self, company, recruiter=None):
        return Need.objects.create(company=company, recruiter=recruiter, title='iOS '+company.name, grade='Junior',
                                   tasks='Задачи', salary_min=100, salary_max=200, work_format='remote')

    def invitation(self, index, status='sent', days=2, recruiter=None, viewed=False):
        user = self.user('person'+str(index), 'candidate')
        profile = Profile.objects.create(user=user, name='Кандидат '+str(index), confirmed_grade='Junior', published=True)
        obj = Invitation.objects.create(company=self.company, need=self.need, candidate=profile, recruiter=recruiter,
                                         snapshot={}, status=status)
        created = self.now-timedelta(days=days)
        Invitation.objects.filter(pk=obj.pk).update(created_at=created,
            viewed_at=created+timedelta(hours=1) if viewed else None,
            responded_at=created+timedelta(days=1) if status!='sent' else None)
        return obj

    def test_cohort_metrics_and_no_foreign_data_or_contacts(self):
        self.invitation(1, 'accepted', recruiter=self.hr)
        self.invitation(2, 'declined', recruiter=self.hr, viewed=True)
        self.invitation(3, days=8, recruiter=self.hr, viewed=True)
        self.invitation(4)
        self.invitation(5, 'accepted', days=40, recruiter=self.hr)
        Invitation.objects.create(company=self.foreign_company, need=self.foreign_need, candidate=self.profile,
                                  recruiter=self.foreign_hr, status='accepted', snapshot={})
        response = self.client.get('/company/dashboard/')
        summary = response.context['summary']
        self.assertEqual({k: summary[k] for k in ['total', 'accepted', 'declined', 'pending', 'viewed', 'overdue']},
                         {'total':4, 'accepted':1, 'declined':1, 'pending':2, 'viewed':3, 'overdue':1})
        self.assertEqual(summary['conversion'],25)
        self.assertEqual(summary['response_days'],1)
        self.assertEqual(sum(bucket['sent'] for bucket in response.context['buckets']),4)
        self.assertEqual(sum(bucket['accepted'] for bucket in response.context['buckets']),1)
        self.assertNotContains(response,'Чужой HR')
        self.assertNotContains(response,'Чужая компания')
        self.assertNotContains(response,'secret@demo.invalid')
        self.assertNotContains(response,'+79999999999')

    def test_filters_combine_and_unassigned_history_is_preserved(self):
        self.invitation(1, 'accepted', recruiter=self.hr)
        self.invitation(2, days=40)
        self.invitation(3, days=8, recruiter=self.second_hr)
        response = self.client.get('/company/dashboard/', {'period':'7','hr':self.hr.pk,'need':self.need.pk})
        self.assertEqual(response.context['summary']['total'],1)
        self.assertEqual(len(response.context['people']),1)
        response = self.client.get('/company/dashboard/', {'period':'all','hr':'unassigned'})
        self.assertEqual(response.context['summary']['total'],1)
        self.assertEqual(response.context['people'][0]['name'],'Без ответственного')
        self.assertEqual(self.client.get('/company/dashboard/', {'period':'90'}).context['summary']['total'],3)

    def test_send_attribution_stays_fixed_after_reassignment_and_replay(self):
        offer = invite(self.company, self.need.pk, self.profile.pk)
        self.assertEqual(offer.recruiter_id,self.hr.pk)
        self.client.post('/company/team/', {'action':'assign','need':self.need.pk,'recruiter':self.second_hr.pk})
        self.need.refresh_from_db()
        self.assertEqual(self.need.recruiter_id,self.second_hr.pk)
        replay = invite(self.company,self.need.pk,self.profile.pk)
        self.assertEqual(replay.recruiter_id,self.hr.pk)
        next_offer = self.invitation(2)
        Invitation.objects.filter(pk=next_offer.pk).delete()
        next_offer = invite(self.company,self.need.pk,next_offer.candidate_id)
        self.assertEqual(next_offer.recruiter_id,self.second_hr.pk)
        decide(self.profile,offer.pk,'accepted')
        response = self.client.get('/company/dashboard/',{'hr':self.hr.pk})
        self.assertEqual(response.context['summary']['accepted'],1)

    def test_assignment_and_need_form_reject_foreign_recruiter(self):
        for data in [{'need':self.foreign_need.pk,'recruiter':self.hr.pk},
                     {'need':self.need.pk,'recruiter':self.foreign_hr.pk}]:
            self.client.post('/company/team/',{'action':'assign',**data})
        self.need.refresh_from_db()
        self.foreign_need.refresh_from_db()
        self.assertEqual(self.need.recruiter_id,self.hr.pk)
        self.assertEqual(self.foreign_need.recruiter_id,self.foreign_hr.pk)
        form = NeedForm({'company_name':'Своя','title':'iOS','grade':'Junior','skills':'Swift','tasks':'Задачи',
                         'salary_min':100,'salary_max':200,'work_format':'remote','next_step':'Встреча',
                         'recruiter':self.foreign_hr.pk}, company=self.company)
        self.assertFalse(form.is_valid())
        self.assertIn('recruiter',form.errors)

    def test_malformed_and_foreign_filters_fail_without_500(self):
        for key in ['hr','need']:
            for value in ['abc','²','-1','0','9'*198,str(2**63)]:
                with self.subTest(key=key,value=value):
                    self.assertEqual(self.client.get('/company/dashboard/',{key:value}).status_code,404)
        self.assertEqual(self.client.get('/company/dashboard/',{'hr':self.foreign_hr.pk}).status_code,404)
        self.assertEqual(self.client.get('/company/dashboard/',{'need':self.foreign_need.pk}).status_code,404)
        self.assertEqual(self.client.get('/company/dashboard/',{'period':'nonsense'}).status_code,404)

    def test_empty_state_has_no_invented_rates_or_get_side_effects(self):
        response=self.client.get('/company/dashboard/')
        self.assertContains(response,'пока нет приглашений')
        self.assertIsNone(response.context['summary']['conversion'])
        self.assertIsNone(response.context['summary']['response_days'])
        new_owner=self.user('fresh','employer')
        self.client.force_login(new_owner)
        self.assertEqual(self.client.get('/company/dashboard/').status_code,200)
        self.assertFalse(Company.objects.filter(user=new_owner).exists())

    def test_role_consent_confirmation_csrf_and_methods(self):
        self.assertEqual(self.client.post('/company/dashboard/').status_code,405)
        self.assertEqual(self.client.get('/company/team/').status_code,405)
        secure=Client(enforce_csrf_checks=True)
        secure.force_login(self.owner)
        self.assertEqual(secure.post('/company/team/',{'action':'add','name':'HR'}).status_code,403)
        self.client.force_login(self.candidate)
        self.assertEqual(self.client.get('/company/dashboard/').status_code,403)
        self.assertEqual(self.client.post('/company/team/',{'action':'add','name':'HR'}).status_code,403)
        self.owner.email_confirmed=False;self.owner.save()
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get('/company/dashboard/').status_code,403)
        self.owner.email_confirmed=True;self.owner.processing_consent_version='expired';self.owner.save()
        self.assertRedirects(self.client.get('/company/dashboard/'),'/accounts/consent/')
        self.client.logout()
        self.assertEqual(self.client.get('/company/dashboard/').status_code,302)

    def test_new_recruiter_and_unassignment_are_company_scoped(self):
        self.client.post('/company/team/', {'action':'add','name':'Елена'})
        self.assertTrue(Recruiter.objects.filter(company=self.company,name='Елена').exists())
        self.assertFalse(Recruiter.objects.filter(company=self.foreign_company,name='Елена').exists())
        self.client.post('/company/team/',{'action':'assign','need':self.need.pk,'recruiter':''})
        self.need.refresh_from_db();self.assertIsNone(self.need.recruiter_id)
        self.client.post('/company/team/',{'action':'add','name':'  '})
        self.assertEqual(Recruiter.objects.filter(company=self.company).count(),3)

    def test_dashboard_read_does_not_mark_invitations_viewed(self):
        offer=self.invitation(1,recruiter=self.hr)
        self.client.get('/company/dashboard/')
        offer.refresh_from_db();self.assertIsNone(offer.viewed_at)

    def test_day_boundary_is_local_and_future_rows_excluded(self):
        from unittest.mock import patch
        from datetime import datetime, timezone as dt_timezone
        now=datetime(2026,10,11,21,30,tzinfo=dt_timezone.utc) # 12 October in Moscow
        old=self.invitation(1)
        fresh=self.invitation(2)
        future=self.invitation(3)
        Invitation.objects.filter(pk=old.pk).update(created_at=datetime(2026,10,5,20,59,tzinfo=dt_timezone.utc))
        Invitation.objects.filter(pk=fresh.pk).update(created_at=datetime(2026,10,5,21,0,tzinfo=dt_timezone.utc))
        Invitation.objects.filter(pk=future.pk).update(created_at=now+timedelta(hours=1))
        with patch('hiring.dashboard.timezone.now',return_value=now):
            response=self.client.get('/company/dashboard/',{'period':'7'})
        self.assertEqual(response.context['summary']['total'],1)
        self.assertEqual(sum(b['sent'] for b in response.context['buckets']),1)

    def test_fixture_is_separate_and_repeat_preserves_changes(self):
        from django.core.management import call_command
        from io import StringIO
        offer=invite(self.company,self.need.pk,self.profile.pk)
        call_command('seed_owner_dashboard',stdout=StringIO())
        fixture=Company.objects.get(user__username='fixture-owner@demo.invalid')
        self.assertEqual(Invitation.objects.filter(company=fixture).count(),30)
        self.assertEqual(Recruiter.objects.filter(company=fixture).count(),3)
        self.assertEqual(User.objects.filter(username__startswith='fixture-owner-candidate-').count(),20)
        offer.refresh_from_db();self.assertEqual(offer.status,'sent')
        fixture.name='Сохранённое изменение';fixture.save()
        call_command('seed_owner_dashboard',stdout=StringIO())
        fixture.refresh_from_db();self.assertEqual(fixture.name,'Сохранённое изменение')
        self.assertEqual(Invitation.objects.filter(company=fixture).count(),30)
        self.assertEqual(Invitation.objects.filter(company=self.company).count(),1)
