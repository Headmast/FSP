from io import BytesIO
from html import escape
from pathlib import Path
from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.http import FileResponse, JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from accounts.access import role_required
from accounts.models import ConsentEvent
from accounts.consents import PUBLICATION_VERSION
from django.utils import timezone
from .forms import ProfileForm, ExperienceFormSet
from .models import Profile

@role_required("candidate")
@require_http_methods(["GET", "POST"])
def profile(request):
    obj = Profile.objects.get(user=request.user)
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


def build_pdf(profile, include_contacts=False):
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
    if include_contacts:
        texts.extend(["О себе (самоописание):", profile.description or 'Не заполнено', "Опыт (самоописание):"])
        for item in profile.experiences.order_by('pk'):
            texts.extend([f"{item.organization} / {item.role} - {item.months} месяцев", item.description])
        texts.extend([f"Email: {profile.contact_email}", f"Телефон: {profile.contact_phone}"])
    else:
        texts.append('Подробный опыт, описание и контакты скрыты до принятия предложения этой компании.')
    story = []
    for text in texts:
        story.extend([Paragraph(escape(text).replace('\n', '<br/>'), style), Spacer(1, 8)])
    SimpleDocTemplate(stream).build(story)
    stream.seek(0)
    return stream

@role_required("candidate")
def resume(request):
    return FileResponse(build_pdf(Profile.objects.get(user=request.user), include_contacts=True), as_attachment=True, filename="resume.pdf")

@role_required("candidate")
def fsp(request):
    p = Profile.objects.get(user=request.user)
    return JsonResponse({"source": "mock", "status": p.fsp_status, "changes_grade": False})
