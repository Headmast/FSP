from io import BytesIO
from html import escape
from pathlib import Path
from django.conf import settings
from django.contrib import messages
from django.http import FileResponse, JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from accounts.access import role_required
from .forms import ProfileForm
from .models import Profile

@role_required("candidate")
@require_http_methods(["GET", "POST"])
def profile(request):
    obj = Profile.objects.get(user=request.user)
    form = ProfileForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Профиль сохранён.")
        return redirect("profile")
    return render(request, "profiles/profile.html", {"form": form, "profile": obj})


def build_pdf(profile, include_contacts=False):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    name = "FSPDejaVu"
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(name, str(settings.BASE_DIR / "static/fonts/DejaVuSans.ttf")))
    stream = BytesIO()
    style = ParagraphStyle("body", fontName=name, fontSize=12, leading=18)
    texts = ["ФСП — резюме кандидата", profile.name, f"Город: {profile.city}", f"Навыки (заявлены кандидатом): {profile.skills}",
             f"Категория: {profile.confirmed_grade or 'не подтверждена'}", f"Результат теста: {profile.test_score:.0%}",
             f"ФСП: {profile.get_fsp_status_display()} (мок интеграции)"]
    if include_contacts:
        texts.extend([f"Email: {profile.contact_email}", f"Телефон: {profile.contact_phone}"])
    story = []
    for text in texts:
        story.extend([Paragraph(escape(text), style), Spacer(1, 10)])
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
