#!/usr/bin/env python3
"""Publish only committed public assets to the existing LLM Love FTPS directory.

Run after deploy_mvp.py so the exact Git release is present on digitarium.
Credentials remain in shared/portal-publisher.json; no runtime or app files publish.
"""
import argparse
import json
import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--ref', default='HEAD')
parser.add_argument('--delivery-only',action='store_true',help='Publish the committed current delivery bundle without reuploading unchanged landing/video assets')
args = parser.parse_args()
sha = subprocess.check_output(['git', 'rev-parse', args.ref + '^{commit}'], cwd=ROOT, text=True).strip()
files = ['index.html', 'style.css', 'robots.txt', 'strategy-71c4.html',
         'accessibility/accessibility.css', 'accessibility/accessibility.js',
         'prototype/index.html', 'prototype/style.css', 'prototype/app.js', 'prototype/state.mjs',
         'prototype/accessibility.css', 'prototype/accessibility.js',
         'portal/fsp-demo.html', 'bots/index.html', 'bots/style.css',
         'bots/app.mjs', 'bots/engine.mjs', 'bots/transports.mjs',
         'video/index.html', 'video/README.md', 'video/manifest.json',
         *[f'video/{i}.mp4' for i in range(1, 7)],
         'doc/presentation/trudyazhki-fsp.html', 'doc/presentation/trudyazhki-fsp.pptx',
         'doc/presentation/trudyazhki-fsp.md',
         'doc/research/competitor-analysis-2026-10-11.html']
tracked = set(subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', sha], cwd=ROOT, text=True).splitlines())
delivery=[]
if 'doc/delivery/package-manifest.json' in tracked:
    manifest=json.loads(subprocess.check_output(['git','show',sha+':doc/delivery/package-manifest.json'],cwd=ROOT,text=True))
    fixed={'doc/delivery/index.html','doc/delivery/README.md','doc/delivery/current-mvp.md','doc/delivery/requirements-coverage.md',
        'doc/delivery/mvp-handbook.pdf','doc/delivery/current-mvp.pptx','doc/delivery/current-mvp-slides.md',
        'doc/delivery/current-mvp-slides.html','doc/delivery/current-mvp-slides.pdf','doc/delivery/demo-script.md'}
    for artifact in manifest['files']:
        name=artifact['path'];path=Path(name)
        assert not path.is_absolute() and '..' not in path.parts
        assert name in fixed or name.startswith('doc/delivery/assets/') and path.suffix in {'.png','.mp4'},'Unexpected delivery export'
        delivery.append(name)
    delivery.append('doc/delivery/package-manifest.json')
if args.delivery_only:
    assert delivery,'Selected commit has no delivery bundle'
    files=delivery
else:files+=delivery
assert set(files) <= tracked, 'All published assets must exist in the committed release'
remote = r'''
import base64, fcntl, hashlib, json, ssl, sys
from pathlib import Path, PurePosixPath
payload=json.load(sys.stdin)
root=Path.home()/'fsp-mvp'; shared=root/'shared'; release=root/'releases'/payload['commit']
sys.path.insert(0,str(release/'scripts'))
from maintain_demo import SessionFTP_TLS
config=json.loads((shared/'portal-publisher.json').read_text())
certificate=base64.b64decode(config['certificate_der'])
context=ssl.create_default_context()
context.minimum_version=context.maximum_version=ssl.TLSVersion.TLSv1_2
context.check_hostname=False
context.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(certificate))
if hasattr(ssl,'VERIFY_X509_PARTIAL_CHAIN'):context.verify_flags|=ssl.VERIFY_X509_PARTIAL_CHAIN
results=[]
with (shared/'public-site.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 ftp=SessionFTP_TLS(context=context,timeout=90)
 try:
  ftp.connect(config['host'],config.get('port',21));ftp.auth()
  if ftp.sock.getpeercert(binary_form=True)!=certificate:raise RuntimeError('Hosting certificate changed')
  ftp.login(config['user'],config['password']);ftp.prot_p()
  base=config['remote_directory']
  for name in payload['files']:
   source=release/name
   destination=name
   if name=='portal/fsp-demo.html':destination='fsp-demo.html'
   if name.startswith('doc/research/'):destination=PurePosixPath(name).name
   target=PurePosixPath(destination)
   ftp.cwd(base)
   for part in target.parts[:-1]:
    try:ftp.cwd(part)
    except Exception:
     ftp.mkd(part);ftp.cwd(part)
   temporary='.'+target.name+'.release-upload'
   with source.open('rb') as handle:ftp.storbinary('STOR '+temporary,handle)
   expected=hashlib.sha256(source.read_bytes()).hexdigest()
   received=hashlib.sha256()
   ftp.retrbinary('RETR '+temporary,received.update)
   if received.hexdigest()!=expected:raise RuntimeError('Upload checksum mismatch: '+destination)
   backup='.'+target.name+'.previous-release'
   try:ftp.size(target.name)
   except Exception:pass
   else:
    try:ftp.delete(backup)
    except Exception:pass
    ftp.rename(target.name,backup)
   ftp.rename(temporary,target.name)
   results.append({'path':destination,'bytes':source.stat().st_size,'sha256':expected})
   print(json.dumps({'published':destination}),flush=True)
  ftp.quit()
 finally:ftp.close()
report={'commit':payload['commit'],'files':results}
(shared/'public-site-release.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'status':'published','commit':payload['commit'],'files':len(results)}))
'''
subprocess.run(['ssh', '-o', 'BatchMode=yes', 'digitarium', 'python3 -c ' + shlex.quote(remote)],
               input=json.dumps({'commit': sha, 'files': files}), text=True, check=True)
