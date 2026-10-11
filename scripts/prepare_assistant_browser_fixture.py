#!/usr/bin/env python3
"""Prepare owned synthetic accounts for the stages browser check in .runtime/qa only."""
import json,os,secrets,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'));os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.conf import settings
from django.utils import timezone
from accounts.models import User
from profiles.models import Profile
from hiring.models import Company,Need
from assessments.services import start_attempt,save_answers
runtime=(ROOT/'.runtime/qa').resolve()
if not settings.DEBUG or not Path(settings.DATABASES['default']['NAME']).resolve().is_relative_to(runtime):
    raise SystemExit('Only a DEBUG database under this checkout .runtime/qa is allowed')
suffix=uuid.uuid4().hex;password=secrets.token_urlsafe(24)
candidate=User.objects.create_user(username=f'stage-browser-{suffix}-c@demo.invalid',password=password,role='candidate',email_confirmed=True,
    processing_consented_at=timezone.now(),processing_consent_version='processing-v1')
profile=Profile.objects.create(user=candidate,name='Кандидат Сценария',skills='Swift, UIKit',published=True,description='Приватный текст',contact_email='private@demo.invalid')
obj=start_attempt(profile,'Junior')
# Only this newly created perfect-answer fixture: functional UI check, never grading validation.
save_answers(profile,obj.pk,{q['id']:q['correct'] for q in obj.tasks},finish=True)
employer=User.objects.create_user(username=f'stage-browser-{suffix}-e@demo.invalid',password=password,role='employer',email_confirmed=True,
    processing_consented_at=timezone.now(),processing_consent_version='processing-v1')
company=Company.objects.create(user=employer,name='Компания Сценария',contact_email='company@demo.invalid')
need=Need.objects.create(company=company,title='iOS Сценария',grade='Junior',skills='Swift, SwiftUI',tasks='Задачи команды',salary_min=100000,salary_max=150000,work_format='remote')
path=runtime/'AI-001-fixture.json'
path.write_text(json.dumps({'candidate':candidate.username,'employer':employer.username,'password':password,'profile':profile.pk,'need':need.pk,'attempt':obj.pk},ensure_ascii=False))
path.chmod(0o600)
print('Prepared isolated synthetic browser fixture; credentials only in ignored .runtime/qa.')
