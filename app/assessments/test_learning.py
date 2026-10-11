import copy
from collections import Counter
from datetime import timedelta
from unittest.mock import patch
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.utils import timezone
from accounts.models import User
from profiles.models import Profile
from .bank import BANK
from .learning import (LearningLocked, complete_lesson, public_questions, review_questions,
                       save_practice, start_practice)
from .learning_content import LESSONS, PRACTICE_BANK, TOPICS, VERSION
from .models import Attempt, LessonProgress, PracticeSession
from .services import start_attempt


class LearningTests(TestCase):
    def setUp(self):
        self.user = self.make_user('learner')
        self.profile = Profile.objects.create(user=self.user, confirmed_grade='Junior', test_score=.75,
                                               grade_changed_at=timezone.now() - timedelta(days=31))
        self.client.force_login(self.user)

    def make_user(self, name, role='candidate'):
        return User.objects.create_user(username=f'{name}@demo.invalid', role=role, email_confirmed=True,
                                       processing_consented_at=timezone.now(), processing_consent_version='processing-v1')

    def correct_answers(self, session):
        return {task['id']: str(task['correct']) for task in session.tasks}

    def finish(self, session, wrong=()):
        answers = {task['id']: str((task['correct'] + (1 if i in wrong else 0)) % 4) for i, task in enumerate(session.tasks)}
        return save_practice(self.profile, session.pk, answers, finish=True)

    def test_content_is_balanced_and_independent_of_exam(self):
        self.assertEqual(len(LESSONS), 8)
        self.assertEqual(len(PRACTICE_BANK), 32)
        self.assertEqual(len({task['id'] for task in PRACTICE_BANK}), 32)
        exam_ids = {task['id'] for tasks in BANK.values() for task in tasks}
        exam_prompts = {task['prompt'] for tasks in BANK.values() for task in tasks}
        for task in PRACTICE_BANK:
            self.assertNotIn(task['id'], exam_ids)
            self.assertNotIn(task['prompt'], exam_prompts)
            self.assertEqual(len(set(task['options'])), 4)
            self.assertIn(task['correct'], range(4))
            self.assertTrue(task['explanation'])
            self.assertIn((task['grade'], task['topic']), LESSONS)
        self.assertEqual(Counter((t['grade'], t['topic']) for t in PRACTICE_BANK),
                         {(grade, topic): 4 for grade in ('Junior', 'Middle') for topic in TOPICS})

    def test_full_check_balanced_for_each_grade_and_topic_check_has_four(self):
        for grade in ('Junior', 'Middle'):
            obj = start_practice(self.profile, grade)
            self.assertEqual(Counter(t['topic'] for t in obj.tasks), {topic: 2 for topic in TOPICS})
            self.assertTrue(all(task['grade'] == grade for task in obj.tasks))
            self.finish(obj)
            for topic in TOPICS:
                obj = start_practice(self.profile, grade, topic)
                self.assertEqual(len(obj.tasks), 4)
                self.assertEqual({t['topic'] for t in obj.tasks}, {topic})
                self.finish(obj)

    def test_resume_keeps_saved_answers_and_snapshot(self):
        obj = start_practice(self.profile, 'Junior')
        snapshot = copy.deepcopy(obj.tasks)
        task = obj.tasks[0]
        save_practice(self.profile, obj.pk, {task['id']: '0'})
        second = start_practice(self.profile, 'Middle', 'arc')
        self.assertEqual(second.pk, obj.pk)
        self.assertEqual(second.tasks, snapshot)
        self.assertEqual(second.answers, {task['id']: 0})
        self.assertEqual(PracticeSession.objects.filter(status='active').count(), 1)

    def test_scoring_and_lessons_never_update_category_or_exam_history(self):
        baseline = (self.profile.confirmed_grade, self.profile.test_score, self.profile.grade_changed_at)
        obj = start_practice(self.profile, 'Middle')
        self.finish(obj)
        complete_lesson(self.profile, 'Middle', 'swift')
        self.profile.refresh_from_db()
        self.assertEqual((self.profile.confirmed_grade, self.profile.test_score, self.profile.grade_changed_at), baseline)
        self.assertEqual(Attempt.objects.count(), 0)

    def test_missing_answers_are_errors_and_area_totals_are_exact(self):
        obj = start_practice(self.profile, 'Junior')
        task = obj.tasks[0]
        obj = save_practice(self.profile, obj.pk, {task['id']: str(task['correct'])}, finish=True)
        self.assertEqual(obj.correct_count, 1)
        self.assertEqual(sum(s['total'] for s in obj.area_scores.values()), 8)
        self.assertEqual(sum(s['correct'] for s in obj.area_scores.values()), 1)
        rows = review_questions(obj)
        self.assertEqual(sum(row['selected_text'] == 'Нет ответа' for row in rows), 7)

    def test_invalid_answers_are_rejected_atomically(self):
        obj = start_practice(self.profile, 'Junior')
        task = obj.tasks[0]
        for values in ({'forged': '0'}, {task['id']: '-1'}, {task['id']: '4'}, {task['id']: 'nan'},
                       {task['id']: True}, {task['id']: '1.0'}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                save_practice(self.profile, obj.pk, values, finish=True)
        obj.refresh_from_db()
        self.assertEqual(obj.answers, {})
        self.assertEqual(obj.status, 'active')

    def test_finished_result_is_idempotent_and_no_repeat_cooldown(self):
        obj = self.finish(start_practice(self.profile, 'Junior'), wrong=(0,))
        when, answers = obj.finished_at, copy.deepcopy(obj.answers)
        repeated = save_practice(self.profile, obj.pk, self.correct_answers(obj), finish=True)
        self.assertEqual(repeated.finished_at, when)
        self.assertEqual(repeated.answers, answers)
        self.assertEqual(repeated.correct_count, 7)
        self.assertNotEqual(start_practice(self.profile, 'Junior').pk, obj.pk)

    def test_review_contains_only_wrong_or_unanswered_questions(self):
        obj = self.finish(start_practice(self.profile, 'Middle'), wrong=(1, 4))
        wrong_ids = {obj.tasks[i]['id'] for i in (1, 4)}
        response = self.client.post('/learning/start/', {'grade': 'Middle', 'source': obj.pk})
        review = PracticeSession.objects.get(candidate=self.profile, status='active')
        self.assertNotContains(self.client.get(response.url), 'Продолжена текущая самопроверка.')
        self.assertEqual({t['id'] for t in review.tasks}, wrong_ids)
        self.assertEqual(review.kind, 'review')
        self.assertEqual(review.answers, {})
        self.finish(review)
        with self.assertRaises(ValueError):
            start_practice(self.profile, 'Middle', source_id=review.pk)

    def test_active_html_hides_keys_and_explanations_until_finish(self):
        obj = start_practice(self.profile, 'Junior')
        response = self.client.get(f'/learning/sessions/{obj.pk}/')
        self.assertEqual(response.status_code, 200)
        for task in obj.tasks:
            self.assertNotContains(response, task['explanation'])
        self.assertTrue(all('correct' not in row and 'explanation' not in row for row in public_questions(obj)))
        with self.assertRaises(ValueError):
            review_questions(obj)
        self.finish(obj)
        response = self.client.get(f'/learning/sessions/{obj.pk}/')
        for task in obj.tasks:
            self.assertContains(response, task['explanation'])

    def test_lesson_completion_scoped_by_grade_version_and_idempotent(self):
        first = complete_lesson(self.profile, 'Junior', 'swift')
        self.assertEqual(complete_lesson(self.profile, 'Junior', 'swift').pk, first.pk)
        complete_lesson(self.profile, 'Middle', 'swift')
        with patch('assessments.learning.VERSION', 'ios-learning-2'):
            complete_lesson(self.profile, 'Junior', 'swift')
        self.assertEqual(LessonProgress.objects.count(), 3)
        self.assertContains(self.client.get('/learning/?grade=Junior'), '1 из 4 тем изучено')
        self.assertContains(self.client.get('/learning/?grade=Middle'), '1 из 4 тем изучено')

    def test_lesson_post_requires_explicit_read_checkbox(self):
        url = '/learning/lessons/Junior/swift/complete/'
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(LessonProgress.objects.count(), 0)
        self.client.post(url, {'read': 'on'})
        self.assertEqual(LessonProgress.objects.count(), 1)

    def test_foreign_sessions_and_error_sources_return_404(self):
        obj = self.finish(start_practice(self.profile, 'Junior'), wrong=(0,))
        other = self.make_user('foreign-learning')
        Profile.objects.create(user=other)
        self.client.force_login(other)
        self.assertEqual(self.client.get(f'/learning/sessions/{obj.pk}/').status_code, 404)
        self.assertEqual(self.client.post(f'/learning/sessions/{obj.pk}/answer/', {'action': 'finish'}).status_code, 404)
        self.assertEqual(self.client.post('/learning/start/', {'grade': 'Junior', 'source': obj.pk}).status_code, 404)

    def test_role_confirmation_and_consent_gates(self):
        company = self.make_user('learning-company', 'employer')
        self.client.force_login(company)
        self.assertEqual(self.client.get('/learning/').status_code, 403)
        self.assertEqual(self.client.post('/learning/start/', {'grade': 'Junior'}).status_code, 403)
        self.user.email_confirmed = False
        self.user.save()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/learning/').status_code, 403)
        self.user.email_confirmed = True
        self.user.processing_consented_at = None
        self.user.save()
        self.assertRedirects(self.client.get('/learning/'), '/accounts/consent/')
        self.client.logout()
        self.assertEqual(self.client.get('/learning/').status_code, 302)

    def test_active_exam_blocks_lessons_practice_and_finished_review(self):
        finished = self.finish(start_practice(self.profile, 'Junior'))
        active = start_practice(self.profile, 'Junior')
        exam = start_attempt(self.profile, 'Middle')
        for url in ('/learning/lessons/Junior/swift/', f'/learning/sessions/{active.pk}/',
                    f'/learning/sessions/{finished.pk}/'):
            self.assertEqual(self.client.get(url).status_code, 423)
        self.assertNotContains(self.client.get('/learning/'), LESSONS[('Junior', 'swift')]['title'])
        self.assertEqual(self.client.post('/learning/start/', {'grade': 'Junior'}).status_code, 423)
        self.assertEqual(self.client.post('/learning/lessons/Junior/swift/complete/', {'read': 'on'}).status_code, 423)
        self.assertEqual(self.client.post(f'/learning/sessions/{active.pk}/answer/', {'action': 'finish'}).status_code, 423)
        for call in (lambda: start_practice(self.profile, 'Junior'), lambda: save_practice(self.profile, active.pk, {}),
                     lambda: complete_lesson(self.profile, 'Junior', 'swift')):
            with self.assertRaises(LearningLocked):
                call()
        active.refresh_from_db()
        self.assertEqual(active.status, 'active')
        self.assertEqual(LessonProgress.objects.count(), 0)
        exam.expires_at = timezone.now() - timedelta(seconds=1)
        exam.save()
        self.assertEqual(self.client.get('/learning/lessons/Junior/swift/').status_code, 200)
        self.assertEqual(self.client.get(f'/learning/sessions/{active.pk}/').status_code, 200)

    def test_invalid_routes_selection_and_question_index_are_safe(self):
        obj = start_practice(self.profile, 'Junior')
        for value in ('bad', '-1', '8', '999999999999999999'):
            self.assertEqual(self.client.get(f'/learning/sessions/{obj.pk}/?question={value}').status_code, 404)
        for value in ('0', '9223372036854775808', '999999999999999999999999'):
            self.assertEqual(self.client.get(f'/learning/sessions/{value}/').status_code, 404)
        self.assertEqual(self.client.get('/learning/lessons/Senior/swift/').status_code, 404)
        self.assertEqual(self.client.get('/learning/lessons/Junior/missing/').status_code, 404)
        for value in ('bad', '-1', '9223372036854775808'):
            self.assertEqual(self.client.post('/learning/start/', {'grade': 'Junior', 'source': value}).status_code, 404)
        for grade, topic in (('Senior', 'all'), ('Junior', 'missing')):
            with self.assertRaises(ValueError):
                start_practice(self.profile, grade, topic)

    def test_mutations_require_post_and_csrf(self):
        obj = start_practice(self.profile, 'Junior')
        for url in ('/learning/start/', '/learning/lessons/Junior/swift/complete/', f'/learning/sessions/{obj.pk}/answer/'):
            self.assertEqual(self.client.get(url).status_code, 405)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post('/learning/start/', {'grade': 'Junior'}).status_code, 403)
        self.assertEqual(csrf_client.post(f'/learning/sessions/{obj.pk}/answer/', {'action': 'finish'}).status_code, 403)

    def test_unique_active_session_and_lesson_constraints(self):
        obj = start_practice(self.profile, 'Junior')
        with self.assertRaises(IntegrityError), transaction.atomic():
            PracticeSession.objects.create(candidate=self.profile, grade='Junior', content_version=VERSION, tasks=obj.tasks)
        complete_lesson(self.profile, 'Junior', 'arc')
        with self.assertRaises(IntegrityError), transaction.atomic():
            LessonProgress.objects.create(candidate=self.profile, grade='Junior', topic='arc', content_version=VERSION)

    def test_post_flow_preserves_answers_and_redirects_to_first_missing(self):
        response = self.client.post('/learning/start/', {'grade': 'Junior', 'topic': 'swift'})
        obj = PracticeSession.objects.get()
        self.assertEqual(response.url, f'/learning/sessions/{obj.pk}/?question=0')
        first = obj.tasks[0]
        response = self.client.post(f'/learning/sessions/{obj.pk}/answer/', {f'q_{first["id"]}': str(first['correct']), 'action': 'save'})
        self.assertEqual(response.url, f'/learning/sessions/{obj.pk}/?question=1')
        self.assertContains(self.client.get(f'/learning/sessions/{obj.pk}/?question=0'), 'checked')
        self.client.post(f'/learning/sessions/{obj.pk}/answer/', {'action': 'finish'})
        self.assertContains(self.client.get(f'/learning/sessions/{obj.pk}/'), 'Нет ответа')

    def test_existing_snapshot_does_not_change_when_bank_changes(self):
        obj = start_practice(self.profile, 'Junior')
        original = copy.deepcopy(obj.tasks)
        with patch('assessments.learning.PRACTICE_BANK', []):
            self.assertEqual(start_practice(self.profile, 'Junior').tasks, original)
        obj.refresh_from_db()
        self.assertEqual(obj.tasks, original)

    def test_pause_saves_current_selection_before_returning_to_dashboard(self):
        obj = start_practice(self.profile, 'Junior')
        task = obj.tasks[0]
        response = self.client.post(f'/learning/sessions/{obj.pk}/answer/',
                                    {f'q_{task["id"]}': str(task['correct']), 'action': 'pause'})
        self.assertEqual(response.url, '/learning/?grade=Junior')
        obj.refresh_from_db()
        self.assertEqual(obj.answers, {task['id']: task['correct']})
        self.assertEqual(obj.status, 'active')

    def test_weak_topics_still_visible_after_twenty_recent_reviews(self):
        obj = self.finish(start_practice(self.profile, 'Junior'), wrong=(0,))
        for _ in range(21):
            self.finish(start_practice(self.profile, 'Junior', source_id=obj.pk))
        response = self.client.get('/learning/?grade=Junior')
        self.assertContains(response, 'стоит повторить', count=1)
        self.assertEqual(response.context['latest'].pk, obj.pk)
        self.assertEqual(len(response.context['history']), 20)
