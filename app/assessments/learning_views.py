from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from accounts.access import role_required
from profiles.models import Profile
from .learning import (LearningLocked, active_exam, complete_lesson, next_question,
                       public_questions, review_questions, save_practice, start_practice)
from .learning_tracks import TRACKS, get_track, track_context
from .models import LessonProgress, PracticeSession


def profile_for(request):
    return get_object_or_404(Profile, user=request.user)


def locked(request, profile, status=423):
    return render(request, 'learning/locked.html', {'exam': active_exam(profile), **track_context('ios')}, status=status)


def material_for(track):
    try:
        return get_track(track)['material']
    except ValueError:
        raise Http404


def safe_id(value):
    try:
        pk = int(value)
    except (TypeError, ValueError):
        raise Http404
    if not 0 < pk <= 9223372036854775807:
        raise Http404
    return pk


def owned_session(request, pk, **filters):
    return get_object_or_404(PracticeSession, pk=safe_id(pk), candidate__user=request.user, **filters)


@role_required('candidate')
@require_GET
def dashboard(request):
    profile = profile_for(request)
    if active_exam(profile):
        return locked(request, profile, 200)
    track = request.GET.get('track', request.session.get('learning_track', 'ios'))
    material = material_for(track)
    request.session['learning_track'] = track
    grade = request.GET.get('grade', profile.desired_grade)
    if grade not in {'Junior', 'Middle'}:
        grade = 'Junior'
    completed = set(LessonProgress.objects.filter(candidate=profile, track=track, grade=grade,
                    content_version=material.VERSION).values_list('topic', flat=True))
    history = list(PracticeSession.objects.filter(candidate=profile, track=track, status='finished')[:20])
    latest = PracticeSession.objects.filter(candidate=profile, track=track, status='finished', grade=grade,
                                            kind='check', topic='all').first()
    topics = []
    for slug, topic in material.TOPICS.items():
        score = latest.area_scores.get(slug) if latest else None
        topics.append({**topic, 'slug': slug, 'title': material.LESSONS[(grade, slug)]['title'],
                       'completed': slug in completed, 'score': score,
                       'needs_review': score is not None and score['correct'] < score['total']})
    active = PracticeSession.objects.filter(candidate=profile, track=track, status='active').first()
    return render(request, 'learning/dashboard.html', {
        **track_context(track), 'tracks': [{'slug': slug, 'name': data['name']} for slug, data in TRACKS.items()],
        'profile': profile, 'grade': grade, 'topics': topics, 'completed_count': len(completed),
        'completion_percent': len(completed) * 25, 'history': history, 'latest': latest,
        'active': active, 'next_question': next_question(active) if active else 0,
    })


@role_required('candidate')
@require_GET
def lesson(request, grade, topic, track='ios'):
    material = material_for(track)
    content = material.LESSONS.get((grade, topic))
    if content is None:
        raise Http404
    profile = profile_for(request)
    if active_exam(profile):
        return locked(request, profile)
    request.session['learning_track'] = track
    completed = LessonProgress.objects.filter(candidate=profile, track=track, grade=grade, topic=topic, content_version=material.VERSION).exists()
    return render(request, 'learning/lesson.html', {**track_context(track), 'lesson': content, 'grade': grade,
                  'topic': topic, 'topic_name': material.TOPICS[topic]['name'], 'completed': completed})


@role_required('candidate')
@require_POST
def lesson_complete(request, grade, topic, track='ios'):
    material = material_for(track)
    if (grade, topic) not in material.LESSONS:
        raise Http404
    profile = profile_for(request)
    if active_exam(profile):
        return locked(request, profile)
    if request.POST.get('read') != 'on':
        messages.error(request, 'Подтвердите, что изучили урок и проверили себя по списку.')
        return redirect('learning-track-lesson', track=track, grade=grade, topic=topic)
    try:
        complete_lesson(profile, grade, topic, track=track)
    except LearningLocked:
        return locked(request, profile)
    messages.success(request, 'Урок отмечен как изученный. Закрепите его в самопроверке.')
    return redirect('learning-track-lesson', track=track, grade=grade, topic=topic)


@role_required('candidate')
@require_POST
def start(request):
    profile = profile_for(request)
    track = request.POST.get('track', 'ios')
    source_id = None
    if request.POST.get('source'):
        source = owned_session(request, request.POST['source'], status='finished')
        source_id, track = source.pk, source.track
    existing_id = PracticeSession.objects.filter(candidate=profile, track=track, status='active').values_list('pk', flat=True).first()
    try:
        session = start_practice(profile, request.POST.get('grade', ''), request.POST.get('topic', 'all'), source_id, track=track)
    except LearningLocked:
        return locked(request, profile)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('learning')
    request.session['learning_track'] = session.track
    if session.pk == existing_id:
        messages.info(request, 'Продолжена текущая самопроверка. Завершите её перед началом новой.')
    return redirect(reverse('learning-session', args=[session.pk]) + f'?question={next_question(session)}')


@role_required('candidate')
@require_GET
def session(request, pk):
    obj = owned_session(request, pk)
    if active_exam(obj.candidate):
        return locked(request, obj.candidate)
    material = material_for(obj.track)
    request.session['learning_track'] = obj.track
    if obj.status == 'finished':
        scores = [{**material.TOPICS[slug], **score, 'slug': slug} for slug, score in obj.area_scores.items()]
        return render(request, 'learning/result.html', {**track_context(obj.track), 'session': obj, 'questions': review_questions(obj),
                      'scores': scores, 'has_errors': obj.correct_count < len(obj.tasks),
                      'total': len(obj.tasks), 'percent': round(obj.correct_count / len(obj.tasks) * 100)})
    questions = public_questions(obj)
    try:
        index = int(request.GET.get('question', next_question(obj)))
    except (TypeError, ValueError):
        raise Http404
    if not 0 <= index < len(questions):
        raise Http404
    nav = [{'index': i, 'number': i + 1, 'answered': task['id'] in obj.answers, 'current': i == index} for i, task in enumerate(obj.tasks)]
    return render(request, 'learning/session.html', {
        **track_context(obj.track), 'session': obj, 'question': questions[index], 'index': index, 'number': index + 1,
        'total': len(questions), 'answered_count': len(obj.answers), 'navigation': nav,
        'previous': index - 1, 'following': index + 1, 'last': index == len(questions) - 1,
    })


@role_required('candidate')
@require_POST
def answer(request, pk):
    obj = owned_session(request, pk)
    submitted = {key[2:]: value for key, value in request.POST.items() if key.startswith('q_')}
    profile = obj.candidate
    try:
        obj = save_practice(profile, obj.pk, submitted, finish=request.POST.get('action') == 'finish')
    except LearningLocked:
        return locked(request, profile)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('learning-session', pk=obj.pk)
    if obj.status == 'finished':
        return redirect('learning-session', pk=obj.pk)
    if request.POST.get('action') == 'pause':
        messages.success(request, 'Ответ сохранён. Вы можете продолжить самопроверку позже.')
        return redirect(reverse('learning') + f'?track={obj.track}&grade={obj.grade}')
    messages.success(request, 'Ответ сохранён. Можно вернуться и изменить его до завершения.')
    return redirect(reverse('learning-session', args=[obj.pk]) + f'?question={next_question(obj)}')
