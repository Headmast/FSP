"""Shared object access; queries never create companies or mark invitations read."""
from django.http import Http404
from django.shortcuts import get_object_or_404
from profiles.models import Profile
from assessments.models import Attempt
from .models import Company, Need, Invitation
from .services import contacts_allowed


def company_read(user):
    return Company.objects.filter(user=user).first()


def visible_profile(company, pk):
    profile = get_object_or_404(Profile, pk=pk)
    grant = bool(company and contacts_allowed(company, profile))
    if not grant and not (profile.published and profile.confirmed_grade):
        raise Http404
    return profile, grant


def owned_need(user, pk):
    return get_object_or_404(Need, pk=pk, company__user=user)


def invitation_query(user):
    if user.role == 'candidate':
        return Invitation.objects.filter(candidate__user=user)
    if user.role == 'employer':
        return Invitation.objects.filter(company__user=user)
    return Invitation.objects.none()


def accessible_proof(user, pk):
    obj = get_object_or_404(Attempt, pk=pk, status='finished')
    if user.role == 'candidate' and obj.candidate.user_id == user.pk:
        return obj
    if user.role == 'employer':
        profile, _ = visible_profile(company_read(user), obj.candidate_id)
        if obj.grade == profile.confirmed_grade:
            return obj
    raise Http404
