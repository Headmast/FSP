from django.conf import settings
from django.db import models

class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=80, blank=True)
    city = models.CharField(max_length=80, blank=True)
    skills = models.CharField(max_length=200, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    published = models.BooleanField(default=False)
    desired_grade = models.CharField(max_length=8, default="Junior", choices=[("Junior", "Junior"), ("Middle", "Middle")])
    confirmed_grade = models.CharField(max_length=8, blank=True)
    test_score = models.FloatField(default=0)
    grade_changed_at = models.DateTimeField(null=True, blank=True)
    fsp_status = models.CharField(max_length=20, default="not_connected", choices=[("not_connected", "Не подключено"), ("no_history", "Нет истории"), ("demo_history", "Демо история")])
    fsp_prize = models.BooleanField(default=False)
