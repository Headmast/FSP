from django.db import models
from django.db.models import Q
from profiles.models import Profile

class Attempt(models.Model):
    candidate = models.ForeignKey(Profile, on_delete=models.CASCADE)
    grade = models.CharField(max_length=8)
    bank_version = models.CharField(max_length=40)
    variant = models.CharField(max_length=1)
    tasks = models.JSONField()
    answers = models.JSONField(default=dict)
    started_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True)
    status = models.CharField(max_length=8, default='active')
    correct_count = models.PositiveSmallIntegerField(default=0)
    area_scores = models.JSONField(default=dict)
    passed = models.BooleanField(default=False)
    expired = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['candidate'], condition=Q(status='active'), name='one_active_attempt')]
