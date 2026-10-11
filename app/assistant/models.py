from django.conf import settings
from django.db import models
from django.utils import timezone
class Usage(models.Model):
    user=models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    window_start=models.DateTimeField()
    count=models.PositiveSmallIntegerField(default=0)


class Draft(models.Model):
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    mode=models.CharField(max_length=12,choices=[('profile','Описание профиля'),('need','Новая потребность')])
    payload=models.JSONField()
    source=models.CharField(max_length=12,default='mock')
    created_at=models.DateTimeField(auto_now_add=True)
    expires_at=models.DateTimeField()
    target_fingerprint=models.CharField(max_length=64,blank=True)
    source_need=models.ForeignKey('hiring.Need',null=True,blank=True,on_delete=models.SET_NULL,related_name='+')
    applied_need=models.ForeignKey('hiring.Need',null=True,blank=True,on_delete=models.SET_NULL,related_name='+')
    applied_at=models.DateTimeField(null=True,blank=True)

    @property
    def expired(self):return self.expires_at<=timezone.now()
