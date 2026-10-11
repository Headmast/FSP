import unittest
from mcp import Client
from fsp_client.mcp import build_server
from fsp_client.http import ClientError


class FakeApi:
    def __init__(self,role='candidate',kind='mcp'):
        self.role,self.kind=role,kind
        self.calls=[]
    def get(self,path,**params):
        self.calls.append((path,params))
        data={'id':1,'role':self.role,'token_kind':self.kind,'scopes':[self.role+'.read']} if path=='me' else {'id':1,'published':True}
        return {'data':data,'meta':{'api_version':'1','data_mode':'demo','request_id':'test'}}


class McpTests(unittest.IsolatedAsyncioTestCase):
    async def test_roles_schemas_and_official_sdk_calls(self):
        for role in ['candidate','employer']:
            api=FakeApi(role)
            async with Client(build_server(api)) as client:
                result=await client.list_tools()
                names=[t.name for t in result.tools]
                self.assertNotIn('fsp_get_contacts',names)
                expected='fsp_get_profile' if role=='candidate' else 'fsp_search_candidates'
                self.assertIn(expected,names)
                self.assertNotIn('fsp_search_candidates' if role=='candidate' else 'fsp_get_profile',names)
                for tool in result.tools:
                    self.assertIsNotNone(tool.output_schema)
                    self.assertTrue(tool.annotations.read_only_hint)
                call=await client.call_tool('fsp_get_me')
                self.assertFalse(call.is_error)
                self.assertEqual(call.structured_content['data']['role'],role)
                invalid=await client.call_tool('fsp_get_invitation',{'id':-1})
                self.assertTrue(invalid.is_error)
                self.assertFalse(any(path=='invitations/-1' for path,_ in api.calls))

    async def test_rejects_cli_credentials(self):
        with self.assertRaises(ClientError):build_server(FakeApi(kind='cli'))


if __name__=='__main__':unittest.main()

class DraftApi(FakeApi):
    def __init__(self,role='candidate',draft=True):
        super().__init__(role);self.draft=draft
    def get(self,path,**params):
        result=super().get(path,**params)
        if path=='me' and self.draft:result['data']['scopes'].append(self.role+'.draft')
        if path=='catalog':result['data']={'features':['read','drafts']}
        return result
    def request(self,method,path,data):
        self.calls.append((path,data))
        return {'data':{'kind':data.get('kind'),'approval_path':'/drafts/example/'},'meta':{'api_version':'1','data_mode':'demo'}}

class DraftMcpTests(unittest.IsolatedAsyncioTestCase):
    async def test_candidate_scope_and_preparation_without_apply_or_contacts(self):
        api=DraftApi()
        async with Client(build_server(api)) as client:
            tools=(await client.list_tools()).tools
            names=[t.name for t in tools]
            self.assertIn('fsp_prepare_profile',names)
            self.assertFalse(any('apply' in name for name in names))
            prepare=next(t for t in tools if t.name=='fsp_prepare_profile')
            self.assertFalse(prepare.annotations.read_only_hint)
            result=await client.call_tool('fsp_prepare_profile',{'changes':{'city':'Москва'}})
            self.assertFalse(result.is_error)
            self.assertEqual(api.calls[-1][1]['payload'],{'city':'Москва'})
            count=len(api.calls)
            result=await client.call_tool('fsp_prepare_profile',{'changes':{'contact_email':'hidden@example.invalid'}})
            self.assertTrue(result.is_error);self.assertEqual(len(api.calls),count)
            result=await client.call_tool('fsp_prepare_invitation_response',{'id':2,'decision':'accept'})
            self.assertFalse(result.is_error)
            self.assertEqual(api.calls[-1][1],{'kind':'invitation.accept','target_id':2,'payload':{}})
        async with Client(build_server(DraftApi(draft=False))) as client:
            names=[t.name for t in (await client.list_tools()).tools]
            self.assertIn('fsp_get_draft',names);self.assertNotIn('fsp_prepare_profile',names)

    async def test_employer_typed_preparation_and_role_isolation(self):
        api=DraftApi('employer')
        async with Client(build_server(api)) as client:
            names=[t.name for t in (await client.list_tools()).tools]
            self.assertIn('fsp_prepare_company',names);self.assertNotIn('fsp_prepare_profile',names)
            result=await client.call_tool('fsp_prepare_company',{'changes':{'name':'Команда'}})
            self.assertFalse(result.is_error)
            result=await client.call_tool('fsp_prepare_need_create',{'need':{'title':'Разработчик','grade':'Junior',
                'tasks':'Разработка','salary_min':100000,'salary_max':150000,'work_format':'remote'}})
            self.assertFalse(result.is_error)
            self.assertEqual(api.calls[-1][1]['kind'],'need.create')
            result=await client.call_tool('fsp_prepare_invitation',{'need_id':1,'candidate_id':2,'accepted_attempts':[3]})
            self.assertFalse(result.is_error)
            self.assertEqual(api.calls[-1][1]['target_id'],1)
            self.assertEqual(api.calls[-1][1]['payload']['accepted_attempts'],[3])
            before=len(api.calls)
            result=await client.call_tool('fsp_prepare_company',{'changes':{'contact_email':'hidden@example.invalid'}})
            self.assertTrue(result.is_error);self.assertEqual(len(api.calls),before)


class ConditionsMcpTests(unittest.IsolatedAsyncioTestCase):
    async def test_preferences_and_typed_filters_through_official_sdk(self):
        api=DraftApi()
        async with Client(build_server(api)) as client:
            result=await client.call_tool('fsp_prepare_profile',{'changes':{'preferred_work_formats':['remote'],
                'preferred_employment_types':['part_time'],'preferred_task_types':['testing']}})
            self.assertFalse(result.is_error)
            self.assertEqual(api.calls[-1][1]['payload']['preferred_work_formats'],['remote'])
            before=len(api.calls)
            result=await client.call_tool('fsp_prepare_profile',{'changes':{'preferred_task_types':['hidden@demo.invalid']}})
            self.assertTrue(result.is_error);self.assertEqual(len(api.calls),before)
        api=DraftApi('employer')
        async with Client(build_server(api)) as client:
            result=await client.call_tool('fsp_search_candidates',{'need_id':2,'conditions':'compatible'})
            self.assertFalse(result.is_error);self.assertEqual(api.calls[-1][1]['conditions'],'compatible')
            result=await client.call_tool('fsp_prepare_need_update',{'id':2,'changes':{'employment_type':'project','task_types':['support']}})
            self.assertFalse(result.is_error);self.assertEqual(api.calls[-1][1]['payload']['task_types'],['support'])
            before=len(api.calls)
            result=await client.call_tool('fsp_search_candidates',{'need_id':2,'conditions':'PRIVATE'})
            self.assertTrue(result.is_error);self.assertEqual(len(api.calls),before)
