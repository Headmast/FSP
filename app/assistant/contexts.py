"""Owned context and an explicit provider allowlist; no contact/free-text/task keys."""
from django.http import Http404
from django.shortcuts import get_object_or_404
from profiles.models import Profile
from hiring.models import Need,Invitation
from hiring.services import explain,contacts_allowed
from assessments.models import Attempt
from assessments.proofs import witness
from profiles.conditions import snapshot_conditions


def safe_proof(proof):
    return {key:proof[key] for key in ('grade','finished_at','bank_version','rules_version','areas','correct_count','total','passed','expired','limitations')}


def matching(user,mode,need_id,candidate_id):
    need=get_object_or_404(Need,company__user=user,pk=need_id)
    profile=get_object_or_404(Profile,pk=candidate_id)
    grant=contacts_allowed(need.company,profile)
    if not profile.confirmed_grade or (not profile.published and not grant):raise Http404
    if mode=='invitation' and (not profile.published or profile.confirmed_grade!=need.grade):raise Http404
    explanation=explain(profile,need)
    context={'grade_requirement':need.grade,'candidate_grade':profile.confirmed_grade,
        'declared_matches':explanation['declared_matches'],'declared_gaps':explanation['declared_gaps'],
        'unknown':explanation['unknown'],'conditions':explanation['conditions'],
        'confirmation':safe_proof(explanation['confirmation']) if explanation['confirmation'] else None,
        'salary_min':need.salary_min,'salary_max':need.salary_max,'work_format':need.get_work_format_display()}
    proofs=[witness(item) for item in Attempt.objects.filter(candidate=profile,status='finished',grade=need.grade).order_by('-finished_at','-pk')]
    # Provider gets no object IDs or submitted tasks/answers, even when invited contacts are visible.
    if mode=='invitation':context['available_results']=[safe_proof(proof) for proof in proofs]
    return context,{'selected_need':need,'selected_candidate':profile,'proofs':proofs,'explanation':explanation}


def conversation(user,invitation_id):
    query=Invitation.objects.filter(candidate__user=user) if user.role=='candidate' else Invitation.objects.filter(company__user=user)
    invitation=get_object_or_404(query,pk=invitation_id)
    if invitation.candidate_erased_at:raise Http404
    snapshot=invitation.snapshot
    context={'role':user.role,'status':invitation.status,
        'grade':snapshot['grade'],'salary_min':snapshot['salary_min'],'salary_max':snapshot['salary_max'],
        'work_format':snapshot['work_format'],'conditions':snapshot_conditions(snapshot),'accepted_results':[safe_proof(p) for p in snapshot.get('accepted_results',[])]}
    return context,{'selected_invitation':invitation}
