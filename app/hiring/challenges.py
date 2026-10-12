"""Explicit consent, immutable terms, private drafts and a company-scoped manual result."""
from datetime import datetime,timedelta
from uuid import UUID,uuid4
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import transaction
from django.db.models import F
from django.http import Http404
from django.utils import timezone
from .models import Company,Invitation,GapChallenge
from .services import contacts_allowed
from profiles.skills import SKILLS,canonical_skill,normalized


class ChallengeConflict(ValidationError):
    pass


def actor(user,role=None):
    if not user.is_active or not user.email_confirmed or not user.has_processing_consent:
        raise PermissionDenied
    if user.role not in {'candidate','employer'} or (role and user.role!=role):raise PermissionDenied


def own_query(user):
    actor(user)
    query=GapChallenge.objects.select_related('candidate__user','company','need','invitation')
    return query.filter(candidate__user=user) if user.role=='candidate' else query.filter(company__user=user)


def owned(user,pk):
    try:return own_query(user).get(pk=pk)
    except GapChallenge.DoesNotExist:raise Http404


def invitation_open(invitation):
    return bool(invitation and invitation.candidate_id and invitation.status=='accepted'
        and invitation.contact_revoked_at is None and invitation.candidate_erased_at is None
        and contacts_allowed(invitation.company,invitation.candidate))


def contents_open(obj):
    return bool(obj.candidate_id and obj.candidate_erased_at is None and obj.consent_revoked_at is None
        and obj.state not in {'revoked','erased'} and invitation_open(obj.invitation))


def share_open(obj):
    return contents_open(obj) and obj.state not in {'declined','withdrawn'}


def due_at(obj):
    return min(obj.deadline_at,obj.accepted_at+timedelta(minutes=obj.duration_minutes)) if obj.accepted_at else obj.deadline_at


def effective_state(obj,now=None):
    if obj.candidate_erased_at or not obj.candidate_id:return 'erased'
    if obj.consent_revoked_at or obj.state=='revoked':return 'revoked'
    if obj.state in {'offered','accepted','submitted','reviewed'} and not invitation_open(obj.invitation):return 'revoked'
    if obj.state in {'offered','accepted'} and (now or timezone.now())>=due_at(obj):return 'expired'
    return obj.state


def result(obj):
    if obj.reviewed_at is None or obj.candidate_erased_at:return None
    points=sum(obj.review_scores)
    return {'points':points,'maximum':2*len(obj.criteria),'threshold':obj.pass_points,'sufficient':points>=obj.pass_points,
        'scores':list(obj.review_scores),'credited':obj.credited_at is not None}


def text(value,limit,label,required=True):
    if not isinstance(value,str):raise ValidationError(f'{label}: ожидается текст.')
    value=value.strip()
    if len(value)>limit or (required and not value):raise ValidationError(f'{label}: заполните значение до {limit} символов.')
    return value


def send(user,invitation_id,*,request_id,skill,title,instructions,criteria,duration_minutes,deadline_at,pass_points):
    actor(user,'employer')
    with transaction.atomic():
        try:invitation=Invitation.objects.select_related('candidate','company','need').get(pk=invitation_id,company__user=user)
        except Invitation.DoesNotExist:raise Http404
        if not invitation_open(invitation):raise ChallengeConflict('Задание доступно только по действующему принятому предложению.')
        try:nonce=UUID(str(request_id))
        except (ValueError,TypeError):raise ValidationError('Некорректный идентификатор отправки.')
        if not isinstance(skill,str):raise ValidationError('Выберите навык этой потребности.')
        skill=canonical_skill(skill)
        if skill not in SKILLS or skill.casefold() not in normalized(invitation.need.skills):
            raise ValidationError('Выберите навык этой потребности.')
        title=text(title,120,'Название');instructions=text(instructions,4000,'Задание')
        if not isinstance(criteria,list) or not 1<=len(criteria)<=5:raise ValidationError('Нужны от одного до пяти критериев.')
        criteria=[text(value,180,'Критерий') for value in criteria]
        if len(set(criteria))!=len(criteria):raise ValidationError('Критерии не должны повторяться.')
        if type(duration_minutes) is not int or not 5<=duration_minutes<=60:raise ValidationError('Бюджет задания: 5–60 минут.')
        if type(pass_points) is not int or not 1<=pass_points<=2*len(criteria):raise ValidationError('Порог должен помещаться в объявленную шкалу.')
        if not isinstance(deadline_at,datetime) or timezone.is_naive(deadline_at):raise ValidationError('Укажите крайний срок с часовым поясом.')
        now=timezone.now()
        if not now<deadline_at<=now+timedelta(days=30):raise ValidationError('Крайний срок должен быть в ближайшие 30 дней.')
        terms=dict(title=title,instructions=instructions,criteria=criteria,duration_minutes=duration_minutes,
            deadline_at=deadline_at,pass_points=pass_points,skill=skill)
        previous=GapChallenge.objects.filter(request_id=nonce).first()
        if previous and (previous.company_id!=invitation.company_id or previous.invitation_id!=invitation.pk):raise Http404
        previous=previous or GapChallenge.objects.filter(invitation=invitation,skill=skill).first()
        if previous:
            if any(getattr(previous,key)!=value for key,value in terms.items()):
                raise ChallengeConflict('Задание уже отправлено. Прежние условия не заменяются; откройте существующее задание.')
            return previous,False
        obj=GapChallenge.objects.create(request_id=nonce,invitation=invitation,candidate=invitation.candidate,
            company=invitation.company,need=invitation.need,
            gap_kind='missing_declared' if skill.casefold() not in normalized(invitation.candidate.skills) else 'unverified_skill',**terms)
        return obj,True


def action(user,pk,kind,*,revision,acknowledge=False,answer=''):
    actor(user)
    with transaction.atomic():
        obj=owned(user,pk);now=timezone.now()
        candidate_action=kind in {'accept','decline','save','submit','revoke'}
        if (candidate_action and user.role!='candidate') or (kind in {'withdraw','credit'} and user.role!='employer'):
            raise PermissionDenied
        if kind not in {'accept','decline','save','submit','revoke','withdraw','credit'}:raise ValidationError('Неизвестное действие.')
        if kind not in {'save','decline'} and acknowledge is not True:raise ValidationError('Подтвердите выбранное действие.')
        if obj.candidate_erased_at or not obj.candidate_id:raise ChallengeConflict('Данные задания очищены.')
        if kind=='revoke':
            if obj.consent_revoked_at:return obj,False
            if obj.state not in {'accepted','submitted','reviewed'}:raise ChallengeConflict('Передача ответа ещё не разрешена.')
            from profiles.privacy import append_ledger,apply_record,identity
            row={'id':str(uuid4()),'user_id':user.pk,'identity':identity(user),'action':'revoke_challenge','company_id':None,
                'challenge_id':obj.pk,'challenge_nonce':str(obj.request_id),'created_at':now.isoformat()}
            row=append_ledger(row);apply_record(row);obj.refresh_from_db()
            return obj,True
        else:
            if kind=='decline' and obj.state=='declined':return obj,False
            if kind=='withdraw' and obj.state=='withdrawn':return obj,False
            if not share_open(obj):raise ChallengeConflict('Доступ к этому заданию закрыт.')
            # Replayed accepted/declined/withdrawn requests cannot restart or replace the decision.
            if kind=='accept' and obj.state=='accepted':return obj,False
            if kind=='credit' and obj.credited_at:return obj,False
            if kind in {'save','submit'}:
                answer=text(answer,12000,'Ответ',required=kind=='submit')
                if kind=='submit' and obj.state in {'submitted','reviewed'} and obj.answer==answer:return obj,False
        if kind!='revoke' and (type(revision) is not int or revision!=obj.revision):raise ChallengeConflict('Состояние изменилось. Обновите страницу перед действием.')
        state=effective_state(obj,now)
        if kind in {'accept','decline','withdraw'} and state!='offered':raise ChallengeConflict('Предложение задания уже закрыто или начато.')
        if kind in {'save','submit'} and state!='accepted':raise ChallengeConflict('Ответ можно сохранить/отправить только до срока начатого задания.')
        if kind=='accept':obj.state='accepted';obj.accepted_at=now
        elif kind=='decline':obj.state='declined'
        elif kind=='withdraw':obj.state='withdrawn'
        elif kind=='credit':
            if state!='reviewed' or not result(obj)['sufficient']:raise ChallengeConflict('Зачесть можно только достаточный оценённый результат.')
            obj.credited_at=now
        else:
            if kind=='save' and obj.answer==answer:return obj,False
            obj.answer=answer
            if kind=='submit':obj.state='submitted';obj.submitted_at=now
        obj.revision+=1;obj.save()
        return obj,True


def review(user,pk,*,revision,scores,note,acknowledge=False,credit=False):
    actor(user,'employer')
    with transaction.atomic():
        obj=owned(user,pk)
        if not share_open(obj):raise ChallengeConflict('Доступ к ответу отозван или данные очищены.')
        if acknowledge is not True:raise ValidationError('Подтвердите оценку компании.')
        if not isinstance(scores,list) or len(scores)!=len(obj.criteria) or any(type(v) is not int or not 0<=v<=2 for v in scores):
            raise ValidationError('Оцените каждый критерий баллом 0, 1 или 2.')
        note=text(note,2000,'Объяснение оценки')
        if type(credit) is not bool:raise ValidationError('Некорректный зачёт.')
        if obj.state=='reviewed':
            if obj.review_scores==scores and obj.review_note==note:return obj,False
            raise ChallengeConflict('Оценка уже сохранена и не заменяется повторным запросом.')
        if obj.state!='submitted':raise ChallengeConflict('Кандидат ещё не отправил ответ.')
        if type(revision) is not int or revision!=obj.revision:raise ChallengeConflict('Ответ/состояние изменились. Обновите страницу.')
        if credit and sum(scores)<obj.pass_points:raise ValidationError('Недостаточный результат нельзя зачесть. Снимите выбор зачёта.')
        now=timezone.now();obj.state='reviewed';obj.review_scores=scores;obj.review_note=note
        obj.reviewed_at=now;obj.reviewed_by=user;obj.credited_at=now if credit else None
        obj.revision+=1;obj.save()
        return obj,True


def revoke_for_invitation(invitation,at):
    GapChallenge.objects.filter(invitation=invitation,state__in=['offered','accepted','submitted','reviewed'],
        consent_revoked_at__isnull=True,candidate_erased_at__isnull=True).update(
        consent_revoked_at=at,state='revoked',credited_at=None,revision=F('revision')+1)


def revoke_one(obj,at):
    if obj.consent_revoked_at:return
    obj.state='revoked';obj.consent_revoked_at=at;obj.credited_at=None;obj.revision+=1;obj.save()


def erase_for_profile(profile,at):
    for obj in GapChallenge.objects.filter(candidate=profile):
        obj.candidate=None;obj.candidate_erased_at=at;obj.consent_revoked_at=obj.consent_revoked_at or at
        obj.title=f'Задание #{obj.pk}';obj.instructions='';obj.criteria=[];obj.answer=''
        obj.review_scores=[];obj.review_note='';obj.reviewed_by=None;obj.credited_at=None;obj.state='erased'
        obj.revision+=1;obj.save()
