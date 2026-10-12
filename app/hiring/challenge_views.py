from datetime import timedelta
from uuid import uuid4
from functools import wraps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError,PermissionDenied
from django.http import Http404
from django.shortcuts import render,redirect,get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods,require_safe
from accounts.access import role_required
from .models import Invitation,GapChallenge
from . import challenges
from .challenge_forms import ChallengeOfferForm,ChallengeActionForm,ChallengeReviewForm


def both_roles(view):
    @login_required
    @wraps(view)
    def wrapped(request,*args,**kwargs):
        if request.user.role not in {'candidate','employer'} or not request.user.email_confirmed:raise PermissionDenied
        if not request.user.has_processing_consent:return redirect('consent')
        return view(request,*args,**kwargs)
    return wrapped


def presentation(obj,user):
    state=challenges.effective_state(obj)
    company_body=user.role=='employer' and challenges.contents_open(obj)
    company_answer=user.role=='employer' and challenges.share_open(obj)
    candidate_body=user.role=='candidate' and not obj.candidate_erased_at
    details=candidate_body or company_body
    return {'obj':obj,'state':state,'state_label':dict(GapChallenge.STATES).get(state,state),
        'show_details':details,'show_answer':candidate_body or (company_answer and obj.state in {'submitted','reviewed'}),
        'show_result':(candidate_body or company_answer) and obj.reviewed_at is not None,'result':challenges.result(obj) if candidate_body or company_answer else None,
        'due':challenges.due_at(obj),'can_revoke':user.role=='candidate' and obj.state in {'accepted','submitted','reviewed'} and obj.consent_revoked_at is None,
        'can_credit':user.role=='employer' and state=='reviewed' and bool(challenges.result(obj)['sufficient']) and not obj.credited_at}


@both_roles
@require_safe
def index(request):
    challenges.actor(request.user)
    rows=challenges.own_query(request.user).order_by('-created_at','-pk')
    return render(request,'hiring/challenges.html',{'items':[presentation(obj,request.user) for obj in rows]})


@role_required('employer')
@require_http_methods(['GET','POST'])
def offer(request,pk):
    invitation=get_object_or_404(Invitation.objects.select_related('candidate','need','company'),pk=pk,company__user=request.user)
    if not challenges.invitation_open(invitation):
        return render(request,'hiring/challenge_offer.html',{'closed':True,'invitation':invitation},status=409)
    initial={'request_id':uuid4(),'deadline_at':timezone.localtime(timezone.now()+timedelta(days=7)).replace(second=0,microsecond=0),
        'duration_minutes':15,'pass_points':3,'criteria':'Решение соответствует описанному случаю\nПояснены ограничения и проверка решения'}
    form=ChallengeOfferForm(request.POST if request.method=='POST' else None,invitation=invitation,initial=initial)
    status=200
    if request.method=='POST':
        if form.is_valid():
            try:
                values={key:value for key,value in form.cleaned_data.items() if key!='acknowledge'}
                obj,created=challenges.send(request.user,invitation.pk,**values)
            except challenges.ChallengeConflict as error:form.add_error(None,error);status=409
            except ValidationError as error:form.add_error(None,error);status=400
            else:
                messages.success(request,'Задание отправлено. Условия зафиксированы.' if created else 'Это задание уже отправлено; прежние условия сохранены.')
                return redirect('challenge-detail',pk=obj.pk)
        else:status=400
    return render(request,'hiring/challenge_offer.html',{'form':form,'invitation':invitation},status=status)


@both_roles
@require_http_methods(['GET','POST'])
def detail(request,pk):
    challenges.actor(request.user);obj=challenges.owned(request.user,pk);status=200;bound=None
    if request.method=='POST':
        kind=request.POST.get('action')
        if (kind in {'review','credit','withdraw'} and request.user.role!='employer') or (kind in {'accept','decline','save','submit','revoke'} and request.user.role!='candidate'):
            raise PermissionDenied
        bound=ChallengeReviewForm(request.POST,challenge=obj) if request.POST.get('action')=='review' else ChallengeActionForm(request.POST)
        if bound.is_valid():
            try:
                values=bound.cleaned_data
                if values['action']=='review':
                    challenges.review(request.user,pk,revision=values['revision'],scores=bound.scores(obj),note=values['note'],
                        credit=values['credit'],acknowledge=values['acknowledge'])
                else:
                    challenges.action(request.user,pk,values['action'],revision=values['revision'],
                        answer=values.get('answer',''),acknowledge=values['acknowledge'])
            except challenges.ChallengeConflict as error:bound.add_error(None,error);status=409
            except ValidationError as error:bound.add_error(None,error);status=400
            else:return redirect('challenge-detail',pk=pk)
        else:status=400
    obj=challenges.owned(request.user,pk)
    data=presentation(obj,request.user)
    data.update(errors=bound,answer_form=ChallengeActionForm(initial={'action':'save','revision':obj.revision,'answer':obj.answer}),
        review_form=ChallengeReviewForm(challenge=obj,initial={'revision':obj.revision}))
    return render(request,'hiring/challenge_detail.html',data,status=status)
