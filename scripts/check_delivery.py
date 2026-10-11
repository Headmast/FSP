"""Verify actual package bytes and portability; metadata or file presence alone is insufficient."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from zipfile import ZipFile
import xml.etree.ElementTree as ET
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
REQUIRED={'doc/delivery/current-mvp.md','doc/delivery/requirements-coverage.md','doc/delivery/mvp-handbook.pdf',
 'doc/delivery/current-mvp.pptx','doc/delivery/current-mvp-slides.pdf','doc/delivery/current-mvp-slides.md','doc/delivery/current-mvp-slides.html',
 'doc/delivery/demo-script.md','doc/delivery/README.md','doc/delivery/assets/current-demo.mp4','doc/delivery/assets/timed-rehearsal.mp4'}


def verify(root,manifest):
    files={item['path']:item for item in manifest['files']}
    assert REQUIRED<=set(files),'Required deliverable missing from manifest'
    for name,item in files.items():
        path=(root/name).resolve();assert path.is_relative_to(root.resolve()),'Path escapes repository'
        data=path.read_bytes();assert len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256'],'Artifact mismatch: '+name
    with ZipFile(root/'doc/delivery/current-mvp.pptx') as z:
        assert z.testzip() is None;slides=[p for p in z.namelist() if re.fullmatch(r'ppt/slides/slide[0-9]+\.xml',p)]
        assert len(slides)==8,'Wrong slide count'
        media=[p for p in z.namelist() if p.startswith('ppt/media/')]
        assert len(media)==6 and all(z.read(p).startswith(b'\x89PNG\r\n\x1a\n') and len(z.read(p))>100 for p in media),'Missing/empty image assets'
        texts=' '.join(ET.fromstring(z.read(p)).findtext('.//{http://schemas.openxmlformats.org/drawingml/2006/main}t') or '' for p in slides)
        assert 'Трудяжки' in texts and 'Проверки' in texts,'PPTX native text missing'
        for name in z.namelist():
            if name.endswith('.rels'):
                assert b'TargetMode="External"' not in z.read(name),'External PPTX dependency'
    pdf_pages={}
    for name,count in [('mvp-handbook.pdf',9),('current-mvp-slides.pdf',8)]:
        path=root/'doc/delivery'/name;assert path.read_bytes().startswith(b'%PDF-')
        reader=PdfReader(path);pages=len(reader.pages);assert pages==count,'Wrong PDF page count'
        pdf_pages[name]=pages
    handbook='\n'.join(page.extract_text() or '' for page in PdfReader(root/'doc/delivery/mvp-handbook.pdf').pages)
    assert all(term in handbook for term in ['iOS','SQLite','69','111','processing-v1','24','R01','R20']), 'PDF missing required content'
    assert '\u25a0' not in handbook and '\ufffd' not in handbook,'Unreadable PDF glyphs'
    for name in ['current-demo.mp4','timed-rehearsal.mp4']:
        path=root/'doc/delivery/assets'/name
        info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],text=True))
        streams=[s for s in info['streams'] if s['codec_type']=='video'];assert len(streams)==1 and streams[0]['codec_name']=='h264'
        assert streams[0]['width']==1280 and streams[0]['height']==720 and float(info['format']['duration'])>30
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-i',str(path),'-f','null','-'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    return {'status':'PASS','files':len(files),'pdf_pages':pdf_pages,'pptx_slides':8,'embedded_images':6,'video_decode':'PASS'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--output',type=Path,default=ROOT/'.runtime/qa/DEL-001-package-check.json');args=p.parse_args()
    manifest=json.loads((args.root/'doc/delivery/package-manifest.json').read_text());result=verify(args.root,manifest)
    bad=json.loads(json.dumps(manifest));bad['files']=[f for f in bad['files'] if f['path']!='doc/delivery/assets/current-demo.mp4']
    try:verify(args.root,bad)
    except AssertionError:result['missing_artifact_counterfactual']='PASS: rejected'
    else:raise AssertionError('Verifier accepted incomplete bundle')
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
