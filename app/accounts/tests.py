from datetime import timedelta
from django.test import TestCase, Client
from django.utils import timezone
from django.db import OperationalError
from unittest.mock import patch
from .models import User, DemoConfirmation, ConsentEvent

class RegistrationTests(TestCase):
    def register(self, client=None, email='candidate@demo.invalid', role='candidate'):
        client = client or self.client
        return client.post('/accounts/register/', {'email':email,'role':role,'processing_consent':'on','password1':'Synthetic-password-2026!','password2':'Synthetic-password-2026!'})

    def test_demo_domain_and_role_validation(self):
        for email, role in [('real@example.org','candidate'),('ok@demo.invalid','administrator')]:
            self.assertEqual(self.register(email=email,role=role).status_code,200)
        self.assertEqual(User.objects.count(),0)

    def test_confirmation_is_bound_to_originating_session_and_single_use(self):
        self.assertEqual(self.register().status_code,302)
        token = self.client.session['pending_registration']['token']
        other = Client()
        self.assertEqual(other.get('/accounts/confirm/').status_code,404)
        self.assertEqual(other.post('/accounts/confirm/', {'token':token}).status_code,404)
        self.assertFalse(User.objects.get().is_active)
        self.assertEqual(self.client.post('/accounts/confirm/', {'token':token}).status_code,302)
        user=User.objects.get();self.assertTrue(user.email_confirmed);self.assertTrue(user.is_active)
        self.assertEqual(self.client.post('/accounts/confirm/', {'token':token}).status_code,404)
        self.assertEqual(self.client.get('/profile/').status_code,200)

    def test_expired_or_wrong_token_rejected(self):
        self.register()
        token=self.client.session['pending_registration']['token']
        self.assertEqual(self.client.post('/accounts/confirm/',{'token':'wrong'}).status_code,400)
        item=DemoConfirmation.objects.get();item.expires_at=timezone.now()-timedelta(seconds=1);item.save()
        self.assertEqual(self.client.post('/accounts/confirm/',{'token':token}).status_code,400)
        self.assertFalse(User.objects.get().email_confirmed)

    def test_another_pending_registration_cannot_use_first_token(self):
        self.register()
        token=self.client.session['pending_registration']['token']
        other=Client();self.register(other,email='other@demo.invalid')
        self.assertEqual(other.post('/accounts/confirm/',{'token':token}).status_code,400)

    def test_csrf_required_for_registration(self):
        client=Client(enforce_csrf_checks=True)
        self.assertEqual(self.register(client).status_code,403)

    def test_unconfirmed_account_cannot_login(self):
        self.register()
        client=Client()
        client.post('/accounts/login/',{'username':'candidate@demo.invalid','password':'Synthetic-password-2026!'})
        self.assertNotIn('_auth_user_id',client.session)

    def test_health_checks_schema_without_mutating_user_data(self):
        before=list(User.objects.values())
        self.assertEqual(self.client.get('/health/').json(),{'status':'ok'})
        self.assertEqual(list(User.objects.values()),before)
        self.assertContains(self.client.get('/accounts/login/'),'data-testid="login-form"')

    def test_failed_database_is_503_even_when_version_is_reachable(self):
        with patch('accounts.models.User.objects.exists',side_effect=OperationalError('private database location')):
            response=self.client.get('/health/')
            self.assertEqual(response.status_code,503)
            self.assertEqual(response.json(),{'status':'unavailable'})
            self.assertNotContains(response,'private database location',status_code=503)
            self.assertEqual(self.client.get('/version/').status_code,200)

    def test_registration_requires_unchecked_explicit_processing_consent(self):
        response=self.client.get('/accounts/register/')
        self.assertFalse(response.context['form'].fields['processing_consent'].initial)
        response=self.client.post('/accounts/register/',{'email':'new@demo.invalid','role':'candidate',
            'password1':'Synthetic-password-2026!','password2':'Synthetic-password-2026!'})
        self.assertEqual(response.status_code,200);self.assertEqual(User.objects.count(),0)
        self.register();user=User.objects.get()
        self.assertTrue(user.has_processing_consent)
        self.assertEqual(ConsentEvent.objects.get().version,'processing-v1')
        self.assertFalse(user.profile.published)

    def test_existing_user_gates_require_consent_without_automatic_grant(self):
        from profiles.models import Profile
        user=User.objects.create_user(username='old@demo.invalid',role='candidate',email_confirmed=True)
        Profile.objects.create(user=user);self.client.force_login(user)
        for url in ['/','/profile/','/assessments/','/assistant/','/invitations/']:
            self.assertRedirects(self.client.get(url),'/accounts/consent/')
        self.assertEqual(self.client.post('/accounts/consent/',{}).status_code,200)
        user.refresh_from_db();self.assertFalse(user.has_processing_consent)
        self.assertEqual(self.client.post('/accounts/consent/',{'processing_consent':'on'}).status_code,302)
        self.client.post('/accounts/consent/',{'processing_consent':'on'})
        self.assertEqual(ConsentEvent.objects.count(),1)
        user.refresh_from_db();self.assertTrue(user.has_processing_consent)
        self.assertEqual(self.client.get('/profile/').status_code,200)

    def test_synthetic_seed_marks_source_and_preserves_existing_accounts(self):
        from django.core.management import call_command
        from io import StringIO
        from profiles.models import Profile
        old=User.objects.create_user(username='fixture-junior-01@demo.invalid',role='candidate',email_confirmed=True)
        Profile.objects.create(user=old)
        call_command('seed_demo',stdout=StringIO())
        old.refresh_from_db();self.assertFalse(old.has_processing_consent)
        count=ConsentEvent.objects.count();self.assertGreater(count,0)
        self.assertEqual(set(ConsentEvent.objects.values_list('source',flat=True)),{'synthetic_demo_seed'})
        call_command('seed_demo',stdout=StringIO());self.assertEqual(ConsentEvent.objects.count(),count)
