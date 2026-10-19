"""Build the selected interface with disposable Pages-only synthetic adapters."""
from pathlib import Path
import argparse,os,shutil
from datetime import datetime,timezone

def build(output):
    root=Path(__file__).resolve().parents[1]
    output.mkdir(parents=True,exist_ok=True)
    for name in ('index.html','preview.css','preview.js','access-preview.js','student-profile.js','edit-windows.js','school-logo.jpg','IBMPlexSansArabic-Regular.ttf','IBM_Plex_Sans_Arabic_OFL.txt','.nojekyll'):
        shutil.copy2(root/'docs'/name,output/name)
    for name in ('workspace-runtime.js','workspace-entry.js','workspace-config.json'):
        shutil.copy2(root/'preview'/name,output/name)
    for source,target in (('bridge.js','live-bridge.js'),('workspace.js','workspace.js'),('workspace.css','workspace.css')):
        shutil.copy2(root/'live'/source,output/target)
    html=(output/'index.html').read_text(encoding='utf-8').replace('</head>','<link rel="stylesheet" href="workspace.css"></head>')
    html=html.replace('</body>','<script src="workspace-runtime.js"></script><script src="live-bridge.js"></script><script src="workspace.js"></script><script src="workspace-entry.js"></script></body>')
    # Fixed synthetic fixtures still use today's browser form bounds.
    js=(output/'preview.js').read_text(encoding='utf-8')
    js=js.replace("'2026-10-14'",repr(datetime.now(timezone.utc).date().isoformat()))
    (output/'preview.js').write_text(js,encoding='utf-8')
    version=os.environ.get('GITHUB_RUN_ID') or os.environ.get('GITHUB_SHA','local')[:12]
    for name in ('preview.css','preview.js','access-preview.js','student-profile.js','edit-windows.js','workspace.css','workspace-runtime.js','live-bridge.js','workspace.js','workspace-entry.js'):
        html=html.replace('"'+name+'"','"'+name+'?v='+version+'"')
    (output/'index.html').write_text(html,encoding='utf-8')
    print('PAGES_PREVIEW_BUILT',version)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('dist'));build(p.parse_args().output)
