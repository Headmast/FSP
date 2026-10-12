from .core import endpoint, reply


@endpoint()
def me(request):
    token = request.api_token
    return reply(request, {'id': request.user.pk, 'role': request.user.role, 'token_kind': token.kind,
        'scopes': token.scopes, 'expires_at': token.expires_at.isoformat()})

from django.shortcuts import get_object_or_404
from django.http import FileResponse
from accounts.identifiers import parse_identifier
from profiles.models import Profile, FspLink, ROLES, SOFT_SKILLS
from profiles.skills import SKILLS
from profiles.conditions import WORK_FORMATS, EMPLOYMENT_TYPES, TASK_TYPES
from profiles.views import build_pdf
from assessments.models import Attempt
from hiring.access import invitation_query
from .core import require, paged, ApiError
from .serializers import profile_data, private_profile, proof_data, invitation_data, label


def is_mcp(request):
    return request.api_token.kind == 'mcp'


def owned_profile(request):
    return get_object_or_404(Profile,user=request.user)


@endpoint()
def catalog(request):
    return reply(request, {'specializations':['ios_swift'],'grades':['Junior','Middle'],'skills':list(SKILLS),
        'roles':dict(ROLES),'soft_skills':dict(SOFT_SKILLS),'work_formats':dict(WORK_FORMATS),
        'employment_types':dict(EMPLOYMENT_TYPES),'task_types':dict(TASK_TYPES),'features':['read','drafts','conditions-v1','privacy-web-actions','company-challenges-v1'],'fsp_source':'mock'})


@endpoint('candidate')
def profile(request):
    return reply(request,profile_data(owned_profile(request)))


@endpoint('candidate')
def privacy_status(request):
    from profiles.privacy import status_data
    return reply(request,status_data(request.user))


@endpoint('candidate',private=True)
def profile_private(request):
    return reply(request,private_profile(owned_profile(request)))


def pdf_response(request,obj,grant,need=None):
    require(not is_mcp(request))
    flag=request.GET.get('with_contacts','false')
    require(flag in {'false','true'},400,'INVALID_PARAMETER','with_contacts должен быть true/false.')
    with_contacts=flag=='true'
    if with_contacts:
        require(grant and 'contacts.read' in request.api_token.scopes)
    return FileResponse(build_pdf(obj,include_contacts=with_contacts,need=need),as_attachment=True,filename='resume.pdf')


@endpoint('candidate')
def profile_pdf(request):
    return pdf_response(request,owned_profile(request),True)


@endpoint('candidate')
def assessments(request):
    rows,pagination=paged(request,Attempt.objects.filter(candidate__user=request.user).order_by('-started_at','-pk'))
    return reply(request,[{'id':obj.pk,'grade':obj.grade,'status':obj.status,'started_at':obj.started_at.isoformat(),
        'expires_at':obj.expires_at.isoformat(),'result':proof_data(obj) if obj.status=='finished' else None} for obj in rows],pagination=pagination)


@endpoint('candidate')
def assessment_result(request,pk):
    obj=get_object_or_404(Attempt,pk=parse_identifier(pk),candidate__user=request.user)
    require(obj.status=='finished',409,'RESULT_NOT_READY','Попытка ещё не завершена.')
    return reply(request,proof_data(obj))


@endpoint('candidate')
def achievements(request):
    obj=owned_profile(request)
    link=FspLink.objects.filter(profile=obj).first()
    events=[]
    if link:
        for event in link.achievements.order_by('occurred_on','pk'):
            item={'id':event.pk,'source':'mock','event_name':label(event.event_name,f'Событие #{event.pk}'),
                'occurred_on':event.occurred_on.isoformat(),'team':event.team,'prize':event.prize}
            if not is_mcp(request):
                item.update(event_id=event.event_id,discipline=event.discipline,result=event.result)
            events.append(item)
    data={'source':'mock','status':obj.fsp_status,'changes_grade':False,'events':events}
    if not is_mcp(request):
        data['external_id']=link.external_id if link else None
    return reply(request,data)


@endpoint()
def invitations(request):
    rows,pagination=paged(request,invitation_query(request.user).order_by('-created_at','-pk'))
    return reply(request,[invitation_data(obj,is_mcp(request)) for obj in rows],pagination=pagination)


@endpoint()
def challenges(request):
    from hiring.challenges import own_query
    from hiring.challenge_projection import data
    rows,pagination=paged(request,own_query(request.user).order_by('-created_at','-pk'))
    return reply(request,[data(obj,request.user) for obj in rows],pagination=pagination)


@endpoint()
def challenge(request,pk):
    from hiring.challenges import owned
    from hiring.challenge_projection import data
    return reply(request,data(owned(request.user,parse_identifier(pk)),request.user))


@endpoint()
def invitation(request,pk):
    obj=get_object_or_404(invitation_query(request.user),pk=parse_identifier(pk))
    return reply(request,invitation_data(obj,is_mcp(request)))


@endpoint(private=True)
def invitation_contacts(request,pk):
    obj=get_object_or_404(invitation_query(request.user),pk=parse_identifier(pk))
    if request.user.role=='candidate':
        return reply(request,{'company_id':obj.company_id,'contact_email':obj.snapshot.get('company_email','')})
    from hiring.services import contacts_allowed
    require(obj.candidate is not None and obj.contact_revoked_at is None and obj.candidate_erased_at is None
        and contacts_allowed(obj.company,obj.candidate))
    return reply(request,private_profile(obj.candidate))

from hiring.access import company_read, owned_need, visible_profile
from hiring.models import Need
from hiring.forms import SearchForm
from hiring.services import search, explain
from .serializers import company_data, need_data, skills


@endpoint('employer')
def company(request):
    return reply(request,company_data(company_read(request.user),is_mcp(request)))


@endpoint('employer')
def needs(request):
    rows,pagination=paged(request,Need.objects.filter(company__user=request.user).order_by('pk'))
    return reply(request,[need_data(obj,is_mcp(request)) for obj in rows],pagination=pagination)


@endpoint('employer')
def need(request,pk):
    return reply(request,need_data(owned_need(request.user,parse_identifier(pk)),is_mcp(request)))


def chosen_need(request):
    identifier=parse_identifier(request.GET.get('need_id'),required=False)
    return owned_need(request.user,identifier) if identifier else None


@endpoint('employer')
def candidates(request):
    company=company_read(request.user)
    chosen=chosen_need(request)
    grade=request.GET.get('grade') or (chosen.grade if chosen else '')
    form=SearchForm({'need':chosen.pk if chosen else '', 'grade':grade, 'skill':request.GET.get('skill',''),
        'fsp':request.GET.get('fsp_status',''),'conditions':request.GET.get('conditions','')},company=company)
    require(form.is_valid(),400,'INVALID_FILTERS','Проверьте категорию, навык и потребность.')
    results=search(**form.cleaned_data)
    rows,pagination=paged(request,results)
    # Rebuild sensitive subobjects from their controlled DTOs, never spread search dictionaries.
    data=[]
    for row in rows:
        obj=get_object_or_404(Profile,pk=row['id'])
        data.append({'profile':profile_data(obj),'score':row['score'],'parts':row['parts'],
            'explanation':explanation_data(obj,chosen)})
    return reply(request,data,pagination=pagination)


def explanation_data(obj,chosen):
    value=explain(obj,chosen)
    from .serializers import proof_snapshot
    return {'declared_matches':value['declared_matches'],'declared_gaps':value['declared_gaps'],
        'confirmation':proof_snapshot(value['confirmation']) if value['confirmation'] else None,
        'unknown':value['unknown'],'conditions':value['conditions']}


@endpoint('employer')
def candidate(request,pk):
    obj,grant=visible_profile(company_read(request.user),parse_identifier(pk))
    chosen=chosen_need(request)
    require(not chosen or chosen.grade==obj.confirmed_grade,400,'INVALID_FILTERS','Категории не совпадают.')
    return reply(request,{'profile':profile_data(obj),'contacts_allowed':grant,
        'explanation':explanation_data(obj,chosen)})


@endpoint('employer')
def candidate_proofs(request,pk):
    obj,_=visible_profile(company_read(request.user),parse_identifier(pk))
    rows,pagination=paged(request,Attempt.objects.filter(candidate=obj,status='finished',grade=obj.confirmed_grade).order_by('-finished_at','-pk'))
    return reply(request,[proof_data(p) for p in rows],pagination=pagination)


@endpoint('employer',private=True)
def candidate_private(request,pk):
    obj,grant=visible_profile(company_read(request.user),parse_identifier(pk))
    require(grant)
    return reply(request,private_profile(obj))


@endpoint('employer')
def candidate_pdf(request,pk):
    obj,grant=visible_profile(company_read(request.user),parse_identifier(pk))
    chosen=chosen_need(request)
    require(not chosen or chosen.grade==obj.confirmed_grade,400,'INVALID_FILTERS','Категории не совпадают.')
    return pdf_response(request,obj,grant,chosen)


@endpoint()
def openapi(request):
    from .schema import document
    from django.http import JsonResponse
    return JsonResponse(document())


@endpoint(methods=("GET","POST","PUT","PATCH","DELETE","HEAD","OPTIONS"))
def not_found(request,unknown=""):
    raise ApiError(404,"NOT_FOUND","Маршрут не найден.")


def client_version():
    import tomllib
    from django.conf import settings
    return tomllib.loads((settings.ROOT/'clients/python/pyproject.toml').read_text())['project']['version']


from django.views.decorators.http import require_safe

@require_safe
def download_client(request,filename):
    from django.conf import settings
    from django.http import Http404
    version=client_version()
    allowed={f'fsp_client-{version}-py3-none-any.whl',f'fsp_client-{version}.tar.gz','manifest.json'}
    if request.method not in {'GET','HEAD'} or filename not in allowed:
        raise Http404
    path=settings.ROOT/'.runtime/downloads'/filename
    if not path.is_file():raise Http404
    response=FileResponse(path.open('rb'),as_attachment=True,filename=filename)
    response['Cache-Control']='no-cache'
    return response


def json_body(request):
    import json
    require(len(request.body)<=65536,400,'INVALID_BODY','Запрос до 64 KiB.')
    require(request.content_type=='application/json',400,'INVALID_BODY','Нужен application/json.')
    try:body=json.loads(request.body)
    except (ValueError,UnicodeDecodeError):raise ApiError(400,'INVALID_BODY','Неверный JSON.')
    require(isinstance(body,dict),400,'INVALID_BODY','Нужен JSON объект.')
    return body


@endpoint(methods=('GET','POST'))
def drafts(request):
    from .models import ActionDraft
    from .drafts import prepare,draft_data
    if request.method=='POST':
        body=json_body(request)
        require(set(body)<={'kind','target_id','payload'} and isinstance(body.get('kind'),str),400,'INVALID_BODY','Нужны kind, target_id и payload.')
        obj=prepare(request.user,request.api_token,body['kind'],body.get('target_id'),body.get('payload',{}))
        return reply(request,draft_data(obj,is_mcp(request),private=not is_mcp(request) and "contacts.read" in request.api_token.scopes),201)
    rows,pagination=paged(request,ActionDraft.objects.filter(user=request.user).order_by('-created_at','-pk'))
    return reply(request,[draft_data(obj,is_mcp(request),private=not is_mcp(request) and "contacts.read" in request.api_token.scopes) for obj in rows],pagination=pagination)


@endpoint()
def draft(request,pk):
    from .drafts import get_draft,draft_data
    return reply(request,draft_data(get_draft(request.user,pk),is_mcp(request),private=not is_mcp(request) and "contacts.read" in request.api_token.scopes))


@endpoint(methods=('POST',))
def cancel_draft(request,pk):
    from .drafts import get_draft,cancel,draft_data
    require(f'{request.user.role}.draft' in request.api_token.scopes)
    require(not json_body(request),400,'INVALID_BODY','Отмена не принимает параметры.')
    return reply(request,draft_data(cancel(request.user,get_draft(request.user,pk)),is_mcp(request),private=not is_mcp(request) and "contacts.read" in request.api_token.scopes))
