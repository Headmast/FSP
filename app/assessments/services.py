import copy
import secrets
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from profiles.models import Profile
from .bank import BANK, VERSION
from .models import Attempt
from .proofs import RULES


def validate_answers(attempt, submitted):
    allowed = {task['id'] for task in attempt.tasks}
    if not set(submitted).issubset(allowed):
        raise ValueError('Вопрос не принадлежит попытке.')
    answers = {}
    for key, value in submitted.items():
        try:
            number = int(value)
        except (ValueError, TypeError):
            raise ValueError('Неверный вариант ответа.')
        if not 0 <= number <= 3:
            raise ValueError('Неверный вариант ответа.')
        answers[key] = number
    return answers


def finalize(attempt, now):
    if attempt.status == 'finished':
        return attempt
    areas = {}
    count = 0
    for task in attempt.tasks:
        correct = attempt.answers.get(task['id']) == task['correct']
        count += int(correct)
        areas[task['area']] = areas.get(task['area'], 0) + int(correct)
    attempt.correct_count = count
    attempt.area_scores = areas
    rules=RULES[attempt.rules_version]
    attempt.passed = count >= rules['min_correct'] and all(score >= rules['min_per_area'] for score in areas.values())
    attempt.expired = now > attempt.expires_at
    attempt.status = 'finished'
    attempt.finished_at = now
    attempt.save()
    if attempt.passed:
        profile = Profile.objects.get(pk=attempt.candidate_id)
        if profile.confirmed_grade != attempt.grade:
            profile.confirmed_grade = attempt.grade
            profile.grade_changed_at = now
        profile.test_score = count / 8
        profile.save(update_fields=['confirmed_grade', 'grade_changed_at', 'test_score'])
    return attempt


def start_attempt(profile, grade):
    if grade not in {'Junior', 'Middle'}:
        raise ValueError('Неизвестная категория.')
    now = timezone.now()
    # Expired attempts must stay finalized even when the subsequent start is refused by cooldown.
    with transaction.atomic():
        active = Attempt.objects.filter(candidate=profile, status='active').first()
        if active and active.expires_at >= now:
            return active
        if active:
            finalize(active, now)
    with transaction.atomic():
        profile = Profile.objects.get(pk=profile.pk)
        from django.utils.dateparse import parse_datetime
        holds=profile.user.assessment_privacy_holds
        if isinstance(holds,dict):
            for key in ['change',grade]:
                if key=='change' and grade==holds.get('change_from'):continue
                value=holds.get(key)
                until=parse_datetime(value) if isinstance(value,str) else None
                if until and timezone.is_aware(until) and until>now:
                    raise ValueError('После очистки профиля прежний срок повторной проверки ещё не истёк.')
        active = Attempt.objects.filter(candidate=profile, status='active').first()
        if active:
            return active
        if profile.confirmed_grade == 'Middle' and grade == 'Junior':
            raise ValueError('У вас уже подтверждена более высокая категория.')
        if profile.confirmed_grade and profile.confirmed_grade != grade and profile.grade_changed_at and profile.grade_changed_at > now - timedelta(days=30):
            raise ValueError('Изменить подтверждённую категорию можно через 30 дней.')
        latest = Attempt.objects.filter(candidate=profile, grade=grade, status='finished').order_by('-finished_at').first()
        if latest and latest.finished_at > now - timedelta(days=7):
            raise ValueError('Повтор этой категории доступен через семь дней.')
        retained=None
        if isinstance(holds,dict) and holds.get('variant_bank')==VERSION:
            until=parse_datetime(holds.get('variant_until',''))
            values=holds.get('variants',{})
            if until and timezone.is_aware(until) and until>now and isinstance(values,dict):
                retained=values.get(grade)
        if latest:
            variant = 'B' if latest.variant == 'A' else 'A'
        elif retained in {'A','B'}:
            variant = 'B' if retained=='A' else 'A'
        else:
            # SQLite IMMEDIATE serializes this allocation with creation of the attempt.
            first_candidates=Attempt.objects.filter(grade=grade,bank_version=VERSION).values('candidate').distinct().count()
            variant = 'AB'[first_candidates % 2]
        tasks = copy.deepcopy(BANK[(grade, variant)])
        for task in tasks:
            order = list(range(4))
            secrets.SystemRandom().shuffle(order)
            task['options'] = [task['options'][index] for index in order]
            task['correct'] = order.index(task['correct'])
        return Attempt.objects.create(candidate=profile, grade=grade, variant=variant, bank_version=VERSION,
            tasks=tasks, started_at=now, expires_at=now + timedelta(minutes=15))


def save_answers(profile, attempt_id, submitted, finish=False):
    with transaction.atomic():
        attempt = Attempt.objects.get(pk=attempt_id, candidate=profile)
        if attempt.status == 'finished':
            return attempt
        now = timezone.now()
        if now > attempt.expires_at:
            if finish:
                return finalize(attempt, now)
            raise ValueError('Время вышло. Новые ответы не принимаются; завершите попытку с сохранёнными ответами.')
        answers = validate_answers(attempt, submitted)
        attempt.answers = {**attempt.answers, **answers}
        attempt.save(update_fields=['answers'])
        return finalize(attempt, now) if finish else attempt
