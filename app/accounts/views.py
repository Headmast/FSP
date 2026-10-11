import hashlib
import os
import secrets
import subprocess
from datetime import timedelta
from pathlib import Path
from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods,require_safe
from .forms import RegistrationForm, ConsentForm
from .consents import record_processing
from .models import DemoConfirmation


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


@require_safe
def home(request):
    if request.user.is_authenticated:
        if not request.user.has_processing_consent:return redirect('consent')
        if request.user.role == "candidate":
            return redirect("profile")
        return render(request, "accounts/employer.html")
    return render(request, "accounts/welcome.html")


@require_http_methods(["GET", "POST"])
def register(request):
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = form.save()
            record_processing(user)
            if user.role == "candidate":
                from profiles.models import Profile
                Profile.objects.create(user=user)
            token, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            DemoConfirmation.objects.create(user=user, token_hash=digest(token), session_nonce_hash=digest(nonce),
                expires_at=timezone.now() + timedelta(minutes=30))
        request.session["pending_registration"] = {"user": user.pk, "token": token, "nonce": nonce}
        return redirect("confirm")
    return render(request, "accounts/register.html", {"form": form})


@login_required
@require_http_methods(['GET','POST'])
def consent(request):
    form=ConsentForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():record_processing(request.user)
        return redirect('home')
    return render(request,'accounts/consent.html',{'form':form})


@require_safe
def privacy(request):
    return render(request,'accounts/privacy.html')


@require_http_methods(["GET", "POST"])
def confirm(request):
    pending = request.session.get("pending_registration")
    if not pending:
        raise Http404
    if request.method == "POST":
        with transaction.atomic():
            item = DemoConfirmation.objects.filter(user_id=pending["user"], token_hash=digest(request.POST.get("token", "")),
                session_nonce_hash=digest(pending["nonce"]), used_at__isnull=True, expires_at__gt=timezone.now()).first()
            if not item:
                return render(request, "accounts/confirm.html", {"error": "Токен недействителен или истёк.", "pending": pending}, status=400)
            item.used_at = timezone.now()
            item.save(update_fields=["used_at"])
            user = item.user
            user.email_confirmed = True
            user.is_active = True
            user.save(update_fields=["email_confirmed", "is_active"])
        del request.session["pending_registration"]
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return redirect("home")
    return render(request, "accounts/confirm.html", {"pending": pending})


@require_safe
def health(request):
    from django.db import DatabaseError
    from .models import User, ConsentEvent
    from profiles.models import Profile
    from assessments.models import Attempt
    from hiring.models import Company, Need, Invitation
    try:
        for model in (User, ConsentEvent, Profile, Attempt, Company, Need, Invitation):
            model.objects.exists()
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


@require_safe
def version(request):
    marker = settings.ROOT / "REVISION"
    revision = marker.read_text().strip() if marker.is_file() else subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=settings.ROOT, text=True).strip()
    return JsonResponse({"commit": revision, "assistant_mode": "mock"})
