import hashlib
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from profiles.models import Profile
from hiring.models import Company
from hiring.forms import NeedForm
from .forms import ProfileDraftForm
from .models import Draft


def fingerprint(value):return hashlib.sha256(value.encode()).hexdigest()


def create_draft(user,mode,text,context,source_need=None):
    if mode=='profile':
        profile=Profile.objects.get(user=user)
        return Draft.objects.create(user=user,mode=mode,payload={'description':text},
            target_fingerprint=fingerprint(profile.description),expires_at=timezone.now()+timedelta(hours=24))
    payload={'title':f"iOS разработчик · {context['grade']}",'grade':context['grade'],'skills':context['skills'],
        'tasks':text,'salary_min':source_need.salary_min if source_need else None,
        'salary_max':source_need.salary_max if source_need else None,
        'work_format':source_need.work_format if source_need else 'remote',
        'next_step':'Знакомство с командой'}
    return Draft.objects.create(user=user,mode=mode,payload=payload,source_need=source_need,
        expires_at=timezone.now()+timedelta(hours=24))


def form_for(draft,data=None):
    if draft.mode=='profile':return ProfileDraftForm(data,initial=draft.payload)
    company=Company.objects.filter(user=draft.user).first()
    return NeedForm(data,initial={**draft.payload,'company_name':company.name if company else 'Демо компания',
        'company_email':company.contact_email if company else ''})


class StaleDraft(ValueError):pass
class ExpiredDraft(ValueError):pass
class ActiveAssessment(ValueError):pass


@transaction.atomic
def apply_draft(user,draft_id,form):
    draft=Draft.objects.get(pk=draft_id,user=user)
    if draft.mode=='profile':
        from assessments.models import Attempt
        if Attempt.objects.filter(candidate__user=user,status='active').exists():
            raise ActiveAssessment('Помощник недоступен во время активного теста. Сначала завершите попытку.')
    if draft.applied_at:return draft
    if draft.expired:raise ExpiredDraft('Срок черновика истёк. Получите новый или заполните основную форму вручную.')
    if draft.source_need_id and draft.source_need.company.user_id!=user.pk:raise StaleDraft('Источник черновика больше не принадлежит вам.')
    if draft.mode=='profile':
        profile=Profile.objects.get(user=user)
        if fingerprint(profile.description)!=draft.target_fingerprint:
            raise StaleDraft('Описание уже изменено после создания черновика. Получите новый, чтобы не перезаписать изменения.')
        Profile.objects.filter(pk=profile.pk,user=user).update(description=form.cleaned_data['description'])
        draft.payload={'description':form.cleaned_data['description']}
    else:
        company,_=Company.objects.get_or_create(user=user)
        company.name=form.cleaned_data['company_name'];company.contact_email=form.cleaned_data['company_email']
        company.save(update_fields=['name','contact_email'])
        need=form.save(commit=False);need.company=company;need.save()
        draft.applied_need=need
        draft.payload={key:form.cleaned_data[key] for key in ('title','grade','skills','tasks','salary_min','salary_max','work_format','next_step')}
    draft.applied_at=timezone.now();draft.save(update_fields=['payload','applied_at','applied_need'])
    return draft
