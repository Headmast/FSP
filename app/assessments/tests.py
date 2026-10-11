from collections import Counter
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from accounts.models import User
from profiles.models import Profile
from .bank import BANK
from .models import Attempt
from .services import start_attempt, save_answers

class AssessmentTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user(username='exam@demo.invalid',role='candidate',email_confirmed=True,processing_consented_at=timezone.now(),processing_consent_version="processing-v1")
        self.profile=Profile.objects.create(user=self.user)
        self.client.force_login(self.user)

    def answers(self,attempt,wrong=()):
        return {q['id']:str((q['correct']+1)%4 if index in wrong else q['correct']) for index,q in enumerate(attempt.tasks)}

    def test_bank_is_balanced_and_has_unique_reviewable_items(self):
        ids=[]
        for tasks in BANK.values():
            self.assertEqual(len(tasks),8)
            self.assertEqual(Counter(q['area'] for q in tasks),{'Swift':2,'ARC':2,'Async':2,'UI/Data':2})
            for q in tasks:
                ids.append(q['id']);self.assertEqual(len(set(q['options'])),4);self.assertIn(q['correct'],range(4));self.assertTrue(q['explanation'])
        self.assertEqual(len(set(ids)),32)

    def test_six_correct_with_empty_area_fails(self):
        obj=start_attempt(self.profile,'Junior')
        result=save_answers(self.profile,obj.pk,self.answers(obj,wrong=(0,1)),finish=True)
        self.assertEqual(result.correct_count,6);self.assertFalse(result.passed)
        self.profile.refresh_from_db();self.assertEqual(self.profile.confirmed_grade,'')

    def test_boundary_patterns_across_both_grades_and_variants(self):
        for (grade,variant),tasks in BANK.items():
            for wrong,expected in [((0,2),True),((0,1),False),((0,2,4),False)]:
                with self.subTest(grade=grade,variant=variant,wrong=wrong):
                    obj=Attempt.objects.create(candidate=self.profile,grade=grade,variant=variant,bank_version='ios-swift-1',tasks=tasks,
                        started_at=timezone.now(),expires_at=timezone.now()+timedelta(minutes=15))
                    result=save_answers(self.profile,obj.pk,self.answers(obj,wrong),finish=True)
                    self.assertEqual(result.passed,expected)

    def test_snapshot_stays_fixed_and_keys_are_not_in_active_html(self):
        obj=start_attempt(self.profile,'Junior')
        self.assertEqual(start_attempt(self.profile,'Middle').pk,obj.pk)
        original=obj.tasks;obj.refresh_from_db();self.assertEqual(obj.tasks,original)
        response=self.client.get(f'/assessments/{obj.pk}/')
        self.assertEqual(response.status_code,200)
        for task in obj.tasks:self.assertNotContains(response,task['explanation'])

    def test_finalization_idempotent_and_profile_server_scored(self):
        obj=start_attempt(self.profile,'Junior');answers=self.answers(obj,wrong=(0,2))
        first=save_answers(self.profile,obj.pk,answers,finish=True)
        second=save_answers(self.profile,obj.pk,self.answers(obj,wrong=range(8)),finish=True)
        self.assertEqual(first.correct_count,6);self.assertEqual(second.correct_count,6)
        self.profile.refresh_from_db();self.assertEqual(self.profile.test_score,.75);self.assertEqual(self.profile.confirmed_grade,'Junior')

    def test_foreign_attempt_denied_and_fake_question_rejected(self):
        obj=start_attempt(self.profile,'Junior')
        with self.assertRaises(ValueError):save_answers(self.profile,obj.pk,{'forged-question':'0'})
        other=User.objects.create_user(username='foreign@demo.invalid',role='candidate',email_confirmed=True,processing_consented_at=timezone.now(),processing_consent_version="processing-v1")
        Profile.objects.create(user=other);self.client.force_login(other)
        for suffix in ['', 'answer/', 'finish/']:
            response=self.client.get(f'/assessments/{obj.pk}/') if not suffix else self.client.post(f'/assessments/{obj.pk}/{suffix}')
            self.assertEqual(response.status_code,404)

    def test_expired_attempt_uses_only_saved_answers(self):
        obj=start_attempt(self.profile,'Junior');partial={obj.tasks[0]['id']:obj.tasks[0]['correct']}
        save_answers(self.profile,obj.pk,partial)
        obj.expires_at=timezone.now()-timedelta(seconds=1);obj.save(update_fields=['expires_at'])
        with self.assertRaises(ValueError):save_answers(self.profile,obj.pk,self.answers(obj))
        result=save_answers(self.profile,obj.pk,self.answers(obj),finish=True)
        self.assertTrue(result.expired);self.assertEqual(result.correct_count,1);self.assertFalse(result.passed)

    def test_expired_finalization_persists_even_when_new_start_refused(self):
        obj=start_attempt(self.profile,'Junior');obj.expires_at=timezone.now()-timedelta(seconds=1);obj.save()
        with self.assertRaises(ValueError):start_attempt(self.profile,'Junior')
        obj.refresh_from_db();self.assertEqual(obj.status,'finished')

    def test_first_middle_failure_allows_junior_immediately(self):
        obj=start_attempt(self.profile,'Middle');save_answers(self.profile,obj.pk,self.answers(obj,range(8)),finish=True)
        self.assertEqual(start_attempt(self.profile,'Junior').grade,'Junior')

    def test_failed_upgrade_keeps_existing_grade_and_score(self):
        self.profile.confirmed_grade='Junior';self.profile.test_score=.75;self.profile.grade_changed_at=timezone.now()-timedelta(days=31);self.profile.save()
        obj=start_attempt(self.profile,'Middle');save_answers(self.profile,obj.pk,self.answers(obj,range(8)),finish=True)
        self.profile.refresh_from_db();self.assertEqual(self.profile.confirmed_grade,'Junior');self.assertEqual(self.profile.test_score,.75)

    def test_retry_cooldown_and_grade_change_cooldown(self):
        obj=start_attempt(self.profile,'Junior');save_answers(self.profile,obj.pk,self.answers(obj),finish=True)
        with self.assertRaises(ValueError):start_attempt(self.profile,'Junior')
        with self.assertRaises(ValueError):start_attempt(self.profile,'Middle')
        obj.finished_at=timezone.now()-timedelta(days=8);obj.save(update_fields=['finished_at'])
        other=start_attempt(self.profile,'Junior');self.assertEqual(other.variant,'B')

    def test_fsp_never_changes_grade_or_test_result(self):
        self.profile.fsp_status='demo_history';self.profile.fsp_prize=True;self.profile.save()
        obj=start_attempt(self.profile,'Junior');result=save_answers(self.profile,obj.pk,self.answers(obj,range(8)),finish=True)
        self.profile.refresh_from_db();self.assertFalse(result.passed);self.assertEqual(self.profile.confirmed_grade,'')

    def test_employer_cannot_start_or_read_exam(self):
        employer=User.objects.create_user(username='company@demo.invalid',role='employer',email_confirmed=True,processing_consented_at=timezone.now(),processing_consent_version="processing-v1")
        self.client.force_login(employer)
        self.assertEqual(self.client.get('/assessments/').status_code,403)
        self.assertEqual(self.client.post('/assessments/start/',{'grade':'Junior'}).status_code,403)
