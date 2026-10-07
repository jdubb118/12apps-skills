"""indesign-package / visual: re-render every page FROM THE IDML and diff it against the approved HTML page.

The preview reads frames/images/paths through idml_probe and resolves each story's formatting from Styles.xml + overrides,
the way InDesign would; Chromium stands in for InDesign's composer (line breaks are guarded separately by the wrap windows).
Writes work_dir/visual/: <page>_src.png, <page>_idml.png, <page>_heat.png, sheet.jpg (src | idml | heat per page), stats.json.
usage: python3 visual.py <job.json> [<package_dir>]"""
import sys, os, json, html, math, subprocess, zipfile, urllib.parse
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_job, canvas_offset
from idml_probe import load as probe, ap

HERE = os.path.dirname(os.path.abspath(__file__))


def inv(m):
    a, b, c, d, e, f = m; det = a * d - b * c
    ia, ib, ic, id_ = d / det, -b / det, -c / det, a / det
    return [ia, ib, ic, id_, -(ia * e + ic * f), -(ib * e + id_ * f)]


def preview_pages(job, doc, idml, rep, out):
    z = zipfile.ZipFile(idml); pkg = os.path.dirname(idml)
    styles = ET.fromstring(z.read('Resources/Styles.xml')); graphic = ET.fromstring(z.read('Resources/Graphic.xml'))
    colors = {c.get('Self'): 'rgb(%d,%d,%d)' % tuple(float(x) for x in c.get('ColorValue').split()) for c in graphic.iter('Color') if c.get('Space') == 'RGB'}
    PS = {e.get('Self'): e for e in styles.iter('ParagraphStyle')}; CS = {e.get('Self'): e for e in styles.iter('CharacterStyle')}
    cssname = lambda fam, sty: ('f-' + fam + '-' + sty).replace(' ', '-')
    face_css = ''.join(f"@font-face{{font-family:'{cssname(e['indesign_family'], e['indesign_style'])}';src:url('file://{e['file']}')}}" for e in rep['fonts'])
    spreads, stories = probe(idml)
    files = []
    for sp, p in zip(spreads, doc['pages']):
        ox, oy = canvas_offset(doc, p); ox, oy = -ox, -oy           # canvas = spread - offset
        ex = json.load(open(os.path.join(job['work_dir'], 'extract', p['id'] + '.json'))); W, H = ex['W'], ex['H']
        P = lambda x, y: (x + ox, y + oy)
        body = []; gop = None
        for it in sp['items']:
            t = it['type']
            if t == 'Group': gop = it['opacity']; continue
            if it['depth'] == 0: gop = None
            op = it['opacity'] if it['opacity'] is not None else gop
            pre, post = (f'<div style="position:absolute;inset:0;opacity:{op / 100}">', '</div>') if op is not None and op < 100 else ('', '')
            if t == 'Rectangle' and 'image' not in it:
                x0, y0, x1, y1 = it['bbox']; (a, b), (c, d) = P(x0, y0), P(x1, y1)
                body.append(f'{pre}<div style="position:absolute;left:{a}pt;top:{b}pt;width:{c - a}pt;height:{d - b}pt;border-radius:{it["radius"]}pt;background:{colors.get(it["fill"], "transparent")}"></div>{post}')
            elif t == 'Rectangle':
                x0, y0, x1, y1 = it['bbox']; (a, b), (c, d) = P(x0, y0), P(x1, y1)
                cs = it['image']['corners']; xs = [q[0] for q in cs]; ys = [q[1] for q in cs]
                (ia, ib), (ic, idd) = P(min(xs), min(ys)), P(max(xs), max(ys))
                src = 'file://' + os.path.join(pkg, 'Links', urllib.parse.unquote(it['image']['uri'][len('file:Links/'):]))
                body.append(f'{pre}<div style="position:absolute;left:{a}pt;top:{b}pt;width:{c - a}pt;height:{d - b}pt;overflow:hidden;border-radius:{it["radius"]}pt">'
                            f'<img src="{src}" style="position:absolute;left:{ia - a}pt;top:{ib - b}pt;width:{ic - ia}pt;height:{idd - ib}pt;max-width:none"></div>{post}')
            elif t in ('GraphicLine', 'Polygon'):
                dd = ''
                for path in it['geo']:
                    dd += 'M%.3f,%.3f ' % P(*path[0][0])
                    for (a1, l1, r1), (a2, l2, r2) in zip(path, path[1:]): dd += 'C%.3f,%.3f %.3f,%.3f %.3f,%.3f ' % (*P(*r1), *P(*l2), *P(*a2))
                fill = colors.get(it['fill'], 'none') if it['fill'] and it['fill'] != 'Swatch/None' else 'none'
                body.append(f'{pre}<svg style="position:absolute;left:0;top:0;overflow:visible" width="{W}pt" height="{H}pt" viewBox="0 0 {W} {H}">'
                            f'<path d="{dd}" fill="{fill}" stroke="{colors.get(it["stroke"], "none")}" stroke-width="{float(it["sw"] or 0)}"/></svg>{post}')
            elif t == 'TextFrame':
                st = stories[it['story']]; tfp = it['tfp']
                Wt = float(tfp['TextColumnFixedWidth']); dfb = float(tfp['MinimumFirstBaselineOffset'])
                spans = []; just = 'left'
                for psr in st.iter('ParagraphStyleRange'):
                    ps = PS[psr.get('AppliedParagraphStyle')]
                    just = {'CenterAlign': 'center', 'RightAlign': 'right', 'LeftAlign': 'left', 'LeftJustified': 'justify'}.get(psr.get('Justification') or ps.get('Justification'), 'left')
                    pfont = ps.find('Properties/AppliedFont').text; plead = float(ps.find('Properties/Leading').text)
                    for cr in psr.iter('CharacterStyleRange'):
                        cs_ = CS[cr.get('AppliedCharacterStyle')]
                        fam = cr.find('Properties/AppliedFont').text if cr.find('Properties/AppliedFont') is not None else pfont
                        sty = cr.get('FontStyle') or cs_.get('FontStyle') or ps.get('FontStyle')
                        size = float(cr.get('PointSize') or ps.get('PointSize'))
                        lead = float(cr.find('Properties/Leading').text) if cr.find('Properties/Leading') is not None else plead
                        trk = float(cr.get('Tracking') or ps.get('Tracking'))
                        caps = (cr.get('Capitalization') or ps.get('Capitalization')) == 'AllCaps'
                        col = colors[cr.get('FillColor') or ps.get('FillColor')]
                        txt = html.escape(''.join(c.text or '' for c in cr.iter('Content'))).replace(' ', '<br>')
                        spans.append(f'<span style="font-family:\'{cssname(fam, sty)}\';font-size:{size}pt;line-height:{lead}pt;letter-spacing:{trk / 1000}em;'
                                     f'{"text-transform:uppercase;" if caps else ""}color:{col};{"white-space:nowrap;" if cr.get("NoBreak") == "true" else ""}">{txt}</span>')
                M = it['M']; inner = [ap(inv(M), *a) for a, _, _ in it['geo'][0]]
                lx = min(q[0] for q in inner); ly = min(q[1] for q in inner)
                a_, b_, c_, d_, e_, f_ = M
                body.append(f'{pre}<div class="tf" data-d="{dfb}" style="position:absolute;left:0;top:0;width:{Wt}pt;transform-origin:0 0;'
                            f'transform:matrix({a_},{b_},{c_},{d_},{(e_ + ox) / 0.75},{(f_ + oy) / 0.75}) translate({lx}pt,{ly}pt);text-align:{just};font-size:0;line-height:0">'
                            f'<span class="probe" style="display:inline-block;width:0;height:0"></span>{"".join(spans)}</div>{post}')
        fn = os.path.join(out, p['id'] + '.html')
        open(fn, 'w').write(f'<!doctype html><html><head><meta charset="utf-8"><style>{face_css} *{{margin:0;padding:0;box-sizing:border-box}} '
                            f'html,body{{width:{W}pt;height:{H}pt;overflow:hidden;background:#fff}}</style></head><body>'
                            f'<div style="position:relative;width:{W}pt;height:{H}pt;overflow:hidden">{"".join(body)}</div></body></html>')
        files.append(dict(id=p['id'], src=os.path.join(job['html_root'], p['html']), idml=fn, W=W, H=H))
    return files


def main():
    job = load_job(sys.argv[1])
    pkg = sys.argv[2] if len(sys.argv) > 2 else os.path.join(job['out_dir'], job['name'] + '_InDesign')
    rep = json.load(open(os.path.join(job['work_dir'], 'build_report.json')))
    out = os.path.join(job['work_dir'], 'visual'); os.makedirs(out, exist_ok=True)
    pages = []
    for d in job['documents']: pages += preview_pages(job, d, os.path.join(pkg, d['idml'] + '.idml'), rep, out)
    json.dump(pages, open(os.path.join(out, 'pages.json'), 'w'))
    r = subprocess.run(['node', os.path.join(HERE, 'render_diff.mjs'), os.path.join(out, 'pages.json'), out], capture_output=True, text=True)
    if r.returncode: print(r.stdout, r.stderr); raise SystemExit('render failed')
    stats = []; rows = []
    for p in pages:
        a = np.asarray(Image.open(os.path.join(out, p['id'] + '_src.png')).convert('RGB')).astype(int)
        b = np.asarray(Image.open(os.path.join(out, p['id'] + '_idml.png')).convert('RGB')).astype(int)
        dd = np.abs(a - b).max(axis=2)
        Image.fromarray(np.clip(dd * 4, 0, 255).astype('uint8')).save(os.path.join(out, p['id'] + '_heat.png'))
        s = dict(page=p['id'], mean=round(float(dd.mean()), 2), pct_over32=round(float((dd > 32).mean() * 100), 3))
        s['review'] = s['mean'] > 4 or s['pct_over32'] > 3
        stats.append(s)
        sc = 600 / a.shape[1]
        tiles = [Image.open(os.path.join(out, p['id'] + k)).convert('RGB').resize((600, int(a.shape[0] * sc))) for k in ('_src.png', '_idml.png', '_heat.png')]
        row = Image.new('RGB', (1820, tiles[0].height), (255, 0, 0))
        for i, t in enumerate(tiles): row.paste(t, (i * 610, 0))
        rows.append(row)
    sheet = Image.new('RGB', (1820, sum(r.height + 10 for r in rows)), (255, 0, 0)); y = 0
    for r_ in rows: sheet.paste(r_, (0, y)); y += r_.height + 10
    sheet.save(os.path.join(out, 'sheet.jpg'), quality=80)
    json.dump(stats, open(os.path.join(out, 'stats.json'), 'w'), indent=1)
    for s in stats: print(f"  {s['page']:24} mean diff {s['mean']:5.2f}   pixels >32: {s['pct_over32']:6.3f}%{'   <-- LOOK' if s['review'] else ''}")
    print('contact sheet (approved | from IDML | difference):', os.path.join(out, 'sheet.jpg'))


if __name__ == '__main__':
    main()
