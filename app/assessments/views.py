from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone
from accounts.access import role_required
from profiles.models import Profile
from .models import Attempt
from .services import start_attempt, save_answers

@role_required('candidate')
def dashboard(request):
    profile = Profile.objects.get(user=request.user)
    return render(request, 'assessments/dashboard.html', {'profile':profile,
        'attempts':Attempt.objects.filter(candidate=profile).order_by('-started_at')})

@role_required('candidate')
@require_POST
def start(request):
    profile = Profile.objects.get(user=request.user)
    try:
        obj = start_attempt(profile, request.POST.get('grade', ''))
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('assessments')
    return redirect('attempt', pk=obj.pk)

@role_required('candidate')
def attempt(request, pk):
    obj = get_object_or_404(Attempt, pk=pk, candidate__user=request.user)
    if obj.status == 'finished':
        return render(request, 'assessments/result.html', {'attempt':obj, 'profile':obj.candidate})
    questions = [{'id':task['id'], 'area':task['area'], 'prompt':task['prompt'],
                  'options':list(enumerate(task['options'])), 'selected':obj.answers.get(task['id'])} for task in obj.tasks]
    return render(request, 'assessments/attempt.html', {'attempt':obj, 'questions':questions, 'expired':timezone.now()>obj.expires_at})


def submit(request, pk, finish):
    profile = Profile.objects.get(user=request.user)
    obj = get_object_or_404(Attempt, pk=pk, candidate=profile)
    submitted = {key[2:]:value for key,value in request.POST.items() if key.startswith('q_')}
    try:
        save_answers(profile, obj.pk, submitted, finish=finish)
        messages.success(request, 'Попытка завершена.' if finish else 'Ответы сохранены.')
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect('attempt', pk=obj.pk)

@role_required('candidate')
@require_POST
def answer(request, pk):
    return submit(request, pk, False)

@role_required('candidate')
@require_POST
def finish(request, pk):
    return submit(request, pk, True)
