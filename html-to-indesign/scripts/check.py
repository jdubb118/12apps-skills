"""indesign-package / check: every gate between a build and a designer.

  1 schema      Adobe's InDesign 2026 RNC schema (schema_check.sh, jing)            must be 0 errors
  2 integrity   unique ids; every story/style/swatch/master/font/link reference resolves; link files exist at recorded size
  3 geometry    re-derive every frame from the IDML with idml_probe (the parser proven on InDesign's own output) and diff it
                against the Chromium extraction: frames, image placement, text anchor + first baseline       must be < 0.01 pt
                and every later baseline: measured line spacing == IDML leading                              must be < 0.05 pt
  4 text        every story's text == the HTML's rendered text, character for character
  5 wraps       every text frame keeps >= 1 pt of slack before a line could re-wrap (warn under 2 pt)
usage: python3 check.py <job.json> [<package_dir>]     exit 1 if any gate fails"""
import sys, os, json, subprocess, zipfile, collections, urllib.parse
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_job, canvas_offset
from idml_probe import load as probe
from compare_idml import effective_runs

HERE = os.path.dirname(os.path.abspath(__file__))


def integrity(path):
    pkgdir = os.path.dirname(path); z = zipfile.ZipFile(path)
    P = {n: ET.fromstring(z.read(n)) for n in z.namelist() if n.endswith('.xml')}
    errs = []
    if z.infolist()[0].filename != 'mimetype' or z.infolist()[0].compress_type != zipfile.ZIP_STORED: errs.append('mimetype must be the first, stored entry')
    selfs = collections.Counter(e.get('Self') for n, r in P.items() if not n.startswith('META-INF') for e in r.iter() if e.get('Self'))
    dup = [s for s, c in selfs.items() if c > 1]
    if dup: errs.append(f'duplicate Self ids: {dup[:8]}')
    dm = P['designmap.xml']
    refs = [e.get('src') for e in dm if e.get('src')]
    for s in refs:
        if s not in z.namelist(): errs.append(f'designmap src missing: {s}')
    for n in z.namelist():
        if n.startswith(('Spreads/', 'Stories/', 'MasterSpreads/')) and n not in refs: errs.append(f'part not in designmap: {n}')
    stories = {}
    for n, r in P.items():
        st = r.find('Story') if r.find('Story') is not None else r.find('XmlStory')
        if st is not None and (n.startswith('Stories/') or n == 'XML/BackingStory.xml'): stories[st.get('Self')] = n
    if set(dm.get('StoryList').split()) != set(stories): errs.append('StoryList does not match the story files')
    styles, graphic, fonts = P['Resources/Styles.xml'], P['Resources/Graphic.xml'], P['Resources/Fonts.xml']
    PS = {e.get('Self'): e for e in styles.iter('ParagraphStyle')}; CS = {e.get('Self'): e for e in styles.iter('CharacterStyle')}
    OS = {e.get('Self') for e in styles.iter('ObjectStyle')}
    colors = {e.get('Self') for e in graphic.iter('Color')} | {e.get('Self') for e in graphic.iter('Swatch')} | {'Swatch/None'}
    fontset = {(e.get('FontFamily'), e.get('FontStyleName')) for e in fonts.iter('Font')}
    masters = {r.find('MasterSpread').get('Self') for n, r in P.items() if n.startswith('MasterSpreads/')}
    sections = {e.get('Self') for e in dm.iter('Section')}
    layers = {e.get('Self') for e in dm.iter('Layer')}
    pages = {e.get('Self') for n, r in P.items() if n.startswith('Spreads/') for e in r.iter('Page')}
    for e in dm.iter('Section'):
        if e.get('PageStart') not in pages: errs.append('Section PageStart unresolved')
        if int(e.get('Length')) != len(pages): errs.append(f'Section Length {e.get("Length")} != {len(pages)} pages')
    frames = collections.Counter(); missing_links = []; used_fonts = collections.Counter()
    for n, r in P.items():
        for e in r.iter():
            for a in ('FillColor', 'StrokeColor'):
                v = e.get(a)
                if v and v not in colors and v != 'n': errs.append(f'{n}: {e.tag}@{a}={v} unresolved')
            if e.get('AppliedObjectStyle') and e.get('AppliedObjectStyle') not in OS: errs.append(f'{n}: object style {e.get("AppliedObjectStyle")} unresolved')
            if e.get('ItemLayer') and e.get('ItemLayer') not in layers: errs.append(f'{n}: layer unresolved')
            if e.tag == 'TextFrame':
                frames[e.get('ParentStory')] += 1
                if e.get('ParentStory') not in stories: errs.append(f'{n}: frame {e.get("Self")} -> missing story')
            if e.tag == 'Page' and n.startswith('Spreads/'):
                if e.get('AppliedMaster') not in masters: errs.append(f'{n}: page master unresolved')
                if e.get('AppliedAlternateLayout') not in sections: errs.append(f'{n}: alternate layout unresolved')
            if e.tag == 'Link':
                uri = e.get('LinkResourceURI')
                fp = os.path.join(pkgdir, 'Links', urllib.parse.unquote(uri[len('file:Links/'):])) if uri.startswith('file:Links/') else None
                if not fp or not os.path.isfile(fp): missing_links.append(uri)
                elif int(e.get('LinkResourceSize').split('~')[1], 16) != os.path.getsize(fp): errs.append(f'link size mismatch {uri}')
        if n.startswith('Stories/'):
            for ps in r.iter('ParagraphStyleRange'):
                pst = PS.get(ps.get('AppliedParagraphStyle'))
                if pst is None: errs.append(f'{n}: paragraph style {ps.get("AppliedParagraphStyle")} unresolved'); continue
                pfont = pst.find('Properties/AppliedFont').text
                for cr in ps.iter('CharacterStyleRange'):
                    cst = CS.get(cr.get('AppliedCharacterStyle'))
                    if cst is None: errs.append(f'{n}: character style {cr.get("AppliedCharacterStyle")} unresolved'); continue
                    fam = cr.find('Properties/AppliedFont').text if cr.find('Properties/AppliedFont') is not None else pfont
                    sty = cr.get('FontStyle') or cst.get('FontStyle') or pst.get('FontStyle')
                    used_fonts[(fam, sty)] += 1
                    if (fam, sty) not in fontset: errs.append(f'{n}: font {fam} {sty} not in Fonts.xml')
    for s in stories:
        if s != 'ub1' and frames[s] != 1: errs.append(f'story {s} has {frames[s]} frames')
    if missing_links: errs.append(f'{len(missing_links)} link file(s) missing: {missing_links[:4]}')
    return errs, used_fonts


def geometry_and_text(job, doc, idml, X):
    sp, stories = probe(idml)
    worst = collections.defaultdict(float); n = collections.Counter(); notes = []
    if len(sp) != len(doc['pages']): return worst, n, [f'{len(sp)} spreads in IDML vs {len(doc["pages"])} pages in job']
    for s, p in zip(sp, doc['pages']):
        d = X[p['id']]; ox, oy = canvas_offset(doc, p)
        ex_img = [i for i in d['items'] if i['t'] in ('image', 'raster')]
        ex_txt = [i for i in d['items'] if i['t'] == 'text']
        ex_rect = [i for i in d['items'] if i['t'] == 'rect']
        ex_line = [i for i in d['items'] if i['t'] == 'line']
        ex_poly = sum(len(i['paths']) for i in d['items'] if i['t'] == 'vector')
        im = [i for i in s['items'] if 'image' in i]
        tf = [i for i in s['items'] if i['type'] == 'TextFrame']
        rc = [i for i in s['items'] if i['type'] == 'Rectangle' and 'image' not in i]
        gl = [i for i in s['items'] if i['type'] == 'GraphicLine']; pg = [i for i in s['items'] if i['type'] == 'Polygon']
        got, want = (len(im), len(tf), len(rc), len(gl), len(pg)), (len(ex_img), len(ex_txt), len(ex_rect), len(ex_line), ex_poly)
        if got != want: notes.append(f'{p["id"]}: COUNT img/text/rect/line/path IDML {got} vs HTML {want}'); worst['count'] = 1; continue
        for a, e in zip(im, ex_img):
            x0, y0, x1, y1 = a['bbox']
            ef = e['frame'] if e['t'] == 'image' else [e['clipPx']['x'] * .75, e['clipPx']['y'] * .75, e['clipPx']['width'] * .75, e['clipPx']['height'] * .75]
            worst['frame'] = max(worst['frame'], abs(x0 - ox - ef[0]), abs(y0 - oy - ef[1]), abs(x1 - x0 - ef[2]), abs(y1 - y0 - ef[3])); n['frame'] += 1
            if e['t'] == 'image' and e['fit'] != 'fill':
                cs = a['image']['corners']; xs = [c[0] for c in cs]; ys = [c[1] for c in cs]; ep = e['place']
                err = max(abs(min(xs) - ox - ep[0]), abs(min(ys) - oy - ep[1]), abs(max(xs) - min(xs) - ep[2]), abs(max(ys) - min(ys) - ep[3]))
                worst['place'] = max(worst['place'], err); n['place'] += 1
                if err > 0.01: notes.append(f'{p["id"]}: image placement off {err:.4f} pt ({a["image"]["uri"]})')
        for a, e in zip(rc, ex_rect):
            x0, y0, x1, y1 = a['bbox']; b = e['box']
            worst['rect'] = max(worst['rect'], abs(x0 - ox - b[0]), abs(y0 - oy - b[1]), abs(x1 - x0 - b[2]), abs(y1 - y0 - b[3])); n['rect'] += 1
        for a, e in zip(tf, ex_txt):
            txt = ''.join(c.text or '' for c in stories[a['story']].iter('Content'))
            n['text'] += 1
            if txt != e['text'].replace('\n', ' '): notes.append(f'{p["id"]}: TEXT differs {txt[:30]!r} vs {e["text"][:30]!r}'); worst['text'] = 1
            runs = effective_runs(idml, stories[a['story']])
            leads = {r['lead'] for r in runs}
            bases = [l['base'] for l in e['lines'] if l['base'] is not None]
            for b0, b1 in zip(bases, bases[1:]):
                n['leading'] += 1
                err = min(abs((b1 - b0) - L) for L in leads)
                worst['leading'] = max(worst['leading'], err)
                if err > 0.05: notes.append(f'{p["id"]}: line spacing {b1 - b0:.3f} pt vs IDML leading {sorted(leads)} in {e["text"][:30]!r}'); break
            if e['xf']:     # rotated frame: centre, angle and first-baseline offset in the frame's own (unrotated) coordinates
                import math
                M = a['M']; ang = math.degrees(math.atan2(M[1], M[0]))
                err = max(abs(M[4] - ox - e['xf']['cx']), abs(M[5] - oy - e['xf']['cy']),
                          abs(float(a['tfp']['MinimumFirstBaselineOffset']) - (e['base0'] - e['box'][1])))
                worst['rotated'] = max(worst['rotated'], err, 0 if abs((ang - e['xf']['deg'] + 180) % 360 - 180) < 0.01 else 99); n['rotated'] += 1
                continue
            x0, y0, x1, y1 = a['bbox']
            base = y0 + float(a['tfp']['MinimumFirstBaselineOffset']) - oy
            worst['baseline'] = max(worst['baseline'], abs(base - e['base0'])); n['baseline'] += 1
            just = [q.get('Justification') for q in stories[a['story']].iter('ParagraphStyleRange')][0]
            bx, by, bw, bh = e['box']
            if just == 'CenterAlign': err = abs((x0 + x1) / 2 - ox - (bx + bw / 2))
            elif just == 'RightAlign': err = abs(x1 - ox - (bx + bw))
            else: err = abs(x0 - ox - bx)
            worst['text_anchor'] = max(worst['text_anchor'], err); n['text_anchor'] += 1
    return worst, n, notes


def main():
    job = load_job(sys.argv[1])
    pkg = sys.argv[2] if len(sys.argv) > 2 else os.path.join(job['out_dir'], job['name'] + '_InDesign')
    X = {}
    for d in job['documents']:
        for p in d['pages']: X[p['id']] = json.load(open(os.path.join(job['work_dir'], 'extract', p['id'] + '.json')))
    rep = json.load(open(os.path.join(job['work_dir'], 'build_report.json')))
    failed = []
    for d in job['documents']:
        idml = os.path.join(pkg, d['idml'] + '.idml')
        print(f'== {d["idml"]}.idml')
        r = subprocess.run([os.path.join(HERE, 'schema_check.sh'), idml], capture_output=True, text=True)
        bad = [l for l in r.stdout.splitlines() if not l.startswith('ok ')]
        print(f'  1 schema     {"PASS" if r.returncode == 0 else "FAIL"}  ({sum(l.startswith("ok ") for l in r.stdout.splitlines())} parts ok)')
        for l in bad[:12]: print('      ' + l)
        if r.returncode: failed.append('schema')
        errs, used = integrity(idml)
        print(f'  2 integrity  {"PASS" if not errs else "FAIL"}  (fonts used: {", ".join(f"{a} {b}" for a, b in sorted(used))})')
        for e in errs[:12]: print('      ' + e)
        if errs: failed.append('integrity')
        worst, n, notes = geometry_and_text(job, d, idml, X)
        geo_bad = any(worst[k] > 0.01 for k in ('frame', 'place', 'rect', 'baseline', 'text_anchor', 'rotated')) or worst.get('count') or worst['leading'] > 0.05
        print(f'  3 geometry   {"PASS" if not geo_bad else "FAIL"}  worst pt: ' + ', '.join(f'{k} {worst[k]:.4f} (n={n[k]})' for k in ('frame', 'place', 'rect', 'baseline', 'text_anchor', 'rotated', 'leading')))
        print(f'  4 text       {"PASS" if not worst.get("text") else "FAIL"}  ({n["text"]} stories)')
        for x in notes[:12]: print('      ' + x)
        if geo_bad: failed.append('geometry')
        if worst.get('text'): failed.append('text')
        fr = rep['frames'][d['idml']]
        grow = min((x['grow'], x['text']) for x in fr) if fr else (99, '')
        pulls = [(x['pull'], x['text']) for x in fr if x['pull'] is not None]
        pull = min(pulls) if pulls else (99, '')
        tight = min(grow[0], pull[0])
        print(f'  5 wraps      {"PASS" if tight >= 1 else "FAIL"}{" (tight)" if 1 <= tight < 2 else ""}  min slack {grow[0]:.2f} pt to grow ({grow[1][:24]!r}), '
              f'{pull[0]:.2f} pt before a word pulls up ({pull[1][:24]!r})')
        if tight < 1: failed.append('wraps')
    if rep.get('warnings'):
        print('build warnings (review):'); [print('   ', w) for w in rep['warnings']]
    print('RESULT:', 'ALL GATES PASS' if not failed else 'FAILED ' + ', '.join(sorted(set(failed))))
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
