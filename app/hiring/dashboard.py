"""Company-owner reporting over invitation cohorts, without exposing contacts."""
from collections import defaultdict
from datetime import timedelta
from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from accounts.access import role_required
from accounts.identifiers import parse_identifier
from .access import company_read
from .forms import RecruiterForm, AssignmentForm
from .models import Invitation, Need, Recruiter
from .views import company_for


def summarize(items, now):
    total = len(items)
    accepted = sum(item['status'] == 'accepted' for item in items)
    declined = sum(item['status'] == 'declined' for item in items)
    pending = total - accepted - declined
    viewed = sum(bool(item['viewed_at']) or item['status'] != 'sent' for item in items)
    durations = [(item['responded_at'] - item['created_at']).total_seconds() / 86400
                 for item in items if item['status'] != 'sent' and item['responded_at']
                 and item['created_at'] <= item['responded_at'] <= now]
    return {'total': total, 'viewed': viewed, 'accepted': accepted, 'declined': declined,
            'answered': accepted + declined, 'pending': pending,
            'overdue': sum(item['status'] == 'sent' and item['created_at'] <= now - timedelta(days=7) for item in items),
            'conversion': round(100 * accepted / total, 1) if total else None,
            'response_rate': round(100 * (accepted + declined) / total, 1) if total else None,
            'response_days': round(sum(durations) / len(durations), 1) if durations else None}


@role_required('employer')
@require_GET
def dashboard(request):
    company = company_read(request.user)
    now = timezone.now()
    today = timezone.localdate(now)
    period = request.GET.get('period', '30')
    if period not in {'7', '30', '90', 'all'}:
        raise Http404('Неизвестный период.')
    recruiters = list(Recruiter.objects.filter(company=company).order_by('name', 'pk')) if company else []
    needs = list(Need.objects.filter(company=company).order_by('title', 'pk')) if company else []
    recruiter_filter = request.GET.get('hr', '')
    recruiter_id = None
    if recruiter_filter and recruiter_filter != 'unassigned':
        recruiter_id = parse_identifier(recruiter_filter)
        if recruiter_id not in {person.pk for person in recruiters}:
            raise Http404
        recruiter_filter = str(recruiter_id)
    need_id = parse_identifier(request.GET.get('need'), required=False)
    if need_id and need_id not in {need.pk for need in needs}:
        raise Http404
    query = Invitation.objects.filter(company=company, created_at__lte=now) if company else Invitation.objects.none()
    start = None
    if period != 'all':
        start = today - timedelta(days=int(period) - 1)
        query = query.filter(created_at__date__gte=start)
    if recruiter_filter == 'unassigned':
        query = query.filter(recruiter__isnull=True)
    elif recruiter_id:
        query = query.filter(recruiter_id=recruiter_id)
    if need_id:
        query = query.filter(need_id=need_id)
    items = list(query.order_by('-created_at', '-pk').values(
        'pk', 'need_id', 'need__title', 'candidate__name', 'recruiter_id', 'recruiter__name',
        'created_at', 'viewed_at', 'responded_at', 'status'))
    summary = summarize(items, now)
    people_groups, need_groups = defaultdict(list), defaultdict(list)
    for item in items:
        people_groups[item['recruiter_id']].append(item)
        need_groups[item['need_id']].append(item)
    selected_needs = [need for need in needs if not need_id or need.pk == need_id]
    selected_people = [person for person in recruiters if not recruiter_filter or person.pk == recruiter_id]
    people = []
    for person in selected_people:
        people.append({'name': person.name, 'key': str(person.pk),
                       'needs': sum(need.recruiter_id == person.pk for need in selected_needs),
                       **summarize(people_groups[person.pk], now)})
    if not recruiter_filter or recruiter_filter == 'unassigned':
        people.append({'name': 'Без ответственного', 'key': 'unassigned',
                       'needs': sum(need.recruiter_id is None for need in selected_needs),
                       **summarize(people_groups[None], now)})
    vacancies = [{'need': need, **summarize(need_groups[need.pk], now)} for need in selected_needs]
    if recruiter_filter:
        vacancies = [row for row in vacancies if row['total'] or row['need'].recruiter_id == recruiter_id]
    stages = []
    for label, key in [('Отправлено', 'total'), ('Просмотрено или отвечено', 'viewed'),
                       ('Получен ответ', 'answered'), ('Принято', 'accepted')]:
        value = summary[key]
        stages.append({'label': label, 'count': value,
                       'width': round(100 * value / summary['total']) if summary['total'] else 0})
    # Aggregate by send date; accepted bars show current outcomes of the same cohort.
    chart_start = start or (timezone.localdate(items[-1]['created_at']) if items else today)
    bucket_days = max(1, ((today - chart_start).days + 1 + 11) // 12)
    buckets = []
    cursor = chart_start
    while cursor <= today:
        end = min(cursor + timedelta(days=bucket_days - 1), today)
        cohort = [item for item in items if cursor <= timezone.localdate(item['created_at']) <= end]
        buckets.append({'label': cursor.strftime('%d.%m') + (('–' + end.strftime('%d.%m')) if end != cursor else ''),
                        'sent': len(cohort), 'accepted': sum(item['status'] == 'accepted' for item in cohort)})
        cursor = end + timedelta(days=1)
    peak = max([bucket['sent'] for bucket in buckets] + [1])
    for bucket in buckets:
        bucket['sent_height'] = round(100 * bucket['sent'] / peak)
        bucket['accepted_height'] = round(100 * bucket['accepted'] / peak)
    pending = [item for item in items if item['status'] == 'sent']
    pending.sort(key=lambda item: (item['created_at'], item['pk']))
    for item in pending:
        item['age_days'] = (now - item['created_at']).days
        item['overdue'] = item['created_at'] <= now - timedelta(days=7)
    return render(request, 'hiring/dashboard.html', {
        'company': company, 'summary': summary, 'recruiters': recruiters, 'needs': needs,
        'people': people, 'vacancies': vacancies, 'stages': stages, 'buckets': buckets,
        'pending': pending[:10], 'period': period, 'hr_filter': recruiter_filter,
        'need_filter': str(need_id or ''), 'today': today,
        'recruiter_form': RecruiterForm(), 'assignment_form': AssignmentForm(company=company),
    })


@role_required('employer')
@require_POST
def team(request):
    company = company_for(request.user)
    action = request.POST.get('action')
    if action == 'add':
        form = RecruiterForm(request.POST)
        if form.is_valid():
            person = form.save(commit=False)
            person.company = company
            person.save()
            messages.success(request, 'HR добавлен. Назначьте его ответственным за потребность.')
        else:
            messages.error(request, 'Укажите имя HR от 1 до 120 символов.')
    elif action == 'assign':
        form = AssignmentForm(request.POST, company=company)
        if form.is_valid():
            Need.objects.filter(pk=form.cleaned_data['need'].pk, company=company).update(recruiter=form.cleaned_data['recruiter'])
            messages.success(request, 'Ответственный назначен. История отправленных приглашений сохранена.')
        else:
            messages.error(request, 'Выберите потребность и HR своей компании.')
    else:
        raise Http404
    return redirect('owner-dashboard')
