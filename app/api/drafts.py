"""Immutable action preparation. Application is exposed only to CSRF-protected web sessions."""
import hashlib,json
from datetime import timedelta
from django import forms
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from accounts.models import User,ConsentEvent
from accounts.consents import PUBLICATION_VERSION
from accounts.identifiers import parse_identifier
from profiles.models import Profile,Experience
from profiles.forms import ProfileForm
from hiring.models import Company,Need,Invitation
from hiring.forms import CompanyForm,NeedForm
from hiring.access import company_read,owned_need,invitation_query
from hiring.services import invite,decide
from assessments.models import Attempt
from assessments.proofs import witness
from .models import ActionDraft
from .core import require,ApiError
from .serializers import label

CANDIDATE_KINDS={'profile.update','profile.publish','profile.unpublish','invitation.accept','invitation.decline'}
EMPLOYER_KINDS={'company.update','need.create','need.update','invitation.send'}
PROFILE_FIELDS=set(ProfileForm.Meta.fields)-{'published'}
COMPANY_FIELDS=set(CompanyForm.Meta.fields)
NEED_FIELDS=set(NeedForm.Meta.fields)
PRIVATE_FIELDS={'contact_email','contact_phone','experiences'}


class NeedDraftForm(NeedForm):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields.pop('company_name');self.fields.pop('company_email')


class ExperienceInput(forms.ModelForm):
    class Meta:
        model=Experience
        fields=['organization','role','months','description']


def clean_form(form,keys):
    if not form.is_valid():
        raise ApiError(400,'INVALID_DRAFT','Проверьте поля черновика.',{key:['Недопустимое значение.'] for key in form.errors})
    return {key:form.cleaned_data[key] for key in keys}


def model_state(obj):
    if obj is None:return None
    return {f.attname:getattr(obj,f.attname) for f in obj._meta.concrete_fields}


def checked_actor(user,kind):
    require(user.is_active and user.email_confirmed and user.has_processing_consent)
    allowed=CANDIDATE_KINDS if user.role=='candidate' else EMPLOYER_KINDS if user.role=='employer' else set()
    require(kind in CANDIDATE_KINDS|EMPLOYER_KINDS,400,'INVALID_KIND','Неизвестное действие.')
    require(kind in allowed,403,'FORBIDDEN','Действие недоступно для вашей роли.')


def context(user,kind,target,payload):
    checked_actor(user,kind)
    if kind.startswith('profile.'):
        obj=get_object_or_404(Profile,user=user)
        if target is not None:require(target==obj.pk,404,'NOT_FOUND','Объект не найден.')
        state={'profile':model_state(obj),'experiences':list(obj.experiences.order_by('pk').values())}
    elif kind=='company.update':
        obj=company_read(user)
        if target is not None:require(obj is not None and target==obj.pk,404,'NOT_FOUND','Объект не найден.')
        state=model_state(obj)
    elif kind in {'need.create','need.update'}:
        company=company_read(user)
        require(company is not None,409,'COMPANY_REQUIRED','Сначала создайте компанию.')
        obj=owned_need(user,target) if kind=='need.update' else None
        state={'company':model_state(company),'need':model_state(obj)}
    elif kind=='invitation.send':
        obj=owned_need(user,target)
        profile=get_object_or_404(Profile,pk=parse_identifier(payload.get('candidate_id')),published=True,confirmed_grade=obj.grade)
        attempts=list(Attempt.objects.filter(pk__in=payload.get('accepted_attempts',[]),candidate=profile,status='finished',grade=obj.grade).order_by('pk'))
        require(len(attempts)==len(payload.get('accepted_attempts',[])),400,'INVALID_PROOFS','Свидетельства недоступны.')
        state={'company':model_state(obj.company),'need':model_state(obj),'candidate':model_state(profile),
            'proofs':[witness(p) for p in attempts],
            'existing_invitation':list(Invitation.objects.filter(need=obj,candidate=profile).values('id','status'))}
    else:
        obj=get_object_or_404(invitation_query(user),pk=target)
        state={'id':obj.pk,'status':obj.status,'snapshot':obj.snapshot,'responded_at':obj.responded_at}
    fingerprint=hashlib.sha256(json.dumps(state,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
    return obj,fingerprint


def clean_payload(user,kind,target,payload,source,scopes):
    require(isinstance(payload,dict),400,'INVALID_DRAFT','payload должен быть объектом.')
    if kind in {'profile.publish','profile.unpublish','invitation.accept','invitation.decline'}:
        require(not payload,400,'INVALID_DRAFT','Действие не принимает поля.')
    if source=='mcp':
        require(not (PRIVATE_FIELDS & set(payload)),400,'PRIVATE_FIELDS','MCP не принимает контактные поля или подробный опыт.')
    elif PRIVATE_FIELDS & set(payload):
        require('contacts.read' in scopes)
    if kind=='profile.update':
        require(bool(payload) and set(payload)<=PROFILE_FIELDS|{'experiences'},400,'INVALID_FIELDS','Недопустимые поля профиля.')
        obj,_=context(user,kind,target,payload)
        values={key:getattr(obj,key) for key in ProfileForm.Meta.fields}
        values.update({k:v for k,v in payload.items() if k!='experiences'})
        clean=clean_form(ProfileForm(values,instance=obj),set(payload)-{'experiences'})
        if 'experiences' in payload:
            values=payload['experiences']
            require(isinstance(values,list) and len(values)<=20,400,'INVALID_EXPERIENCE','Не более 20 записей опыта.')
            result=[];seen=set()
            for row in values:
                require(isinstance(row,dict) and set(row)<={'id','organization','role','months','description'},400,'INVALID_EXPERIENCE','Недопустимые поля опыта.')
                identifier=parse_identifier(row.get('id'),required=False)
                if identifier:
                    get_object_or_404(Experience,pk=identifier,profile=obj)
                    require(identifier not in seen,400,'INVALID_EXPERIENCE','Повтор ID опыта.')
                    seen.add(identifier)
                item=clean_form(ExperienceInput(row),set(ExperienceInput.Meta.fields))
                result.append(dict(item,id=identifier))
            clean['experiences']=result
        return clean
    if kind=='company.update':
        require(bool(payload) and set(payload)<=COMPANY_FIELDS,400,'INVALID_FIELDS','Недопустимые поля компании.')
        obj=company_read(user) or Company(user=user)
        values={key:getattr(obj,key) for key in CompanyForm.Meta.fields};values.update(payload)
        return clean_form(CompanyForm(values,instance=obj),set(payload))
    if kind in {'need.create','need.update'}:
        require(bool(payload) and set(payload)<=NEED_FIELDS,400,'INVALID_FIELDS','Недопустимые поля потребности.')
        obj=owned_need(user,target) if kind=='need.update' else Need(company=company_read(user))
        values={key:getattr(obj,key) for key in NeedForm.Meta.fields};values.update(payload)
        return clean_form(NeedDraftForm(values,instance=obj),set(payload) if kind=='need.update' else NEED_FIELDS)
    if kind=='invitation.send':
        require(set(payload)<={'candidate_id','accepted_attempts','discussion'} and 'candidate_id' in payload,400,'INVALID_FIELDS','Недопустимые поля приглашения.')
        ids=payload.get('accepted_attempts',[])
        require(isinstance(ids,list) and len(ids)<=20,400,'INVALID_PROOFS','Не более 20 свидетельств.')
        ids=[parse_identifier(v) for v in ids]
        require(len(set(ids))==len(ids),400,'INVALID_PROOFS','Повтор свидетельства.')
        discussion=payload.get('discussion','')
        require(isinstance(discussion,str) and len(discussion)<=2000,400,'INVALID_DRAFT','Обсуждение до 2000 символов.')
        return {'candidate_id':parse_identifier(payload['candidate_id']),'accepted_attempts':ids,'discussion':discussion.strip()}
    return {}


def prepare(user,token,kind,target,payload):
    checked_actor(user,kind)
    require(f'{user.role}.draft' in token.scopes)
    if kind in {'need.update','invitation.send','invitation.accept','invitation.decline'}:
        target=parse_identifier(target)
    else:
        target=parse_identifier(target,required=False)
    require(kind!='need.create' or target is None,400,'INVALID_TARGET','Создание не принимает target_id.')
    # fingerprint before ModelForm validation mutates an in-memory model instance.
    with transaction.atomic():
        if kind=='invitation.send':
            payload=clean_payload(user,kind,target,payload,token.kind,token.scopes)
        obj,fingerprint=context(user,kind,target,payload)
        clean=clean_payload(user,kind,target,payload,token.kind,token.scopes)
        if kind=='invitation.send':
            require(not Invitation.objects.filter(need=obj,candidate_id=clean['candidate_id']).exists(),409,'ALREADY_INVITED','Предложение уже существует.')
            require(bool(obj.company.contact_email),400,'COMPANY_CONTACT_REQUIRED','Заполните контакт компании через веб.')
        if kind=='profile.publish':
            require(bool(obj.name),400,'PROFILE_INCOMPLETE','Для публикации заполните имя.')
        return ActionDraft.objects.create(user=user,kind=kind,target_id=obj.pk if obj else None,payload=clean,
            source=token.kind,fingerprint=fingerprint,expires_at=timezone.now()+timedelta(hours=24))


def get_draft(user,identifier):
    from uuid import UUID
    try:key=UUID(str(identifier))
    except (ValueError,TypeError,AttributeError):raise ApiError(404,'NOT_FOUND','Черновик не найден.')
    return get_object_or_404(ActionDraft,pk=key,user=user)


def draft_data(draft,mcp=False,private=False):
    effective='expired' if draft.status=='pending' and draft.expires_at<=timezone.now() else draft.status
    data={'id':str(draft.pk),'kind':draft.kind,'target_id':draft.target_id,'status':effective,
        'source':draft.source,'expires_at':draft.expires_at.isoformat(),'created_at':draft.created_at.isoformat(),
        'approval_path':f'/drafts/{draft.pk}/','applied_target_id':draft.applied_target_id,
        'fields':sorted(draft.payload)}
    if not mcp:data['payload']={k:v for k,v in draft.payload.items() if private or k not in PRIVATE_FIELDS|{'description'}}
    else:
        # No private payload or free text, even for a draft originally created through CLI.
        allowed={'city','name','title','grade','desired_grade','specialization','experience_months','roles','soft_skills',
            'skills','salary_min','salary_max','work_format','candidate_id','accepted_attempts'}
        preview={k:v for k,v in draft.payload.items() if k in allowed}
        for key in ['city','name','title']:
            if key in preview:preview[key]=label(preview[key],'Смотрите в веб-кабинете')
        data['preview']=preview
    return data


def cancel(user,draft):
    with transaction.atomic():
        draft=get_draft(user,draft.pk)
        require(draft.status in {'pending','cancelled'},409,'DRAFT_FINAL','Черновик уже применён.')
        if draft.status=='pending':
            draft.status='cancelled';draft.save(update_fields=['status'])
    return draft
