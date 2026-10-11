from urllib.parse import urlencode
from django.contrib import messages
from django.db import transaction
from django.http import FileResponse,Http404
from django.shortcuts import get_object_or_404,redirect,render
from django.utils import timezone
from django.views.decorators.http import require_http_methods,require_POST
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from accounts.access import role_required
from accounts.identifiers import parse_identifier
from profiles.models import Profile
from profiles.views import build_pdf
from .models import Company,Need,Invitation
from .forms import NeedForm,SearchForm,CompanyForm
from .services import search,contacts_allowed,invite,decide

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
    form=NeedForm(request.POST or None,initial={'company_name':company.name,'company_email':company.contact_email})
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            company.name=form.cleaned_data['company_name'];company.contact_email=form.cleaned_data['company_email'];company.save()
            obj=form.save(commit=False);obj.company=company;obj.save()
        messages.success(request,'Потребность создана.')
        return redirect('candidates')
    return render(request,'hiring/needs.html',{'form':form,'needs':Need.objects.filter(company=company)})

@role_required('employer')
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

def visible_profile(company,pk):
    profile=get_object_or_404(Profile,pk=pk)
    grant=contacts_allowed(company,profile)
    if not grant and not(profile.published and profile.confirmed_grade):raise Http404
    return profile,grant

@role_required('employer')
def candidate(request,pk):
    company=company_for(request.user);profile,grant=visible_profile(company,pk)
    return render(request,'hiring/candidate.html',{'profile':profile,'grant':grant,
        'needs':Need.objects.filter(company=company,grade=profile.confirmed_grade),'query':request.GET.urlencode()})

@role_required('employer')
def resume(request,pk):
    profile,grant=visible_profile(company_for(request.user),pk)
    return FileResponse(build_pdf(profile,include_contacts=grant),as_attachment=True,filename='candidate-resume.pdf')

@role_required('employer')
@require_POST
def send(request):
    company=company_for(request.user)
    need=get_object_or_404(Need,pk=posted_id(request,'need'),company=company)
    profile=get_object_or_404(Profile,pk=posted_id(request,'candidate'),published=True,confirmed_grade=need.grade)
    try:
        invite(company,need.pk,profile.pk)
    except (Need.DoesNotExist, Profile.DoesNotExist):
        raise Http404
    except ValidationError:
        messages.error(request,'Перед отправкой заполните корректный email компании для связи.')
        return redirect('company-profile')
    messages.success(request,'Предложение отправлено. Повторная отправка не создаёт дубликат.')
    return redirect('invitations')

@login_required
def invitations(request):
    if not request.user.email_confirmed:raise PermissionDenied
    if request.user.role=='candidate':
        profile=get_object_or_404(Profile,user=request.user)
        items=Invitation.objects.filter(candidate=profile).select_related('candidate')
        items.filter(viewed_at__isnull=True).update(viewed_at=timezone.now())
    elif request.user.role=='employer':items=Invitation.objects.filter(company=company_for(request.user)).select_related('candidate')
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
