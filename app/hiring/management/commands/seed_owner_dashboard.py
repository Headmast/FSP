"""Isolated synthetic owner account; never add activity to existing companies."""
import copy
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from accounts.models import User, ConsentEvent
from accounts.consents import record_processing, PUBLICATION_VERSION
from profiles.models import Profile
from assessments.models import Attempt
from assessments.bank import BANK, VERSION
from assessments.services import save_answers
from hiring.models import Company, Recruiter, Need, Invitation
from hiring.services import invite
from .seed_demo import PASSWORD, NAMES


class Command(BaseCommand):
    help='Create a separate synthetic owner dashboard. Existing owner fixture is left unchanged.'

    def handle(self,*args,**options):
        with transaction.atomic():
            email='fixture-owner@demo.invalid'
            if User.objects.filter(username=email).exists():
                self.stdout.write('Owner fixture already exists; data left unchanged.')
                return
            user=User.objects.create_user(username=email,email=email,password=PASSWORD,role='employer',email_confirmed=True)
            record_processing(user,source='synthetic_owner_dashboard_seed')
            company=Company.objects.create(user=user,name='Демо · Студия приложений',contact_email=email)
            people=[Recruiter.objects.create(company=company,name=name) for name in ['Анна Морозова','Дмитрий Волков','Елена Соколова']]
            now=timezone.now()
            candidates={}
            for grade in ['Junior','Middle']:
                candidates[grade]=[]
                for number,name in enumerate(NAMES,1):
                    candidate_email=f'fixture-owner-candidate-{grade.lower()}-{number:02}@demo.invalid'
                    candidate=User.objects.create_user(username=candidate_email,email=candidate_email,password=PASSWORD,
                        role='candidate',email_confirmed=True)
                    record_processing(candidate,source='synthetic_owner_dashboard_seed')
                    profile=Profile.objects.create(user=candidate,name=f'{name} · Демо {grade}',desired_grade=grade,
                        skills='Swift, SwiftUI',published=True,contact_email=candidate_email,
                        publication_consented_at=now,publication_consent_version=PUBLICATION_VERSION)
                    ConsentEvent.objects.create(user=candidate,purpose='publication',version=PUBLICATION_VERSION,
                        granted=True,source='synthetic_owner_dashboard_seed')
                    tasks=copy.deepcopy(BANK[(grade,'A')])
                    attempt=Attempt.objects.create(candidate=profile,grade=grade,variant='A',bank_version=VERSION,
                        tasks=tasks,started_at=now,expires_at=now+timedelta(minutes=15))
                    save_answers(profile,attempt.pk,{task['id']:task['correct'] for task in tasks},finish=True)
                    profile.refresh_from_db()
                    candidates[grade].append(profile)
            index=0
            for number,(grade,title) in enumerate([('Junior','iOS / SwiftUI · Junior'),('Middle','iOS / SwiftUI · Middle'),('Junior','iOS / UIKit · Junior')]):
                need=Need.objects.create(company=company,recruiter=people[number],title=title,grade=grade,skills='Swift, SwiftUI',
                    tasks='Разработка демонстрационного приложения',salary_min=120000,salary_max=200000,work_format='remote')
                for profile in candidates[grade]:
                    offer=invite(company,need.pk,profile.pk)
                    age=2+(index*7)%28
                    created=now-timedelta(days=age)
                    status='accepted' if index%10<4 else 'declined' if index%10<6 else 'sent'
                    Invitation.objects.filter(pk=offer.pk).update(created_at=created,status=status,
                        viewed_at=created+timedelta(hours=3) if index%10<8 else None,
                        responded_at=created+timedelta(days=1+index%2) if status!='sent' else None)
                    index+=1
            self.stdout.write(self.style.SUCCESS('Synthetic owner dashboard ready: fixture-owner@demo.invalid. No existing company activity changed.'))
