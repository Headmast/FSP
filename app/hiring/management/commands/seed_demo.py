import copy
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from accounts.models import User,ConsentEvent
from accounts.consents import record_processing,PUBLICATION_VERSION
from profiles.models import Profile
from assessments.bank import BANK,VERSION
from assessments.models import Attempt
from assessments.services import save_answers
from hiring.models import Company,Need

PASSWORD='Fsp-demo-2026!'  # Public synthetic fixture credential; never use for real accounts.
NAMES=['Алексей','Борис','Виктор','Глеб','Дмитрий','Егор','Женя','Илья','Кирилл','Лев']
SKILLS=['Swift, SwiftUI, Combine','Swift, UIKit, XCTest','Swift, SwiftUI, Git']

class Command(BaseCommand):
    help='Create 24 synthetic candidates and 3 needs without overwriting existing fixture accounts.'
    @transaction.atomic
    def handle(self,*args,**options):
        for grade,suffix in [('Junior','Юниор'),('Middle','Мидл')]:
            for index,name in enumerate(NAMES):
                email=f'fixture-{grade.lower()}-{index+1:02}@demo.invalid'
                user,created=User.objects.get_or_create(username=email,defaults={'email':email,'role':'candidate','email_confirmed':True})
                if not created:continue
                user.set_password(PASSWORD);user.save();record_processing(user,source='synthetic_demo_seed')
                profile=Profile.objects.create(user=user,name=f'{name} {suffix}',city='Москва',skills=SKILLS[index%3],
                    contact_email=email,contact_phone='+70000000000',published=True,publication_consented_at=timezone.now(),publication_consent_version=PUBLICATION_VERSION,
                    fsp_status='demo_history' if index%4 in (0,2) else 'no_history',fsp_prize=index%4==0)
                ConsentEvent.objects.create(user=user,purpose='publication',version=PUBLICATION_VERSION,granted=True,source='synthetic_demo_seed')
                now=timezone.now();tasks=copy.deepcopy(BANK[(grade,'A')])
                obj=Attempt.objects.create(candidate=profile,grade=grade,variant='A',bank_version=VERSION,tasks=tasks,
                    started_at=now,expires_at=now+timedelta(minutes=15))
                wrong=() if index<3 else (0,) if index<6 else (0,2)
                answers={task['id']:(task['correct']+1)%4 if n in wrong else task['correct'] for n,task in enumerate(tasks)}
                save_answers(profile,obj.pk,answers,finish=True)
        for index,label in enumerate(['Один','Два','Три','Четыре']):
            email=f'fixture-unconfirmed-{index+1}@demo.invalid'
            user,created=User.objects.get_or_create(username=email,defaults={'email':email,'role':'candidate','email_confirmed':True})
            if created:
                user.set_password(PASSWORD);user.save();record_processing(user,source='synthetic_demo_seed')
                Profile.objects.create(user=user,name='Неподтверждённый '+label,city='Москва',skills='Swift, SwiftUI, Combine, UIKit, Git',published=True,publication_consented_at=timezone.now(),publication_consent_version=PUBLICATION_VERSION,contact_email=email,fsp_status='demo_history',fsp_prize=True)
                ConsentEvent.objects.create(user=user,purpose='publication',version=PUBLICATION_VERSION,granted=True,source='synthetic_demo_seed')
        companies=[]
        for label,name in [('alpha','Демо Альфа'),('beta','Демо Бета')]:
            email=f'fixture-company-{label}@demo.invalid'
            user,created=User.objects.get_or_create(username=email,defaults={'email':email,'role':'employer','email_confirmed':True})
            if created:
                user.set_password(PASSWORD);user.save();record_processing(user,source='synthetic_demo_seed')
            company,_=Company.objects.get_or_create(user=user,defaults={'name':name,'contact_email':email})
            companies.append(company)
        for company,title,grade,skills in [(companies[0],'iOS SwiftUI Junior','Junior','SwiftUI, Combine'),
            (companies[0],'iOS SwiftUI Middle','Middle','SwiftUI, Git'),(companies[1],'iOS UIKit Junior','Junior','Swift, UIKit')]:
            Need.objects.get_or_create(company=company,title=title,defaults={'grade':grade,'skills':skills,'tasks':'Развитие демонстрационного приложения',
                'salary_min':120000 if grade=='Junior' else 250000,'salary_max':180000 if grade=='Junior' else 350000,
                'work_format':'remote','next_step':'Знакомство с командой'})
        self.stdout.write(self.style.SUCCESS('Synthetic fixtures ready: 10 Junior, 10 Middle, 4 unconfirmed, 3 needs. Existing accounts preserved.'))
