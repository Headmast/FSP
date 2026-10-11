from datetime import timedelta
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404,render,redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from assessments.models import Attempt
from accounts.identifiers import parse_identifier
from profiles.models import Profile
from hiring.models import Need
from .models import Usage, Draft
from .forms import NeedPromptForm,MatchingContextForm,ConversationContextForm
from . import contexts
from .drafts import create_draft, form_for, apply_draft, StaleDraft, ExpiredDraft, ActiveAssessment
from . import provider

@login_required
@require_http_methods(['GET','POST'])
def assistant(request):
    if not request.user.email_confirmed:raise PermissionDenied
    if not request.user.has_processing_consent:return redirect('consent')
    mode=request.POST.get('mode',request.GET.get('mode','profile' if request.user.role=='candidate' else 'need'))
    if mode not in ({'profile','result','conversation'} if request.user.role=='candidate' else {'need','matching','invitation','conversation'}):raise PermissionDenied
    identifier=request.POST.get('identifier',request.GET.get('attempt',request.GET.get('need','')))
    identifier=parse_identifier(identifier,required=False)
    data={'mode':mode,'identifier':identifier,'text':None,'error':None,
        'prompt_form':NeedPromptForm(initial={'grade':'Junior','skills':'Swift'}),'draft':None,
        'drafts':Draft.objects.filter(user=request.user).order_by('-created_at','-pk')[:10]}
    stage_context=None
    source=request.POST if request.method=='POST' else request.GET
    if mode in {'matching','invitation','conversation'}:
        keys=['invitation'] if mode=='conversation' else ['need','candidate']
        ids={key:parse_identifier(source.get(key,''),required=False) for key in keys}
        form_class=ConversationContextForm if mode=='conversation' else MatchingContextForm
        data['context_form']=form_class(request.POST if request.method=='POST' else None,user=request.user,initial=ids)
        if all(ids.values()):
            stage_context,objects=(contexts.conversation(request.user,ids['invitation']) if mode=='conversation' else
                contexts.matching(request.user,mode,ids['need'],ids['candidate']))
            data.update(objects)
        elif request.method=='POST':
            data['context_form'].is_valid()
            data['error']='Выберите контекст из ваших доступных данных.'
            return render(request,'assistant/helper.html',data,status=400)
    if request.method=='GET':
        if identifier and mode=='need':
            obj=get_object_or_404(Need,company__user=request.user,pk=identifier)
            data['prompt_form']=NeedPromptForm(initial={'grade':obj.grade,'skills':obj.skills})
        elif identifier and mode=='result':
            get_object_or_404(Attempt,candidate__user=request.user,status='finished',pk=identifier)
        return render(request,'assistant/helper.html',data)
    if request.user.role=='candidate' and Attempt.objects.filter(candidate__user=request.user,status='active').exists():
        data['error']='Помощник недоступен во время активного теста. Сначала завершите попытку.'
        return render(request,'assistant/helper.html',data,status=409)
    source_need=None
    if stage_context is not None:context=stage_context
    elif mode=='profile' and request.user.role=='candidate':
        profile=get_object_or_404(Profile,user=request.user);context={'skills':profile.skills}
    elif mode=='need' and request.user.role=='employer':
        needs=Need.objects.filter(company__user=request.user)
        source_need=get_object_or_404(needs,pk=identifier) if identifier else None
        if not source_need and request.POST.get('new_need')!='on':source_need=needs.order_by('-pk').first()
        if source_need:context={'grade':source_need.grade,'skills':source_need.skills}
        else:
            data['prompt_form']=NeedPromptForm(request.POST)
            if not data['prompt_form'].is_valid():return render(request,'assistant/helper.html',data,status=400)
            context={'grade':data['prompt_form'].cleaned_data['grade'] or 'Junior',
                'skills':data['prompt_form'].cleaned_data['skills']}
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
    if mode in {'profile','need'}:
        data['draft']=create_draft(request.user,mode,data['text'],context,source_need)
        data['draft_form']=form_for(data['draft'])
    return render(request,'assistant/helper.html',data)


@login_required
@require_http_methods(['GET','POST'])
def draft_detail(request,pk):
    if not request.user.email_confirmed:raise PermissionDenied
    if not request.user.has_processing_consent:return redirect('consent')
    pk=parse_identifier(str(pk))
    draft=get_object_or_404(Draft,user=request.user,pk=pk)
    if (draft.mode=='profile' and request.user.role!='candidate') or (draft.mode=='need' and request.user.role!='employer'):
        raise PermissionDenied
    data={'draft':draft,'draft_form':form_for(draft),'error':None}
    if request.method=='GET':return render(request,'assistant/draft.html',data)
    if request.user.role=='candidate' and Attempt.objects.filter(candidate__user=request.user,status='active').exists():
        data['error']='Помощник недоступен во время активного теста. Сначала завершите попытку.'
        return render(request,'assistant/draft.html',data,status=409)
    destination='profile' if draft.mode=='profile' else 'needs'
    if draft.applied_at:
        messages.info(request,'Этот черновик уже применён. Повторное сохранение не выполнялось.')
        return redirect(destination)
    if draft.expired:
        data['error']='Срок черновика истёк. Получите новый или заполните основную форму вручную.'
        return render(request,'assistant/draft.html',data,status=410)
    data['draft_form']=form_for(draft,request.POST)
    if not data['draft_form'].is_valid():return render(request,'assistant/draft.html',data,status=400)
    try:apply_draft(request.user,draft.pk,data['draft_form'])
    except ExpiredDraft as exc:
        data['error']=str(exc);return render(request,'assistant/draft.html',data,status=410)
    except (StaleDraft,ActiveAssessment) as exc:
        data['error']=str(exc);return render(request,'assistant/draft.html',data,status=409)
    messages.success(request,'Проверенный черновик сохранён.' if draft.mode=='profile' else 'По проверенному черновику создана новая потребность.')
    return redirect(destination)
