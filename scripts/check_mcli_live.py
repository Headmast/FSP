"""HTTPS release verification using public synthetic fixture accounts. Revokes QA tokens."""
import argparse,asyncio,hashlib,json,re,secrets
from pathlib import Path
import httpx
from mcp import Client
from fsp_client.http import FspClient
from fsp_client.mcp import build_server
p=argparse.ArgumentParser();p.add_argument('--url',required=True);p.add_argument('--expected-sha',required=True);p.add_argument('--drafts',action='store_true');args=p.parse_args()
base=args.url.rstrip('/')
result={'expected_sha':args.expected_sha,'url':base,'roles':{},'drafts':args.drafts}

def csrf(response):
    match=re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"',response.text)
    assert match,'Missing CSRF form'
    return match[1]

async def verify():
    with httpx.Client(timeout=20,follow_redirects=False,trust_env=False) as public:
        version=public.get(base+'/version/').json();assert version['commit']==args.expected_sha
        assert public.get(base+'/health/').json()['status']=='ok'
        assert public.get(base+'/api/v1/me').status_code==401
        manifest=public.get(base+'/downloads/manifest.json').json();assert manifest['commit']==args.expected_sha
        for item in manifest['files']:
            response=public.get(base+'/downloads/'+item['filename']);assert response.status_code==200
            assert hashlib.sha256(response.content).hexdigest()==item['sha256']
        result['client_version']=manifest['version'];result['artifacts']=len(manifest['files'])
    for role,email in [('candidate','fixture-junior-01@demo.invalid'),('employer','fixture-company-alpha@demo.invalid')]:
        with httpx.Client(timeout=20,follow_redirects=False,trust_env=False) as browser:
            response=browser.get(base+'/accounts/login/')
            response=browser.post(base+'/accounts/login/',data={'csrfmiddlewaretoken':csrf(response),'username':email,'password':'Fsp-demo-2026!'},headers={'Referer':base+'/accounts/login/'})
            assert response.status_code==302
            response=browser.get(base+'/accounts/integrations/')
            name='MCLI-QA-'+secrets.token_hex(6)
            response=browser.post(base+'/accounts/integrations/',data={'csrfmiddlewaretoken':csrf(response),'action':'create','name':name,'kind':'mcp','drafts':'on' if args.drafts else ''},headers={'Referer':base+'/accounts/integrations/'})
            assert response.status_code==200
            token=re.search(r'fsp_[A-Za-z0-9_-]{43}',response.text).group()
            identifier=re.search(re.escape(name)+r'.*?name="id" value="([0-9]+)"',response.text,re.S).group(1)
            api=FspClient(base,token)
            try:
                actor=api.get('me')['data'];assert actor['role']==role
                async with Client(build_server(api)) as client:
                    listed=await client.list_tools();assert all('contacts' not in t.name for t in listed.tools)
                    if role=='candidate':
                        call=await client.call_tool('fsp_get_profile')
                    else:
                        need=api.get('needs')['data'][0]['id']
                        call=await client.call_tool('fsp_search_candidates',{'need_id':need})
                    assert not call.is_error
                    assert '@demo.invalid' not in json.dumps(call.structured_content)
                    result['roles'][role]={'web_token':True,'mcp':True,'safe_projection':True}
                    if args.drafts:
                        # Confirm a no-op edit of a public field; fixtures remain unchanged.
                        if role=='candidate':
                            payload={'city':api.get('me/profile')['data']['city']};kind='profile.update'
                        else:
                            payload={'name':api.get('me/company')['data']['company']['name']};kind='company.update'
                        prepared=api.request('POST','drafts',data={'kind':kind,'payload':payload})['data']
                        assert prepared['status']=='pending'
                        preview=browser.get(base+prepared['approval_path']);assert preview.status_code==200
                        applied=browser.post(base+prepared['approval_path'],data={'csrfmiddlewaretoken':csrf(preview),'action':'apply','acknowledge':'on'},headers={'Referer':base+prepared['approval_path']})
                        assert applied.status_code==302
                        assert api.get('drafts/'+prepared['id'])['data']['status']=='applied'
                        denied=browser.post(base+'/api/v1/drafts/'+prepared['id']+'/apply',json={},headers={'Authorization':'Bearer '+token})
                        assert denied.status_code in {403,404}
                        result['roles'][role]['web_approval']=True
            finally:
                api.close()
                page=browser.get(base+'/accounts/integrations/')
                revoked=browser.post(base+'/accounts/integrations/',data={'csrfmiddlewaretoken':csrf(page),'action':'revoke','id':identifier},headers={'Referer':base+'/accounts/integrations/'})
                assert revoked.status_code==302
                check=FspClient(base,token)
                try:assert check.client.get(base+'/api/v1/me').status_code==401
                finally:check.close()
            result['roles'][role]['revoke']=True
    return result

result=asyncio.run(verify())
print(json.dumps(result,indent=2))
(root:=Path(__file__).resolve().parents[1]/'.runtime').mkdir(exist_ok=True)
(root/'mcli-live-results.json').write_text(json.dumps(result,indent=2)+'\n')
