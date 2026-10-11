from datetime import timedelta
from django.test import TestCase, Client
from django.utils import timezone
from django.db import OperationalError
from unittest.mock import patch
from .models import User, DemoConfirmation

class RegistrationTests(TestCase):
    def register(self, client=None, email='candidate@demo.invalid', role='candidate'):
        client = client or self.client
        return client.post('/accounts/register/', {'email':email,'role':role,'password1':'Synthetic-password-2026!','password2':'Synthetic-password-2026!'})

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
