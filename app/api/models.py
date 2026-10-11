from uuid import uuid4
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class ActionDraft(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid4,editable=False)
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    kind=models.CharField(max_length=32)
    target_id=models.PositiveBigIntegerField(null=True)
    payload=models.JSONField()
    fingerprint=models.CharField(max_length=64)
    source=models.CharField(max_length=3,choices=[('cli','CLI'),('mcp','MCP')])
    created_at=models.DateTimeField(auto_now_add=True)
    expires_at=models.DateTimeField()
    status=models.CharField(max_length=10,default='pending',choices=[(s,s) for s in ['pending','applied','cancelled','expired']])
    applied_at=models.DateTimeField(null=True)
    applied_target_id=models.PositiveBigIntegerField(null=True)

    def save(self,*args,**kwargs):
        if not self._state.adding:
            fields=['user_id','kind','target_id','payload','fingerprint','source','expires_at']
            previous=type(self).objects.filter(pk=self.pk).values(*fields).first()
            if previous and any(previous[f]!=getattr(self,f) for f in fields):
                raise ValidationError('Параметры черновика неизменяемы.')
        super().save(*args,**kwargs)
