"""Browser approval only: session, CSRF middleware and an explicit acknowledgement."""
import json
from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied,ValidationError
from django.http import Http404
from django.shortcuts import render,redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from .core import ApiError
from .drafts import get_draft,context,checked_actor,apply,cancel
from .models import ActionDraft


class ApprovalForm(forms.Form):
    acknowledge=forms.BooleanField(label='Я проверил изменения и подтверждаю действие')
    def __init__(self,*args,publish=False,**kwargs):
        super().__init__(*args,**kwargs)
        if publish:
            self.fields['publication_consent']=forms.BooleanField(label='Разрешаю публикацию профиля (publication-v1)')


def guard(request):
    if not request.user.is_active or not request.user.email_confirmed:raise PermissionDenied
    if not request.user.has_processing_consent:return redirect('consent')


@login_required
@require_http_methods(['GET','POST'])
def detail(request,pk):
    response=guard(request)
    if response:return response
    try:draft=get_draft(request.user,pk)
    except ApiError:raise Http404
    try:checked_actor(request.user,draft.kind)
    except ApiError:raise PermissionDenied
    form=ApprovalForm(request.POST if request.method=='POST' else None,publish=draft.kind=='profile.publish')
    error=None;status=200
    if request.method=='POST':
        if request.POST.get('action')=='cancel':
            try:cancel(request.user,draft)
            except ApiError as exc:error,status=exc.message,exc.status
            if not error:return redirect('action-draft',pk=draft.pk)
        elif request.POST.get('action')=='apply' and form.is_valid():
            try:apply(request.user,draft.pk)
            except ApiError as exc:error,status=exc.message,exc.status
            except (ValidationError,ValueError):error,status='Действие не прошло проверку. Подготовьте новый черновик.',400
            if not error:return redirect('action-draft',pk=draft.pk)
        else:
            error,status='Отметьте подтверждение действия.',400
    draft=get_draft(request.user,pk)
    before={}
    try:
        obj,fingerprint=context(request.user,draft.kind,draft.target_id,draft.payload)
        stale=fingerprint!=draft.fingerprint
        if draft.kind in {'profile.update','company.update','need.update'} and obj:
            before={key:getattr(obj,key,None) for key in draft.payload if key!='experiences'}
            if 'experiences' in draft.payload:before['experiences']=list(obj.experiences.order_by('pk').values('id','organization','role','months','description'))
        elif draft.kind=='invitation.send':
            from .serializers import need_data,profile_data,company_data
            from assessments.models import Attempt
            from assessments.proofs import witness
            from profiles.models import Profile
            before={'need':need_data(obj),'company':dict(company_data(obj.company)['company'],contact_email=obj.company.contact_email),
                'candidate':profile_data(Profile.objects.get(pk=draft.payload['candidate_id'])),
                'accepted_results':[witness(item) for item in Attempt.objects.filter(pk__in=draft.payload['accepted_attempts']).order_by('pk')]}
        elif draft.kind.startswith('invitation.'):
            from .serializers import invitation_data
            before=invitation_data(obj)
        elif draft.kind in {'profile.publish','profile.unpublish'}:before={'published':obj.published}
    except (Http404,ApiError):
        stale=True
    can_apply=draft.status=='pending' and draft.expires_at>timezone.now() and not stale
    state='expired' if draft.status=='pending' and draft.expires_at<=timezone.now() else draft.status
    response=render(request,'api/draft.html',{'draft':draft,'state':state,'form':form,'error':error,'stale':stale,
        'can_apply':can_apply,'before':json.dumps(before,ensure_ascii=False,indent=2),
        'payload':json.dumps(draft.payload,ensure_ascii=False,indent=2)},status=status)
    response['Cache-Control']='no-store'
    return response


@login_required
@require_http_methods(['GET'])
def index(request):
    response=guard(request)
    if response:return response
    return render(request,'api/drafts.html',{'drafts':ActionDraft.objects.filter(user=request.user).order_by('-created_at')[:100]})
