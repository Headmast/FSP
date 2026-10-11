from django.db import transaction
from django.utils import timezone
from profiles.models import Profile
from profiles.skills import normalized
from .models import Need,Invitation

def rank(profile,need=None):
    desired=normalized(need.skills) if need else set()
    matches=len(normalized(profile.skills)&desired)/len(desired) if desired else 0
    fsp=(3+2*int(profile.fsp_prize)) if profile.fsp_status=='demo_history' else 0
    parts={'test':85*profile.test_score,'skills':10*matches,'fsp':fsp}
    return round(sum(parts.values()),2),parts

def search(grade,need=None,skill='',fsp=''):
    profiles=Profile.objects.filter(published=True,confirmed_grade=grade).order_by('pk')
    if fsp=='demo_history':profiles=profiles.filter(fsp_status='demo_history')
    elif fsp=='no_history':profiles=profiles.exclude(fsp_status='demo_history')
    results=[]
    for p in profiles:
        if skill and not normalized(skill).issubset(normalized(p.skills)):continue
        score,parts=rank(p,need)
        results.append({'id':p.pk,'name':p.name,'city':p.city,'skills':p.skills,'grade':p.confirmed_grade,
            'test_score':p.test_score,'fsp_status':p.fsp_status,'score':score,'parts':parts})
    return sorted(results,key=lambda row:(-row['score'],-row['test_score'],row['id']))

def contacts_allowed(company,profile):
    return Invitation.objects.filter(company=company,candidate=profile,status='accepted').exists()

def invite(company,need_id,candidate_id):
    with transaction.atomic():
        need=Need.objects.get(pk=need_id,company=company)
        profile=Profile.objects.get(pk=candidate_id,published=True,confirmed_grade=need.grade)
        snapshot={'company':company.name,'company_email':company.contact_email,'title':need.title,'grade':need.grade,
            'tasks':need.tasks,'salary_min':need.salary_min,'salary_max':need.salary_max,
            'work_format':need.get_work_format_display(),'next_step':need.next_step}
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
