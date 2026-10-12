"""Safe read-only projection: no instructions, criteria text, answer or review comment."""
from . import challenges


def data(obj,user):
    from api.serializers import label
    allowed=user.role=='candidate' or challenges.contents_open(obj)
    result=challenges.result(obj) if user.role=='candidate' or challenges.share_open(obj) else None
    date=lambda value:value.isoformat() if value else None
    return {'id':obj.pk,'invitation_id':obj.invitation_id,'candidate_id':obj.candidate_id if allowed else None,
        'company_id':obj.company_id,'need_id':obj.need_id,
        'title':label(obj.title,f'Задание #{obj.pk}') if allowed else f'Задание #{obj.pk}',
        'skill':obj.skill,'gap_kind':obj.gap_kind,'state':challenges.effective_state(obj),'revision':obj.revision,
        'rubric_version':obj.rubric_version,'criterion_count':len(obj.criteria),'duration_minutes':obj.duration_minutes,
        'deadline_at':date(obj.deadline_at),'response_due_at':date(challenges.due_at(obj)),
        'accepted_at':date(obj.accepted_at),'submitted_at':date(obj.submitted_at),'reviewed_at':date(obj.reviewed_at),
        'consent_revoked_at':date(obj.consent_revoked_at),'candidate_erased_at':date(obj.candidate_erased_at),
        'pass_points':obj.pass_points if not obj.candidate_erased_at else None,'result':result,
        'changes_professional_grade':False,'actions_in_browser_only':True,'evaluation_source':'company_manual'}
