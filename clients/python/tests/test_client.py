import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch
import httpx
from fsp_client.http import FspClient,ClientError,server_url
from fsp_client.cli import parser,run
from fsp_client.config import Connections


class ClientTests(unittest.TestCase):
    def test_no_redirect_or_cross_origin_credentials(self):
        requests=[]
        def handle(request):
            requests.append(request)
            return httpx.Response(302,headers={'Location':'https://other.invalid/api/v1/me'})
        client=FspClient('https://demo.invalid','synthetic',transport=httpx.MockTransport(handle))
        with self.assertRaises(ClientError):client.get('me')
        self.assertEqual(len(requests),1)
        self.assertEqual(str(requests[0].url),'https://demo.invalid/api/v1/me')
        for value in ['http://demo.invalid','https://user:password@demo.invalid','https://demo.invalid?token=x']:
            with self.assertRaises(ClientError):server_url(value)
        client.close()

    def test_error_exit_codes_do_not_print_token(self):
        for status,code in [(400,2),(401,3),(403,3),(404,4),(409,4),(503,5)]:
            client=FspClient('https://demo.invalid','synthetic',transport=httpx.MockTransport(lambda r:httpx.Response(status,json={'error':{'code':'TEST','message':'Example'}})))
            with self.assertRaises(ClientError) as error:client.get('me')
            self.assertEqual(error.exception.exit_code,code)
            self.assertNotIn('synthetic',str(error.exception))
            client.close()

    def test_commands_and_json_output(self):
        requests=[]
        def handle(request):
            requests.append(str(request.url))
            return httpx.Response(200,json={'data':[{'id':1}],'meta':{'api_version':'1','data_mode':'demo'}})
        api=FspClient('https://demo.invalid','synthetic',transport=httpx.MockTransport(handle))
        with patch.object(Connections,'load',return_value=({'server':'https://demo.invalid'},'synthetic')),patch('fsp_client.cli.FspClient',return_value=api):
            stream=io.StringIO()
            with contextlib.redirect_stdout(stream):run(parser().parse_args(['candidates','search','--need-id','2','--json']))
            self.assertEqual(json.loads(stream.getvalue())['data'],[{'id':1}])
        self.assertIn('need_id=2',requests[0])
        self.assertEqual(parser().parse_args(['auth','login','--connection','ai','--server','https://demo.invalid']).connection,'ai')
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):parser().parse_args(['candidates','show','²'])

    def test_cli_drafts_send_prepare_only_and_preserve_json(self):
        from pathlib import Path
        for command,kind,target in [(['profile','draft'],'profile.update',None),
            (['company','draft'],'company.update',None),(['needs','update','7'],'need.update',7),
            (['drafts','prepare','--kind','invitation.send','--target-id','7'],'invitation.send',7)]:
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'changes.json';path.write_text('{"name":"Команда"}')
                requests=[]
                def handle(request):
                    requests.append(request)
                    return httpx.Response(201,json={'data':{'approval_path':'/drafts/example/'},'meta':{}})
                api=FspClient('https://demo.invalid','synthetic',transport=httpx.MockTransport(handle))
                with patch.object(Connections,'load',return_value=({'server':'https://demo.invalid'},'synthetic')),patch('fsp_client.cli.FspClient',return_value=api),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                    run(parser().parse_args(command+['--file',str(path),'--json']))
                self.assertEqual(len(requests),1)
                self.assertEqual(requests[0].method,'POST')
                self.assertEqual(requests[0].url.path,'/api/v1/drafts')
                body=json.loads(requests[0].content)
                self.assertEqual(body['kind'],kind);self.assertEqual(body['target_id'],target)
                self.assertEqual(body['payload'],{'name':'Команда'})

    def test_no_insecure_keyring_fallback_and_no_config_secret(self):
        class Secure:
            __module__='keyring.backends.macOS'
            priority=1
            passwords={}
            def set_password(self,s,r,t):self.passwords[r]=t
            def get_password(self,s,r):return self.passwords.get(r)
            def delete_password(self,s,r):self.passwords.pop(r,None)
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'FSP_CONFIG_DIR':directory}),patch('keyring.get_keyring',return_value=Secure()):
            config=Connections();config.login('demo','https://demo.invalid','synthetic-secret',{'role':'candidate','token_kind':'mcp'})
            self.assertNotIn('synthetic-secret',config.path.read_text())
            self.assertEqual(config.load('demo')[1],'synthetic-secret')
            self.assertEqual(config.path.stat().st_mode & 0o777,0o600)
            config.logout('demo');self.assertEqual(config.read(),{})
            with patch('keyring.get_keyring',return_value=object()),self.assertRaises(ClientError):config.backend()


if __name__=='__main__':unittest.main()


class ConditionsClientTests(unittest.TestCase):
    def test_search_and_pdf_pass_condition_parameters(self):
        from pathlib import Path
        requests=[]
        def handle(request):
            requests.append(request)
            if request.url.path.endswith('.pdf'):return httpx.Response(200,content=b'%PDF-synthetic',headers={'Content-Type':'application/pdf'})
            return httpx.Response(200,json={'data':[],'meta':{}})
        with tempfile.TemporaryDirectory() as folder:
            for command in [['candidates','search','--need-id','2','--conditions','matched'],
                            ['candidates','resume','1','--need-id','2','--output',str(Path(folder)/'resume.pdf')]]:
                api=FspClient('https://demo.invalid','synthetic',transport=httpx.MockTransport(handle))
                with patch.object(Connections,'load',return_value=({'server':'https://demo.invalid'},'synthetic')),patch('fsp_client.cli.FspClient',return_value=api),contextlib.redirect_stdout(io.StringIO()):
                    run(parser().parse_args(command))
        self.assertEqual(requests[0].url.params['conditions'],'matched')
        self.assertEqual(requests[0].url.params['need_id'],'2')
        self.assertEqual(requests[1].url.params['need_id'],'2')
        self.assertEqual(requests[1].url.params['with_contacts'],'false')
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
            parser().parse_args(['candidates','search','--conditions','anything'])


class PrivacyCliTests(unittest.TestCase):
    def test_challenge_commands_use_read_routes_and_cannot_submit(self):
        requests=[]
        def handle(request):
            requests.append(request);return httpx.Response(200,json={'data':[],'meta':{'data_mode':'demo'}})
        for command in [['challenges','list','--limit','5','--offset','2','--json'],['challenges','show','7','--json']]:
            api=FspClient('https://demo.invalid','synthetic',transport=httpx.MockTransport(handle))
            with patch.object(Connections,'load',return_value=({'server':'https://demo.invalid'},'synthetic')),patch('fsp_client.cli.FspClient',return_value=api),contextlib.redirect_stdout(io.StringIO()):
                run(parser().parse_args(command))
        self.assertTrue(all(r.method=='GET' for r in requests));self.assertEqual(requests[0].url.path,'/api/v1/challenges')
        self.assertEqual(requests[0].url.params['limit'],'5');self.assertEqual(requests[1].url.path,'/api/v1/challenges/7')
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):parser().parse_args(['challenges','submit','7'])

    def test_privacy_is_read_only_command(self):
        args=parser().parse_args(['privacy','show','--json'])
        self.assertEqual(args.path,'me/privacy')
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):parser().parse_args(['privacy','delete'])
