from datetime import timedelta
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.db import transaction
from django.shortcuts import get_object_or_404,render,redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from assessments.models import Attempt
from accounts.identifiers import parse_identifier
from profiles.models import Profile
from hiring.models import Need
from .models import Usage
from . import provider

@login_required
@require_http_methods(['GET','POST'])
def assistant(request):
    if not request.user.email_confirmed:raise PermissionDenied
    if not request.user.has_processing_consent:return redirect('consent')
    mode=request.POST.get('mode',request.GET.get('mode','profile' if request.user.role=='candidate' else 'need'))
    identifier=request.POST.get('identifier',request.GET.get('attempt',request.GET.get('need','')))
    identifier=parse_identifier(identifier,required=False)
    data={'mode':mode,'identifier':identifier,'text':None,'error':None}
    if request.method=='GET':return render(request,'assistant/helper.html',data)
    if request.user.role=='candidate' and Attempt.objects.filter(candidate__user=request.user,status='active').exists():
        data['error']='Помощник недоступен во время активного теста. Сначала завершите попытку.'
        return render(request,'assistant/helper.html',data,status=409)
    if mode=='profile' and request.user.role=='candidate':
        profile=get_object_or_404(Profile,user=request.user);context={'skills':profile.skills}
    elif mode=='need' and request.user.role=='employer':
        needs=Need.objects.filter(company__user=request.user)
        need=get_object_or_404(needs,pk=identifier) if identifier else needs.order_by('-pk').first()
        if not need:data['error']='Сначала создайте потребность.';return render(request,'assistant/helper.html',data,status=400)
        context={'grade':need.grade,'skills':need.skills}
    elif mode=='result' and request.user.role=='candidate':
        attempts=Attempt.objects.filter(candidate__user=request.user,status='finished')
        obj=get_object_or_404(attempts,pk=identifier) if identifier else attempts.order_by('-finished_at').first()
        if not obj:data['error']='Сначала завершите тест.';return render(request,'assistant/helper.html',data,status=400)
        context={'grade':obj.grade,'correct':obj.correct_count,'areas':obj.area_scores}
    else:raise PermissionDenied
    now=timezone.now()
    with transaction.atomic():
        usage,_=Usage.objects.get_or_create(user=request.user,defaults={'window_start':now})
        if usage.window_start<=now-timedelta(hours=1):usage.window_start=now;usage.count=0
        if usage.count>=10:
            data['error']='Лимит: 10 запросов в час. Основные функции доступны.'
            return render(request,'assistant/helper.html',data,status=429)
        usage.count+=1;usage.save()
    try:data['text']=provider.generate(mode,context)
    except Exception:
        data['error']='Помощник временно недоступен. Профиль, тесты и предложения продолжают работать.'
        return render(request,'assistant/helper.html',data,status=503)
    return render(request,'assistant/helper.html',data)
