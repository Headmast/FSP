"""Record the real browser demo from a clean clone; never use a shared database."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref',default='HEAD')
    parser.add_argument('--output',type=Path,default=ROOT/'.runtime/qa/DEL-001-recording')
    parser.add_argument('--pause-ms',type=int,default=4000)
    parser.add_argument('--node',default=os.environ.get('FSP_NODE','node'))
    args=parser.parse_args()
    sha=subprocess.check_output(['git','rev-parse',args.ref],cwd=ROOT,text=True).strip()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    result={'task':'DEL-001','code_commit':sha,'status':'FAIL','checks':[]}
    def run(command,cwd,env,log):
        subprocess.run(command,cwd=cwd,env=env,check=True,stdout=log,stderr=log)
    with tempfile.TemporaryDirectory(prefix='fsp-delivery-clone-') as tmp, (output/'private-build.log').open('w') as log:
        repo=Path(tmp)/'repo'
        env=dict(os.environ,FSP_ENV_FILE='/dev/null',DEBUG='1',ALLOWED_HOSTS='127.0.0.1,localhost',CSRF_TRUSTED_ORIGINS='')
        run(['git','clone','--local','--no-hardlinks',str(ROOT),str(repo)],ROOT,env,log)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        checkout_info=subprocess.check_output(['python3','scripts/worktree.py','create','delivery-verification','--base',sha,'--port',str(port)],cwd=repo,env=env,text=True)
        checkout=Path(json.loads(checkout_info)['path'])
        env.update(DATABASE_PATH=str(checkout/'.runtime/delivery.sqlite3'),APP_PORT=str(port))
        run(['uv','sync','--locked'],checkout,env,log)
        python=str(checkout/'.venv/bin/python')
        for command in [('scripts/worktree.py','check'),('app/manage.py','migrate','--noinput'),('app/manage.py','collectstatic','--noinput'),('app/manage.py','check'),('app/manage.py','makemigrations','--check','--dry-run'),('app/manage.py','seed_demo'),('app/manage.py','seed_owner_dashboard')]:
            run([python,*command],checkout,env,log)
        run([python,'scripts/build_client_release.py'],checkout,env,log)
        result['checks']+=['clean local clone','isolated worktree/env/database','locked installation','fresh migrations/static/system/drift','synthetic fixtures','packaged client']
        process=subprocess.Popen([python,'scripts/run_app.py'],cwd=checkout,env=env,stdout=log,stderr=log,start_new_session=True)
        try:
            url=f'http://127.0.0.1:{port}'
            for _ in range(80):
                if process.poll() is not None:raise RuntimeError('Clean clone server exited')
                try:
                    with urllib.request.urlopen(url+'/health/',timeout=1) as response:assert json.load(response)['status']=='ok'
                    break
                except (OSError,ValueError):time.sleep(.2)
            else:raise RuntimeError('Clean clone server not ready')
            with urllib.request.urlopen(url+'/version/',timeout=2) as response:assert json.load(response)['commit']==sha
            result['checks']+=['Gunicorn health/version actual SHA']
            env.update(FSP_RECORD_ROOT=str(checkout),FSP_RECORD_PYTHON=python,FSP_RECORD_OUTPUT=str(output),FSP_RECORD_URL=url,FSP_RECORD_PAUSE_MS=str(args.pause_ms),PYTHONPATH=str(checkout/'app'))
            subprocess.run([args.node,str(ROOT/'scripts/record_delivery.cjs')],cwd=checkout,env=env,check=True)
            browser=json.loads((output/'browser.json').read_text());assert browser['status']=='PASS'
            result['browser']=browser
            result['checks']+=['browser journey and privacy','actual Chromium recording','screenshots']
            result['status']='PASS'
        finally:
            if process.poll() is None:os.killpg(process.pid,signal.SIGTERM)
            process.wait(timeout=10)
    (output/'clean-clone.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'code_commit':sha,'checks':result['checks'],'output':str(output)},ensure_ascii=False))


if __name__=='__main__':main()
