"""Remote side of deploy_mvp.py. Never prints environment or secrets."""
import json,os,re,secrets,shlex,signal,sqlite3,subprocess,sys,time,urllib.request
from pathlib import Path
sha=sys.argv[1]
assert re.fullmatch('[0-9a-f]{40}',sha)
root=Path.home()/'fsp-mvp';shared=root/'shared';release=root/'releases'/sha
for name in ['logs','pids','backups']:(shared/name).mkdir(parents=True,exist_ok=True)
uv=shared/'venv-check/bin/uv'
if not uv.exists():
    subprocess.run(['python3','-m','venv',str(shared/'venv-check')],check=True)
    subprocess.run([str(shared/'venv-check/bin/python'),'-m','pip','install','uv==0.12.17'],check=True)
subprocess.run([str(uv),'sync','--locked','--python','/usr/bin/python3'],cwd=release,check=True)
python=release/'.venv/bin/python'
tunnelpid=shared/'pids/mvp-ssh-tunnel.pid';tunnellog=shared/'logs/mvp-ssh-tunnel.log'
def tunnel_alive():
    try:
        cmd=Path(f'/proc/{int(tunnelpid.read_text())}/cmdline').read_bytes()
        return b'nokey@localhost.run' in cmd and b'80:127.0.0.1:8011' in cmd
    except (OSError,ValueError):return False
if not tunnel_alive():
    with tunnellog.open('w') as log:
        proc=subprocess.Popen(['ssh','-F','/dev/null','-T','-o','StrictHostKeyChecking=accept-new','-o','IdentityFile=none',
            '-o','IdentityAgent=none','-o','IdentitiesOnly=yes','-o','ServerAliveInterval=30','-o','ExitOnForwardFailure=yes',
            '-R','80:127.0.0.1:8011','nokey@localhost.run','--','--output','json'],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    tunnelpid.write_text(str(proc.pid))
for _ in range(60):
    urls=re.findall(r'https://[a-z0-9-]+\.(?:lhr\.life|localhost\.run)',tunnellog.read_text())
    urls=[u for u in urls if not u.startswith('https://admin.')]
    if urls:break
    time.sleep(.5)
else:raise RuntimeError('Tunnel not ready; inspect owned log')
url=urls[-1];host=url.split('//')[1]
envfile=shared/'.env';existing={}
if envfile.exists():
    for line in envfile.read_text().splitlines():
        key,sep,value=line.partition('=')
        if sep and not key.startswith('#'):existing[key]=shlex.split(value)[0] if value else ''
existing.update({'DJANGO_SECRET_KEY':existing.get('DJANGO_SECRET_KEY') or secrets.token_urlsafe(60),
    'DEBUG':'0','ALLOWED_HOSTS':host+',localhost,127.0.0.1','CSRF_TRUSTED_ORIGINS':url,
    'DATABASE_PATH':str(shared/'db.sqlite3'),'APP_PORT':'8011','ASSISTANT_MODE':'mock'})
envfile.write_text(''.join(k+'='+shlex.quote(v)+'\n' for k,v in existing.items()));envfile.chmod(0o600)
env=os.environ.copy();env['FSP_ENV_FILE']=str(envfile)
(release/'REVISION').write_text(sha+'\n')
def run(*args):subprocess.run([str(python),*args],cwd=release,env=env,check=True)
pidfile=shared/'pids/mvp-server.pid'
if pidfile.exists():
    try:
        pid=int(pidfile.read_text());cmd=Path(f'/proc/{pid}/cmdline').read_bytes()
        cwd=Path(f'/proc/{pid}/cwd').resolve()
        if b'gunicorn' not in cmd or root/'releases' not in cwd.parents:raise RuntimeError('PID is not owned MVP')
        os.kill(pid,signal.SIGTERM)
        for _ in range(100):
            if not Path(f'/proc/{pid}/cmdline').exists() or not Path(f'/proc/{pid}/cmdline').read_bytes():break
            time.sleep(.1)
        else:raise RuntimeError('Owned server did not stop')
    except (FileNotFoundError,ProcessLookupError):pass
if (shared/'db.sqlite3').exists():
    with sqlite3.connect(shared/'db.sqlite3') as source,sqlite3.connect(shared/'backups'/f'{time.time_ns()}.sqlite3') as target:source.backup(target)
run('app/manage.py','migrate','--noinput');run('app/manage.py','collectstatic','--noinput')
run('app/manage.py','check','--deploy');run('app/manage.py','seed_demo')
current=root/'current';pending=root/'.current-next'
if current.exists() and not current.is_symlink():raise RuntimeError('current is not managed symlink')
if pending.is_symlink():pending.unlink()
pending.symlink_to(release);os.replace(pending,current)
with (shared/'logs/mvp-server.log').open('a') as log:
    process=subprocess.Popen([str(python),'scripts/run_app.py'],cwd=release,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
pidfile.write_text(str(process.pid))
for _ in range(50):
    if process.poll() is not None:raise RuntimeError('Gunicorn exited; inspect server log')
    try:
        request=urllib.request.Request('http://127.0.0.1:8011/version/',headers={'X-Forwarded-Proto':'https'})
        with urllib.request.urlopen(request,timeout=2) as response:version=json.load(response)
        assert version['commit']==sha
        break
    except OSError:time.sleep(.2)
else:raise RuntimeError('Health timeout')
result={'commit':sha,'url':url,'assistant':'mock'}
(shared/'release.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
