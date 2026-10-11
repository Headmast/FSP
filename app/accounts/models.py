from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    ROLE_CHOICES = [("candidate", "Кандидат"), ("employer", "Работодатель")]
    role = models.CharField(max_length=12, choices=ROLE_CHOICES)
    email_confirmed = models.BooleanField(default=False)
    processing_consented_at = models.DateTimeField(null=True, blank=True)
    processing_consent_version = models.CharField(max_length=40, blank=True)

    @property
    def has_processing_consent(self):
        from .consents import PROCESSING_VERSION
        return bool(self.processing_consented_at and self.processing_consent_version == PROCESSING_VERSION)


class ConsentEvent(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    purpose = models.CharField(max_length=20, choices=[('processing','Обработка'),('publication','Публикация')])
    version = models.CharField(max_length=40)
    granted = models.BooleanField()
    source = models.CharField(max_length=40, default='web_form')
    created_at = models.DateTimeField(auto_now_add=True)

class DemoConfirmation(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    token_hash = models.CharField(max_length=64, unique=True)
    session_nonce_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
