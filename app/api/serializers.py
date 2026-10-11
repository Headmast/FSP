"""Explicit wire projections. No raw snapshots, questions, answer keys or contact-bearing MCP text."""
import re
from profiles.models import ROLES, SOFT_SKILLS
from profiles.skills import SKILLS, canonical_skill
from assessments.proofs import witness
from profiles.conditions import preferences, codes, EMPLOYMENT_TYPES, TASK_TYPES, snapshot_conditions


def label(value, fallback):
    return value if isinstance(value,str) and re.fullmatch(r"[^\W\d_]+(?:[ /-][^\W\d_]+)*", value, re.UNICODE) else fallback


def skills(value):
    return [s for s in dict.fromkeys(canonical_skill(v.strip()) for v in (value or '').split(',')) if s in SKILLS]


def profile_data(obj):
    pref=preferences(obj)
    return {'id':obj.pk, 'name':label(obj.name,f'Кандидат #{obj.pk}'), 'city':label(obj.city,'Не указан'),
        'skills':skills(obj.skills), 'specialization':'ios_swift', 'experience_months':obj.experience_months,
        'roles':[v for v in obj.roles if v in dict(ROLES)], 'soft_skills':[v for v in obj.soft_skills if v in dict(SOFT_SKILLS)],
        'published':obj.published, 'desired_grade':obj.desired_grade, 'confirmed_grade':obj.confirmed_grade,
        'preferred_work_formats':pref['work_formats'],'preferred_employment_types':pref['employment_types'],'preferred_task_types':pref['task_types'],
        'test_score':obj.test_score, 'fsp_status':obj.fsp_status, 'self_declared':['skills','experience_months','roles','soft_skills','preferred_work_formats','preferred_employment_types','preferred_task_types']}


def private_profile(obj):
    return {'id':obj.pk, 'contact_email':obj.contact_email, 'contact_phone':obj.contact_phone,
        'description':obj.description, 'experiences':list(obj.experiences.order_by('pk').values('id','organization','role','months','description'))}


def proof_data(obj):
    return proof_snapshot(witness(obj))


def proof_snapshot(value):
    if not isinstance(value,dict):
        return None
    def version(v):
        return v if isinstance(v,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,40}',v) else 'unknown'
    areas=value.get('areas',{})
    if not isinstance(areas,dict):areas={}
    criteria=value.get('criteria',{})
    if not isinstance(criteria,dict):criteria={}
    return {'attempt_id':value.get('attempt_id') if type(value.get('attempt_id')) is int and 0<value['attempt_id']<2**63 else None, 'specialization':'iOS / Swift',
        'grade':value.get('grade') if value.get('grade') in {'Junior','Middle'} else '',
        'finished_at':value.get('finished_at') if isinstance(value.get('finished_at'),str) and re.fullmatch(r'[0-9T:.+Z-]+',value['finished_at']) else None,
        'bank_version':version(value.get('bank_version')), 'rules_version':version(value.get('rules_version')),
        'variant':value.get('variant') if value.get('variant') in {'A','B'} else None,
        'areas':{k:int(v) for k,v in areas.items() if k in {'Swift','ARC','Async','UI/Data'} and isinstance(v,int)},
        'correct_count':value.get('correct_count') if isinstance(value.get('correct_count'),int) else 0,
        'total':value.get('total') if isinstance(value.get('total'),int) else 0,
        'passed':value.get('passed') is True, 'expired':value.get('expired') is True,
        'criteria':{k:criteria[k] for k in ['min_correct','min_per_area','duration_minutes','question_count'] if isinstance(criteria.get(k),int)},
        'limitations':'Короткий тест без прокторинга; опыт и софт-скиллы не подтверждены. Валидация на реальных людях не проведена.'}


def invitation_data(obj, mcp=False):
    s=obj.snapshot
    result={'id':obj.pk,'candidate_id':obj.candidate_id,'need_id':obj.need_id,'company_id':obj.company_id,
        'company':label(s.get('company'),f'Компания #{obj.company_id}') if mcp else s.get('company'),
        'title':label(s.get('title'),f'Предложение #{obj.pk}') if mcp else s.get('title'),
        'grade':s.get('grade') if s.get('grade') in {'Junior','Middle'} else '',
        'salary_min':s.get('salary_min') if isinstance(s.get('salary_min'),int) else None,
        'salary_max':s.get('salary_max') if isinstance(s.get('salary_max'),int) else None,
        'currency':'RUB','salary_period':'month','salary_tax':'gross',
        'work_format':s.get('work_format') if s.get('work_format') in {'Удалённо','Офис','Гибрид','remote','office','hybrid'} else None,
        'employment_type':s.get('employment_type') if isinstance(s.get('employment_type'),str) and s.get('employment_type') in dict(EMPLOYMENT_TYPES) else '',
        'task_types':codes(s.get('task_types'),TASK_TYPES),'conditions':snapshot_conditions(s),
        'status':obj.status,'created_at':obj.created_at.isoformat(),
        'responded_at':obj.responded_at.isoformat() if obj.responded_at else None,
        'accepted_results':[proof_snapshot(p) for p in s.get('accepted_results',[]) if isinstance(p,dict)]}
    if not mcp:
        result.update({k:s.get(k,'') for k in ['company_description','company_industry','tasks','next_step','discussion']})
    return result


def need_data(obj,mcp=False):
    data={'id':obj.pk,'company_id':obj.company_id,'title':label(obj.title,f'Потребность #{obj.pk}') if mcp else obj.title,
        'grade':obj.grade,'skills':skills(obj.skills),'salary_min':obj.salary_min,'salary_max':obj.salary_max,
        'currency':'RUB','salary_period':'month','salary_tax':'gross','work_format':obj.work_format,
        'employment_type':obj.employment_type if obj.employment_type in dict(EMPLOYMENT_TYPES) else '',
        'task_types':codes(obj.task_types,TASK_TYPES)}
    if not mcp:
        data.update(tasks=obj.tasks,next_step=obj.next_step)
    return data


def company_data(obj,mcp=False):
    if obj is None:
        return {'state':'company_not_created','company':None}
    data={'id':obj.pk,'name':label(obj.name,f'Компания #{obj.pk}') if mcp else obj.name}
    if not mcp:
        data.update(industry=obj.industry,description=obj.description)
    return {'state':'ready','company':data}
