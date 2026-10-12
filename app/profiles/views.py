from io import BytesIO
from html import escape
from pathlib import Path
from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.http import FileResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods,require_safe
from accounts.access import role_required
from accounts.models import ConsentEvent
from accounts.consents import PUBLICATION_VERSION
from django.utils import timezone
from .forms import ProfileForm, ExperienceFormSet, FspLinkForm
from .fsp_service import connect, disconnect
from .models import FspLink
from django.core.exceptions import ValidationError
from .models import Profile
from .conditions import preferences, labels, WORK_FORMATS, EMPLOYMENT_TYPES, TASK_TYPES, compare_conditions

@role_required("candidate")
@require_http_methods(["GET", "POST"])
def profile(request):
    obj = get_object_or_404(Profile,user=request.user)
    was_published=obj.published
    form = ProfileForm(request.POST or None, instance=obj)
    experience_data = request.POST if request.method == 'POST' and 'experience-TOTAL_FORMS' in request.POST else None
    experiences = ExperienceFormSet(experience_data, instance=obj, prefix='experience')
    if request.method == "POST" and form.is_valid() and (experience_data is None or experiences.is_valid()):
        with transaction.atomic():
            saved=form.save()
            if saved.published != was_published or (saved.published and not saved.publication_consented_at):
                ConsentEvent.objects.create(user=request.user,purpose='publication',version=PUBLICATION_VERSION,granted=saved.published)
                if saved.published:
                    saved.publication_consented_at=timezone.now()
                    saved.publication_consent_version=PUBLICATION_VERSION
                    saved.save(update_fields=['publication_consented_at','publication_consent_version'])
            if experience_data is not None: experiences.save()
        messages.success(request, "Профиль сохранён.")
        return redirect("profile")
    return render(request, "profiles/profile.html", {"form": form, "profile": obj, "experiences": experiences})


def build_pdf(profile, include_contacts=False, need=None):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    name = "FSPDejaVu"
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(name, str(settings.BASE_DIR / "static/fonts/DejaVuSans.ttf")))
    stream = BytesIO()
    style = ParagraphStyle("body", fontName=name, fontSize=11, leading=16, splitLongWords=True)
    texts = ["ФСП - резюме кандидата", profile.name, f"Город: {profile.city}", f"Специализация: {profile.get_specialization_display()}", f"Навыки (заявлены кандидатом): {profile.skills}",
             f"Стаж (самоописание): {profile.experience_months} месяцев", f"Роли (самоописание): {profile.role_labels or 'не указаны'}",
             f"Софт-скиллы (самоописание): {profile.soft_skill_labels or 'не указаны'}",
             f"Подтверждённая категория: {profile.confirmed_grade or 'не подтверждена'}", f"Результат теста: {profile.test_score:.0%}",
             f"ФСП: {profile.get_fsp_status_display()} (мок интеграции)"]
    pref=preferences(profile)
    texts.extend(['Предпочтения кандидата (не подтверждение навыков):',
        'Формат работы: '+(', '.join(labels(pref['work_formats'],WORK_FORMATS)) or 'неизвестно'),
        'Занятость: '+(', '.join(labels(pref['employment_types'],EMPLOYMENT_TYPES)) or 'неизвестно'),
        'Типы задач: '+(', '.join(labels(pref['task_types'],TASK_TYPES)) or 'неизвестно')])
    if need:
        comparison=compare_conditions(profile,need)
        texts.append('Сравнение с выбранной потребностью: '+need.title)
        for key,title in [('matches','Совпадения'),('conflicts','Противоречия'),('unknown','Неизвестно')]:
            texts.append(title+':')
            for row in comparison[key]:
                texts.append(row['label']+': кандидат — '+(', '.join(row['candidate_labels']) or 'неизвестно')+
                    '; потребность — '+(', '.join(row['required_labels']) or 'неизвестно')+'. '+row['reason'])
            if not comparison[key]:texts.append('Нет.')
        texts.append(comparison['note'])
    for event in profile.achievement_events:
        texts.append(f"{event.event_name}: {event.occurred_on}, {event.discipline}, {event.result}, "
                     f"{'команда' if event.team else 'личное участие'} (источник: мок)")
    from assessments.models import Attempt
    from assessments.proofs import witness
    result=Attempt.objects.filter(candidate=profile,status='finished',passed=True,grade=profile.confirmed_grade).order_by('-finished_at','-pk').first()
    if result:
        proof=witness(result)
        texts.extend([f"Свидетельство: {proof['finished_at']}, банк {proof['bank_version']}, правила {proof['rules_version']}, вариант {proof['variant']}",
            'Области (верных ответов): '+', '.join(f'{area}: {count}' for area,count in proof['areas'].items()),
            f"Критерии: {proof['criteria']['min_correct']}/8, минимум {proof['criteria']['min_per_area']} в каждой области; 15 минут.",
            proof['limitations']])
    else:texts.append('Свидетельство завершённого успешного теста этой категории отсутствует.')
    if include_contacts:
        texts.extend(["О себе (самоописание):", profile.description or 'Не заполнено', "Опыт (самоописание):"])
        for item in profile.experiences.order_by('pk'):
            texts.extend([f"{item.organization} / {item.role} - {item.months} месяцев", item.description])
        texts.extend([f"Email: {profile.contact_email}", f"Телефон: {profile.contact_phone}"])
    else:
        texts.append('Публичная версия резюме. Подробный опыт, описание и контакты не включены в этот файл.')
    story = []
    for text in texts:
        story.extend([Paragraph(escape(text).replace('\n', '<br/>'), style), Spacer(1, 8)])
    SimpleDocTemplate(stream).build(story)
    stream.seek(0)
    return stream

@role_required("candidate")
@require_safe
def resume(request):
    return FileResponse(build_pdf(get_object_or_404(Profile,user=request.user), include_contacts=True), as_attachment=True, filename="resume.pdf")

@role_required("candidate")
@require_safe
def fsp(request):
    p = get_object_or_404(Profile,user=request.user)
    link=FspLink.objects.filter(profile=p).first()
    return JsonResponse({"source": "mock", "status": p.fsp_status, "changes_grade": False,
        'external_id':link.external_id if link else None,'events':list(link.achievements.values(
            'event_id','source','event_name','occurred_on','discipline','result','team','prize')) if link else []})


@role_required('candidate')
@require_http_methods(['GET','POST'])
def fsp_link(request):
    p=get_object_or_404(Profile,user=request.user)
    link=FspLink.objects.filter(profile=p).first()
    form=FspLinkForm(request.POST or None,initial={'external_id':link.external_id if link else ''})
    if request.method=='POST' and request.POST.get('action')=='unlink':
        disconnect(p);messages.success(request,'Демо ID отвязан; достижения и бонус убраны. Категория сохранена.')
        return redirect('fsp-link')
    if request.method=='POST' and form.is_valid():
        try:connect(p,form.cleaned_data['external_id'],form.cleaned_data['consent'])
        except ValidationError as exc:form.add_error(None,exc)
        else:return redirect('fsp-link')
    return render(request,'profiles/fsp.html',{'form':form,'link':link,'profile':p})
