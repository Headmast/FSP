from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F,Q
from profiles.models import Profile
from profiles.conditions import WORK_FORMATS, EMPLOYMENT_TYPES
from profiles.skills import SKILLS

class Company(models.Model):
    user=models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    name=models.CharField(max_length=120,default='Демо компания')
    contact_email=models.EmailField(blank=True)
    description=models.TextField(max_length=3000,blank=True)
    industry=models.CharField(max_length=120,blank=True)

class Recruiter(models.Model):
    company=models.ForeignKey(Company,on_delete=models.CASCADE,related_name='recruiters')
    name=models.CharField(max_length=120)

    def __str__(self):
        return self.name

class Need(models.Model):
    company=models.ForeignKey(Company,on_delete=models.CASCADE)
    recruiter=models.ForeignKey(Recruiter,on_delete=models.SET_NULL,null=True,blank=True)
    title=models.CharField(max_length=120)
    grade=models.CharField(max_length=8,choices=[('Junior','Junior'),('Middle','Middle')])
    skills=models.CharField(max_length=200,blank=True)
    tasks=models.TextField(max_length=1500)
    salary_min=models.PositiveIntegerField(validators=[MinValueValidator(1)])
    salary_max=models.PositiveIntegerField(validators=[MinValueValidator(1)])
    work_format=models.CharField(max_length=10,choices=WORK_FORMATS)
    employment_type=models.CharField(max_length=12,choices=EMPLOYMENT_TYPES,default='',blank=True)
    task_types=models.JSONField(default=list,blank=True)
    next_step=models.CharField(max_length=200,default='Знакомство с командой')
    class Meta:
        constraints=[models.CheckConstraint(condition=Q(salary_min__gt=0)&Q(salary_max__gte=F('salary_min')),name='valid_need_salary')]

class Invitation(models.Model):
    candidate=models.ForeignKey(Profile,on_delete=models.SET_NULL,null=True,blank=True)
    need=models.ForeignKey(Need,on_delete=models.PROTECT)
    company=models.ForeignKey(Company,on_delete=models.PROTECT)
    recruiter=models.ForeignKey(Recruiter,on_delete=models.PROTECT,null=True,blank=True)
    snapshot=models.JSONField()
    status=models.CharField(max_length=8,default='sent',choices=[('sent','Ожидает решения'),('accepted','Принято'),('declined','Отклонено')])
    created_at=models.DateTimeField(auto_now_add=True)
    viewed_at=models.DateTimeField(null=True,blank=True)
    responded_at=models.DateTimeField(null=True,blank=True)
    contact_revoked_at=models.DateTimeField(null=True,blank=True)
    candidate_erased_at=models.DateTimeField(null=True,blank=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['candidate','need'],name='one_invitation_per_need')]


class GapChallenge(models.Model):
    """Company-scoped manual evidence, never a professional category examination."""
    STATES=[(value,label) for value,label in [('offered','Предложено'),('accepted','Начато'),
        ('submitted','Ответ отправлен'),('reviewed','Оценено компанией'),('declined','Кандидат отказался'),
        ('withdrawn','Компания отозвала'),('expired','Срок истёк'),('revoked','Доступ отозван'),('erased','Данные очищены')]]
    request_id=models.UUIDField(unique=True)
    invitation=models.ForeignKey(Invitation,on_delete=models.SET_NULL,null=True,blank=True,related_name='challenges')
    candidate=models.ForeignKey(Profile,on_delete=models.SET_NULL,null=True,blank=True,related_name='challenges')
    company=models.ForeignKey(Company,on_delete=models.PROTECT,related_name='challenges')
    need=models.ForeignKey(Need,on_delete=models.PROTECT,related_name='challenges')
    skill=models.CharField(max_length=32,choices=[(value,value) for value in SKILLS])
    gap_kind=models.CharField(max_length=24,choices=[('missing_declared','Не указан в самоописании'),('unverified_skill','Отдельно не проверен')])
    title=models.CharField(max_length=120)
    instructions=models.TextField(max_length=4000)
    criteria=models.JSONField(default=list)
    rubric_version=models.CharField(max_length=32,default='company-rubric-v1')
    duration_minutes=models.PositiveSmallIntegerField()
    deadline_at=models.DateTimeField()
    pass_points=models.PositiveSmallIntegerField()
    state=models.CharField(max_length=12,choices=STATES,default='offered')
    revision=models.PositiveIntegerField(default=0)
    created_at=models.DateTimeField(auto_now_add=True)
    accepted_at=models.DateTimeField(null=True,blank=True)
    submitted_at=models.DateTimeField(null=True,blank=True)
    reviewed_at=models.DateTimeField(null=True,blank=True)
    credited_at=models.DateTimeField(null=True,blank=True)
    consent_revoked_at=models.DateTimeField(null=True,blank=True)
    candidate_erased_at=models.DateTimeField(null=True,blank=True)
    answer=models.TextField(max_length=12000,blank=True)
    review_scores=models.JSONField(default=list)
    review_note=models.TextField(max_length=2000,blank=True)
    reviewed_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True,related_name='challenge_reviews')

    class Meta:
        constraints=[models.UniqueConstraint(fields=['invitation','skill'],name='one_challenge_per_invitation_skill'),
            models.CheckConstraint(condition=Q(duration_minutes__gte=5)&Q(duration_minutes__lte=60),name='short_challenge_budget'),
            models.CheckConstraint(condition=Q(pass_points__gte=1)&Q(pass_points__lte=10),name='valid_challenge_threshold')]
