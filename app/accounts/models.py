from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    ROLE_CHOICES = [("candidate", "Кандидат"), ("employer", "Работодатель")]
    role = models.CharField(max_length=12, choices=ROLE_CHOICES)
    email_confirmed = models.BooleanField(default=False)

class DemoConfirmation(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    token_hash = models.CharField(max_length=64, unique=True)
    session_nonce_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
