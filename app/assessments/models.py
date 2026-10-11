from django.db import models
from django.db.models import Q
from profiles.models import Profile

class Attempt(models.Model):
    candidate = models.ForeignKey(Profile, on_delete=models.CASCADE)
    grade = models.CharField(max_length=8)
    bank_version = models.CharField(max_length=40)
    rules_version = models.CharField(max_length=40,default='rules-v1')
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


TRACK_CHOICES = [('ios', 'iOS'), ('android', 'Android'), ('flutter', 'Flutter'), ('aurora', 'Аврора')]


class LessonProgress(models.Model):
    track = models.CharField(max_length=16, choices=TRACK_CHOICES, default='ios')
    candidate = models.ForeignKey(Profile, on_delete=models.CASCADE)
    grade = models.CharField(max_length=8)
    topic = models.CharField(max_length=16)
    content_version = models.CharField(max_length=40)
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['candidate', 'track', 'grade', 'topic', 'content_version'],
                                               name='unique_learning_lesson')]


class PracticeSession(models.Model):
    track = models.CharField(max_length=16, choices=TRACK_CHOICES, default='ios')
    candidate = models.ForeignKey(Profile, on_delete=models.CASCADE)
    grade = models.CharField(max_length=8)
    topic = models.CharField(max_length=16, default='all')
    kind = models.CharField(max_length=8, default='check')
    content_version = models.CharField(max_length=40)
    tasks = models.JSONField()
    answers = models.JSONField(default=dict)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True)
    status = models.CharField(max_length=8, default='active')
    correct_count = models.PositiveSmallIntegerField(default=0)
    area_scores = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['candidate', 'track'], condition=Q(status='active'),
                                               name='one_active_practice')]
        ordering = ['-started_at', '-pk']
