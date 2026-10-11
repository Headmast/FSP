from datetime import timedelta
from django.test import TestCase, Client
from django.utils import timezone
from accounts.models import User, ApiToken
from accounts.consents import record_processing
from profiles.models import Profile
from .core import issue_token, ApiError


class ApiFixture(TestCase):
    def user(self, role='candidate', label='person'):
        user = User.objects.create_user(username=label+'@demo.invalid', email=label+'@demo.invalid',
            role=role, email_confirmed=True, password='Synthetic-2026!')
        record_processing(user)
        if role == 'candidate':
            Profile.objects.create(user=user, name='Иван', city='Москва', skills='Swift', published=True,
                confirmed_grade='Junior', test_score=.875, contact_email='hidden@demo.invalid',
                contact_phone='+70000000000', description='hidden@demo.invalid')
        return user

    def setUp(self):
        self.actor = self.user()
        self.token, self.secret = issue_token(self.actor, 'Test', 'cli')
        self.client.defaults['HTTP_AUTHORIZATION'] = 'Bearer '+self.secret

    def get(self, path, **params):
        return self.client.get('/api/v1/'+path, params)


class TokenTests(ApiFixture):
    def test_token_guards(self):
        self.assertEqual(self.get('me').status_code, 200)
        self.assertNotIn(self.secret, self.token.digest)
        self.token.revoked_at = timezone.now(); self.token.save()
        self.assertEqual(self.get('me').status_code, 401)
        self.token.revoked_at = None; self.token.expires_at = timezone.now()-timedelta(seconds=1); self.token.save()
        self.assertEqual(self.get('me').status_code, 401)

    def test_scope_role_consent_and_rate(self):
        self.actor.processing_consent_version = 'old'; self.actor.save()
        self.assertEqual(self.get('me').json()['error']['code'], 'CONSENT_REQUIRED')
        record_processing(self.actor)
        self.token.window_start=timezone.now(); self.token.request_count=60; self.token.save()
        response=self.get('me'); self.assertEqual(response.status_code,429); self.assertEqual(response['Retry-After'],'60')
        self.token.request_count=0; self.token.save()
        self.actor.role='employer'; self.actor.save()
        self.assertEqual(self.get('me').status_code,403)

    def test_web_secret_once_revoke_owner_and_csrf(self):
        self.client.force_login(self.actor)
        response=self.client.post('/accounts/integrations/', {'action':'create','name':'Desktop','kind':'mcp'})
        self.assertEqual(response.status_code,200)
        secret=response.context['secret']; self.assertTrue(secret.startswith('fsp_'))
        self.assertNotContains(self.client.get('/accounts/integrations/'),secret)
        secure=Client(enforce_csrf_checks=True); secure.force_login(self.actor)
        self.assertEqual(secure.post('/accounts/integrations/',{'action':'revoke','id':self.token.pk}).status_code,403)
        other=self.user(label='other'); other_token,_=issue_token(other,'Other','cli')
        self.assertEqual(self.client.post('/accounts/integrations/',{'action':'revoke','id':other_token.pk}).status_code,404)
        self.client.post('/accounts/integrations/',{'action':'revoke','id':self.token.pk})
        self.assertEqual(self.get('me').status_code,401)

    def test_mcp_never_contacts_and_read_only_method(self):
        with self.assertRaises(ApiError):issue_token(self.actor,'AI','mcp',contacts=True)
        self.assertEqual(self.client.post('/api/v1/me').status_code,405)
        self.assertNotIn('email', self.get('me').json()['data'])
