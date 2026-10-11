from django.utils import timezone

PROCESSING_VERSION = 'processing-v1'
PUBLICATION_VERSION = 'publication-v1'


def record_processing(user, source='web_form'):
    from .models import ConsentEvent
    if user.has_processing_consent:
        return
    user.processing_consented_at = timezone.now()
    user.processing_consent_version = PROCESSING_VERSION
    user.save(update_fields=['processing_consented_at','processing_consent_version'])
    ConsentEvent.objects.create(user=user,purpose='processing',version=PROCESSING_VERSION,granted=True,source=source)
