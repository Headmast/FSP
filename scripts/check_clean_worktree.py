#!/usr/bin/env python3
"""Verify committed code boots from an isolated clean Git worktree using documented commands."""
import json
import os
import signal
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run(args, cwd, **kwargs):
    return subprocess.run(args, cwd=cwd, check=True, **kwargs)

sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
with tempfile.TemporaryDirectory(prefix='fsp clean worktree ') as temp:
    repo = Path(temp) / 'repository'
    run(['git', 'clone', '--local', '--no-hardlinks', str(ROOT), str(repo)], ROOT, stdout=subprocess.DEVNULL)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    created = subprocess.check_output(['python3', 'scripts/worktree.py', 'create', 'verification', '--base', sha, '--port', str(port)], cwd=repo, text=True)
    checkout = Path(json.loads(created)['path'])
    run(['uv', 'sync', '--locked'], checkout)
    python = checkout / '.venv/bin/python'
    for args in [['scripts/worktree.py', 'check'], ['app/manage.py', 'migrate', '--noinput'],
                 ['app/manage.py', 'collectstatic', '--noinput'], ['app/manage.py', 'check'],
                 ['app/manage.py', 'makemigrations', '--check', '--dry-run']]:
        run([str(python), *args], checkout)
    with (Path(temp) / 'server.log').open('w') as log:
        process = subprocess.Popen([str(python), 'scripts/run_app.py'], cwd=checkout, stdout=log, stderr=log, start_new_session=True)
    try:
        url = f'http://127.0.0.1:{port}'
        for _ in range(50):
            if process.poll() is not None:
                raise RuntimeError('Fresh worktree server exited: ' + (Path(temp) / 'server.log').read_text()[-1000:])
            try:
                with urllib.request.urlopen(url + '/health/', timeout=1) as response:
                    assert json.load(response)['status'] == 'ok'
                break
            except (OSError, ValueError):
                time.sleep(.2)
        else:
            raise RuntimeError('Fresh worktree did not become ready')
        with urllib.request.urlopen(url + '/version/', timeout=3) as response:
            assert json.load(response)['commit'] == sha
        with urllib.request.urlopen(url + '/accounts/register/', timeout=3) as response:
            assert 'Регистрация в демо' in response.read().decode()
        result = {'status':'PASS','commit':sha,'checks':['isolated Git worktree','locked install','migrations',
            'static manifest','Django check','migration drift','Gunicorn startup','health','version','registration page']}
        output = ROOT / '.runtime/qa/clean-worktree.json'
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
