"""Export the current technical handbook, requirement map and HTTP route index as a readable PDF."""
import argparse
import html
import json
from pathlib import Path
import re
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--slides-image-dir',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'doc/delivery/mvp-handbook.pdf');args=parser.parse_args()
    if args.slides_image_dir:
        from reportlab.pdfgen import canvas
        files=sorted(args.slides_image_dir.glob('slide-*.png'));assert len(files)==8
        pdf=canvas.Canvas(str(args.output),pagesize=(960,540));pdf.setTitle('Трудяжки · ФСП — текущие слайды')
        for image in files:pdf.drawImage(str(image),0,0,width=960,height=540);pdf.showPage()
        pdf.save();print('Generated slide preview PDF',args.output);return
    pdfmetrics.registerFont(TTFont('FSP',str(ROOT/'app/static/fonts/DejaVuSans.ttf')))
    pdfmetrics.registerFontFamily('FSP',normal='FSP',bold='FSP',italic='FSP',boldItalic='FSP')
    ink=colors.HexColor('#1C1D22');purple=colors.HexColor('#520978')
    styles={name:ParagraphStyle(name,fontName='FSP',fontSize=size,leading=leading,textColor=color,spaceAfter=after,alignment=TA_LEFT)
        for name,size,leading,color,after in [('body',9.5,14,ink,7),('title',25,33,purple,20),('h2',15,21,purple,12),('h3',11,16,purple,8),('cell',7.2,10.6,ink,2),('code',7.6,11,ink,6)]}
    def inline(text):
        text=html.escape(text).replace('—','-').replace('–','-').replace('\u2011','-')
        text=re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',text)
        text=re.sub(r'`([^`]+)`',r'\1',text)
        return re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'\1 (\2)',text)
    def para(text,style='body'):return Paragraph(inline(text),styles[style])
    width=A4[0]-36*mm
    story=[]
    def table(rows,ratios=None):
        cells=[[para(str(cell),'cell') for cell in row] for row in rows]
        count=len(rows[0]);ratios=ratios or {2:[.32,.68],3:[.16,.29,.55],4:[.10,.27,.28,.35]}.get(count,[1/count]*count)
        result=Table(cells,colWidths=[width*r for r in ratios],repeatRows=1,hAlign='LEFT')
        result.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#F2EAF6')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),('LINEBELOW',(0,0),(-1,0),.6,purple),('LINEBELOW',(0,1),(-1,-1),.25,colors.HexColor('#DDD5E1'))]))
        return result
    for index,source in enumerate(['doc/delivery/current-mvp.md','doc/delivery/requirements-coverage.md']):
        if index:story.append(PageBreak())
        lines=(ROOT/source).read_text().splitlines();i=0
        while i<len(lines):
            line=lines[i].strip()
            if not line:i+=1;continue
            if line.startswith('```'):
                code=[];i+=1
                while i<len(lines) and not lines[i].startswith('```'):code.append(lines[i]);i+=1
                for item in code:
                    # Keep long commands printable while retaining literal content.
                    story.append(para(item,'code'))
            elif line.startswith('|'):
                rows=[]
                while i<len(lines) and lines[i].strip().startswith('|'):
                    row=[s.strip() for s in lines[i].strip().strip('|').split('|')]
                    if not all(re.fullmatch(r'[: -]+',s) for s in row):rows.append(row)
                    i+=1
                story.append(table(rows));story.append(Spacer(1,8));continue
            elif line.startswith('# '):story.append(para(line[2:],'title'))
            elif line.startswith('## '):story.append(Spacer(1,11));story.append(para(line[3:],'h2'))
            elif line.startswith('### '):story.append(para(line[4:],'h3'))
            elif line.startswith('- '):story.append(para('• '+line[2:]))
            else:story.append(para(line))
            i+=1
    spec=json.loads((ROOT/'doc/api/openapi.json').read_text())
    story+=[PageBreak(),para('Индекс HTTP интерфейсов','title'),para('Полные поля и примеры находятся в doc/api/openapi.json и contracts.md. Веб: session/CSRF; токенный API: Bearer. Таблица перечисляет все 69 маршрутов и 111 поддерживаемых операций; коды включают успешные ответы и документированные ошибки.','body')]
    rows=[['Маршрут','Методы / роль','Ответы']]
    for route,operations in spec['paths'].items():
        op=next(iter(operations.values()));role=op.get('x-role','Bearer/scope')
        codes=sorted({int(code) for data in operations.values() for code in data['responses']})
        rows.append([route,', '.join(m.upper() for m in operations)+' / '+role,', '.join(map(str,codes))])
    # More width for long path names; never truncate endpoint evidence.
    result=table(rows,[.50,.26,.24])
    story.append(result)
    def page(canvas,document):
        canvas.setFont('FSP',7.4);canvas.setFillColor(purple)
        canvas.drawString(18*mm,12*mm,'Трудяжки · ФСП | Текущий MVP | 12.10.2026 | код 34942b5')
        canvas.drawRightString(A4[0]-18*mm,12*mm,str(document.page))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    document=SimpleDocTemplate(str(args.output),pagesize=A4,rightMargin=18*mm,leftMargin=18*mm,topMargin=19*mm,bottomMargin=21*mm,title='Трудяжки · ФСП — документация текущего MVP',author='Команда Трудяжки')
    document.build(story,onFirstPage=page,onLaterPages=page)
    print('Generated',args.output)


if __name__=='__main__':main()
