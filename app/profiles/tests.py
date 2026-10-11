from django.test import TestCase
from accounts.models import User
from .models import Profile
from .views import build_pdf

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
