from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone
from accounts.models import User
from profiles.models import Profile
from hiring.models import Company,Need
from assessments.services import start_attempt,save_answers
from .models import Usage

class AssistantTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user(username='helper@demo.invalid',role='candidate',email_confirmed=True)
        self.profile=Profile.objects.create(user=self.user,name='Кандидат',skills='Swift',contact_email='private@demo.invalid')
        self.client.force_login(self.user)

    def test_mock_explicit_and_context_has_no_contacts(self):
        with patch('assistant.provider.generate',return_value='Мок помощника') as generate:
            response=self.client.post('/assistant/',{'mode':'profile'})
            self.assertEqual(response.status_code,200)
            self.assertEqual(generate.call_args.args,('profile',{'skills':'Swift'}))
        response=self.client.post('/assistant/',{'mode':'profile'})
        self.assertContains(response,'внешний AI не вызывался');self.assertNotContains(response,'private@demo.invalid')
        self.profile.refresh_from_db();self.assertEqual(self.profile.confirmed_grade,'')

    def test_limit_and_hour_reset(self):
        for _ in range(10):self.assertEqual(self.client.post('/assistant/',{'mode':'profile'}).status_code,200)
        self.assertEqual(self.client.post('/assistant/',{'mode':'profile'}).status_code,429)
        usage=Usage.objects.get();usage.window_start=timezone.now()-timedelta(hours=2);usage.save()
        self.assertEqual(self.client.post('/assistant/',{'mode':'profile'}).status_code,200)
        usage.refresh_from_db();self.assertEqual(usage.count,1)

    def test_failure_does_not_block_profile(self):
        with patch('assistant.provider.generate',side_effect=RuntimeError('private provider failure')):
            response=self.client.post('/assistant/',{'mode':'profile'})
            self.assertEqual(response.status_code,503);self.assertNotContains(response,'private provider failure',status_code=503)
        self.assertEqual(self.client.get('/profile/').status_code,200)

    def test_active_exam_blocks_all_assistance(self):
        obj=start_attempt(self.profile,'Junior')
        with patch('assistant.provider.generate') as generate:
            self.assertEqual(self.client.post('/assistant/',{'mode':'profile'}).status_code,409)
            generate.assert_not_called()
        answers={q['id']:q['correct'] for q in obj.tasks};save_answers(self.profile,obj.pk,answers,finish=True)
        self.assertEqual(self.client.post('/assistant/',{'mode':'result','identifier':obj.pk}).status_code,200)

    def test_foreign_or_unfinished_result_and_role_rejected(self):
        other=User.objects.create_user(username='other-helper@demo.invalid',role='candidate',email_confirmed=True)
        profile=Profile.objects.create(user=other);obj=start_attempt(profile,'Junior')
        save_answers(profile,obj.pk,{q['id']:q['correct'] for q in obj.tasks},finish=True)
        self.assertEqual(self.client.post('/assistant/',{'mode':'result','identifier':obj.pk}).status_code,404)
        self.assertEqual(self.client.post('/assistant/',{'mode':'need'}).status_code,403)
        self.assertEqual(self.client.post('/assistant/',{'mode':'result','identifier':'bad'}).status_code,404)

    def test_employer_need_draft_is_owned_and_does_not_include_contacts(self):
        employer=User.objects.create_user(username='company-helper@demo.invalid',role='employer',email_confirmed=True)
        company=Company.objects.create(user=employer,contact_email='company-private@demo.invalid')
        need=Need.objects.create(company=company,title='iOS',grade='Junior',skills='Swift',tasks='Задачи',salary_min=100,salary_max=200,work_format='remote')
        self.client.force_login(employer)
        with patch('assistant.provider.generate',return_value='Мок') as generate:
            response=self.client.post('/assistant/',{'mode':'need','identifier':need.pk});self.assertEqual(response.status_code,200)
            self.assertEqual(generate.call_args.args,('need',{'grade':'Junior','skills':'Swift'}))
        self.assertEqual(self.client.post('/assistant/',{'mode':'profile'}).status_code,403)
