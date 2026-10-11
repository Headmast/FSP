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
    fsp_status = models.CharField(max_length=20, default="not_connected", choices=[("not_connected", "Не подключено"), ("no_history", "Нет истории"), ("demo_history", "Демо история")])
    fsp_prize = models.BooleanField(default=False)

    @property
    def role_labels(self):
        return ', '.join(dict(ROLES)[key] for key in self.roles if key in dict(ROLES))

    @property
    def soft_skill_labels(self):
        return ', '.join(dict(SOFT_SKILLS)[key] for key in self.soft_skills if key in dict(SOFT_SKILLS))


class Experience(models.Model):
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='experiences')
    organization = models.CharField(max_length=120)
    role = models.CharField(max_length=120)
    months = models.PositiveSmallIntegerField(validators=[MaxValueValidator(600)])
    description = models.TextField(max_length=2000, blank=True)
