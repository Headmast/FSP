#!/usr/bin/env python3
"""25 concurrent virtual users, independent authenticated sessions, mixed search/profile writes."""
import argparse,concurrent.futures,http.cookiejar,json,math,re,statistics,threading,time,urllib.parse,urllib.request
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('url');p.add_argument('--output',default='.runtime/qa/load.json');a=p.parse_args();base=a.url.rstrip('/')
barrier=threading.Barrier(25)
def actor(i):
    candidate=i>=20
    jar=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    def request(path,data=None):
        body=urllib.parse.urlencode(data).encode() if data else None
        response=client.open(urllib.request.Request(base+path,data=body,headers={'Referer':base+path,**({'X-Forwarded-Proto':'https'} if base.startswith('http://127.0.0.1:') else {})}),timeout=25)
        if base.startswith('http://127.0.0.1:'):
            for cookie in jar:cookie.secure=False
        return response
    def csrf():return next(c.value for c in jar if c.name=='csrftoken')
    request('/accounts/login/').close()
    request('/accounts/login/',{'username':('fixture-junior-01' if candidate else 'fixture-company-alpha')+'@demo.invalid','password':'Fsp-demo-2026!','csrfmiddlewaretoken':csrf()}).close()
    path='/profile/' if candidate else '/candidates/?grade=Junior'
    request(path).close();barrier.wait(timeout=90)
    results=[]
    for j in range(10):
        started=time.monotonic()
        try:
            data={'csrfmiddlewaretoken':csrf(),'name':'Алексей Юниор','city':'Москва','skills':'Swift, SwiftUI, Combine',
                  'contact_email':'fixture-junior-01@demo.invalid','contact_phone':'+70000000000','desired_grade':'Junior','published':'on'} if candidate else None
            with request(path,data) as response:
                text=response.read().decode();code=response.status
            valid=code==200 and ('Алексей Юниор' in text)
            if 'database is locked' in text.lower():valid=False
            results.append({'seconds':time.monotonic()-started,'ok':valid,'status':code,'kind':'write' if candidate else 'search'})
        except Exception as exc:results.append({'seconds':time.monotonic()-started,'ok':False,'error':type(exc).__name__})
    return results
start=time.monotonic()
with concurrent.futures.ThreadPoolExecutor(max_workers=25) as pool:rows=[r for group in pool.map(actor,range(25)) for r in group]
elapsed=time.monotonic()-start;times=sorted(r['seconds'] for r in rows);p95=times[math.ceil(.95*len(times))-1]
failures=[r for r in rows if not r['ok']]
result={'status':'PASS' if not failures and p95<=2 else 'FAIL','virtual_users':25,'independent_sessions':25,
        'distinct_accounts':2,'requests':len(rows),'search_requests':200,'profile_writes':50,'setup_in_elapsed':True,
        'elapsed_seconds':round(elapsed,3),'p95_seconds':round(p95,3),'mean_seconds':round(statistics.mean(times),3),'errors':failures}
out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
raise SystemExit(0 if result['status']=='PASS' else 1)
