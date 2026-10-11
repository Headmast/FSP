#!/usr/bin/env python3
"""Install committed watchdog code and one user crontab entry. Secrets are provisioned separately."""
import json,shlex,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
files=['scripts/maintain_demo.py','portal/fsp-demo.html']
payload={'commit':sha,'files':{file:subprocess.check_output(['git','show',sha+':'+file],cwd=ROOT,text=True) for file in files}}
remote=r'''
import fcntl,json,shlex,subprocess,sys
from pathlib import Path
payload=json.load(sys.stdin);root=Path.home()/'fsp-mvp';shared=root/'shared'
with (shared/'maintenance.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 tools=shared/'tools';tools.mkdir(exist_ok=True)
 for name,text in payload['files'].items():(tools/Path(name).name).write_text(text)
 (shared/'watchdog-code.json').write_text(json.dumps({'commit':payload['commit']})+'\n')
 result=subprocess.run(['crontab','-l'],capture_output=True,text=True)
 if result.returncode not in (0,1):raise RuntimeError('Unable to read crontab')
 text=result.stdout if result.returncode==0 else ''
 sys.path.insert(0,str(tools))
 from maintain_demo import cron_content
 command='* * * * * /usr/bin/python3 '+shlex.quote(str(tools/'maintain_demo.py'))+' --root '+shlex.quote(str(root))+' >> '+shlex.quote(str(shared/'logs/watchdog.log'))+' 2>&1'
 text=cron_content(text,command)
 subprocess.run(['crontab','-'],input=text,text=True,check=True)
 print(json.dumps({'status':'installed','commit':payload['commit'],'schedule':'every minute','existing_jobs_preserved':True}))
'''
subprocess.run(['ssh','-o','BatchMode=yes','digitarium','python3 -c '+shlex.quote(remote)],input=json.dumps(payload),text=True,check=True)
