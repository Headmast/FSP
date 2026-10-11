#!/usr/bin/env python3
"""Migrate synthetic legacy iOS progress in a disposable database and verify it survives."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / '.runtime' / 'qa'
QA.mkdir(parents=True, exist_ok=True)


def main():
    with tempfile.TemporaryDirectory(prefix='learning-migration-', dir=QA) as temporary:
        os.environ['DATABASE_PATH'] = str(Path(temporary) / 'test.sqlite3')
        os.environ['DEBUG'] = '1'
        os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
        sys.path.insert(0, str(ROOT / 'app'))
        import django
        django.setup()
        from django.db import connection, connections
        from django.db.migrations.executor import MigrationExecutor
        from django.utils import timezone
        from assessments.learning_content import PRACTICE_BANK, VERSION
        old_target = [('assessments', '0003_lessonprogress_practicesession')]
        executor = MigrationExecutor(connection)
        executor.migrate(old_target)
        old = executor.loader.project_state(old_target).apps
        user = old.get_model('accounts', 'User').objects.create(username='migration@demo.invalid', role='candidate')
        profile = old.get_model('profiles', 'Profile').objects.create(user_id=user.pk, confirmed_grade='Junior', test_score=.75)
        tasks = copy.deepcopy([task for task in PRACTICE_BANK if task['grade'] == 'Junior' and task['topic'] == 'swift'])
        answers = {tasks[0]['id']: tasks[0]['correct']}
        session = old.get_model('assessments', 'PracticeSession').objects.create(candidate_id=profile.pk,
                    grade='Junior', topic='swift', content_version=VERSION, tasks=tasks, answers=answers)
        lesson = old.get_model('assessments', 'LessonProgress').objects.create(candidate_id=profile.pk,
                    grade='Junior', topic='swift', content_version=VERSION)
        finished = old.get_model('assessments', 'PracticeSession').objects.create(candidate_id=profile.pk,
                    grade='Junior', topic='swift', content_version=VERSION, tasks=tasks, answers=answers,
                    status='finished', finished_at=timezone.now(), correct_count=1, area_scores={'swift': {'correct': 1, 'total': 4}})
        started_at, completed_at, finished_at = session.started_at, lesson.completed_at, finished.finished_at
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        from assessments.learning import complete_lesson, save_practice, start_practice
        from assessments.models import LessonProgress, PracticeSession
        from profiles.models import Profile
        candidate = Profile.objects.get(pk=profile.pk)
        migrated = PracticeSession.objects.get(pk=session.pk)
        assert (migrated.track, migrated.content_version, migrated.tasks, migrated.answers, migrated.started_at) == (
            'ios', VERSION, tasks, answers, started_at)
        assert migrated.status == 'active'
        assert LessonProgress.objects.get(pk=lesson.pk).completed_at == completed_at
        assert complete_lesson(candidate, 'Junior', 'swift').pk == lesson.pk
        assert start_practice(candidate, 'Middle').pk == session.pk
        completed = PracticeSession.objects.get(pk=finished.pk)
        assert (completed.track, completed.answers, completed.correct_count, completed.area_scores, completed.finished_at) == (
            'ios', answers, 1, {'swift': {'correct': 1, 'total': 4}}, finished_at)
        android = start_practice(candidate, 'Junior', track='android')
        assert android.pk != session.pk and android.track == 'android'
        resumed = save_practice(candidate, session.pk, {t['id']: str(t['correct']) for t in tasks}, finish=True)
        assert resumed.correct_count == 4
        candidate.refresh_from_db()
        assert candidate.confirmed_grade == 'Junior' and candidate.test_score == .75
        result = {'status': 'PASS', 'checked_at': timezone.now().isoformat(), 'from': 'assessments/0003', 'to': 'assessments/0004',
                  'database': 'temporary SQLite; deleted after check', 'scenarios': [
                      'legacy_ios_snapshot_answers_version_and_timestamps_preserved', 'finished_score_and_history_preserved',
                      'lesson_completion_idempotent_after_migration', 'legacy_active_session_resumes',
                      'independent_android_session_created', 'legacy_session_finishes_correctly', 'profile_category_unchanged']}
        (QA / 'MOBILE7-002-migration.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        connections.close_all()


if __name__ == '__main__':
    main()
