from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase,Client
from django.utils import timezone
from accounts.models import User
from profiles.models import Profile
from hiring.models import Company,Need
from assessments.services import start_attempt,save_answers
from .models import Usage,Draft

class AssistantTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user(username='helper@demo.invalid',role='candidate',email_confirmed=True,processing_consented_at=timezone.now(),processing_consent_version="processing-v1")
        self.profile=Profile.objects.create(user=self.user,name='Кандидат',skills='Swift',contact_email='private@demo.invalid')
        self.client.force_login(self.user)

    def test_mock_explicit_and_context_has_no_contacts(self):
        with patch('assistant.provider.generate',return_value='Мок помощника') as generate:
            response=self.client.post('/assistant/',{'mode':'profile'})
            self.assertEqual(response.status_code,200)
            self.assertEqual(generate.call_args.args,('profile',{'skills':'Swift'}))
        response=self.client.post('/assistant/',{'mode':'profile'})
        self.assertContains(response,'внешний AI не вызывался');self.assertNotContains(response,'private@demo.invalid')
        self.profile.refresh_from_db();self.assertEqual(self.profile.confirmed_grade,'')

    def test_limit_and_hour_reset(self):
        for _ in range(10):self.assertEqual(self.client.post('/assistant/',{'mode':'profile'}).status_code,200)
        self.assertEqual(self.client.post('/assistant/',{'mode':'profile'}).status_code,429)
        usage=Usage.objects.get();usage.window_start=timezone.now()-timedelta(hours=2);usage.save()
        self.assertEqual(self.client.post('/assistant/',{'mode':'profile'}).status_code,200)
        usage.refresh_from_db();self.assertEqual(usage.count,1)

    def test_failure_does_not_block_profile(self):
        with patch('assistant.provider.generate',side_effect=RuntimeError('private provider failure')):
            response=self.client.post('/assistant/',{'mode':'profile'})
            self.assertEqual(response.status_code,503);self.assertNotContains(response,'private provider failure',status_code=503)
        self.assertEqual(self.client.get('/profile/').status_code,200)

    def test_active_exam_blocks_all_assistance(self):
        obj=start_attempt(self.profile,'Junior')
        with patch('assistant.provider.generate') as generate:
            self.assertEqual(self.client.post('/assistant/',{'mode':'profile'}).status_code,409)
            generate.assert_not_called()
        answers={q['id']:q['correct'] for q in obj.tasks};save_answers(self.profile,obj.pk,answers,finish=True)
        self.assertEqual(self.client.post('/assistant/',{'mode':'result','identifier':obj.pk}).status_code,200)

    def test_foreign_or_unfinished_result_and_role_rejected(self):
        other=User.objects.create_user(username='other-helper@demo.invalid',role='candidate',email_confirmed=True,processing_consented_at=timezone.now(),processing_consent_version="processing-v1")
        profile=Profile.objects.create(user=other);obj=start_attempt(profile,'Junior')
        save_answers(profile,obj.pk,{q['id']:q['correct'] for q in obj.tasks},finish=True)
        self.assertEqual(self.client.post('/assistant/',{'mode':'result','identifier':obj.pk}).status_code,404)
        self.assertEqual(self.client.post('/assistant/',{'mode':'need'}).status_code,403)
        self.assertEqual(self.client.post('/assistant/',{'mode':'result','identifier':'bad'}).status_code,404)

    def test_employer_need_draft_is_owned_and_does_not_include_contacts(self):
        employer=User.objects.create_user(username='company-helper@demo.invalid',role='employer',email_confirmed=True,processing_consented_at=timezone.now(),processing_consent_version="processing-v1")
        company=Company.objects.create(user=employer,contact_email='company-private@demo.invalid')
        need=Need.objects.create(company=company,title='iOS',grade='Junior',skills='Swift',tasks='Задачи',salary_min=100,salary_max=200,work_format='remote')
        self.client.force_login(employer)
        with patch('assistant.provider.generate',return_value='Мок') as generate:
            response=self.client.post('/assistant/',{'mode':'need','identifier':need.pk});self.assertEqual(response.status_code,200)
            self.assertEqual(generate.call_args.args,('need',{'grade':'Junior','skills':'Swift'}))
            for value in ['²','١','9'*198,str(2**63),'-1']:
                self.assertEqual(self.client.post('/assistant/',
                    {'mode':'need','identifier':value}).status_code,404)
            self.assertEqual(generate.call_count,1)
        self.assertEqual(self.client.post('/assistant/',{'mode':'profile'}).status_code,403)

    def test_malformed_context_ids_return_404_without_provider_calls(self):
        with patch('assistant.provider.generate') as generate:
            for value in ['²', '١', '-1', '0', '9'*198, str(2**63), 'abc']:
                with self.subTest(value=value):
                    self.assertEqual(self.client.post('/assistant/',
                        {'mode':'result','identifier':value}).status_code,404)
                    self.assertEqual(self.client.get('/assistant/',{'attempt':value}).status_code,404)
            generate.assert_not_called()

    def test_empty_optional_identifier_preserves_latest_own_result(self):
        obj=start_attempt(self.profile,'Junior')
        save_answers(self.profile,obj.pk,{q['id']:q['correct'] for q in obj.tasks},finish=True)
        self.assertEqual(self.client.post('/assistant/',{'mode':'result','identifier':''}).status_code,200)


class DraftTests(TestCase):
    def setUp(self):
        self.candidate=User.objects.create_user(username='draft-candidate@demo.invalid',role='candidate',
            email_confirmed=True,processing_consented_at=timezone.now(),processing_consent_version='processing-v1')
        self.profile=Profile.objects.create(user=self.candidate,skills='Swift',description='Исходное описание',
            confirmed_grade='Junior',test_score=.75,published=True,contact_email='private@demo.invalid')
        self.employer=User.objects.create_user(username='draft-employer@demo.invalid',role='employer',
            email_confirmed=True,processing_consented_at=timezone.now(),processing_consent_version='processing-v1')
        self.company=Company.objects.create(user=self.employer,name='Исходная компания',contact_email='company@demo.invalid',description='О компании')
        self.values={'title':'Проверенная роль','grade':'Middle','skills':'Core Data, Swift',
            'tasks':'Отредактированные задачи','salary_min':100000,'salary_max':200000,'work_format':'hybrid',
            'next_step':'Разговор с командой','company_name':'Проверенная компания','company_email':'new@demo.invalid'}

    def generate(self,mode='profile',**values):
        self.client.force_login(self.candidate if mode=='profile' else self.employer)
        response=self.client.post('/assistant/',{'mode':mode,**values})
        self.assertEqual(response.status_code,200)
        return response.context['draft']

    def test_profile_review_and_apply_changes_only_own_description(self):
        draft=self.generate()
        self.profile.refresh_from_db();self.assertEqual(self.profile.description,'Исходное описание')
        self.assertContains(self.client.get(f'/assistant/drafts/{draft.pk}/'),'Проверил черновик — применить')
        result=self.client.post(f'/assistant/drafts/{draft.pk}/',{'description':'Проверенное описание',
            'confirmed_grade':'Middle','published':'','contact_email':'stolen@demo.invalid','user':self.employer.pk})
        self.assertRedirects(result,'/profile/')
        self.profile.refresh_from_db();self.assertEqual(self.profile.description,'Проверенное описание')
        self.assertEqual((self.profile.confirmed_grade,self.profile.test_score,self.profile.published,self.profile.contact_email),
            ('Junior',.75,True,'private@demo.invalid'))
        draft.refresh_from_db();self.assertIsNotNone(draft.applied_at);self.assertEqual(draft.payload,{'description':'Проверенное описание'})
        usage=Usage.objects.get(user=self.candidate);self.assertEqual(usage.count,1)
        self.assertRedirects(self.client.post(f'/assistant/drafts/{draft.pk}/',{'description':'Повтор'}),'/profile/')
        self.profile.refresh_from_db();self.assertEqual(self.profile.description,'Проверенное описание')
        usage.refresh_from_db();self.assertEqual(usage.count,1)

    def test_new_employer_can_start_before_need_and_validate_then_edit(self):
        draft=self.generate('need',new_need='on',grade='Junior',skills='Swift')
        self.assertFalse(Need.objects.exists())
        self.assertEqual(draft.payload['salary_min'],None)
        bad=self.client.post(f'/assistant/drafts/{draft.pk}/',{'title':'Нельзя сохранить'})
        self.assertEqual(bad.status_code,400);self.assertFalse(Need.objects.exists())
        self.company.refresh_from_db();self.assertEqual(self.company.name,'Исходная компания')
        response=self.client.post(f'/assistant/drafts/{draft.pk}/',{**self.values,'company':999,'source_need':999})
        self.assertRedirects(response,'/company/needs/')
        need=Need.objects.get();self.assertEqual(need.company,self.company);self.assertEqual(need.grade,'Middle')
        self.assertEqual(need.skills,'Swift, CoreData');self.assertEqual(need.tasks,self.values['tasks'])
        self.company.refresh_from_db();self.assertEqual(self.company.name,self.values['company_name'])
        self.assertEqual(self.company.description,'О компании')
        draft.refresh_from_db();self.assertEqual(draft.applied_need,need);self.assertNotIn('company_email',draft.payload)
        self.assertRedirects(self.client.post(f'/assistant/drafts/{draft.pk}/',{}),'/company/needs/')
        self.assertEqual(Need.objects.count(),1)

    def test_fresh_account_without_company_has_no_target_write_until_apply(self):
        self.company.delete()
        draft=self.generate('need',new_need='on')
        self.assertFalse(Company.objects.filter(user=self.employer).exists())
        self.assertEqual(self.client.get(f'/assistant/drafts/{draft.pk}/').status_code,200)
        self.assertEqual(self.client.post(f'/assistant/drafts/{draft.pk}/',{}).status_code,400)
        self.assertFalse(Company.objects.filter(user=self.employer).exists())
        self.assertRedirects(self.client.post(f'/assistant/drafts/{draft.pk}/',self.values),'/company/needs/')
        self.assertEqual(Company.objects.filter(user=self.employer).count(),1)

    def test_saved_draft_can_be_resumed_from_owned_history(self):
        draft=self.generate()
        page=self.client.get('/assistant/');self.assertContains(page,'Ваши последние черновики')
        self.assertContains(page,f'href="/assistant/drafts/{draft.pk}/"')
        self.client.force_login(self.employer)
        self.assertNotContains(self.client.get('/assistant/'),f'href="/assistant/drafts/{draft.pk}/"')

    def test_existing_need_is_owned_seed_and_is_not_modified(self):
        original=Need.objects.create(company=self.company,title='Исходная роль',grade='Junior',skills='Swift',
            tasks='Исходные задачи',salary_min=10,salary_max=20,work_format='remote')
        draft=self.generate('need',identifier=original.pk)
        self.assertEqual(draft.source_need,original);self.assertEqual(draft.payload['salary_min'],10)
        self.assertRedirects(self.client.post(f'/assistant/drafts/{draft.pk}/',self.values),'/company/needs/')
        original.refresh_from_db();self.assertEqual(original.tasks,'Исходные задачи');self.assertEqual(original.salary_min,10)
        self.assertEqual(Need.objects.count(),2)
        fresh=self.generate('need',new_need='on',grade='Middle',skills='SwiftUI')
        self.assertIsNone(fresh.source_need);self.assertIsNone(fresh.payload['salary_min'])

    def test_foreign_draft_and_source_and_malformed_ids(self):
        draft=self.generate()
        self.client.force_login(self.employer)
        for method in (self.client.get,self.client.post):
            self.assertEqual(method(f'/assistant/drafts/{draft.pk}/').status_code,404)
            for ident in ('0','abc','²',str(2**63),'9'*198):
                self.assertEqual(method(f'/assistant/drafts/{ident}/').status_code,404)
        company=Company.objects.create(user=User.objects.create_user(username='foreign-source@demo.invalid',role='employer'))
        need=Need.objects.create(company=company,title='Чужая',grade='Junior',skills='Swift',tasks='Задачи',salary_min=1,salary_max=2,work_format='remote')
        self.assertEqual(self.client.post('/assistant/',{'mode':'need','identifier':need.pk}).status_code,404)
        self.assertEqual(self.client.get('/assistant/',{'mode':'need','need':need.pk}).status_code,404)
        self.assertEqual(self.client.get('/assistant/',{'mode':'profile'}).status_code,403)

    def test_expiry_replay_and_manual_change_protection(self):
        draft=self.generate();draft.expires_at=timezone.now()-timedelta(seconds=1);draft.save()
        self.assertEqual(self.client.post(f'/assistant/drafts/{draft.pk}/',{'description':'Позднее'}).status_code,410)
        self.assertNotContains(self.client.get(f'/assistant/drafts/{draft.pk}/'),'Проверил черновик — применить')
        second=self.generate();self.profile.description='Ручное обновление';self.profile.save()
        result=self.client.post(f'/assistant/drafts/{second.pk}/',{'description':'Устаревший текст'})
        self.assertEqual(result.status_code,409);self.profile.refresh_from_db();self.assertEqual(self.profile.description,'Ручное обновление')
        second.refresh_from_db();self.assertIsNone(second.applied_at)

    def test_active_test_and_request_limit_do_not_bypass_apply_guard(self):
        draft=self.generate();obj=start_attempt(self.profile,'Junior')
        self.assertEqual(self.client.post(f'/assistant/drafts/{draft.pk}/',{'description':'Запрещённый текст'}).status_code,409)
        save_answers(self.profile,obj.pk,{q['id']:q['correct'] for q in obj.tasks},finish=True)
        usage=Usage.objects.get(user=self.candidate);usage.count=10;usage.save()
        self.assertEqual(self.client.post('/assistant/',{'mode':'profile'}).status_code,429)
        self.assertRedirects(self.client.post(f'/assistant/drafts/{draft.pk}/',{'description':'Проверенный текст'}),'/profile/')
        usage.refresh_from_db();self.assertEqual(usage.count,10)

    def test_invalid_salary_and_profile_text_never_partially_save(self):
        draft=self.generate('need',new_need='on')
        for values in ({**self.values,'salary_min':300000},{**self.values,'salary_max':0},{**self.values,'skills':'Unknown'}):
            self.assertEqual(self.client.post(f'/assistant/drafts/{draft.pk}/',values).status_code,400)
        self.assertFalse(Need.objects.exists());self.company.refresh_from_db();self.assertEqual(self.company.name,'Исходная компания')
        profile_draft=self.generate()
        for text in ('','x'*3001):
            self.assertEqual(self.client.post(f'/assistant/drafts/{profile_draft.pk}/',{'description':text}).status_code,400)
        self.profile.refresh_from_db();self.assertEqual(self.profile.description,'Исходное описание')

    def test_provider_failure_and_invalid_prompt_create_no_draft(self):
        self.client.force_login(self.employer)
        with patch('assistant.provider.generate') as generate:
            self.assertEqual(self.client.post('/assistant/',{'mode':'need','grade':'Senior'}).status_code,400)
            self.assertEqual(self.client.post('/assistant/',{'mode':'need','skills':'Unknown'}).status_code,400)
            generate.assert_not_called()
        with patch('assistant.provider.generate',side_effect=RuntimeError('secret error')):
            response=self.client.post('/assistant/',{'mode':'need','new_need':'on'})
            self.assertEqual(response.status_code,503);self.assertContains(response,'Заполнить потребность вручную',status_code=503)
            self.assertNotContains(response,'secret error',status_code=503)
        self.assertFalse(Draft.objects.exists());self.assertFalse(Need.objects.exists())

    def test_blank_hidden_identifier_and_csrf_and_processing_consent(self):
        self.client.force_login(self.employer)
        page=self.client.get('/assistant/');self.assertContains(page,'name="identifier" value=""');self.assertNotContains(page,'value="None"')
        draft=self.generate('need',new_need='on')
        protected=Client(enforce_csrf_checks=True);protected.force_login(self.employer)
        self.assertEqual(protected.post(f'/assistant/drafts/{draft.pk}/',self.values).status_code,403)
        self.employer.processing_consent_version='old';self.employer.save()
        self.assertRedirects(self.client.get(f'/assistant/drafts/{draft.pk}/'),'/accounts/consent/')
        self.assertRedirects(self.client.post(f'/assistant/drafts/{draft.pk}/',self.values),'/accounts/consent/')
        self.assertFalse(Need.objects.exists())

    def test_source_reassignment_is_rejected(self):
        need=Need.objects.create(company=self.company,title='Роль',grade='Junior',skills='Swift',tasks='Задачи',salary_min=1,salary_max=2,work_format='remote')
        draft=self.generate('need',identifier=need.pk)
        other=Company.objects.create(user=User.objects.create_user(username='moved-source@demo.invalid',role='employer'))
        need.company=other;need.save()
        self.assertEqual(self.client.post(f'/assistant/drafts/{draft.pk}/',self.values).status_code,409)
        self.assertEqual(Need.objects.count(),1)
