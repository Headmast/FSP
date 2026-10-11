from urllib.parse import urlencode
from django.contrib import messages
from django.db import transaction
from django.http import FileResponse,Http404
from django.shortcuts import get_object_or_404,redirect,render
from django.utils import timezone
from django.views.decorators.http import require_http_methods,require_POST,require_safe
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from accounts.access import role_required
from accounts.identifiers import parse_identifier
from profiles.models import Profile
from profiles.views import build_pdf
from .models import Company,Need,Invitation
from .forms import NeedForm,SearchForm,CompanyForm
from .access import visible_profile, invitation_query
from .services import search,contacts_allowed,invite,decide,InvalidProof,explain
from assessments.models import Attempt
from assessments.proofs import witness

def posted_id(request, key):
    return parse_identifier(request.POST.get(key))

def company_for(user):
    return Company.objects.get_or_create(user=user)[0]

@role_required('employer')
@require_http_methods(['GET','POST'])
def company_profile(request):
    company=company_for(request.user)
    form=CompanyForm(request.POST or None,instance=company)
    if request.method=='POST' and form.is_valid():
        form.save();messages.success(request,'Профиль компании сохранён.')
        return redirect('company-profile')
    return render(request,'hiring/company.html',{'form':form,'company':company})

@role_required('employer')
@require_http_methods(['GET','POST'])
def needs(request):
    company=company_for(request.user)
    form=NeedForm(request.POST or None,company=company,initial={'company_name':company.name,'company_email':company.contact_email})
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            company.name=form.cleaned_data['company_name'];company.contact_email=form.cleaned_data['company_email'];company.save()
            obj=form.save(commit=False);obj.company=company;obj.save()
        messages.success(request,'Потребность создана.')
        return redirect('candidates')
    return render(request,'hiring/needs.html',{'form':form,'needs':Need.objects.filter(company=company)})

@role_required('employer')
@require_safe
def candidates(request):
    company=company_for(request.user);data=request.GET.copy()
    default=Need.objects.filter(company=company).order_by('pk').first()
    if not data.get('need') and default:data['need']=str(default.pk)
    identifier=parse_identifier(data.get('need'),required=False)
    chosen=get_object_or_404(Need,company=company,pk=identifier) if identifier else None
    if not data.get('grade'):data['grade']=chosen.grade if chosen else 'Junior'
    form=SearchForm(data,company=company);results=[]
    if form.is_valid():results=search(**form.cleaned_data)
    return render(request,'hiring/candidates.html',{'form':form,'results':results,'query':data.urlencode(),'selected_need':chosen})

@role_required('employer')
@require_safe
def candidate(request,pk):
    company=company_for(request.user);profile,grant=visible_profile(company,pk)
    need_id=parse_identifier(request.GET.get('need'),required=False)
    chosen=get_object_or_404(Need,pk=need_id,company=company) if need_id else Need.objects.filter(company=company,grade=profile.confirmed_grade).order_by('pk').first()
    return render(request,'hiring/candidate.html',{'profile':profile,'grant':grant,
        'needs':Need.objects.filter(company=company,grade=profile.confirmed_grade),'query':request.GET.urlencode(),'explanation':explain(profile,chosen),'chosen_need':chosen,
        'proofs':[witness(item) for item in Attempt.objects.filter(candidate=profile,status='finished',grade=profile.confirmed_grade).order_by('-finished_at')]})

@role_required('employer')
@require_safe
def resume(request,pk):
    profile,grant=visible_profile(company_for(request.user),pk)
    return FileResponse(build_pdf(profile,include_contacts=grant),as_attachment=True,filename='candidate-resume.pdf')

@role_required('employer')
@require_POST
def send(request):
    company=company_for(request.user)
    need=get_object_or_404(Need,pk=posted_id(request,'need'),company=company)
    profile=get_object_or_404(Profile,pk=posted_id(request,'candidate'),published=True,confirmed_grade=need.grade)
    accepted=request.POST.getlist('accepted_attempts')
    if len(accepted)>20:raise Http404
    ids=[parse_identifier(value) for value in accepted]
    try:
        invite(company,need.pk,profile.pk,ids,request.POST.get('discussion',''))
    except (Need.DoesNotExist, Profile.DoesNotExist):
        raise Http404
    except ValidationError:
        messages.error(request,'Перед отправкой заполните корректный email компании для связи.')
        return redirect('company-profile')
    except InvalidProof as exc:
        messages.error(request,str(exc))
        return redirect('candidate',pk=profile.pk)
    messages.success(request,'Предложение отправлено. Повторная отправка не создаёт дубликат.')
    return redirect('invitations')

@login_required
@require_safe
def invitations(request):
    if not request.user.email_confirmed:raise PermissionDenied
    if not request.user.has_processing_consent:return redirect('consent')
    if request.user.role=='candidate':
        profile=get_object_or_404(Profile,user=request.user)
        items=invitation_query(request.user).select_related('candidate')
        items.filter(viewed_at__isnull=True).update(viewed_at=timezone.now())
    elif request.user.role=='employer':items=invitation_query(request.user).select_related('candidate')
    else:raise PermissionDenied
    return render(request,'hiring/invitations.html',{'items':items.order_by('-created_at')})

@role_required('candidate')
@require_POST
def respond(request,pk,status):
    profile=get_object_or_404(Profile,user=request.user)
    get_object_or_404(Invitation,pk=pk,candidate=profile)
    try:decide(profile,pk,status)
    except ValueError as exc:messages.error(request,str(exc))
    return redirect('invitations')
