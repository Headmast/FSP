"""Learning services are separate from category scoring and witnesses."""
import copy
import secrets
from django.db import transaction
from django.utils import timezone
from .learning_content import LESSONS, PRACTICE_BANK, TOPICS, VERSION
from .models import Attempt, LessonProgress, PracticeSession


class LearningLocked(ValueError):
    pass


def active_exam(profile):
    return Attempt.objects.filter(candidate=profile, status='active', expires_at__gte=timezone.now()).first()


def require_learning(profile):
    if active_exam(profile):
        raise LearningLocked('Обучение и самопроверка доступны после завершения активного теста категории.')


def validate_selection(grade, topic):
    if grade not in {'Junior', 'Middle'} or topic not in {'all', *TOPICS}:
        raise ValueError('Выберите существующие уровень и тему.')


def public_questions(session):
    return [{'id': task['id'], 'area': task['area'], 'prompt': task['prompt'],
             'options': list(enumerate(task['options'])), 'selected': session.answers.get(task['id'])}
            for task in session.tasks]


def review_questions(session):
    if session.status != 'finished':
        raise ValueError('Разбор доступен после завершения самопроверки.')
    return [{**task, 'selected_text': task['options'][session.answers[task['id']]] if task['id'] in session.answers else 'Нет ответа',
             'correct_text': task['options'][task['correct']], 'is_correct': session.answers.get(task['id']) == task['correct']}
            for task in session.tasks]


def next_question(session):
    return next((i for i, task in enumerate(session.tasks) if task['id'] not in session.answers), len(session.tasks) - 1)


@transaction.atomic
def start_practice(profile, grade, topic='all', source_id=None):
    require_learning(profile)
    validate_selection(grade, topic)
    active = PracticeSession.objects.filter(candidate=profile, status='active').first()
    if active:
        return active
    if source_id is not None:
        source = PracticeSession.objects.get(pk=source_id, candidate=profile, status='finished')
        tasks = [copy.deepcopy(task) for task in source.tasks if source.answers.get(task['id']) != task['correct']]
        if not tasks:
            raise ValueError('Ошибок в этой самопроверке нет. Начните новую проверку.')
        grade, topic, kind = source.grade, source.topic, 'review'
        version = source.content_version
    else:
        kind, version, tasks = 'check', VERSION, []
        for slug in TOPICS if topic == 'all' else [topic]:
            pool = [item for item in PRACTICE_BANK if item['grade'] == grade and item['topic'] == slug]
            tasks.extend(copy.deepcopy(secrets.SystemRandom().sample(pool, 2 if topic == 'all' else 4)))
    for task in tasks:
        order = list(range(len(task['options'])))
        secrets.SystemRandom().shuffle(order)
        task['options'] = [task['options'][index] for index in order]
        task['correct'] = order.index(task['correct'])
    return PracticeSession.objects.create(candidate=profile, grade=grade, topic=topic, kind=kind,
                                          content_version=version, tasks=tasks)


@transaction.atomic
def save_practice(profile, session_id, submitted, finish=False):
    require_learning(profile)
    session = PracticeSession.objects.select_for_update().get(pk=session_id, candidate=profile)
    if session.status == 'finished':
        return session
    allowed = {task['id']: len(task['options']) for task in session.tasks}
    if not set(submitted).issubset(allowed):
        raise ValueError('Вопрос не принадлежит этой самопроверке.')
    answers = {}
    for key, value in submitted.items():
        if isinstance(value, bool) or str(value) not in {str(i) for i in range(allowed[key])}:
            raise ValueError('Выберите существующий вариант ответа.')
        answers[key] = int(value)
    session.answers = {**session.answers, **answers}
    if finish:
        scores = {}
        for task in session.tasks:
            area = scores.setdefault(task['topic'], {'correct': 0, 'total': 0})
            area['total'] += 1
            area['correct'] += int(session.answers.get(task['id']) == task['correct'])
        session.area_scores = scores
        session.correct_count = sum(score['correct'] for score in scores.values())
        session.status = 'finished'
        session.finished_at = timezone.now()
    session.save()
    return session


@transaction.atomic
def complete_lesson(profile, grade, topic):
    require_learning(profile)
    if (grade, topic) not in LESSONS:
        raise ValueError('Урок не найден.')
    return LessonProgress.objects.get_or_create(candidate=profile, grade=grade, topic=topic,
                                                content_version=VERSION)[0]
