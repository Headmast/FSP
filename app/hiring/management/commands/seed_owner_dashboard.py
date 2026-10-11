"""Isolated synthetic owner account; never add activity to existing companies."""
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone
from accounts.models import User
from accounts.consents import record_processing
from profiles.models import Profile
from hiring.models import Company, Recruiter, Need, Invitation
from hiring.services import invite
from .seed_demo import PASSWORD


class Command(BaseCommand):
    help='Create a separate synthetic owner dashboard. Existing owner fixture is left unchanged.'

    def handle(self,*args,**options):
        call_command('seed_demo',stdout=self.stdout)
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
            index=0
            for number,(grade,title) in enumerate([('Junior','iOS / SwiftUI · Junior'),('Middle','iOS / SwiftUI · Middle'),('Junior','iOS / UIKit · Junior')]):
                need=Need.objects.create(company=company,recruiter=people[number],title=title,grade=grade,skills='Swift, SwiftUI',
                    tasks='Разработка демонстрационного приложения',salary_min=120000,salary_max=200000,work_format='remote')
                for profile in Profile.objects.filter(user__username__startswith='fixture-'+grade.lower()+'-',confirmed_grade=grade,published=True).order_by('pk')[:10]:
                    offer=invite(company,need.pk,profile.pk)
                    age=2+(index*7)%28
                    created=now-timedelta(days=age)
                    status='accepted' if index%10<4 else 'declined' if index%10<6 else 'sent'
                    Invitation.objects.filter(pk=offer.pk).update(created_at=created,status=status,
                        viewed_at=created+timedelta(hours=3) if index%10<8 else None,
                        responded_at=created+timedelta(days=1+index%2) if status!='sent' else None)
                    index+=1
            self.stdout.write(self.style.SUCCESS('Synthetic owner dashboard ready: fixture-owner@demo.invalid. No existing company activity changed.'))
