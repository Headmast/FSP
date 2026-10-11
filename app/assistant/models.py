from django.conf import settings
from django.db import models
class Usage(models.Model):
    user=models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    window_start=models.DateTimeField()
    count=models.PositiveSmallIntegerField(default=0)
