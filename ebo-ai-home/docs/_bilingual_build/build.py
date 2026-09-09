from __future__ import annotations
import copy, hashlib, json, math, os, re, sys, zipfile
from pathlib import Path
from lxml import etree
from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.table import Table
from content import SECTIONS
import content2
from parameters import GROUPS
from appendices import PROMPT_EN,GLOSSARY,SOURCES,WEB

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parent.parent
OUT=PROJECT/'docs'
ASSETS=HERE/'figures'; ASSETS.mkdir(exist_ok=True)
REF=Path(os.environ.get('EBO_DOC_TEMPLATE', str(HERE/'reference.docx')))
NAVY='#0C2C4B'; BLUE='#2F6B9A'; PALE='#E7F1F9'; INK='#22354A'; MUTED='#587189'; GREEN='#DDEFE9'
FONTP=Path(r'C:\Windows\Fonts\msyh.ttc'); BOLDP=Path(r'C:\Windows\Fonts\msyhbd.ttc')
def font(sz,bold=False): return ImageFont.truetype(str(BOLDP if bold else FONTP),sz)
def wrap(draw,text,f,maxw):
    lines=[]
    for raw in text.split('\n'):
        words=re.findall(r'[A-Za-z0-9=/-]+[_.]?\s*|[^A-Za-z0-9=/-]',raw)
        line=''
        for word in words:
            if draw.textlength(line+word,font=f)>maxw and line:
                lines.append(line.rstrip());line=word.lstrip()
            else: line+=word
        lines.append(line.rstrip())
    return lines
def label(d,box,text,size=30,bold=False,fill=INK):
    x1,y1,x2,y2=box; f=font(size,bold); lines=wrap(d,text,f,x2-x1-28)
    while len(lines)*(size*1.35)>y2-y1-15 and size>21:
        size-=1;f=font(size,bold);lines=wrap(d,text,f,x2-x1-28)
    assert len(lines)*size*1.35<=y2-y1, (text,box,lines)
    assert all(d.textlength(s,font=f)<=x2-x1-20 for s in lines), (text,box,lines)
    y=y1+(y2-y1-len(lines)*size*1.35)/2
    for s in lines:
        d.text(((x1+x2-d.textlength(s,font=f))/2,y),s,font=f,fill=fill)
        y+=size*1.35
def arrow(d,a,b,color=BLUE,width=5):
    d.line([a,b],fill=color,width=width)
    ang=math.atan2(b[1]-a[1],b[0]-a[0]);n=16
    pts=[b,(b[0]-n*math.cos(ang-.5),b[1]-n*math.sin(ang-.5)),(b[0]-n*math.cos(ang+.5),b[1]-n*math.sin(ang+.5))]
    d.polygon(pts,fill=color)
def box(d,r,text,num=None,fill=PALE):
    d.rounded_rectangle(r,radius=15,fill=fill,outline=BLUE,width=2)
    if num is not None:
        x,y=r[:2];d.ellipse((x+14,y+12,x+54,y+52),fill=NAVY)
        label(d,(x+10,y+9,x+59,y+52),str(num),23,True,'white')
        r=(r[0],r[1]+44,r[2],r[3])
    label(d,r,text,29,True)
def figure(sec,lang):
    n=sec['n']; nodes=sec['nodes'][lang]; kind=sec['kind']; W,H=1600,570
    im=Image.new('RGB',(W,H),'white');d=ImageDraw.Draw(im)
    d.rounded_rectangle((5,5,W-5,H-5),18,fill='#F7FAFD',outline='#D5E4F0',width=2)
    d.rectangle((6,6,W-6,59),fill=NAVY)
    label(d,(20,6,W-20,58),('图 ' if lang==0 else 'Figure ')+str(n)+'   '+sec['title'][lang],26,True,'white')
    if kind=='samples':
        d.line((60,215,1540,215),fill=MUTED,width=2)
        pts=[(x,215-70*math.sin((x-60)/40)*math.sin((x-60)/140)) for x in range(60,1541,3)]
        d.line(pts,fill=BLUE,width=4)
        for x,y in pts[::10]: d.line((x,215,x,y),fill='#72A8CA',width=2);d.ellipse((x-5,y-5,x+5,y+5),fill=NAVY)
        for i,t in enumerate(nodes): box(d,(40+i*390,325,390+i*390,530),t,i+1)
    elif kind=='stack':
        for i,t in enumerate(nodes):
            y=80+i*118;box(d,(130,y,1470,y+95),t,fill=PALE if i%2==0 else GREEN)
            if i<3: arrow(d,(800,y+98),(800,y+115))
    elif kind in ('cards','loop'):
        rects=[(90,90,715,280),(885,90,1510,280),(90,335,715,525),(885,335,1510,525)]
        if kind=='loop':
            rects=[rects[0],rects[1],rects[3],rects[2]]
            arrow(d,(720,180),(880,180));arrow(d,(1200,285),(1200,330));arrow(d,(880,430),(720,430));arrow(d,(400,330),(400,285))
        for i,(r,t) in enumerate(zip(rects,nodes)):box(d,r,t,i+1)
    elif kind=='branch':
        # Picture stream splits to viewing and analysis; transcription splits from audio understanding.
        if n==6:
            rects=[(35,190,360,425),(440,85,845,275),(440,325,845,525),(970,325,1565,525)]
            arrow(d,(362,285),(435,185));arrow(d,(362,345),(435,420));arrow(d,(850,420),(965,420))
        elif n==12:
            rects=[(30,190,340,420),(450,80,965,270),(450,330,965,535),(1070,200,1570,430)]
            arrow(d,(345,270),(445,180));arrow(d,(345,350),(445,425));arrow(d,(970,420),(1065,355));arrow(d,(1320,195),(970,160))
        else:
            rects=[(35,190,360,425),(440,190,760,425),(835,190,1185,425),(1260,190,1575,425)]
            for i in range(3):arrow(d,(rects[i][2]+3,300),(rects[i+1][0]-5,300))
        for i,(r,t) in enumerate(zip(rects,nodes)):box(d,r,t,i+1)
    elif kind=='lanes' and n==2:
        xs=[30,425,820,1215]
        for i,t in enumerate(nodes):box(d,(xs[i],170,xs[i]+355,360),t,i+1)
        for i in range(3):arrow(d,(xs[i]+358,230),(xs[i+1]-5,230));arrow(d,(xs[i+1]-5,320),(xs[i]+358,320),color='#379184')
        label(d,(50,75,1550,140),'上行  机器人声音与选定图片 → 模型' if lang==0 else 'Upstream  robot sound and selected images → model',29)
        label(d,(50,400,1550,475),'下行  模型声音 → 本地适配 → Agora → 机器人' if lang==0 else 'Downstream  model audio → local adaptation → Agora → robot',29)
        label(d,(50,485,1550,545),'Enabot 管理登录和设备信息   Agora 管理实时消息和媒体' if lang==0 else 'Enabot manages login and device information   Agora handles realtime messages and media',24)
    else:
        for i,t in enumerate(nodes):
            x=30+i*395;box(d,(x,150,x+355,420),t,i+1)
            if i<3:arrow(d,(x+358,285),(x+390,285))
        if kind=='timeline':
            arrow(d,(65,490),(1530,490))
            label(d,(50,490,1550,555),'时间向右   各阶段可能重叠  并非按比例绘制' if lang==0 else 'Time moves right   Stages can overlap   Not drawn to scale',25)
        else:
            label(d,(45,450,1555,540),'按编号读图  再看下面每一步的原因与限制' if lang==0 else 'Follow the numbered steps, then read the reasons and limits below',25)
    path=ASSETS/f'{n:02d}_{lang}.png';im.save(path);return path

def env_values():
    # Parse only locally; secret values never enter generated artifacts or diagnostic output.
    text=(PROJECT/'.env').read_text(encoding='utf-8-sig'); vals={}
    lines=text.splitlines();i=0
    while i<len(lines):
        m=re.match(r'^([A-Z][A-Z0-9_]*)=(.*)$',lines[i]);i+=1
        if not m:continue
        k,v=m.groups()
        if v.startswith("'") and not (len(v)>1 and v.endswith("'")):
            chunks=[v[1:]]
            while i<len(lines):
                z=lines[i];i+=1
                if z.endswith("'"): chunks.append(z[:-1]);break
                chunks.append(z)
            v='\n'.join(chunks)
        else:v=v.strip().strip("'\"")
        vals[k]=v
    return vals
ENV=env_values();OPTIONS=json.loads((PROJECT/'ebo-data/options.json').read_text(encoding='utf-8-sig'))

def distill():
    d=Document(REF); z=zipfile.ZipFile(REF)
    inventory={n:dict(size=len(z.read(n)),sha256=hashlib.sha256(z.read(n)).hexdigest()) for n in z.namelist()}
    (HERE/'reference_inventory.json').write_text(json.dumps(inventory,indent=2),encoding='utf-8')
    styles={s.name:etree.tostring(s.element,encoding='unicode') for s in d.styles}
    (HERE/'reference_styles.json').write_text(json.dumps(styles,ensure_ascii=False,indent=2),encoding='utf-8')
    sha=hashlib.sha256(REF.read_bytes()).hexdigest()
    contract=f'''# Artifact execution contract
Reference: {REF}
SHA256: {sha}
Reference has 7 rendered pages, one Letter section, width 8.5in height 11in, top 0.7in bottom 0.6201389in left/right 0.7in. Header/footer distances and first-page behavior retained from sectPr.
Evidence: reference_render/page-1.png through page-7.png, reference_inventory.json and reference_styles.json. Word is the rendering backend because the canonical renderer could not find bundled LibreOffice on Windows. Word COM export succeeded. Final rasterization uses the packaged render_docx.py with a local conversion adapter and bundled Poppler.
Visual roles: title 22pt bold, first cover title has larger direct formatting; body uses inherited theme Arial. Heading1 13.5pt bold, after 6.5pt, line 1.1875. Dark navy table headers, pale blue/near-white alternating body, centered tables. Diagram panel uses navy header, blue boxes and connectors.
Page patterns: cover with generous vertical whitespace, two Title slots and metadata table; subsequent pages use headings, body prose, diagram with caption, or comparison tables. Recurring footer is centered organization and document title.
Editable slots: word/document.xml body Title paragraphs replace system and proposal names; cover metadata tables replace audience/edition/scope records. All proposal narrative, example architecture drawing, example footnote, examples and unsupported approval/reviewer slots are replaced or removed. Expand narrative slots into 30 tutorial sections and parameter/prompt/glossary/source appendices using cloned source heading and table patterns. All body content is task-owned; no template placeholder remains. Footer text is an editable recurring slot.
User-requested deviations: tutorial depth requires many added sections and diagrams rather than the template's short proposal. Chinese uses Microsoft YaHei for CJK glyphs. Both languages have identical section and figure IDs. Body stays editable text, tables stay editable tables, diagram images have editable captions. New parameter tables need three columns with room for long names.
Document-skill overrides: all heading/title/footer text black; visible table grid D9D9D9; table headers repeat, rows grow without fixed heights. Main body 11pt (CJK 10.5pt), approximately 1.18 line spacing; readability for a beginner takes priority over dense reference typography. One conceptual lesson per page allows pictures and explanation to be read together.
Preserve-only: theme, numbering, fontTable and all untouched reference package parts. styles edited only for language/readability and heading-color requirements. document, settings, rels, footer and metadata are editable. Remove the unused template footnote text. Existing unused media may stay but are not visible. Save via python-docx then preserve reference opaque parts by package comparison. Update page fields using Word only.
Fidelity gates: keep one section and exact page geometry; original reference hash unchanged; source theme and numbering preserved; inspect every final page and check all paragraphs/tables fit. Expected differences are cover wording, expanded lesson count and new figures. No movement outside the recurring page geometry is allowed.
'''
    (HERE/'artifact.md').write_text(contract,encoding='utf-8')
    return sha

def set_font(run,size=11,bold=None,color=INK):
    run.font.name='Arial';run.font.size=Pt(size);run.font.color.rgb=RGBColor.from_string(color.lstrip('#'))
    rp=run._element.get_or_add_rPr();rf=rp.rFonts
    if rf is None:rf=OxmlElement('w:rFonts');rp.insert(0,rf)
    rf.set(qn('w:eastAsia'),'Microsoft YaHei')
    if bold is not None:run.bold=bold

def bookmark(p,name):
    n=str(100+len(BOOKMARKS));BOOKMARKS.append(name)
    b=OxmlElement('w:bookmarkStart');b.set(qn('w:id'),n);b.set(qn('w:name'),name)
    e=OxmlElement('w:bookmarkEnd');e.set(qn('w:id'),n)
    p._p.insert(0,b);p._p.append(e)

def para(d,text,lang,bold=False,size=None,after=7):
    p=d.add_paragraph(style='normal');p.paragraph_format.space_after=Pt(after)
    p.paragraph_format.line_spacing=1.18;p.paragraph_format.widow_control=True
    snap=OxmlElement('w:snapToGrid');snap.set(qn('w:val'),'0');p._p.get_or_add_pPr().append(snap)
    r=p.add_run(text);set_font(r,size or (10.5 if lang==0 else 11),bold)
    return p
def heading(d,text,lang,anchor=None,newpage=False):
    p=d.add_paragraph(text,style='Heading 1');p.paragraph_format.page_break_before=newpage
    for r in p.runs:set_font(r,15,True,'#000000')
    p.paragraph_format.space_after=Pt(9);p.paragraph_format.keep_with_next=True
    if anchor:bookmark(p,anchor)
    return p

def table(d,headers,rows,widths,lang):
    # Clone the reference comparison table so its table style remains source-derived.
    el=copy.deepcopy(TABLE_PATTERN);t=Table(el,d._body)
    for row in list(t.rows):el.remove(row._tr)
    grid=el.tblGrid
    for c in list(grid):grid.remove(c)
    for w in widths:
        c=OxmlElement('w:gridCol');c.set(qn('w:w'),str(round(w*1440)));grid.append(c)
    d._body._body.insert(len(d._body._body)-1,el)
    t.autofit=False;t.alignment=WD_TABLE_ALIGNMENT.CENTER
    pr=el.tblPr
    for child in list(pr):
        if child.tag in [qn('w:tblW'),qn('w:tblBorders'),qn('w:tblCellMar')]:pr.remove(child)
    tw=OxmlElement('w:tblW');tw.set(qn('w:w'),str(round(sum(widths)*1440)));tw.set(qn('w:type'),'dxa');pr.append(tw)
    borders=OxmlElement('w:tblBorders')
    for edge in ['top','left','bottom','right','insideH','insideV']:
        v=OxmlElement('w:'+edge);v.set(qn('w:val'),'single');v.set(qn('w:sz'),'4');v.set(qn('w:color'),'D9D9D9');borders.append(v)
    pr.append(borders)
    mar=OxmlElement('w:tblCellMar')
    for edge,val in [('top',90),('bottom',90),('left',110),('right',110)]:
        v=OxmlElement('w:'+edge);v.set(qn('w:w'),str(val));v.set(qn('w:type'),'dxa');mar.append(v)
    pr.append(mar)
    for ri,vals in enumerate([headers]+rows):
        r=t.add_row();rp=r._tr.get_or_add_trPr();rp.append(OxmlElement('w:cantSplit'))
        if ri==0:rp.append(OxmlElement('w:tblHeader'))
        for ci,(c,txt,w) in enumerate(zip(r.cells,vals,widths)):
            c.width=Inches(w);c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            cp=c._tc.get_or_add_tcPr(); sh=OxmlElement('w:shd');sh.set(qn('w:fill'),'0C2C4B' if ri==0 else ('E7F1F9' if ri%2 else 'F7FAFC'));cp.append(sh)
            cm=OxmlElement('w:tcMar')
            for edge,val in [('top',95),('bottom',95),('left',120),('right',120)]:
                vv=OxmlElement('w:'+edge);vv.set(qn('w:w'),str(val));vv.set(qn('w:type'),'dxa');cm.append(vv)
            cp.append(cm)
            p=c.paragraphs[0];p.paragraph_format.space_after=Pt(0);p.paragraph_format.line_spacing=1.1
            p.paragraph_format.keep_with_next=False
            snap=OxmlElement('w:snapToGrid');snap.set(qn('w:val'),'0');p._p.get_or_add_pPr().append(snap)
            run=p.add_run(str(txt));set_font(run,9.3 if lang else 9.2,ri==0,'#FFFFFF' if ri==0 else INK)
            if ci==1 and len(widths)==3 and widths[1]<1.5:p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    return t

def page_ref(p,name):
    r=p.add_run();set_font(r,10)
    fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),f' PAGEREF {name} \\h ')
    rr=OxmlElement('w:r');tt=OxmlElement('w:t');tt.text='…';rr.append(tt);fld.append(rr);p._p.append(fld)

def current(row,lang):
    key,default,z,e,kind=row
    if key in ['OPENAI_API_KEY','EBO_API_TOKEN','EBO_EMAIL / EBO_PASSWORD','EBO_PAYLOAD_KEY / EBO_SIGN_KEY']:return '已配置 值省略' if lang==0 else 'Configured\nvalue omitted'
    if key=='EBO_ASSISTANT_INSTRUCTIONS':return '见附录 B' if lang==0 else 'Appendix B'
    if kind=='A':return ENV.get(key,default) or ('空' if lang==0 else 'blank')
    if kind=='B' and key in OPTIONS:
        v=OPTIONS[key];return str(v).lower() if isinstance(v,bool) else str(v)
    if key=='EBO_REGION / EBO_CLOUD_HOST':return 'CN / CN host'
    if key=='robot_id / mcp / log_level':return '0 / false / info'
    return default or ('空' if lang==0 else 'blank')

def cover(d,lang):
    # Preserve the retained cover's structure, spacing and two metadata components.
    titles=[p for p in d.paragraphs if p.style.name=='Title'][:2]
    for p,text in zip(titles,[['EBO 家庭机器人助手','EBO Home Robot Assistant'][lang],['架构与音视频技术图解','Architecture and Media Technology'][lang]]):
        p.clear();r=p.add_run(text);set_font(r,24,True,'#000000')
    first=d.tables[0]
    texts=[['版本\n技术图解 1.0','','对象\n零技术基础读者','','日期\n2026 09 08'],['EDITION\nTechnical guide 1.0','','AUDIENCE\nReaders new to technology','','UPDATED\n2026 09 08']][lang]
    for c,txt in zip(first.rows[0].cells,texts):
        c.text=txt
        for p in c.paragraphs:
            for r in p.runs:set_font(r,9,False)
    vals=[['读者','希望理解机器人工作原理并能修改参数的人'],['两种语言','中文和英文采用同一章节 图号 示例与参数'],['内容','30 幅图解  参数目录  完整 Prompt  术语与代码索引'],['范围','机器人  设备云  本地电脑  OpenAI 的完整往返链路']] if lang==0 else [
        ['Audience','Readers who want to understand and configure the robot'],['Two editions','Matching sections, figure IDs, examples and parameters'],['Contents','30 diagrams, parameter catalog, complete prompt, glossary and code index'],['Scope','The full path through the robot, device cloud, local computer and OpenAI']]
    for row,data in zip(d.tables[1].rows,vals):
        for c,txt in zip(row.cells,data):
            c.text=txt
            for p in c.paragraphs:
                for r in p.runs:set_font(r,10)
    # Everything after the cover is expanded from tutorial-owned source slots.
    body=d._element.body;last=d.tables[1]._tbl;seen=False
    for el in list(body):
        if seen and el.tag!=qn('w:sectPr'):body.remove(el)
        if el is last:seen=True

def make(lang):
    global TABLE_PATTERN,BOOKMARKS
    BOOKMARKS=[];d=Document(REF);TABLE_PATTERN=copy.deepcopy(d.tables[3]._tbl)
    cover(d,lang)
    for sn in ['Title','Heading 1','Heading 2','Heading 3']:
        s=d.styles[sn];s.font.color.rgb=RGBColor(0,0,0)
        if s.element.rPr is not None:
            c=s.element.rPr.find(qn('w:color'))
            if c is not None:
                for a in list(c.attrib):
                    if a!=qn('w:val'):del c.attrib[a]
    for sec in d.sections:
        for p in sec.footer.paragraphs:
            p.clear();p.alignment=WD_ALIGN_PARAGRAPH.CENTER
            r=p.add_run('EBO AI Home   |   '+('架构与音视频技术' if lang==0 else 'Architecture and media technology')+'   |   ');set_font(r,8,color='#000000')
            fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),'PAGE');p._p.append(fld)
    # Native page-reference fields remain editable and are refreshed in Word.
    for part in [0,1]:
        heading(d,['阅读导航','Reading guide'][lang]+('' if part==0 else [' 续',' continued'][lang]),lang,newpage=True)
        if part==0:
            para(d,['从第 1 章开始，先看图和比喻，再读解释。需要改参数时查附录 A；想修改性格和说话方式时查附录 B。图中的编号表示阅读顺序，不代表固定耗时。','Start at section 1: read the picture and analogy, then the explanation. Use Appendix A for settings and Appendix B for persona and speech behavior. Diagram numbers indicate reading order, not fixed durations.'][lang],lang)
        for sec in SECTIONS[part*15:(part+1)*15]:
            p=para(d,f"{sec['n']:02d}   {sec['title'][lang]}",lang,after=9,size=10.5)
            p.add_run('   ');page_ref(p,f"ch{sec['n']}")
        if part==1:
            for an,z,e in [('params','附录 A 参数目录','Appendix A Parameter catalog'),('prompt','附录 B 完整运行 Prompt','Appendix B Complete runtime prompt'),('interfaces','附录 C 接口与技术依赖','Appendix C Interfaces and dependencies'),('glossary','附录 D 术语表','Appendix D Glossary'),('sources','附录 E 代码和官方来源','Appendix E Code and official sources')]:
                p=para(d,[z,e][lang],lang,after=7,size=10);p.add_run('   ');page_ref(p,an)
    for sec in SECTIONS:
        heading(d,f"{sec['n']:02d}  {sec['title'][lang]}",lang,f"ch{sec['n']}",True)
        para(d,sec['analogy'][lang],lang,bold=True,after=9)
        p=d.add_paragraph();p.paragraph_format.space_after=Pt(2);p.paragraph_format.keep_with_next=True
        img=p.add_run().add_picture(str(figure(sec,lang)),width=Inches(7.05));img._inline.docPr.set('descr',sec['title'][lang]+': '+' → '.join(sec['nodes'][lang]))
        p=para(d,('图 ' if lang==0 else 'Figure ')+str(sec['n'])+'  '+sec['title'][lang],lang,size=9,after=9)
        for z,e in sec['paras']:para(d,[z,e][lang],lang)
        para(d,('代码依据 ' if lang==0 else 'Code references ')+sec['ref']+('  见附录 E' if lang==0 else '  See Appendix E'),lang,size=8.5,after=0)
    heading(d,['附录 A 参数目录','Appendix A Parameter catalog'][lang],lang,'params',True)
    para(d,['当前值为 2026-09-08 文件快照；只有正文健康检查列出的少量字段同时得到运行服务确认。默认值优先采用当前 Compose 的回退值，裸 Python 默认不同时单独注明。修改本书不会修改机器人。','Current values are a file snapshot from 2026-09-08. Only the limited fields described in the health-check section were additionally confirmed by the running service. Defaults use current Compose fallbacks where wired; differing bare-Python defaults are stated. Editing this guide does not reconfigure the robot.'][lang],lang)
    table(d,['类别','在哪里改','如何应用'] if lang==0 else ['Class','Where to edit','How to apply'],[
        ['A','.env',('Assistant 用 reload 脚本；Agora 开关用音频设置脚本；Engine 日志参数重建 Engine。' if lang==0 else 'Use the reload script for Assistant, the audio-settings script for Agora switches, and recreate Engine for Engine log settings.')],
        ['B','ebo-data/options.json / prepare-ebo.ps1',('检查脚本是否会重写旧值，再应用 Engine 配置。' if lang==0 else 'Check whether preparation overwrites tuned settings before applying Engine configuration.')],
        ['C',('代码或 Compose 映射' if lang==0 else 'Code or Compose wiring'),('需要配套改动和验证，不能只在 .env 添一行。' if lang==0 else 'Requires coordinated edits and validation; an extra .env line is insufficient.')]], [0.55,2.45,4.05],lang)
    para(d,['同一参数的“默认”和“当前”分别列出。空表示未显式提供，由程序或服务器回退。单位 ms 是毫秒，1000 ms=1 秒；MiB=1048576 字节。范围来自本地校验时，并不承诺所有模型接受所有组合。','Default and current values are shown separately. Blank means no explicit value, leaving program or server fallback. ms means milliseconds; 1000 ms=1 second. MiB=1048576 bytes. Local validation ranges do not guarantee that every model accepts every combination.'][lang],lang)
    para(d,['常用路线  模型与声音 → VAD → 流式播放 → 视觉选帧 → 上下文与恢复 → Prompt → 存储 → Engine → 固定常量。','Suggested route: model and voice → VAD → streaming → vision → context and recovery → prompt → storage → Engine → constants.'][lang],lang,bold=True)
    for gi,g in enumerate(GROUPS,1):
        # Limit a table page to six or seven parameter records for readable names.
        chunks=[g['rows']]
        for ci,chunk in enumerate(chunks):
            heading(d,f"A{gi:02d}  {g['title'][lang]}"+([' 续',' continued'][lang] if ci else ''),lang,newpage=True)
            rows=[]
            for r in chunk:
                key,default,z,e,kind=r
                defv=('空' if lang==0 else 'blank') if not default else default
                if key=='EBO_ASSISTANT_INSTRUCTIONS':defv='内置中文' if lang==0 else 'Built-in Chinese'
                cur=current(r,lang)
                v=(('默认 = 当前\n' if lang==0 else 'Default = current\n')+defv) if cur==defv else (('默认 ' if lang==0 else 'Default\n')+defv+'\n'+('当前 ' if lang==0 else 'Current\n')+cur)
                # Wrap long identifiers at their visible underscore boundaries.
                pretty=key
                if len(key)>24 and '_' in key:
                    chunks2=[];line=''
                    for word in key.split('_'):
                        part=word+('_' if word!=key.split('_')[-1] else '')
                        if line and len(line+part)>24:chunks2.append(line);line=''
                        line+=part
                    if line:chunks2.append(line)
                    pretty='\n'.join(chunks2)
                rows.append([pretty+'\n'+kind,v,[z,e][lang]])
            table(d,['参数名与类别','默认与当前','含义 范围和修改影响'] if lang==0 else ['Parameter and class','Default and current','Meaning, range and effect'],rows,[2.45,1.65,2.95],lang)
            para(d,g['note'][lang],lang,after=8)
            para(d,['依据 Config.from_env 与 validate、compose.yaml、Engine run.sh、pcm_talk.py 和当前私有配置的非敏感字段。','Sources: Config.from_env and validate, compose.yaml, Engine run.sh, pcm_talk.py and nonsecret fields in current private configuration.'][lang],lang,size=8.5)
    prompt_appendix(d,lang)
    technical_appendix(d,lang)
    for part in range(2):
        heading(d,['附录 D 术语表','Appendix D Glossary'][lang]+f'  {part+1}',lang,'glossary' if part==0 else None,True)
        rows=[[r[0]+('\n'+r[1] if lang==0 else ''),r[2+lang]] for r in GLOSSARY[part*16:(part+1)*16]]
        table(d,['术语','用日常语言理解'] if lang==0 else ['Term','Plain-language meaning'],rows,[2.25,4.8],lang)
    source_appendix(d,lang)
    d.core_properties.title=['EBO 家庭机器人助手架构与音视频技术图解','EBO Home Robot Assistant Architecture and Media Technology'][lang]
    d.core_properties.subject='EBO AI Home architecture and technical reference'
    d.core_properties.author='EBO AI Home';d.core_properties.keywords='EBO, Realtime, audio, video, architecture'
    update=d.settings.element.find(qn('w:updateFields'))
    if update is None:update=OxmlElement('w:updateFields');d.settings.element.append(update)
    update.set(qn('w:val'),'true')
    p=OUT/(['EBO_架构与音视频技术详解_中文版.docx','EBO_Architecture_and_Media_Technology_English.docx'][lang]);d.save(p)
    cleanup_package(p)
    return p

def prompt_appendix(d,lang):
    text=ENV['EBO_ASSISTANT_INSTRUCTIONS'].strip();sections=[]
    for block in re.split(r'^# ',text,flags=re.M):
        if not block.strip():continue
        lines=block.strip().splitlines();sections.append((lines[0],[x[2:] if x.startswith('- ') else x for x in lines[1:] if x.strip()]))
    assert len(sections)==len(PROMPT_EN)==7
    assert [len(x[1]) for x in sections]==[len(x[1]) for x in PROMPT_EN]
    for part,ids in enumerate([[0,1],[2,3],[4,5,6]]):
        heading(d,['附录 B 完整运行 Prompt','Appendix B Complete runtime prompt'][lang]+f'  {part+1}',lang,'prompt' if part==0 else None,True)
        if part==0:
            para(d,['以下保留当前基础 Prompt 的全部规则。英文版逐条翻译同一组规则；翻译是文档说明，不代表运行配置已经改为英语。这里是基础 Prompt，程序另附加视觉规则和动态记忆。','The following translates every rule in the current base prompt. The Chinese edition contains the original rules. This documentation translation does not switch the runtime to English. These are base instructions; the program separately appends visual rules and dynamic memories.'][lang],lang)
        for i in ids:
            title,items=sections[i] if lang==0 else PROMPT_EN[i]
            heading(d,title,lang)
            for item in items:para(d,'• '+item,lang,after=7)
    heading(d,['B04 程序追加的视觉规则与交接指令','B04 Appended visual rules and handoff instructions'][lang],lang,newpage=True)
    rules_zh=['摄像头图片是内部感知上下文，不是用户发言，也不是需要确认的任务。','不要仅因收到图片而回答，也不要说“已收到图片”或“已把图片作为视觉上下文”。','优先回答最近一次有效语音。只有用户明确询问你看到了什么时，才自然描述图中的具体内容。','不要向用户解释图片注入、运动检测或其他内部工作方式。','对空白声音、背景噪声或无法理解的碎片不要回答。','通常每次只说一到两句，并避免重复上一轮表达。']
    rules_en=['Camera images are internal perceptual context, not user speech or tasks requiring acknowledgment.','Do not respond merely because an image arrived, or announce that it was received or added as visual context.','Prioritize the latest valid speech. Describe concrete image details naturally only when explicitly asked what you see.','Do not explain image injection, motion detection or other internal mechanisms to the user.','Do not respond to empty audio, background noise or unintelligible fragments.','Usually speak only one or two sentences and avoid repeating the previous response.']
    for t in [rules_zh,rules_en][lang]:para(d,'• '+t,lang)
    para(d,['交接指令要求保留已确认事实、用户偏好、进行中任务、未解决问题和必要的近期背景；不问候、不解释、不提及会话或摘要，不从声音或画面推断敏感属性，用简洁中文且最多 1200 汉字。请求最多 600 tokens，随后本地还按字符限制截取。','The handoff instruction requests confirmed facts, preferences, ongoing tasks, unresolved questions and necessary recent context. It prohibits greetings, explanations, references to sessions/summaries and sensitive inferences from sound or images. It asks for concise Chinese with at most 1200 Chinese characters. The request is capped at 600 tokens and the resulting string is additionally capped locally.'][lang],lang)
    para(d,['记忆前缀明确说明摘要和断线记录是历史背景而非指令；家人当前的纠正应优先。角色 Prompt、追加规则与历史内容都要避免相互矛盾。','Memory prefixes explicitly label summaries and reconnect records as background, not instructions, with current corrections taking precedence. Base instructions, appended rules and history should avoid contradictions.'][lang],lang)

def technical_appendix(d,lang):
    heading(d,['附录 C 接口与技术依赖','Appendix C Interfaces and dependencies'][lang],lang,'interfaces',True)
    rows=[['8123','Home Assistant',('浏览器家庭面板' if lang==0 else 'Household dashboard')],['8098','Engine HTTP API',('/api/robots 状态  /api/cmd 命令  /api/snapshot 图片' if lang==0 else '/api/robots state; /api/cmd commands; /api/snapshot images')],['127.0.0.1:8101 → 8099','Engine Panel',('仅本机控制面板' if lang==0 else 'Host-local control panel')],['8554–8557','RTSP',('当前默认路径 /ebo；音视频给本地消费者' if lang==0 else 'Default path /ebo; audio/video to local consumers')],['8189–8192 TCP/UDP','WebRTC/WHEP',('媒体观看连接；需浏览器可达网络候选地址' if lang==0 else 'Viewing connection; browser needs reachable network candidates')],['8200','PCM WebSocket',('仅容器网络，/talk；start 二进制 end stop' if lang==0 else 'Container network only, /talk; start, binary, end, stop')],['8099','Assistant HTTP',('/health 状态与 /audio WAV，当前接口没有单独登录' if lang==0 else '/health and /audio WAV; no separate login in the current handler')],['443 WSS','OpenAI Realtime',('会话事件与 Base64 音频 图片' if lang==0 else 'Session events with Base64 audio/images')]]
    table(d,['端口','接口','用途'] if lang==0 else ['Port','Interface','Purpose'],rows,[1.25,1.5,4.3],lang)
    para(d,['宿主机的 localhost 指当前电脑；容器里的 localhost 指该容器。不要在 Assistant 内把 localhost:8098 当成 Engine。主机发布的 8098、8099、8554 等端口是否从局域网可达还受防火墙影响。','localhost on the host means the current computer; localhost inside a container means that container. localhost:8098 inside Assistant is not Engine. Firewall rules also affect LAN reachability of published host ports such as 8098, 8099 and 8554.'][lang],lang)
    heading(d,['C02 消息字段和单位速查','C02 Message fields and units'][lang],lang,newpage=True)
    rows=[['session.update','Session settings',('配置不是用户发言' if lang==0 else 'Configuration, not user speech')],['input_audio_buffer.append','Base64 PCM24',('输入约 100 ms 读取；音频块不是单词' if lang==0 else 'Input reads around 100 ms; chunks are not words')],['conversation.item.create / input_image','JPEG data URL',('最新图片背景；ID 总长 32' if lang==0 else 'Latest image context; 32-character ID')],['response.create','Response request',('当前在最终转写通过后发送' if lang==0 else 'Currently sent after validated final transcription')],['response.output_audio.delta','Base64 PCM24',('流式生成声音增量' if lang==0 else 'Incremental generated audio')],['response.cancel','response_id',('停止继续生成；与停止本地播放不同' if lang==0 else 'Stops generation; separate from stopping local playback')],['conversation.item.truncate','item_id / audio_end_ms',('纠正未播放部分的上下文；毫秒近似播放点' if lang==0 else 'Corrects unplayed audio context; millisecond playback proxy')],['start / ready / progress / end / stop','Local WebSocket',('ready 已接收握手；end 播完余量；stop 丢弃余量' if lang==0 else 'ready confirms handshake; end drains; stop discards')]]
    table(d,['消息','载荷或字段','读法'] if lang==0 else ['Message','Payload or field','Interpretation'],rows,[2.55,1.35,3.15],lang)
    heading(d,['C03 依赖版本与实现语言','C03 Dependency versions and implementation languages'][lang],lang,newpage=True)
    rows=[['Assistant Python','3.12 slim bookworm','Dockerfile'],['Engine Python','3.11 slim / glibc','Dockerfile'],['NumPy','2.2.6',('像素和声音数组计算' if lang==0 else 'Pixel/audio array calculations')],['OpenCV headless','4.12.0.88',('图像解码 缩放和运动检测' if lang==0 else 'Image decoding, resizing and motion detection')],['websocket-client','1.8.0',('Assistant 的 OpenAI 与 Engine 客户端' if lang==0 else 'Assistant client for OpenAI and Engine')],['webrtcvad-wheels','2.0.14',('本地插话语音检测' if lang==0 else 'Local interruption speech detection')],['Agora Python Server SDK','2.4.9',('设备 RTC RTM 与 APM' if lang==0 else 'Device RTC, RTM and APM')],['websockets','17.1',('Engine PCM 服务端' if lang==0 else 'Engine PCM server')],['MediaMTX','1.9.3',('本地媒体分发' if lang==0 else 'Local media distribution')],['hls.js','1.5.15',('浏览器 HLS 播放回退' if lang==0 else 'Browser HLS fallback')]]
    table(d,['依赖','代码声明的版本','用途或出处'] if lang==0 else ['Dependency','Version declared in code','Role or source'],rows,[2.15,1.55,3.35],lang)
    para(d,['这些是构建文件中的声明，不代表已重新检查所有正在运行的镜像。HA 使用 stable 标签；FFmpeg 通过系统包安装，因此本文不虚构一个固定运行版本。Engine 的 Agora 二进制依赖 glibc，不能直接换成 Alpine musl 基础镜像；PCM 重采样使用 Python 3.11 的 audioop，升级 Python 需处理兼容性。','These are build-file declarations, not a fresh inventory of every running image. HA uses a stable tag and FFmpeg comes from system packages, so no fixed runtime version is invented. Engine’s Agora binaries require glibc rather than Alpine musl. PCM resampling uses audioop in Python 3.11, so a Python upgrade needs compatibility work.'][lang],lang)

def source_appendix(d,lang):
    for i in range(2):
        heading(d,['附录 E 代码和官方来源','Appendix E Code and official sources'][lang]+f'  {i+1}',lang,'sources' if i==0 else None,True)
        if i==0:para(d,['代码基线 HEAD 71fc0c4，检查日期 2026-09-08。这里的文件名相对于 ebo-ai-home 根目录。正文 S 编号对应代码依据；O 编号对应官方说明。原有旧手册中整段 WAV 的描述已按当前流式代码更新。','Code baseline HEAD 71fc0c4, inspected on 2026-09-08. Paths are relative to ebo-ai-home. S identifiers map to local implementation; O identifiers map to official documentation. Older whole-WAV descriptions have been updated to match the current streaming code.'][lang],lang)
        for sid,path,anchor,z,e in SOURCES[i*10:(i+1)*10]:
            p=para(d,sid+'  '+path,lang,bold=True,size=10,after=3)
            para(d,anchor+'\n'+[z,e][lang],lang,size=9.5,after=10)
    heading(d,['E03 官方来源与证据边界','E03 Official sources and evidence boundaries'][lang],lang,newpage=True)
    for oid,title,url,z,e in WEB:
        para(d,oid+'  '+title,lang,bold=True,after=3)
        para(d,url,lang,size=9,after=3);para(d,[z,e][lang],lang,size=10)
    para(d,['官方页面核对日期 2026-09-08。具体实现以本地代码为准：模型支持某能力，不代表本程序已经接入。参数当前值来自配置，少量 VAD 和连通性字段还由 health 回传确认；历史故障记录标明日期。所有容量、时延与存储算例均标明单位，不替代实际测量。','Official pages checked on 2026-09-08. Implementation claims follow local code: model support does not mean this program has integrated the feature. Current values come from configuration, with a limited set of VAD and connectivity fields also confirmed through health. Historical incidents are dated. Capacity, latency and storage examples state their units and do not replace measurements.'][lang],lang)

def cleanup_package(path):
    # Remove unused instructional footnote content left in the retained template.
    with zipfile.ZipFile(path) as z:data={n:z.read(n) for n in z.namelist()}
    if 'word/footnotes.xml' in data:
        root=etree.fromstring(data['word/footnotes.xml'])
        for node in list(root):
            if node.get(qn('w:id')) not in ('-1','0'):root.remove(node)
        data['word/footnotes.xml']=etree.tostring(root,encoding='UTF-8',xml_declaration=True,standalone=True)
    tmp=path.with_suffix('.tmp.docx')
    with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as z:
        for n,b in data.items():z.writestr(n,b)
    tmp.replace(path)

if __name__=='__main__':
    refhash=distill()
    result=[make(0),make(1)]
    assert hashlib.sha256(REF.read_bytes()).hexdigest()==refhash
    counts=dict(sections=len(SECTIONS),figures_per_edition=len(SECTIONS),parameter_records=sum(len(g['rows']) for g in GROUPS),parameter_groups=len(GROUPS),glossary_entries=len(GLOSSARY),prompt_rules=sum(len(x[1]) for x in PROMPT_EN))
    (HERE/'manifest.json').write_text(json.dumps(dict(outputs=[str(p) for p in result],counts=counts),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(counts));print('\n'.join(str(p) for p in result))
