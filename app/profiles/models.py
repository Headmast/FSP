from django.conf import settings
from django.db import models
from django.core.validators import MaxValueValidator

ROLES = [('developer', 'Разработчик'), ('reviewer', 'Ревьюер'), ('mentor', 'Наставник'), ('lead', 'Лидер команды')]
SOFT_SKILLS = [('communication', 'Коммуникация'), ('teamwork', 'Работа в команде'), ('planning', 'Планирование'), ('feedback', 'Обратная связь')]

class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=80, blank=True)
    city = models.CharField(max_length=80, blank=True)
    skills = models.CharField(max_length=200, blank=True)
    specialization = models.CharField(max_length=20, default='ios_swift', choices=[('ios_swift', 'iOS / Swift')])
    experience_months = models.PositiveSmallIntegerField(default=0, blank=True, validators=[MaxValueValidator(600)])
    roles = models.JSONField(default=list, blank=True)
    soft_skills = models.JSONField(default=list, blank=True)
    preferred_work_formats = models.JSONField(default=list, blank=True)
    preferred_employment_types = models.JSONField(default=list, blank=True)
    preferred_task_types = models.JSONField(default=list, blank=True)
    description = models.TextField(max_length=3000, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    published = models.BooleanField(default=False)
    publication_consented_at = models.DateTimeField(null=True, blank=True)
    publication_consent_version = models.CharField(max_length=40, blank=True)
    desired_grade = models.CharField(max_length=8, default="Junior", choices=[("Junior", "Junior"), ("Middle", "Middle")])
    confirmed_grade = models.CharField(max_length=8, blank=True)
    test_score = models.FloatField(default=0)
    grade_changed_at = models.DateTimeField(null=True, blank=True)
    fsp_status = models.CharField(max_length=20, default="not_connected", choices=[("not_connected", "Не подключено"), ("no_history", "Нет истории"), ("demo_history", "Демо история"), ("unavailable", "Источник недоступен")])
    fsp_prize = models.BooleanField(default=False)

    @property
    def role_labels(self):
        return ', '.join(dict(ROLES)[key] for key in self.roles if key in dict(ROLES))

    @property
    def soft_skill_labels(self):
        return ', '.join(dict(SOFT_SKILLS)[key] for key in self.soft_skills if key in dict(SOFT_SKILLS))

    @property
    def achievement_events(self):
        return Achievement.objects.filter(link__profile=self).order_by('occurred_on','pk')


class Experience(models.Model):
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='experiences')
    organization = models.CharField(max_length=120)
    role = models.CharField(max_length=120)
    months = models.PositiveSmallIntegerField(validators=[MaxValueValidator(600)])
    description = models.TextField(max_length=2000, blank=True)


class FspLink(models.Model):
    profile=models.OneToOneField(Profile,on_delete=models.CASCADE,related_name='fsp_link')
    external_id=models.CharField(max_length=40,unique=True)
    source=models.CharField(max_length=12,default='mock')
    consented_at=models.DateTimeField()
    consent_version=models.CharField(max_length=40,default='fsp-mock-v1')
    synced_at=models.DateTimeField(null=True)
    status=models.CharField(max_length=20)


class Achievement(models.Model):
    link=models.ForeignKey(FspLink,on_delete=models.CASCADE,related_name='achievements')
    event_id=models.CharField(max_length=40)
    source=models.CharField(max_length=12,default='mock')
    event_name=models.CharField(max_length=120)
    occurred_on=models.DateField()
    discipline=models.CharField(max_length=80)
    result=models.CharField(max_length=80)
    team=models.BooleanField(default=False)
    prize=models.BooleanField(default=False)

    class Meta:
        constraints=[models.UniqueConstraint(fields=['link','event_id'],name='unique_fsp_event')]


class PrivacyReceipt(models.Model):
    """Technical idempotency receipt. No profile text, contacts, secrets or raw request."""
    from uuid import uuid4
    id=models.UUIDField(primary_key=True,default=uuid4,editable=False)
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True)
    action=models.CharField(max_length=20)
    created_at=models.DateTimeField()
    applied_at=models.DateTimeField()
