"""Use the canonical rasterizer with Word PDFs when bundled LO is unavailable on Windows."""
import importlib.util,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
SKILL=Path(os.environ['EBO_DOCUMENTS_SKILL_DIR'])
POPPLER=Path(os.environ['EBO_POPPLER_BIN'])
os.environ['PATH']=str(POPPLER)+os.pathsep+os.environ['PATH']
spec=importlib.util.spec_from_file_location('canonical_docx_renderer',SKILL/'render_docx.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
def word_conversion(doc_path,user_profile,convert_tmp_dir,stem,verbose=False):
    p=HERE/(stem+'.pdf')
    if not p.exists():raise FileNotFoundError(p)
    return str(p),'Microsoft Word ExportAsFixedFormat; canonical rasterization follows.'
mod.convert_to_pdf=word_conversion
outputs=json.loads((HERE/'manifest.json').read_text(encoding='utf-8'))['outputs']
for i,path in enumerate(outputs):
    out=HERE/('render_zh' if i==0 else 'render_en')
    pages=mod.rasterize(path,str(out),125,verbose=False,emit_pdf=False)
    print(out,len(pages),flush=True)
