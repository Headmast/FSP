#!/usr/bin/env python3
"""Publish committed prototype files on digitarium via a temporary localhost.run HTTPS tunnel."""
import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--ref', default='HEAD', help='Committed ref to publish; uncommitted changes are excluded')
args = parser.parse_args()
sha = subprocess.check_output(['git', 'rev-parse', '--verify', args.ref + '^{commit}'], cwd=ROOT, text=True).strip()
archive = subprocess.check_output(['git', 'archive', sha, 'prototype', 'accessibility'], cwd=ROOT)
subprocess.run(['ssh', '-o', 'BatchMode=yes', 'digitarium',
                f'mkdir -p ~/fsp-mvp/releases/{sha} && tar --warning=no-timestamp -xf - -C ~/fsp-mvp/releases/{sha}'], input=archive, check=True)
remote = r'''
import json, os, re, socket, subprocess, time
from pathlib import Path
root = Path.home() / 'fsp-mvp'
release = root / 'releases' / '__SHA__'
(release / 'prototype' / 'version.json').write_text(json.dumps({'commit':'__SHA__','mode':'mock-prototype'})+'\n')
shared = root / 'shared'
for name in ['logs','pids']:
    (shared/name).mkdir(parents=True,exist_ok=True)
current = root / 'prototype-current'
if current.exists() and not current.is_symlink():
    raise RuntimeError('prototype-current is not a managed symlink')
pending = root / '.prototype-current-next'
if pending.is_symlink(): pending.unlink()
pending.symlink_to(release)
os.replace(pending, current)
def alive(name):
    file = shared/'pids'/f'{name}.pid'
    if not file.exists(): return False
    try:
        pid=int(file.read_text())
        cmd=Path(f'/proc/{pid}/cmdline').read_bytes()
        if name=='prototype-server':
            return b'fsp-mvp' in cmd and b'http.server' in cmd
        return b'nokey@localhost.run' in cmd and b'80:127.0.0.1:8010' in cmd
    except (OSError,ValueError): return False
def launch(name,args):
    if alive(name): return
    log=shared/'logs'/f'{name}.log'
    with log.open('w') as handle:
        process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
    (shared/'pids'/f'{name}.pid').write_text(str(process.pid))
if not alive('prototype-server'):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',8010))
launch('prototype-server',['python3','-m','http.server','8010','--bind','127.0.0.1','--directory',str(current/'prototype')])
launch('prototype-ssh-tunnel',['ssh','-F','/dev/null','-T','-o','StrictHostKeyChecking=accept-new',
    '-o','IdentityFile=none','-o','IdentityAgent=none','-o','IdentitiesOnly=yes',
    '-o','ServerAliveInterval=30','-o','ExitOnForwardFailure=yes',
    '-R','80:127.0.0.1:8010','nokey@localhost.run','--','--output','json'])
for _ in range(60):
    text=(shared/'logs'/'prototype-ssh-tunnel.log').read_text()
    urls=re.findall(r'https://[a-z0-9-]+\.(?:lhr\.life|localhost\.run)',text)
    urls=[u for u in urls if not u.startswith('https://admin.')]
    if urls:
        print(json.dumps({'commit':'__SHA__','url':urls[-1],'provider':'localhost.run'},indent=2))
        break
    time.sleep(.5)
else:
    raise RuntimeError('No tunnel URL yet; inspect managed SSH tunnel log on server')
'''.replace('__SHA__',sha)
result = subprocess.run(['ssh','-o','BatchMode=yes','digitarium','python3 -'],input=remote,text=True,capture_output=True,check=True)
print(result.stdout.strip())
