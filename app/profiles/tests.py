from django.test import TestCase
from accounts.models import User
from .models import Profile, Experience
from .views import build_pdf
from .skills import normalized,validate_skills
from django.core.exceptions import ValidationError

class ProfileTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user(username='owner@demo.invalid',password='synthetic',role='candidate',email_confirmed=True)
        self.profile=Profile.objects.create(user=self.user,name='Алексей Демо',contact_email='private@demo.invalid',confirmed_grade='Junior',test_score=.75)
        self.other=User.objects.create_user(username='other@demo.invalid',password='synthetic',role='candidate',email_confirmed=True)
        self.other_profile=Profile.objects.create(user=self.other,name='Другой Демо')
        self.client.force_login(self.user)

    def test_only_own_profile_is_modified_and_server_fields_ignored(self):
        response=self.client.post('/profile/',{'id':self.other_profile.pk,'name':'Алексей','city':'Москва','skills':'Swift, UIKit',
            'contact_email':'mine@demo.invalid','contact_phone':'','desired_grade':'Middle','published':'on','confirmed_grade':'Middle','test_score':'1'})
        self.assertEqual(response.status_code,302)
        self.profile.refresh_from_db();self.other_profile.refresh_from_db()
        self.assertEqual(self.profile.confirmed_grade,'Junior');self.assertEqual(self.profile.test_score,.75)
        self.assertEqual(self.other_profile.name,'Другой Демо')

    def test_contact_text_cannot_be_saved_as_skills(self):
        self.client.post('/profile/',{'name':'Алексей','city':'Москва','skills':'private@demo.invalid','desired_grade':'Junior'})
        self.profile.refresh_from_db();self.assertEqual(self.profile.skills,'')

    def test_contacts_cannot_be_published_as_name_or_city(self):
        for field in ['name', 'city']:
            data={'name':'Алексей','city':'Москва','skills':'Swift','desired_grade':'Junior'}
            data[field]='private@demo.invalid'
            response=self.client.post('/profile/',data)
            self.assertEqual(response.status_code,200)
            self.profile.refresh_from_db()
            self.assertNotEqual(getattr(self.profile,field),'private@demo.invalid')

    def test_employer_cannot_access_candidate_self_service(self):
        employer=User.objects.create_user(username='employer@demo.invalid',role='employer',email_confirmed=True)
        self.client.force_login(employer)
        for url in ['/profile/','/profile/resume.pdf','/profile/fsp/']:
            self.assertEqual(self.client.get(url).status_code,403)

    def test_pdf_and_fsp_contract(self):
        response=self.client.get('/profile/resume.pdf');self.assertEqual(response.status_code,200)
        self.assertTrue(b''.join(response.streaming_content).startswith(b'%PDF'))
        self.assertEqual(self.client.get('/profile/fsp/').json(),{'source':'mock','status':'not_connected','changes_grade':False})

    def test_skill_aliases_save_one_canonical_value_and_unknown_is_rejected(self):
        self.assertEqual(normalized('CoreData, Core Data, CORE DATA'),{'coredata'})
        self.assertEqual(validate_skills('Core Data, CoreData, swift'),'Swift, CoreData')
        self.assertEqual(self.client.post('/profile/',{'name':'Алексей','city':'Москва',
            'skills':'Core Data, CoreData','desired_grade':'Junior'}).status_code,302)
        self.profile.refresh_from_db();self.assertEqual(self.profile.skills,'CoreData')
        with self.assertRaises(ValidationError):validate_skills('Unknown skill')

    def full_data(self):
        return {'name':'Алексей', 'city':'Москва', 'skills':'Swift', 'desired_grade':'Junior',
            'specialization':'ios_swift', 'experience_months':'24', 'roles':['developer','reviewer'],
            'soft_skills':['teamwork'], 'description':'Черновик private@demo.invalid',
            'experience-TOTAL_FORMS':'1', 'experience-INITIAL_FORMS':'0',
            'experience-0-organization':'Проект Демо', 'experience-0-role':'Разработчик',
            'experience-0-months':'12', 'experience-0-description':'Разработка SwiftUI'}

    def test_complete_profile_and_experience_persist_and_reload(self):
        self.assertEqual(self.client.post('/profile/',self.full_data()).status_code,302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.experience_months,24)
        self.assertEqual(self.profile.roles,['developer','reviewer'])
        self.assertEqual(self.profile.soft_skills,['teamwork'])
        self.assertEqual(self.profile.experiences.get().description,'Разработка SwiftUI')
        self.assertContains(self.client.get('/profile/'),'Черновик private@demo.invalid')
        self.assertContains(self.client.get('/profile/'),'Проект Демо')

    def test_invalid_public_fields_and_experience_are_atomic(self):
        for field,value in [('experience_months','601'),('roles',['private@demo.invalid']),
                            ('soft_skills',['private@demo.invalid']),('experience-0-months','-1')]:
            with self.subTest(field=field):
                data=self.full_data();data[field]=value
                self.assertEqual(self.client.post('/profile/',data).status_code,200)
                self.profile.refresh_from_db();self.assertEqual(self.profile.experience_months,0)
                self.assertEqual(Experience.objects.count(),0)

    def test_foreign_experience_id_cannot_be_modified(self):
        other=Experience.objects.create(profile=self.other_profile,organization='Другой',role='Разработчик',months=6)
        data=self.full_data();data.update({'experience-INITIAL_FORMS':'1','experience-0-id':str(other.pk)})
        self.assertEqual(self.client.post('/profile/',data).status_code,200)
        other.refresh_from_db();self.assertEqual(other.organization,'Другой')
        self.assertEqual(self.profile.experiences.count(),0)
