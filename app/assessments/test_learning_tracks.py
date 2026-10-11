import copy
from collections import Counter
from unittest.mock import patch
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.utils import timezone
from accounts.models import User
from profiles.models import Profile
from .bank import BANK
from .learning import LearningLocked, complete_lesson, save_practice, start_practice
from .learning_tracks import TRACKS
from .models import LessonProgress, PracticeSession
from .services import save_answers, start_attempt


class LearningTrackTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tracks@demo.invalid', role='candidate', email_confirmed=True,
                                            processing_consented_at=timezone.now(), processing_consent_version='processing-v1')
        self.profile = Profile.objects.create(user=self.user)
        self.client.force_login(self.user)

    def finish(self, obj, correct=True):
        answers = {t['id']: str(t['correct']) for t in obj.tasks} if correct else {}
        return save_practice(self.profile, obj.pk, answers, finish=True)

    def test_all_content_balanced_unique_and_separate_from_exam(self):
        ids, prompts = set(), set()
        exam_prompts = {q['prompt'] for questions in BANK.values() for q in questions}
        for track, data in TRACKS.items():
            material = data['material']
            self.assertEqual(len(material.LESSONS), 8)
            self.assertEqual(len(material.PRACTICE_BANK), 32)
            self.assertEqual(len(material.TOPICS), 4)
            self.assertTrue(all(len(topic) <= 16 for topic in material.TOPICS))
            self.assertEqual(Counter((q['grade'], q['topic']) for q in material.PRACTICE_BANK),
                             {(grade, topic): 4 for grade in ('Junior', 'Middle') for topic in material.TOPICS})
            for question in material.PRACTICE_BANK:
                self.assertNotIn(question['id'], ids)
                self.assertNotIn(question['prompt'], prompts | exam_prompts)
                ids.add(question['id']); prompts.add(question['prompt'])
                self.assertEqual(len(set(question['options'])), 4)
                self.assertIn(question['correct'], range(4))
                self.assertTrue(question['explanation'])
                lesson = material.LESSONS[(question['grade'], question['topic'])]
                self.assertTrue(lesson['source'].startswith('https://'))
        self.assertEqual(len(ids), 128)

    def test_all_tracks_generate_both_levels_and_each_topic(self):
        for track, data in TRACKS.items():
            for grade in ('Junior', 'Middle'):
                obj = start_practice(self.profile, grade, track=track)
                self.assertEqual(obj.track, track)
                self.assertEqual(obj.content_version, data['material'].VERSION)
                self.assertEqual(Counter(t['topic'] for t in obj.tasks), {topic: 2 for topic in data['material'].TOPICS})
                self.assertTrue(all(t['grade'] == grade for t in obj.tasks))
                self.assertEqual(self.finish(obj).correct_count, 8)
                for topic in data['material'].TOPICS:
                    obj = start_practice(self.profile, grade, topic, track=track)
                    self.assertEqual({t['topic'] for t in obj.tasks}, {topic})
                    self.assertEqual(self.finish(obj).correct_count, 4)

    def test_active_sessions_are_independent_and_resume_their_own_snapshot(self):
        attempts = {track: start_practice(self.profile, 'Junior', track=track) for track in TRACKS}
        self.assertEqual(len({obj.pk for obj in attempts.values()}), 4)
        for track, obj in attempts.items():
            first = obj.tasks[0]
            snapshot = copy.deepcopy(obj.tasks)
            save_practice(self.profile, obj.pk, {first['id']: '1'})
            resumed = start_practice(self.profile, 'Middle', track=track)
            self.assertEqual(resumed.pk, obj.pk)
            self.assertEqual(resumed.tasks, snapshot)
            self.assertEqual(resumed.answers, {first['id']: 1})
            with self.assertRaises(IntegrityError), transaction.atomic():
                PracticeSession.objects.create(candidate=self.profile, track=track, grade='Junior', tasks=[], content_version='1')

    def test_lesson_progress_dashboard_history_and_recommendations_are_scoped(self):
        for track, data in TRACKS.items():
            topic = next(iter(data['material'].TOPICS))
            first = complete_lesson(self.profile, 'Junior', topic, track=track)
            self.assertEqual(complete_lesson(self.profile, 'Junior', topic, track=track).pk, first.pk)
            with patch.object(data['material'], 'VERSION', 'new-version'):
                self.assertNotEqual(complete_lesson(self.profile, 'Junior', topic, track=track).pk, first.pk)
            complete_lesson(self.profile, 'Middle', topic, track=track)
            finished = self.finish(start_practice(self.profile, 'Junior', track=track), correct=False)
            active = start_practice(self.profile, 'Junior', track=track)
            response = self.client.get(f'/learning/?track={track}&grade=Junior')
            self.assertContains(response, '1 из 4 тем изучено')
            self.assertEqual(response.context['active'].pk, active.pk)
            self.assertEqual([item.pk for item in response.context['history']], [finished.pk])
            self.assertEqual(response.context['latest'].pk, finished.pk)
            self.assertContains(response, 'стоит повторить', count=4)
        self.assertEqual(LessonProgress.objects.count(), 12)

    def test_selected_track_persists_but_legacy_routes_still_choose_ios(self):
        self.client.get('/learning/?track=flutter')
        self.assertEqual(self.client.get('/learning/').context['track'], 'flutter')
        self.assertEqual(self.client.get('/learning/lessons/Junior/swift/').context['track'], 'ios')
        self.client.get('/learning/?track=aurora')
        self.client.post('/learning/start/', {'grade': 'Junior'})
        self.assertEqual(PracticeSession.objects.get().track, 'ios')
        self.client.get('/learning/?track=android')
        self.assertContains(self.client.get('/assessments/'), '/learning/?track=ios&amp;grade=Junior')
        exam = start_attempt(self.profile, 'Junior')
        save_answers(self.profile, exam.pk, {}, finish=True)
        self.assertContains(self.client.get(f'/assessments/{exam.pk}/'), '/learning/?track=ios&amp;grade=Junior')

    def test_review_source_defines_track_level_snapshot_even_if_client_forges_selection(self):
        ios = start_practice(self.profile, 'Junior')
        for track in ('android', 'flutter', 'aurora'):
            source = self.finish(start_practice(self.profile, 'Middle', track=track), correct=False)
            with patch.object(TRACKS[track]['material'], 'PRACTICE_BANK', []):
                response = self.client.post('/learning/start/', {'source': source.pk, 'track': 'ios', 'grade': 'Junior'})
            review = PracticeSession.objects.get(candidate=self.profile, track=track, status='active')
            self.assertEqual(response.url, f'/learning/sessions/{review.pk}/?question=0')
            self.assertEqual((review.grade, review.topic, review.content_version), (source.grade, source.topic, source.content_version))
            self.assertEqual({t['id'] for t in review.tasks}, {t['id'] for t in source.tasks})
            self.assertNotEqual(review.pk, ios.pk)
            self.finish(review)
        self.assertEqual(PracticeSession.objects.get(pk=ios.pk).status, 'active')

    def test_non_ios_views_do_not_offer_platform_certification(self):
        for track in ('android', 'flutter', 'aurora'):
            response = self.client.get(f'/learning/?track={track}')
            self.assertContains(response, f'Подтверждение категории для {TRACKS[track]["name"]} пока недоступно.')
            self.assertNotContains(response, 'Перейти к тесту категории')
            obj = self.finish(start_practice(self.profile, 'Junior', track=track))
            response = self.client.get(f'/learning/sessions/{obj.pk}/')
            self.assertEqual(response.context['track'], track)
            self.assertNotContains(response, '>Тест категории iOS</a>')
            self.assertContains(response, f'?track={track}&amp;grade=Junior')
            self.assertContains(response, f'/learning/tracks/{track}/lessons/')

    def test_unknown_tracks_and_cross_platform_topics_are_rejected(self):
        for url in ('/learning/?track=missing', '/learning/tracks/missing/lessons/Junior/dart/',
                    '/learning/tracks/android/lessons/Junior/swift/', '/learning/tracks/flutter/lessons/Senior/dart/'):
            self.assertEqual(self.client.get(url).status_code, 404)
        for track, topic in (('missing', 'all'), ('android', 'dart'), ('flutter', 'qml'), ('aurora', 'compose')):
            with self.assertRaises(ValueError):
                start_practice(self.profile, 'Junior', topic, track=track)
            self.assertEqual(self.client.post('/learning/start/', {'track': track, 'grade': 'Junior', 'topic': topic}).status_code, 302)
        self.assertEqual(PracticeSession.objects.count(), 0)

    def test_new_routes_protect_lesson_writes_and_foreign_attempts(self):
        foreign = User.objects.create_user(username='foreign-tracks@demo.invalid', role='candidate', email_confirmed=True,
                                           processing_consented_at=timezone.now(), processing_consent_version='processing-v1')
        Profile.objects.create(user=foreign)
        csrf_client = Client(enforce_csrf_checks=True); csrf_client.force_login(self.user)
        for track in ('android', 'flutter', 'aurora'):
            topic = next(iter(TRACKS[track]['material'].TOPICS))
            url = f'/learning/tracks/{track}/lessons/Junior/{topic}/complete/'
            self.assertEqual(self.client.get(url).status_code, 405)
            self.assertEqual(csrf_client.post(url, {'read': 'on'}).status_code, 403)
            self.client.post(url)
            self.assertFalse(LessonProgress.objects.filter(track=track).exists())
            self.client.post(url, {'read': 'on'})
            self.assertTrue(LessonProgress.objects.filter(track=track).exists())
            obj = self.finish(start_practice(self.profile, 'Junior', track=track), correct=False)
            self.client.force_login(foreign)
            self.assertEqual(self.client.get(f'/learning/sessions/{obj.pk}/').status_code, 404)
            self.assertEqual(self.client.post('/learning/start/', {'track': track, 'source': obj.pk}).status_code, 404)
            self.assertEqual(self.client.post(f'/learning/sessions/{obj.pk}/answer/', {'action': 'finish'}).status_code, 404)
            self.client.force_login(self.user)

    def test_all_tracks_locked_during_active_exam_without_losing_answers(self):
        attempts = {track: start_practice(self.profile, 'Junior', track=track) for track in TRACKS}
        start_attempt(self.profile, 'Junior')
        for track, obj in attempts.items():
            topic = next(iter(TRACKS[track]['material'].TOPICS))
            url = f'/learning/tracks/{track}/lessons/Junior/{topic}/'
            self.assertEqual(self.client.get(url).status_code, 423)
            self.assertEqual(self.client.post(url + 'complete/', {'read': 'on'}).status_code, 423)
            self.assertEqual(self.client.get(f'/learning/sessions/{obj.pk}/').status_code, 423)
            self.assertEqual(self.client.post('/learning/start/', {'track': track, 'grade': 'Junior'}).status_code, 423)
            for call in (lambda: complete_lesson(self.profile, 'Junior', topic, track=track),
                         lambda: start_practice(self.profile, 'Junior', track=track)):
                with self.assertRaises(LearningLocked):
                    call()
            obj.refresh_from_db()
            self.assertEqual(obj.answers, {})
            self.assertEqual(obj.status, 'active')

    def test_scores_and_completions_do_not_change_profile_category(self):
        baseline = (self.profile.confirmed_grade, self.profile.test_score, self.profile.grade_changed_at)
        for track in ('android', 'flutter', 'aurora'):
            obj = self.finish(start_practice(self.profile, 'Middle', track=track))
            topic = next(iter(TRACKS[track]['material'].TOPICS))
            complete_lesson(self.profile, 'Middle', topic, track=track)
            self.assertEqual(obj.correct_count, 8)
        self.profile.refresh_from_db()
        self.assertEqual((self.profile.confirmed_grade, self.profile.test_score, self.profile.grade_changed_at), baseline)
