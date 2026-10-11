"""Independent acceptance of optional preferences, immutable offers and shared rights."""
import json
from io import BytesIO
from types import SimpleNamespace
from django.test import TestCase, SimpleTestCase, Client
from django.utils import timezone
from pypdf import PdfReader
from accounts.models import User
from api.core import issue_token
from api.drafts import prepare, apply
from api.serializers import profile_data, invitation_data
from hiring.models import Company, Need
from hiring.forms import NeedForm, SearchForm
from hiring.services import invite, decide, search, rank
from profiles.forms import ProfileForm
from profiles.models import Profile
from profiles.views import build_pdf
from profiles.conditions import compare_conditions, snapshot_conditions


def pdf_text(response):
    data=b''.join(response.streaming_content)
    response.close()
    return '\n'.join(p.extract_text() for p in PdfReader(BytesIO(data)).pages)


class ConditionRulesTests(SimpleTestCase):
    def profile(self, **values):
        return SimpleNamespace(preferred_work_formats=['remote','hybrid'],
            preferred_employment_types=['full_time'], preferred_task_types=['development','testing'], **values)

    def test_full_match_alternatives_and_rating_disclaimer(self):
        p=self.profile()
        n=SimpleNamespace(work_format='hybrid',employment_type='full_time',task_types=['testing','development'])
        value=compare_conditions(p,n)
        self.assertEqual([r['key'] for r in value['matches']],['work_format','employment_type','task_types'])
        self.assertEqual(value['unknown'],[]);self.assertEqual(value['conflicts'],[])
        self.assertIn('не подтверждают навыки',value['note'])

    def test_explicit_conflict_partial_tasks_and_missing_are_distinct(self):
        p=self.profile()
        n=SimpleNamespace(work_format='office',employment_type='',task_types=['development','support'])
        value=compare_conditions(p,n)
        self.assertEqual([r['key'] for r in value['conflicts']],['work_format','task_types'])
        self.assertEqual([r['key'] for r in value['unknown']],['employment_type'])
        self.assertEqual(value['matches'],[])
        self.assertIn('Часть',value['conflicts'][1]['reason'])

    def test_no_need_and_no_preferences_never_match(self):
        p=SimpleNamespace(preferred_work_formats=[],preferred_employment_types=[],preferred_task_types=[])
        n=SimpleNamespace(work_format='remote',employment_type='',task_types=[])
        for need in [None,n]:
            value=compare_conditions(p,need)
            self.assertEqual(len(value['unknown']),3)
            self.assertFalse(value['matches']);self.assertFalse(value['conflicts'])

    def test_corrupt_or_free_text_values_are_unknown_and_never_projected(self):
        p=SimpleNamespace(preferred_work_formats='remote',preferred_employment_types={'secret':'x'},preferred_task_types=['contact@demo.invalid',{'phone':'x'}])
        value=compare_conditions(p,SimpleNamespace(work_format='remote',employment_type='full_time',task_types=['development']))
        self.assertEqual(len(value['unknown']),3)
        self.assertNotIn('contact@',json.dumps(value))
        self.assertNotIn('phone',json.dumps(value))
        legacy=snapshot_conditions({'work_format':'Удалённо','candidate_preferences':'private text'})
        self.assertEqual(len(legacy['unknown']),3)


class ConditionsJourneyTests(TestCase):
    def setUp(self):
        def user(name,role):
            return User.objects.create_user(username=name+'@demo.invalid',role=role,email_confirmed=True,
                processing_consented_at=timezone.now(),processing_consent_version='processing-v1')
        self.actor=user('conditions-candidate','candidate')
        self.profile=Profile.objects.create(user=self.actor,name='Анна',city='Москва',skills='Swift',
            published=True,confirmed_grade='Junior',test_score=.75,description='PRIVATE_DESCRIPTION',
            contact_email='PRIVATE_CONTACT@demo.invalid',contact_phone='PRIVATE_PHONE',
            preferred_work_formats=['remote'],preferred_employment_types=['full_time'],preferred_task_types=['development'])
        self.employer=user('conditions-employer','employer');self.other=user('conditions-other','employer')
        self.company=Company.objects.create(user=self.employer,name='Компания',contact_email='company@demo.invalid')
        self.foreign=Company.objects.create(user=self.other,name='Другая')
        self.need=Need.objects.create(company=self.company,title='iOS',grade='Junior',skills='Swift',tasks='Задачи',
            salary_min=100000,salary_max=150000,work_format='remote',employment_type='full_time',task_types=['development'])
        self.foreign_need=Need.objects.create(company=self.foreign,title='Другая',grade='Junior',tasks='Задачи',
            salary_min=1,salary_max=2,work_format='office')
        self.web=Client();self.web.force_login(self.employer)
        _,secret=issue_token(self.employer,'Conditions','mcp')
        self.api=Client(HTTP_AUTHORIZATION='Bearer '+secret)

    def test_optional_form_fields_clear_without_changing_grade_and_reject_unknown_codes(self):
        data={'name':'Анна','city':'Москва','desired_grade':'Junior','published':'on',
              'preferred_work_formats':['remote','remote','office'],'preferred_employment_types':['project'],
              'preferred_task_types':['testing']}
        form=ProfileForm(data,instance=self.profile)
        self.assertTrue(form.is_valid(),form.errors)
        saved=form.save();self.assertEqual(saved.preferred_work_formats,['remote','office'])
        self.assertEqual(saved.confirmed_grade,'Junior');self.assertEqual(saved.test_score,.75)
        for key in ['preferred_work_formats','preferred_employment_types','preferred_task_types']:
            bad=ProfileForm({**data,key:['hidden@example.invalid']},instance=saved)
            self.assertFalse(bad.is_valid());self.assertIn(key,bad.errors)
        empty=ProfileForm({'name':'Анна','desired_grade':'Junior'},instance=saved)
        self.assertTrue(empty.is_valid(),empty.errors)
        saved=empty.save();self.assertEqual(saved.preferred_work_formats,[])
        self.assertEqual(saved.preferred_employment_types,[]);self.assertEqual(saved.preferred_task_types,[])

    def test_browser_profile_and_need_save_with_invalid_atomic_rejection(self):
        self.web.force_login(self.actor)
        response=self.web.post('/profile/',{'name':'Анна','desired_grade':'Junior','published':'on',
            'preferred_work_formats':['hybrid'],'preferred_employment_types':['part_time'],'preferred_task_types':['testing']})
        self.assertEqual(response.status_code,302)
        self.profile.refresh_from_db();self.assertEqual(self.profile.preferred_work_formats,['hybrid'])
        self.web.force_login(self.employer)
        data={'company_name':'Компания','company_email':'company@demo.invalid','title':'Новая','grade':'Junior','tasks':'Задачи',
            'salary_min':1,'salary_max':2,'work_format':'hybrid','employment_type':'part_time','task_types':['testing'],'next_step':'Встреча'}
        self.assertEqual(self.web.post('/company/needs/',data).status_code,302)
        obj=Need.objects.get(title='Новая');self.assertEqual(obj.employment_type,'part_time');self.assertEqual(obj.task_types,['testing'])
        count=Need.objects.count()
        self.assertEqual(self.web.post('/company/needs/',{**data,'company_name':'Не сохранять','employment_type':'PRIVATE'}).status_code,200)
        self.company.refresh_from_db();self.assertEqual(self.company.name,'Компания');self.assertEqual(Need.objects.count(),count)
        minimal=NeedForm({k:v for k,v in data.items() if k not in {'employment_type','task_types'}},company=self.company)
        self.assertTrue(minimal.is_valid(),minimal.errors)
        self.assertEqual(minimal.cleaned_data['employment_type'],'');self.assertEqual(minimal.cleaned_data['task_types'],[])

    def test_filters_preserve_unknown_category_and_original_ranking(self):
        p2=Profile.objects.create(user=User.objects.create_user(username='conditions-conflict',role='candidate'),
            name='Иван',published=True,confirmed_grade='Junior',test_score=.75,skills='Swift',preferred_work_formats=['office'])
        p3=Profile.objects.create(user=User.objects.create_user(username='conditions-unknown',role='candidate'),
            name='Пётр',published=True,confirmed_grade='Junior',test_score=.75,skills='Swift')
        baseline=[r['id'] for r in search('Junior',self.need)]
        self.assertEqual(baseline,[self.profile.pk,p2.pk,p3.pk])
        self.assertEqual([r['id'] for r in search('Junior',self.need,conditions='matched')],[self.profile.pk])
        self.assertEqual([r['id'] for r in search('Junior',self.need,conditions='compatible')],[self.profile.pk,p3.pk])
        self.assertEqual([r['id'] for r in search('Junior',self.need,conditions='conflicts')],[p2.pk])
        self.assertEqual(rank(self.profile,self.need),(73.75,{'test':63.75,'skills':10.0,'fsp':0}))
        self.assertEqual(search('Middle',self.need,conditions='compatible'),[])
        invalid=SearchForm({'grade':'Junior','conditions':'matched'},company=self.company)
        self.assertFalse(invalid.is_valid())
        self.assertEqual(self.api.get('/api/v1/candidates',{'grade':'Junior','conditions':'matched'}).status_code,400)
        self.assertEqual(self.api.get('/api/v1/candidates',{'need_id':self.need.pk,'conditions':'invalid'}).status_code,400)

    def test_shared_browser_api_explanations_before_contact_and_foreign_need(self):
        response=self.web.get(f'/candidates/{self.profile.pk}/',{'need':self.need.pk})
        self.assertContains(response,'Условия до контакта');self.assertContains(response,'Полная занятость')
        self.assertNotContains(response,'PRIVATE_CONTACT');self.assertNotContains(response,'PRIVATE_DESCRIPTION')
        response=self.api.get(f'/api/v1/candidates/{self.profile.pk}',{'need_id':self.need.pk})
        self.assertEqual(response.status_code,200)
        value=response.json()['data'];self.assertEqual(len(value['explanation']['conditions']['matches']),3)
        self.assertFalse(value['contacts_allowed']);self.assertNotIn('PRIVATE',json.dumps(value))
        self.assertEqual(value['profile']['preferred_task_types'],['development'])
        for route,key in [(f'/candidates/{self.profile.pk}/','need'),(f'/api/v1/candidates/{self.profile.pk}','need_id')]:
            client=self.api if route.startswith('/api/') else self.web
            self.assertEqual(client.get(route,{key:self.foreign_need.pk}).status_code,404)
        self.assertEqual(self.api.get('/api/v1/candidates',{'need_id':self.need.pk,'conditions':'matched'}).json()['pagination']['total'],1)

    def test_invitation_condition_snapshot_is_immutable_for_both_roles_and_mcp(self):
        obj=invite(self.company,self.need.pk,self.profile.pk);initial=json.loads(json.dumps(obj.snapshot))
        self.profile.preferred_work_formats=['office'];self.profile.save()
        self.need.work_format='hybrid';self.need.task_types=['support'];self.need.save()
        duplicate=invite(self.company,self.need.pk,self.profile.pk)
        self.assertEqual(duplicate.snapshot,initial)
        value=invitation_data(duplicate,mcp=True)
        self.assertEqual(len(value['conditions']['matches']),3)
        self.assertNotIn('PRIVATE',json.dumps(value));self.assertEqual(value['conditions']['matches'][0]['required'],['remote'])
        for actor in [self.actor,self.employer]:
            self.web.force_login(actor)
            response=self.web.get('/invitations/')
            self.assertContains(response,'зафиксированы при отправке');self.assertContains(response,'Полная занятость')
            self.assertNotContains(response,'PRIVATE_CONTACT')
        self.assertEqual(len(compare_conditions(self.profile,self.need)['conflicts']),2)

    def test_legacy_and_poisoned_snapshot_are_safe_unknowns(self):
        obj=invite(self.company,self.need.pk,self.profile.pk)
        for key in ['candidate_preferences','employment_type','task_types','work_format_code']:obj.snapshot.pop(key,None)
        value=invitation_data(obj,mcp=True)
        self.assertEqual(len(value['conditions']['unknown']),3)
        obj.snapshot.update(employment_type={'secret':'PRIVATE'},task_types=['PRIVATE'],
            candidate_preferences={'work_formats':['remote','PRIVATE'],'task_types':['PRIVATE']})
        value=invitation_data(obj,mcp=True)
        self.assertNotIn('PRIVATE',json.dumps(value));self.assertEqual(value['employment_type'],'')
        self.assertEqual(value['task_types'],[])

    def test_pdf_conditions_before_acceptance_and_company_scoped_rights(self):
        public=self.web.get(f'/candidates/{self.profile.pk}/resume.pdf',{'need':self.need.pk})
        text=pdf_text(public)
        self.assertIn('Полная занятость',text);self.assertIn('Совпадения',text);self.assertIn('iOS',text)
        self.assertNotIn('PRIVATE_CONTACT',text);self.assertNotIn('PRIVATE_DESCRIPTION',text)
        self.assertEqual(self.web.get(f'/candidates/{self.profile.pk}/resume.pdf',{'need':self.foreign_need.pk}).status_code,404)
        self.assertEqual(self.web.get(f'/candidates/{self.profile.pk}/resume.pdf',{'need':'invalid'}).status_code,404)
        own_text='\n'.join(p.extract_text() for p in PdfReader(build_pdf(self.profile,include_contacts=True)).pages)
        self.assertIn('PRIVATE_CONTACT',own_text);self.assertIn('Предпочтения',own_text)
        _,secret=issue_token(self.employer,'PDF','cli',contacts=True)
        cli=Client(HTTP_AUTHORIZATION='Bearer '+secret)
        path=f'/api/v1/candidates/{self.profile.pk}/resume.pdf'
        self.assertEqual(cli.get(path,{'need_id':self.need.pk,'with_contacts':'true'}).status_code,403)
        self.assertIn('Полная занятость',pdf_text(cli.get(path,{'need_id':self.need.pk})))
        self.assertEqual(cli.get(path,{'need_id':self.foreign_need.pk}).status_code,404)
        self.assertEqual(self.api.get(path,{'need_id':self.need.pk}).status_code,403)
        obj=invite(self.company,self.need.pk,self.profile.pk);decide(self.profile,obj.pk,'accepted')
        self.assertIn('PRIVATE_CONTACT',pdf_text(cli.get(path,{'need_id':self.need.pk,'with_contacts':'true'})))
        self.web.force_login(self.other)
        self.assertNotIn('PRIVATE_CONTACT',pdf_text(self.web.get(f'/candidates/{self.profile.pk}/resume.pdf')))

    def test_profile_draft_approval_updates_preferences_only_after_browser_acknowledgement(self):
        token,secret=issue_token(self.actor,'Draft','mcp',drafts=True)
        api=Client(HTTP_AUTHORIZATION='Bearer '+secret)
        payload={'preferred_work_formats':['hybrid'],'preferred_task_types':['testing']}
        response=api.post('/api/v1/drafts',{'kind':'profile.update','payload':payload},content_type='application/json')
        self.assertEqual(response.status_code,201)
        draft=response.json()['data'];self.assertEqual(draft['preview'],payload)
        self.profile.refresh_from_db();self.assertEqual(self.profile.preferred_work_formats,['remote'])
        self.web.force_login(self.actor)
        page='/drafts/'+draft['id']+'/'
        self.assertEqual(self.web.post(page,{'action':'apply','acknowledge':'on'}).status_code,302)
        self.profile.refresh_from_db();self.assertEqual(self.profile.preferred_work_formats,['hybrid'])
        self.assertEqual(self.profile.preferred_task_types,['testing']);self.assertEqual(self.profile.confirmed_grade,'Junior')
        self.assertEqual(self.web.post(page,{'action':'apply','acknowledge':'on'}).status_code,302)
        self.assertEqual(api.post('/api/v1/drafts',{'kind':'profile.update','payload':{'preferred_work_formats':['PRIVATE']}},content_type='application/json').status_code,400)

    def test_need_draft_conditions_and_stale_invitation_profile(self):
        token,_=issue_token(self.employer,'Draft','mcp',drafts=True)
        draft=prepare(self.employer,token,'need.update',self.need.pk,{'employment_type':'project','task_types':['testing']})
        apply(self.employer,draft.pk);self.need.refresh_from_db()
        self.assertEqual(self.need.employment_type,'project');self.assertEqual(self.need.task_types,['testing'])
        draft=prepare(self.employer,token,'invitation.send',self.need.pk,{'candidate_id':self.profile.pk})
        self.profile.preferred_work_formats=['office'];self.profile.save()
        from api.core import ApiError
        with self.assertRaises(ApiError) as error:apply(self.employer,draft.pk)
        self.assertEqual(error.exception.code,'DRAFT_STALE')
        from hiring.models import Invitation
        self.assertEqual(Invitation.objects.count(),0)

    def test_safe_catalog_and_privacy_notice_cover_preferences(self):
        value=self.api.get('/api/v1/catalog').json()['data']
        self.assertEqual(value['work_formats']['remote'],'Удалённо')
        self.assertEqual(value['employment_types']['full_time'],'Полная занятость')
        self.assertIn('conditions-v1',value['features'])
        self.assertContains(self.web.get('/accounts/privacy/'),'предпочтений по формату работы/занятости/типам задач')
        self.assertEqual(profile_data(self.profile)['preferred_work_formats'],['remote'])
