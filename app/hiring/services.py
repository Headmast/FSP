from django.db import transaction
from django.utils import timezone
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from profiles.models import Profile
from profiles.skills import normalized,canonical_skill
from .models import Company,Need,Invitation
from assessments.models import Attempt
from assessments.proofs import witness


class InvalidProof(ValueError):
    pass


def explain(profile,need=None):
    desired=normalized(need.skills) if need else set()
    declared=normalized(profile.skills)
    result=Attempt.objects.filter(candidate=profile,status='finished',passed=True,grade=profile.confirmed_grade).order_by('-finished_at','-pk').first()
    unknown=['Опыт, роли и софт-скиллы указаны кандидатом; независимой проверки нет.']
    if desired:unknown.append('Совпадение заявленных навыков не означает отдельную проверку каждого инструмента.')
    else:unknown.append('Потребность с конкретными навыками не выбрана.')
    if not result:unknown.append('Для указанной категории нет сохранённого свидетельства успешного теста.')
    if profile.fsp_status=='not_connected':unknown.append('FSP ID не привязан; история неизвестна.')
    elif profile.fsp_status=='unavailable':unknown.append('Источник ФСП недоступен; история неизвестна.')
    elif profile.fsp_status=='no_history':unknown.append('Демо источник ФСП вернул отсутствие истории.')
    else:unknown.append('Достижения ФСП синтетические; реестр не проверялся.')
    return {'declared_matches':[canonical_skill(s) for s in sorted(desired&declared)],
        'declared_gaps':[canonical_skill(s) for s in sorted(desired-declared)],
        'confirmation':witness(result) if result else None,'unknown':unknown}

def rank(profile,need=None):
    desired=normalized(need.skills) if need else set()
    matches=len(normalized(profile.skills)&desired)/len(desired) if desired else 0
    fsp=(3+2*int(profile.fsp_prize)) if profile.fsp_status=='demo_history' else 0
    parts={'test':85*profile.test_score,'skills':10*matches,'fsp':fsp}
    return round(sum(parts.values()),2),parts

def search(grade,need=None,skill='',fsp=''):
    profiles=Profile.objects.filter(published=True,confirmed_grade=grade).order_by('pk')
    if fsp=='demo_history':profiles=profiles.filter(fsp_status='demo_history')
    elif fsp=='no_history':profiles=profiles.filter(fsp_status='no_history')
    results=[]
    for p in profiles:
        if skill and not normalized(skill).issubset(normalized(p.skills)):continue
        score,parts=rank(p,need)
        results.append({'id':p.pk,'name':p.name,'city':p.city,'skills':p.skills,'grade':p.confirmed_grade,
            'test_score':p.test_score,'fsp_status':p.fsp_status,'score':score,'parts':parts,'explanation':explain(p,need)})
    return sorted(results,key=lambda row:(-row['score'],-row['test_score'],row['id']))

def contacts_allowed(company,profile):
    return Invitation.objects.filter(company=company,candidate=profile,status='accepted').exists()

def invite(company,need_id,candidate_id,accepted_ids=(),discussion=''):
    with transaction.atomic():
        need=Need.objects.get(pk=need_id,company=company)
        profile=Profile.objects.get(pk=candidate_id,published=True,confirmed_grade=need.grade)
        existing=Invitation.objects.filter(company=company,need=need,candidate=profile).first()
        if existing:return existing
        ids=set(accepted_ids)
        if len(accepted_ids)>20 or len(discussion)>2000:raise InvalidProof('Слишком много результатов или слишком длинный текст.')
        attempts=list(Attempt.objects.filter(pk__in=ids,candidate=profile,status='finished',grade=need.grade).order_by('pk'))
        if len(attempts)!=len(ids):raise InvalidProof('Можно зачесть только завершённые результаты этого кандидата и категории.')
        company=Company.objects.get(pk=company.pk)
        if not company.contact_email:raise ValidationError('Укажите контакт компании.')
        validate_email(company.contact_email)
        snapshot={'company':company.name,'company_email':company.contact_email,
            'company_description':company.description,'company_industry':company.industry,'title':need.title,'grade':need.grade,
            'tasks':need.tasks,'salary_min':need.salary_min,'salary_max':need.salary_max,
            'work_format':need.get_work_format_display(),'next_step':need.next_step,
            'accepted_results':[witness(attempt) for attempt in attempts],
            'accepted_at':timezone.now().isoformat(),'discussion':discussion.strip()}
        invitation,_=Invitation.objects.get_or_create(company=company,need=need,candidate=profile,defaults={'snapshot':snapshot})
        return invitation

def decide(profile,invitation_id,status):
    if status not in {'accepted','declined'}:raise ValueError('Неверное решение.')
    with transaction.atomic():
        obj=Invitation.objects.get(pk=invitation_id,candidate=profile)
        if obj.status not in {'sent',status}:
            raise ValueError('Решение уже принято; изменить его в этом MVP нельзя.')
        if obj.status=='sent':
            obj.status=status;obj.responded_at=timezone.now();obj.save(update_fields=['status','responded_at'])
        return obj
