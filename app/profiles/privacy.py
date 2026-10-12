"""Candidate-owned privacy actions and a durable restore fence outside database backups."""
import fcntl
import hashlib
import hmac
import json
import os
import re
from datetime import timedelta
from pathlib import Path
from uuid import UUID
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from accounts.models import User, ApiToken, ConsentEvent
from hiring.models import Invitation, Company
from .models import Profile, Experience, FspLink, PrivacyReceipt
from .conditions import WORK_FORMATS, EMPLOYMENT_TYPES, TASK_TYPES, codes, preferences

PRIVACY_FORMAT_VERSION = 2

ACTIONS={'revoke_company','revoke_all','clear_profile','delete_account'}
LEDGER_ACTIONS=ACTIONS|{'revoke_challenge'}


class PrivacyUnavailable(RuntimeError):
    pass


def identity(user):
    value=json.dumps([user.pk,user.username,user.email],ensure_ascii=False,separators=(',',':'))
    return hmac.new(settings.SECRET_KEY.encode(),value.encode(),hashlib.sha256).hexdigest()


def ledger_records():
    path=Path(settings.PRIVACY_LEDGER_PATH)
    try:
        floor=path.parent/'privacy-floor-v1'
        if floor.exists() and int(floor.read_text().strip())>PRIVACY_FORMAT_VERSION:
            raise ValueError('Privacy format downgrade')
        if not path.exists():return []
        with path.open('r') as stream:
            fcntl.flock(stream,fcntl.LOCK_SH)
            records=[json.loads(line) for line in stream if line.strip()]
        for row in records:
            if not isinstance(row,dict):raise ValueError('Invalid record type')
            expected={'id','user_id','identity','action','company_id','created_at'}
            if row.get('action')=='revoke_challenge':expected|={'challenge_id','challenge_nonce'}
            if set(row)!=expected:raise ValueError('Invalid shape')
            if not isinstance(row['id'],str) or str(UUID(row['id']))!=row['id']:raise ValueError('Invalid UUID')
            if row['action'] not in LEDGER_ACTIONS or type(row['user_id']) is not int or row['user_id']<=0:raise ValueError('Invalid action')
            if row['action']=='revoke_challenge':
                if type(row['challenge_id']) is not int or row['challenge_id']<=0:raise ValueError('Invalid challenge')
                if not isinstance(row['challenge_nonce'],str) or str(UUID(row['challenge_nonce']))!=row['challenge_nonce']:raise ValueError('Invalid challenge nonce')
            if not isinstance(row['identity'],str) or not re.fullmatch('[0-9a-f]{64}',row['identity']):raise ValueError('Invalid identity')
            if row['company_id'] is not None and (type(row['company_id']) is not int or row['company_id']<=0):raise ValueError('Invalid company')
            created=parse_datetime(row['created_at'])
            if created is None or timezone.is_naive(created):raise ValueError('Invalid timestamp')
        return records
    except (OSError,ValueError,TypeError,KeyError) as exc:
        raise PrivacyUnavailable('Privacy recovery ledger unavailable') from exc


def append_ledger(row):
    path=Path(settings.PRIVACY_LEDGER_PATH)
    try:
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        floor=path.parent/'privacy-floor-v1'
        with os.fdopen(os.open(floor,os.O_RDWR|os.O_CREAT,0o600),'r+') as marker:
            fcntl.flock(marker,fcntl.LOCK_EX)
            existing=marker.read().strip()
            version=max(PRIVACY_FORMAT_VERSION,int(existing) if existing else 0)
            marker.seek(0);marker.write(str(version)+'\n');marker.truncate();marker.flush();os.fsync(marker.fileno());os.fchmod(marker.fileno(),0o600)
        with os.fdopen(os.open(path,os.O_RDWR|os.O_CREAT,0o600),'r+') as stream:
            fcntl.flock(stream,fcntl.LOCK_EX)
            existing=[json.loads(line) for line in stream if line.strip()]
            for previous in existing:
                if not isinstance(previous,dict):raise ValueError('Invalid record type')
                if previous['id']==row['id']:
                    if any(previous.get(key)!=row.get(key) for key in ['user_id','identity','action','company_id','challenge_id','challenge_nonce']):
                        raise ValidationError('Идентификатор запроса уже используется.')
                    return previous
            stream.seek(0,os.SEEK_END);stream.write(json.dumps(row,separators=(',',':'))+'\n')
            stream.flush();os.fsync(stream.fileno());os.fchmod(stream.fileno(),0o600)
        # Fsync the parent as well: a newly created ledger must survive a process/host restart.
        descriptor=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(descriptor)
        finally:os.close(descriptor)
        return row
    except (OSError,ValueError,KeyError) as exc:
        raise PrivacyUnavailable('Privacy request could not be recorded durably') from exc


def safe_snapshot(invitation,erase=False):
    old=invitation.snapshot if isinstance(invitation.snapshot,dict) else {}
    work=old.get('work_format_code')
    if not isinstance(work,str) or work not in dict(WORK_FORMATS):
        work=next((key for key,label in WORK_FORMATS if old.get('work_format') in (key,label)), '')
    employment=old.get('employment_type')
    if not isinstance(employment,str) or employment not in dict(EMPLOYMENT_TYPES):employment=''
    candidate=old.get('candidate_preferences',{})
    if not isinstance(candidate,dict) or erase:candidate={}
    return {'company':f'Компания #{invitation.company_id}','company_email':'','company_description':'','company_industry':'',
        'title':f'Предложение #{invitation.pk}','grade':old.get('grade') if old.get('grade') in ('Junior','Middle') else '',
        'salary_min':old.get('salary_min') if type(old.get('salary_min')) is int else None,
        'salary_max':old.get('salary_max') if type(old.get('salary_max')) is int else None,
        'work_format_code':work,'work_format':dict(WORK_FORMATS).get(work,''),'employment_type':employment,
        'task_types':codes(old.get('task_types'),TASK_TYPES),
        'candidate_preferences':{'work_formats':codes(candidate.get('work_formats'),WORK_FORMATS),
            'employment_types':codes(candidate.get('employment_types'),EMPLOYMENT_TYPES),'task_types':codes(candidate.get('task_types'),TASK_TYPES)},
        'conditions_version':'conditions-v1','tasks':'','next_step':'','discussion':'','accepted_results':[],
        'privacy_redacted':True}


def remove_related_drafts(profile):
    from api.models import ActionDraft
    ids=list(Invitation.objects.filter(candidate=profile).values_list('pk',flat=True))
    ActionDraft.objects.filter(kind='invitation.send',payload__candidate_id=profile.pk).delete()
    ActionDraft.objects.filter(kind__in=['invitation.accept','invitation.decline'],target_id__in=ids).delete()
    ActionDraft.objects.filter(user=profile.user).delete()
    from assistant.models import Draft,Usage
    Draft.objects.filter(user=profile.user).delete();Usage.objects.filter(user=profile.user).delete()


def archive_profile_links(profile,at=None):
    """Also a pre_delete invariant for administrator/cascade deletion, not just the web route."""
    now=at or timezone.now()
    from hiring.challenges import erase_for_profile
    erase_for_profile(profile,now)
    remove_related_drafts(profile)
    for invitation in Invitation.objects.filter(candidate=profile):
        invitation.snapshot=safe_snapshot(invitation,erase=True)
        invitation.candidate=None;invitation.candidate_erased_at=now
        invitation.contact_revoked_at=invitation.contact_revoked_at or now
        invitation.save(update_fields=['snapshot','candidate','candidate_erased_at','contact_revoked_at'])


def revoke(profile,company_id=None,cutoff=None):
    cutoff=cutoff or timezone.now()
    query=Invitation.objects.filter(candidate=profile,created_at__lte=cutoff)
    if company_id is not None:query=query.filter(company_id=company_id)
    count=0
    for invitation in query:
        # A deliberate later acceptance is a new grant; a restored old receipt must not revoke it.
        if invitation.responded_at and invitation.responded_at>cutoff:continue
        from hiring.challenges import revoke_for_invitation
        revoke_for_invitation(invitation,cutoff)
        if invitation.status=='accepted' and invitation.contact_revoked_at is None:
            invitation.contact_revoked_at=cutoff;count+=1
        invitation.snapshot=safe_snapshot(invitation)
        invitation.save(update_fields=['snapshot','contact_revoked_at'])
    return count


def privacy_holds(profile,at=None):
    from assessments.models import Attempt
    now=timezone.now();holds={};variants={};retained_until=None
    if isinstance(profile.user.assessment_privacy_holds,dict):
        for key,value in profile.user.assessment_privacy_holds.items():
            if key=='change_from':continue
            if key not in {'change','Junior','Middle'} or not isinstance(value,str):continue
            parsed=parse_datetime(value)
            if parsed and timezone.is_aware(parsed) and parsed>now:holds[key]=parsed
    previous=profile.user.assessment_privacy_holds
    if isinstance(previous,dict):
        raw=previous.get('variant_until')
        retained_until=parse_datetime(raw) if isinstance(raw,str) else None
        values=previous.get('variants',{})
        from assessments.bank import VERSION
        if retained_until and timezone.is_aware(retained_until) and retained_until>now and previous.get('variant_bank')==VERSION and isinstance(values,dict):
            variants={k:v for k,v in values.items() if k in {'Junior','Middle'} and v in {'A','B'}}
        else:retained_until=None
    new_variant=False
    change_from=profile.confirmed_grade or (profile.user.assessment_privacy_holds.get('change_from') if isinstance(profile.user.assessment_privacy_holds,dict) else '')
    if profile.grade_changed_at and profile.grade_changed_at+timedelta(days=30)>now:
        holds['change']=max(holds.get('change',now),profile.grade_changed_at+timedelta(days=30))
    for active in Attempt.objects.filter(candidate=profile,status='active'):
        if active.variant in {'A','B'}:variants[active.grade]=active.variant;new_variant=True
        until=(at or now)+timedelta(days=7)
        if until>now:holds[active.grade]=max(holds.get(active.grade,now),until)
    for grade in ['Junior','Middle']:
        latest=Attempt.objects.filter(candidate=profile,grade=grade,status='finished').order_by('-finished_at').first()
        if latest and latest.variant in {'A','B'}:variants[grade]=latest.variant;new_variant=True
        if latest and latest.finished_at and latest.finished_at+timedelta(days=7)>now:
            holds[grade]=max(holds.get(grade,now),latest.finished_at+timedelta(days=7))
    result={key:value.isoformat() for key,value in holds.items()}
    if 'change' in holds and change_from in {'Junior','Middle'}:result['change_from']=change_from
    variant_until=(at or now)+timedelta(days=30) if new_variant else (retained_until or now)
    if variants and variant_until>now:
        from assessments.bank import VERSION
        result.update(variants=variants,variant_until=variant_until.isoformat(),variant_bank=VERSION)
    return result


def clear(profile,at=None):
    from assessments.models import Attempt,LessonProgress,PracticeSession
    user=profile.user;holds=privacy_holds(profile,at)
    archive_profile_links(profile,at)
    Experience.objects.filter(profile=profile).delete();FspLink.objects.filter(profile=profile).delete()
    Attempt.objects.filter(candidate=profile).delete();LessonProgress.objects.filter(candidate=profile).delete()
    PracticeSession.objects.filter(candidate=profile).delete();ApiToken.objects.filter(user=user).delete()
    blank=Profile(user=user)
    for field in Profile._meta.concrete_fields:
        if field.name not in {'id','user'}:setattr(profile,field.attname,getattr(blank,field.attname))
    profile.save()
    ConsentEvent.objects.filter(user=user,purpose='publication').delete()
    ConsentEvent.objects.create(user=user,purpose='publication',version='publication-v1',granted=False,source='privacy_clear')
    user.session_generation+=1;user.assessment_privacy_holds=holds
    user.first_name='';user.last_name=''
    user.save(update_fields=['session_generation','assessment_privacy_holds','first_name','last_name'])
    return user


def apply_record(row):
    with transaction.atomic():
        if PrivacyReceipt.objects.filter(pk=row['id']).exists():return False
        user=User.objects.filter(pk=row['user_id'],role='candidate').first()
        actor=None
        if user and hmac.compare_digest(identity(user),row['identity']):
            actor=user
            profile=Profile.objects.filter(user=user).first()
            if row['action']=='revoke_challenge':
                from hiring.models import GapChallenge
                from hiring.challenges import revoke_one
                obj=GapChallenge.objects.filter(pk=row['challenge_id'],request_id=row['challenge_nonce'],candidate__user=user).first()
                if obj:revoke_one(obj,parse_datetime(row['created_at']))
            elif row['action'] in {'clear_profile','delete_account'}:
                if profile:clear(profile,parse_datetime(row['created_at']))
                if row['action']=='delete_account':
                    user.delete();actor=None
            elif profile:
                revoke(profile,row['company_id'] if row['action']=='revoke_company' else None,parse_datetime(row['created_at']))
        PrivacyReceipt.objects.create(id=row['id'],actor=actor,action=row['action'],
            created_at=parse_datetime(row['created_at']),applied_at=timezone.now())
    return True


def reconcile():
    """Called before request dispatch/startup: rollback/restore cannot re-open old grants."""
    for row in ledger_records():
        if not PrivacyReceipt.objects.filter(pk=row['id']).exists():apply_record(row)


def request_action(user,action,request_id,company_id=None):
    if user.role!='candidate' or not user.is_active:raise ValidationError('Действие недоступно.')
    if action not in ACTIONS:raise ValidationError('Неизвестное действие.')
    try:request_id=str(UUID(str(request_id)))
    except (ValueError,TypeError):raise ValidationError('Недопустимый идентификатор запроса.')
    if action=='delete_account' and Company.objects.filter(user=user).exists():
        raise ValidationError('Аккаунт с данными компании требует отдельного удаления компании.')
    profile=Profile.objects.filter(user=user).first()
    if not profile and action!='delete_account':return False
    if action=='revoke_company' and not Invitation.objects.filter(candidate=profile,company_id=company_id).exists():
        from django.http import Http404
        raise Http404
    if action.startswith('revoke'):
        query=Invitation.objects.filter(candidate=profile,status='accepted',contact_revoked_at__isnull=True)
        if action=='revoke_company':query=query.filter(company_id=company_id)
        if not query.exists():return False
    row={'id':request_id,'user_id':user.pk,'identity':identity(user),'action':action,
         'company_id':company_id if action=='revoke_company' else None,'created_at':timezone.now().isoformat()}
    row=append_ledger(row)
    return apply_record(row)


def status_data(user):
    from api.serializers import label
    profile=Profile.objects.filter(user=user).first()
    invitations=Invitation.objects.filter(candidate=profile,status='accepted',contact_revoked_at__isnull=True) if profile else Invitation.objects.none()
    company_ids=invitations.values_list('company_id',flat=True).distinct()
    return {'published':bool(profile and profile.published),'companies':[{'id':company.pk,'name':label(company.name,f'Компания #{company.pk}'),
        'accepted_grants':invitations.filter(company=company).count()} for company in Company.objects.filter(pk__in=company_ids).order_by('pk')],
        'actions_in_browser_only':True,'archive_retention_days':settings.PRIVACY_ARCHIVE_DAYS,
        'backup_retention_days':settings.PRIVACY_BACKUP_DAYS,'saved_copies_revocable':False}
