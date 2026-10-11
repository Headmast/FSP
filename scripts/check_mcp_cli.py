#!/usr/bin/env python3
"""Isolated local HTTP + SDK stdio QA; emits only booleans/counts, never tokens/data."""
import asyncio,json,os,subprocess,sys,time,tempfile,re
from jsonschema import Draft202012Validator
from pathlib import Path
from mcp import Client,StdioServerParameters
from fsp_client.http import FspClient,ClientError
from fsp_client.config import Connections
root=Path(__file__).resolve().parents[1]
backend=root/'.venv/bin/python'
port=int(os.environ.get('MCLI_QA_PORT','8043'))
base=f'http://127.0.0.1:{port}'
env=os.environ.copy();env.update({'FSP_ENV_FILE':'/dev/null','DEBUG':'1','DATABASE_PATH':str(root/'.runtime/mcli-qa.sqlite3')})
(root/'.runtime').mkdir(exist_ok=True)
fixture=root/'.runtime/mcli-fixtures.json'
subprocess.run([str(backend),'app/manage.py','migrate','--noinput'],cwd=root,env=env,check=True,stdout=subprocess.DEVNULL)
subprocess.run([str(backend),'scripts/setup_mcli_fixture.py',str(fixture)],cwd=root,env=env,check=True,stdout=subprocess.DEVNULL)
log=(root/'.runtime/mcli-qa-server.log').open('w')
process=subprocess.Popen([str(backend),'app/manage.py','runserver',f'127.0.0.1:{port}','--noreload'],cwd=root,env=env,stdout=log,stderr=log)
result={}

async def check(values):
    for role in ['candidate','employer']:
        value=values[role]
        api=FspClient(base,value['cli'])
        paths=['me','catalog','invitations',f'invitations/{value["invitation_id"]}']
        paths += ['me/profile','me/profile/private','me/assessments',f'me/assessments/{value["result_id"]}/result','me/achievements'] if role=='candidate' else [
            'me/company','needs',f'needs/{value["need_id"]}','candidates',f'candidates/{value["candidate_id"]}',f'candidates/{value["candidate_id"]}/proofs']
        specification=api.client.get(base+'/api/v1/openapi.json').json()
        for path in paths:
            response=api.get(path,**({'need_id':value['need_id']} if path=='candidates' else {}))
            assert response['meta']['data_mode']=='demo'
            contract_path='/'+re.sub(r'/[0-9]+(?=/|$)','/{id}',path)
            schema=specification['paths'][contract_path]['get']['responses']['200']['content']['application/json']['schema']
            Draft202012Validator(dict(schema,components=specification['components'])).validate(response)
        result[role+'_http']=len(paths)
        api.close()
        params=StdioServerParameters(command=sys.executable,args=[str(root/'scripts/mcli_stdio_fixture.py'),str(fixture),role,base])
        for mode in ['auto','legacy']:
            async with Client(params,mode=mode) as client:
                tools=await client.list_tools()
                names=[t.name for t in tools.tools]
                assert 'fsp_get_contacts' not in names
                call=await client.call_tool('fsp_get_profile' if role=='candidate' else 'fsp_search_candidates',{} if role=='candidate' else {'need_id':value['need_id']})
                assert not call.is_error and call.structured_content['meta']['data_mode']=='demo'
                result[role+'_stdio_'+mode]=True
        # Native store and the packaged CLI, when the platform provides a protected backend.
        with tempfile.TemporaryDirectory() as directory:
            os.environ['FSP_CONFIG_DIR']=directory
            config=Connections()
            try:
                identity={'role':role,'token_kind':'cli'}
                config.login('qa',base,value['cli'],identity)
                assert config.load('qa')[1]==value['cli']
                completed=subprocess.run([sys.executable,'-m','fsp_client.cli','--connection','qa','--json','me'],capture_output=True,text=True,check=True)
                assert json.loads(completed.stdout)['data']['role']==role
                result[role+'_native_keyring_cli']=True
            except ClientError as exc:
                assert exc.exit_code==3
                result[role+'_native_keyring_cli']='NOT_RUN: no protected backend'
            finally:
                if 'qa' in config.read():config.logout('qa')
                os.environ.pop('FSP_CONFIG_DIR',None)

try:
    values=json.loads(fixture.read_text())
    for _ in range(100):
        if process.poll() is not None:raise RuntimeError('QA server exited')
        api=FspClient(base,values['candidate']['cli'])
        try:api.get('me');break
        except ClientError:time.sleep(.1)
        finally:api.close()
    else:raise RuntimeError('QA server not ready')
    asyncio.run(check(values))
    print(json.dumps(result,indent=2))
    (root/'.runtime/mcli-http-stdio-results.json').write_text(json.dumps(result,indent=2)+'\n')
finally:
    process.terminate()
    try:process.wait(timeout=10)
    except subprocess.TimeoutExpired:process.kill();process.wait()
    log.close()
    fixture.unlink(missing_ok=True)
