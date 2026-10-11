from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import FspLink,Achievement
from . import fsp_adapter


@transaction.atomic
def connect(profile,external_id,consent):
    if not consent or not profile.user.has_processing_consent:
        raise ValidationError('Требуется явное согласие на демо-привязку.')
    external_id=external_id.strip().upper()
    if not fsp_adapter.valid_demo_id(external_id):raise ValidationError('Используйте DEMO-001..999, DEMO-EMPTY или DEMO-DOWN.')
    if FspLink.objects.filter(external_id=external_id).exclude(profile=profile).exists():
        raise ValidationError('Этот демо ID уже привязан к другому аккаунту.')
    try:result=fsp_adapter.fetch(external_id)
    except fsp_adapter.SourceUnavailable:result={'status':'unavailable','events':[]}
    link,created=FspLink.objects.get_or_create(profile=profile,defaults={
        'external_id':external_id,'consented_at':timezone.now(),'status':result['status']})
    if not created and link.external_id!=external_id:
        link.consented_at=timezone.now()
    link.external_id=external_id;link.status=result['status'];link.synced_at=timezone.now();link.save()
    link.achievements.all().delete()
    Achievement.objects.bulk_create([Achievement(link=link,**event) for event in result['events']])
    profile.fsp_status=result['status'];profile.fsp_prize=any(e['prize'] for e in result['events'])
    profile.save(update_fields=['fsp_status','fsp_prize'])
    return link


@transaction.atomic
def disconnect(profile):
    FspLink.objects.filter(profile=profile).delete()
    profile.fsp_status='not_connected';profile.fsp_prize=False
    profile.save(update_fields=['fsp_status','fsp_prize'])
