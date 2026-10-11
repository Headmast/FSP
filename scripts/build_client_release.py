"""Build public client archives and a checksum manifest, excluding runtime/secrets."""
import hashlib,json,os,subprocess,tomllib
from pathlib import Path
root=Path(__file__).resolve().parents[1]
version=tomllib.loads((root/'clients/python/pyproject.toml').read_text())['project']['version']
output=root/'.runtime/downloads';output.mkdir(parents=True,exist_ok=True)
subprocess.run([os.environ.get('FSP_UV','uv'),'build','--project',str(root/'clients/python'),'--out-dir',str(output)],check=True)
revision=(root/'REVISION').read_text().strip() if (root/'REVISION').exists() else subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
files=[]
for name in [f'fsp_client-{version}-py3-none-any.whl',f'fsp_client-{version}.tar.gz']:
    path=output/name
    files.append({'filename':name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
(output/'manifest.json').write_text(json.dumps({'version':version,'commit':revision,'files':files},indent=2)+'\n')
print('Client release artifacts ready:',version)
