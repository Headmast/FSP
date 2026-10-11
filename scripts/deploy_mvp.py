#!/usr/bin/env python3
"""Deploy a committed release to digitarium; restart only the owned MVP process."""
import argparse,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ref',default='HEAD');args=p.parse_args()
sha=subprocess.check_output(['git','rev-parse','--verify',args.ref+'^{commit}'],cwd=ROOT,text=True).strip()
archive=subprocess.check_output(['git','archive',sha],cwd=ROOT)
subprocess.run(['ssh','-o','BatchMode=yes','digitarium',f'mkdir -p ~/fsp-mvp/releases/{sha} && tar --warning=no-timestamp -xf - -C ~/fsp-mvp/releases/{sha}'],input=archive,check=True)
script=(ROOT/'scripts/deploy_mvp_remote.py').read_text()
subprocess.run(['ssh','-o','BatchMode=yes','digitarium',f'python3 - {sha}'],input=script,text=True,check=True)
