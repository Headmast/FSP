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
        'roles':dict(ROLES),'soft_skills':dict(SOFT_SKILLS),'features':['read','drafts'],'fsp_source':'mock'})


@endpoint('candidate')
def profile(request):
    return reply(request,profile_data(owned_profile(request)))


@endpoint('candidate',private=True)
def profile_private(request):
    return reply(request,private_profile(owned_profile(request)))


def pdf_response(request,obj,grant):
    require(not is_mcp(request))
    flag=request.GET.get('with_contacts','false')
    require(flag in {'false','true'},400,'INVALID_PARAMETER','with_contacts должен быть true/false.')
    with_contacts=flag=='true'
    if with_contacts:
        require(grant and 'contacts.read' in request.api_token.scopes)
    return FileResponse(build_pdf(obj,include_contacts=with_contacts),as_attachment=True,filename='resume.pdf')


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
def invitation(request,pk):
    obj=get_object_or_404(invitation_query(request.user),pk=parse_identifier(pk))
    return reply(request,invitation_data(obj,is_mcp(request)))


@endpoint(private=True)
def invitation_contacts(request,pk):
    obj=get_object_or_404(invitation_query(request.user),pk=parse_identifier(pk))
    if request.user.role=='candidate':
        return reply(request,{'company_id':obj.company_id,'contact_email':obj.snapshot.get('company_email','')})
    require(obj.status=='accepted')
    return reply(request,private_profile(obj.candidate))
