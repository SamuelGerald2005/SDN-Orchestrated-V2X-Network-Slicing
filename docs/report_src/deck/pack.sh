#!/bin/bash
# Rebuilds V2X_Evaluation.pptx from the template: unpack, edit kept slides, generate, clean, check, zip.
set -e
cd "$(dirname "$0")"
rm -rf un && python3 -c "import zipfile; zipfile.ZipFile('tpl/template.pptx').extractall('un')"
sed -i 's|EVALUATION I<|EVALUATION II<|' un/ppt/slides/slide1.xml
sed -i 's|CURRENT PROGRESS: Environment &amp; Topology Changes|IMPLEMENTATION: MININET-WIFI TOPOLOGY|' un/ppt/slides/slide9.xml
python3 build.py
python3 - <<'EOF'
import os, re, glob, posixpath
from xml.dom import minidom
U = 'un'
pres = open(U + '/ppt/presentation.xml').read(); rels = open(U + '/ppt/_rels/presentation.xml.rels').read(); ct = open(U + '/[Content_Types].xml').read()
used = set(re.findall(r'r:id="(rId\d+)"', re.search(r'<p:sldIdLst>.*?</p:sldIdLst>', pres, re.S).group(0)))
for rid, tgt in re.findall(r'<Relationship Id="(rId\d+)" Type="[^"]*/slide" Target="slides/(slide\d+\.xml)"/>', rels):
    if rid not in used:
        rels = re.sub(r'<Relationship Id="%s" [^>]*/>' % rid, '', rels)
        ct = ct.replace('<Override PartName="/ppt/slides/%s" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>' % tgt, '')
        os.remove(U + '/ppt/slides/' + tgt); os.remove(U + '/ppt/slides/_rels/' + tgt + '.rels')
# co-authoring change tracking refers to deleted slides: drop it
rels = re.sub(r'<Relationship [^>]*(changesInfo|revisionInfo)[^>]*/>', '', rels)
ct = re.sub(r'<Override PartName="/ppt/(changesInfos/changesInfo1|revisionInfo)\.xml"[^>]*/>', '', ct)
for p in ('ppt/revisionInfo.xml',):
    if os.path.exists(U + '/' + p): os.remove(U + '/' + p)
import shutil; shutil.rmtree(U + '/ppt/changesInfos', ignore_errors=True)
open(U + '/ppt/_rels/presentation.xml.rels', 'w').write(rels); open(U + '/[Content_Types].xml', 'w').write(ct)
refd = set()
for f in glob.glob(U + '/**/*.rels', recursive=True):
    refd |= set(os.path.basename(t) for t in re.findall(r'Target="[^"]*media/([^"]+)"', open(f).read()))
for m in os.listdir(U + '/ppt/media'):
    if m not in refd: os.remove(U + '/ppt/media/' + m)
# app.xml slide count
app = open(U + '/docProps/app.xml').read()
app = re.sub(r'<Slides>\d+</Slides>', '<Slides>%d</Slides>' % len(used), app)
open(U + '/docProps/app.xml', 'w').write(app)
# ---- checks: well-formed XML, rels targets exist, content types cover every part
bad = 0
for f in glob.glob(U + '/**/*.xml', recursive=True) + glob.glob(U + '/**/*.rels', recursive=True) + [U + '/[Content_Types].xml']:
    try: minidom.parse(f)
    except Exception as e: print('XML ERROR', f, e); bad += 1
for f in glob.glob(U + '/**/*.rels', recursive=True):
    base = posixpath.dirname(posixpath.dirname(f[len(U) + 1:]))
    for t, mode in re.findall(r'Target="([^"]+)"(?: TargetMode="(\w+)")?', open(f).read()):
        if mode == 'External': continue
        p = posixpath.normpath(posixpath.join(base, t)) if not t.startswith('/') else t[1:]
        if not os.path.exists(U + '/' + p): print('MISSING TARGET', f, t); bad += 1
ct = open(U + '/[Content_Types].xml').read()
defaults = set(re.findall(r'Default Extension="(\w+)"', ct)); overrides = set(re.findall(r'PartName="([^"]+)"', ct))
for f in glob.glob(U + '/**/*', recursive=True):
    if os.path.isdir(f) or f.endswith('[Content_Types].xml'): continue
    part = '/' + f[len(U) + 1:]
    if part not in overrides and part.rsplit('.', 1)[-1] not in defaults: print('NO CONTENT TYPE', part); bad += 1
for o in overrides:
    if not os.path.exists(U + o): print('OVERRIDE FOR MISSING PART', o); bad += 1
# unique shape ids per slide
for f in glob.glob(U + '/ppt/slides/*.xml'):
    ids = re.findall(r'<p:cNvPr id="(\d+)"', open(f).read())
    if len(ids) != len(set(ids)): print('DUPLICATE SHAPE IDS', f); bad += 1
print('checks:', 'OK' if not bad else '%d problems' % bad, '| slides', len(used))
EOF
cd un && rm -f ../V2X_Evaluation.pptx && zip -qXr ../V2X_Evaluation.pptx '[Content_Types].xml' _rels docProps ppt $(ls -d customXml 2>/dev/null) && cd ..
ls -la V2X_Evaluation.pptx
