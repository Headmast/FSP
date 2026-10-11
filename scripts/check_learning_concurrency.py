#!/usr/bin/env python3
"""Check learning write races on a temporary SQLite database, never on user data."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / '.runtime' / 'qa'
QA.mkdir(parents=True, exist_ok=True)


def main():
    with tempfile.TemporaryDirectory(prefix='learning-races-', dir=QA) as temporary:
        os.environ['DATABASE_PATH'] = str(Path(temporary) / 'test.sqlite3')
        os.environ['DEBUG'] = '1'
        os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
        sys.path.insert(0, str(ROOT / 'app'))
        import django
        django.setup()
        from django.core.management import call_command
        from django.db import close_old_connections, connections
        from django.utils import timezone
        from accounts.models import User
        from profiles.models import Profile
        from assessments.learning import complete_lesson, save_practice, start_practice
        from assessments.models import LessonProgress, PracticeSession
        call_command('migrate', verbosity=0)
        user = User.objects.create_user(username='concurrency-learning@demo.invalid', role='candidate')
        profile = Profile.objects.create(user=user)

        def isolated(fn):
            close_old_connections()
            try:
                return fn(Profile.objects.get(pk=profile.pk))
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=4) as pool:
            ids = list(pool.map(lambda _: isolated(lambda p: start_practice(p, 'Junior').pk), range(4)))
        assert len(set(ids)) == 1, ids
        session = PracticeSession.objects.get(pk=ids[0])
        assert PracticeSession.objects.filter(status='active').count() == 1
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda task: isolated(lambda p: save_practice(p, session.pk, {task['id']: str(task['correct'])})), session.tasks[:4]))
        session.refresh_from_db()
        assert len(session.answers) == 4, session.answers
        answers = {task['id']: str(task['correct']) for task in session.tasks}
        with ThreadPoolExecutor(max_workers=4) as pool:
            scores = list(pool.map(lambda _: isolated(lambda p: save_practice(p, session.pk, answers, finish=True).correct_count), range(4)))
        assert scores == [8, 8, 8, 8], scores
        with ThreadPoolExecutor(max_workers=4) as pool:
            lessons = list(pool.map(lambda _: isolated(lambda p: complete_lesson(p, 'Junior', 'arc').pk), range(4)))
        assert len(set(lessons)) == 1, lessons
        assert LessonProgress.objects.count() == 1
        from assessments.learning_tracks import TRACKS
        with ThreadPoolExecutor(max_workers=4) as pool:
            starts = list(pool.map(lambda track: (track, isolated(lambda p: start_practice(p, 'Middle', track=track).pk)), list(TRACKS) * 2))
        for track in TRACKS:
            assert len({pk for slug, pk in starts if slug == track}) == 1, starts
        assert PracticeSession.objects.filter(status='active').count() == 4
        sessions = list(PracticeSession.objects.filter(status='active'))
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda obj: isolated(lambda p: save_practice(p, obj.pk,
                {t['id']: str(t['correct']) for t in obj.tasks}, finish=True).correct_count), sessions))
        assert results == [8] * 4, results
        with ThreadPoolExecutor(max_workers=4) as pool:
            progress = list(pool.map(lambda track: isolated(lambda p: complete_lesson(p, 'Junior',
                next(iter(TRACKS[track]['material'].TOPICS)), track=track).pk), TRACKS))
        assert len(set(progress)) == 4
        assert LessonProgress.objects.count() == 5
        profile.refresh_from_db()
        assert profile.confirmed_grade == '' and profile.test_score == 0
        result = {'status': 'PASS', 'checked_at': timezone.now().isoformat(), 'database': 'temporary SQLite; deleted after check',
                  'workers': 4, 'scenarios': ['one_active_session_on_parallel_start', 'parallel_answers_no_lost_update',
                  'parallel_finalization_idempotent', 'parallel_lesson_completion_unique', 'profile_grade_unchanged', 'parallel_starts_one_active_per_track',
                  'parallel_track_scoring_independent', 'parallel_track_lesson_progress_independent']}
        (QA / 'MOBILE7-002-concurrency.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        connections.close_all()


if __name__ == '__main__':
    main()
