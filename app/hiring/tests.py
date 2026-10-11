from django.utils import timezone
from django.test import TestCase,Client
from accounts.models import User
from profiles.models import Profile
from .models import Company,Need,Invitation
from .services import search,invite,decide,contacts_allowed,rank
from .forms import NeedForm

class HiringTests(TestCase):
    def setUp(self):
        self.candidate=User.objects.create_user(username='candidate@demo.invalid',role='candidate',email_confirmed=True,processing_consented_at=timezone.now(),processing_consent_version="processing-v1")
        self.profile=Profile.objects.create(user=self.candidate,name='Алексей',city='Москва',skills='Swift, SwiftUI',published=True,
            confirmed_grade='Junior',test_score=.75,contact_email='private@demo.invalid',contact_phone='+70000000000')
        self.employer=User.objects.create_user(username='employer@demo.invalid',role='employer',email_confirmed=True,processing_consented_at=timezone.now(),processing_consent_version="processing-v1")
        self.company=Company.objects.create(user=self.employer,name='Компания Демо',contact_email='company@demo.invalid')
        self.other=User.objects.create_user(username='other-company@demo.invalid',role='employer',email_confirmed=True,processing_consented_at=timezone.now(),processing_consent_version="processing-v1")
        self.other_company=Company.objects.create(user=self.other,name='Другая Демо')
        self.need=Need.objects.create(company=self.company,title='iOS',grade='Junior',skills='SwiftUI',tasks='Развитие приложения',salary_min=100000,salary_max=150000,work_format='remote')
        self.other_need=Need.objects.create(company=self.other_company,title='iOS',grade='Junior',skills='Swift',tasks='Развитие',salary_min=100000,salary_max=150000,work_format='remote')
        self.client.force_login(self.employer)

    def test_contacts_hidden_in_html_until_acceptance_and_only_for_sender(self):
        url=f'/candidates/{self.profile.pk}/'
        self.assertNotContains(self.client.get(url),'private@demo.invalid')
        self.assertNotContains(self.client.get(url),'+70000000000')
        obj=invite(self.company,self.need.pk,self.profile.pk)
        self.assertNotContains(self.client.get(url),'private@demo.invalid')
        decide(self.profile,obj.pk,'accepted')
        self.assertContains(self.client.get(url),'private@demo.invalid')
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(url),'private@demo.invalid')
        self.assertFalse(contacts_allowed(self.other_company,self.profile))

    def test_decline_does_not_unlock_and_cannot_be_reversed(self):
        obj=invite(self.company,self.need.pk,self.profile.pk);decide(self.profile,obj.pk,'declined')
        self.assertFalse(contacts_allowed(self.company,self.profile))
        with self.assertRaises(ValueError):decide(self.profile,obj.pk,'accepted')

    def test_duplicate_invites_and_replies_are_idempotent_and_keep_snapshot(self):
        obj=invite(self.company,self.need.pk,self.profile.pk)
        self.need.salary_min=120000;self.need.save()
        self.assertEqual(invite(self.company,self.need.pk,self.profile.pk).pk,obj.pk)
        self.assertEqual(Invitation.objects.count(),1);obj.refresh_from_db();self.assertEqual(obj.snapshot['salary_min'],100000)
        first=decide(self.profile,obj.pk,'accepted');second=decide(self.profile,obj.pk,'accepted')
        self.assertEqual(first.responded_at,second.responded_at)

    def test_foreign_need_and_forged_id_denied(self):
        for need in [str(self.other_need.pk),'abc']:
            self.assertEqual(self.client.post('/invitations/send/',{'candidate':self.profile.pk,'need':need}).status_code,404)
        self.assertEqual(Invitation.objects.count(),0)

    def test_other_candidate_cannot_respond_or_see_invitation(self):
        obj=invite(self.company,self.need.pk,self.profile.pk)
        foreign=User.objects.create_user(username='foreign@demo.invalid',role='candidate',email_confirmed=True,processing_consented_at=timezone.now(),processing_consent_version="processing-v1")
        Profile.objects.create(user=foreign);self.client.force_login(foreign)
        self.assertEqual(self.client.post(f'/invitations/{obj.pk}/accept/').status_code,404)
        self.assertNotContains(self.client.get('/invitations/'),'Компания Демо')
        obj.refresh_from_db();self.assertEqual(obj.status,'sent')

    def test_roles_and_csrf_protect_offer_actions(self):
        self.client.force_login(self.candidate)
        self.assertEqual(self.client.get('/candidates/').status_code,403)
        self.assertEqual(self.client.post('/invitations/send/').status_code,403)
        secure=Client(enforce_csrf_checks=True);secure.force_login(self.employer)
        self.assertEqual(secure.post('/invitations/send/',{'candidate':self.profile.pk,'need':self.need.pk}).status_code,403)

    def test_only_published_confirmed_correct_category_and_filters(self):
        for grade,published in [('',True),('Middle',True),('Junior',False)]:
            user=User.objects.create_user(username=f'hidden-{grade}-{published}@demo.invalid',role='candidate',email_confirmed=True,processing_consented_at=timezone.now(),processing_consent_version="processing-v1")
            Profile.objects.create(user=user,name='Скрытый',confirmed_grade=grade,published=published)
        rows=search('Junior',self.need)
        self.assertEqual([row['id'] for row in rows],[self.profile.pk])
        self.assertNotIn('contact_email',rows[0]);self.assertNotIn('user',rows[0])
        self.assertEqual(search('Junior',self.need,skill='Combine'),[])
        self.assertEqual(search('Junior',self.need,fsp='demo_history'),[])
        response=self.client.get(f'/candidates/?need={self.need.pk}&grade=Junior&skill=Combine')
        self.assertContains(response,'Кандидатов не найдено');self.assertContains(response,'value="Combine" selected')

    def test_ranking_parts_and_fsp_do_not_change_grade(self):
        self.profile.fsp_status='demo_history';self.profile.fsp_prize=True;self.profile.save()
        score,parts=rank(self.profile,self.need)
        self.assertEqual(score,78.75);self.assertEqual(parts,{'test':63.75,'skills':10,'fsp':5})
        self.profile.refresh_from_db();self.assertEqual(self.profile.confirmed_grade,'Junior')
        self.assertEqual(rank(self.profile,None)[1]['skills'],0)

    def test_invalid_salary_rejected(self):
        base={'company_name':'Демо','title':'iOS','grade':'Junior','skills':'Swift','tasks':'Задачи','work_format':'remote','next_step':'Знакомство'}
        for minimum,maximum in [(0,100),(-1,100),(200,100)]:
            self.assertFalse(NeedForm({**base,'salary_min':minimum,'salary_max':maximum}).is_valid())

    def test_candidate_marked_viewed_only_on_own_inbox(self):
        obj=invite(self.company,self.need.pk,self.profile.pk)
        self.client.force_login(self.candidate);self.client.get('/invitations/')
        obj.refresh_from_db();self.assertIsNotNone(obj.viewed_at)

    def test_malformed_ids_never_reach_orm_or_create_invitation(self):
        for value in ['²', '١', '-1', '0', '9'*198, str(2**63), 'abc']:
            with self.subTest(value=value):
                self.assertEqual(self.client.get('/candidates/', {'need':value}).status_code,404)
                self.assertEqual(self.client.post('/invitations/send/',
                    {'need':value, 'candidate':self.profile.pk}).status_code,404)
                self.assertEqual(self.client.post('/invitations/send/',
                    {'need':self.need.pk, 'candidate':value}).status_code,404)
        self.assertEqual(Invitation.objects.count(),0)

    def test_optional_empty_need_keeps_default_and_foreign_need_denied(self):
        self.assertContains(self.client.get('/candidates/',{'need':''}),self.profile.name)
        self.assertEqual(self.client.get('/candidates/',{'need':self.other_need.pk}).status_code,404)
        for field in ['need','candidate']:
            data={'need':self.need.pk,'candidate':self.profile.pk}
            data[field]=''
            self.assertEqual(self.client.post('/invitations/send/',data).status_code,404)

    def test_skill_aliases_have_identical_filter_and_rank_without_double_weight(self):
        self.profile.skills='Core Data, CoreData';self.profile.save()
        self.need.skills='Core Data, CoreData';self.need.save()
        canonical=search('Junior',self.need,skill='CoreData')
        alias=search('Junior',self.need,skill='Core Data')
        self.assertEqual(canonical,alias);self.assertEqual(len(alias),1)
        self.assertEqual(alias[0]['parts']['skills'],10)
        self.assertContains(self.client.get('/candidates/',{'need':self.need.pk,'grade':'Junior','skill':'Core Data'}),self.profile.name)
        data={'company_name':'Демо','title':'iOS','grade':'Junior','skills':'Core Data, CoreData',
            'tasks':'Задачи','salary_min':100,'salary_max':200,'work_format':'remote','next_step':'Встреча'}
        form=NeedForm(data);self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(form.cleaned_data['skills'],'CoreData')

    def test_existing_skill_alias_data_is_migrated_without_losing_other_fields(self):
        from django.apps import apps
        from django.db import connection
        from importlib import import_module
        from types import SimpleNamespace
        self.profile.skills='Core Data, CoreData, Swift';self.profile.save()
        self.need.skills='Core Data, CoreData';self.need.save()
        import_module('profiles.migrations.0002_canonical_skills').canonicalize(
            apps,SimpleNamespace(connection=connection))
        self.profile.refresh_from_db();self.need.refresh_from_db()
        self.assertEqual(self.profile.skills,'CoreData, Swift')
        self.assertEqual(self.need.skills,'CoreData')
        self.assertEqual(self.profile.contact_email,'private@demo.invalid')
        self.assertEqual(self.profile.confirmed_grade,'Junior')

    def test_free_text_experience_is_hidden_until_grant_in_employer_html(self):
        from profiles.models import Experience
        self.profile.description='Описание private@demo.invalid';self.profile.save()
        Experience.objects.create(profile=self.profile,organization='private@demo.invalid',role='Разработчик',months=6,description='+70000000000')
        url=f'/candidates/{self.profile.pk}/'
        self.assertNotContains(self.client.get(url),'private@demo.invalid')

        obj=invite(self.company,self.need.pk,self.profile.pk);decide(self.profile,obj.pk,'accepted')
        self.assertContains(self.client.get(url),'Описание private@demo.invalid')
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(url),'private@demo.invalid')

    def test_company_profile_is_owned_and_invitation_keeps_description_snapshot(self):
        self.assertEqual(self.client.post('/company/',{'id':self.other_company.pk,'name':'Компания Новая',
            'industry':'Разработка приложений','description':'Делаем продукты на Swift','contact_email':'hello@demo.invalid'}).status_code,302)
        self.company.refresh_from_db();self.other_company.refresh_from_db()
        self.assertEqual(self.other_company.name,'Другая Демо')
        self.assertEqual(self.company.industry,'Разработка приложений')
        obj=invite(self.company,self.need.pk,self.profile.pk)
        self.company.description='Другое описание';self.company.contact_email='new@demo.invalid';self.company.save()
        self.client.force_login(self.candidate)
        response=self.client.get('/invitations/')
        self.assertContains(response,'Делаем продукты на Swift');self.assertContains(response,'hello@demo.invalid')
        self.assertNotContains(response,'Другое описание')
        self.assertEqual(self.client.get('/company/').status_code,403)
        obj.refresh_from_db();self.assertEqual(obj.status,'sent')

    def test_company_contact_required_by_service_and_http_send(self):
        from django.core.exceptions import ValidationError
        for email in ['', 'invalid']:
            self.company.contact_email=email;self.company.save()
            with self.assertRaises(ValidationError):invite(self.company,self.need.pk,self.profile.pk)
            self.assertRedirects(self.client.post('/invitations/send/',{'need':self.need.pk,'candidate':self.profile.pk}),'/company/')
            self.assertEqual(Invitation.objects.count(),0)
        self.company.contact_email='valid@demo.invalid';self.company.save()
        obj=invite(self.company,self.need.pk,self.profile.pk)
        self.company.contact_email='';self.company.save()
        self.assertEqual(invite(self.company,self.need.pk,self.profile.pk).pk,obj.pk)

    def test_withdrawing_publication_hides_search_but_keeps_prior_accepted_grant(self):
        obj=invite(self.company,self.need.pk,self.profile.pk);decide(self.profile,obj.pk,'accepted')
        self.client.force_login(self.candidate)
        self.client.post('/profile/',{'name':'Алексей','city':'Москва','skills':'Swift','desired_grade':'Junior','contact_email':'private@demo.invalid','contact_phone':'+70000000000'})
        self.profile.refresh_from_db();self.assertFalse(self.profile.published)
        self.assertEqual(search('Junior',self.need),[])
        self.client.force_login(self.employer)
        self.assertContains(self.client.get(f'/candidates/{self.profile.pk}/'),'private@demo.invalid')
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(f'/candidates/{self.profile.pk}/').status_code,404)
