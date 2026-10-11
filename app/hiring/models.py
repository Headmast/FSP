from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F,Q
from profiles.models import Profile

class Company(models.Model):
    user=models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    name=models.CharField(max_length=120,default='Демо компания')
    contact_email=models.EmailField(blank=True)
    description=models.TextField(max_length=3000,blank=True)
    industry=models.CharField(max_length=120,blank=True)

class Need(models.Model):
    company=models.ForeignKey(Company,on_delete=models.CASCADE)
    title=models.CharField(max_length=120)
    grade=models.CharField(max_length=8,choices=[('Junior','Junior'),('Middle','Middle')])
    skills=models.CharField(max_length=200,blank=True)
    tasks=models.TextField(max_length=1500)
    salary_min=models.PositiveIntegerField(validators=[MinValueValidator(1)])
    salary_max=models.PositiveIntegerField(validators=[MinValueValidator(1)])
    work_format=models.CharField(max_length=10,choices=[('remote','Удалённо'),('office','Офис'),('hybrid','Гибрид')])
    next_step=models.CharField(max_length=200,default='Знакомство с командой')
    class Meta:
        constraints=[models.CheckConstraint(condition=Q(salary_min__gt=0)&Q(salary_max__gte=F('salary_min')),name='valid_need_salary')]

class Invitation(models.Model):
    candidate=models.ForeignKey(Profile,on_delete=models.CASCADE)
    need=models.ForeignKey(Need,on_delete=models.PROTECT)
    company=models.ForeignKey(Company,on_delete=models.PROTECT)
    snapshot=models.JSONField()
    status=models.CharField(max_length=8,default='sent',choices=[('sent','Ожидает решения'),('accepted','Принято'),('declined','Отклонено')])
    created_at=models.DateTimeField(auto_now_add=True)
    viewed_at=models.DateTimeField(null=True,blank=True)
    responded_at=models.DateTimeField(null=True,blank=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['candidate','need'],name='one_invitation_per_need')]
