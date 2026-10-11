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
