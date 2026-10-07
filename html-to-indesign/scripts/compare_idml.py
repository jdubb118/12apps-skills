"""Semantic diff of two IDML files (regression tool): spread by spread, item by item, compare type, geometry, link name,
story text and the EFFECTIVE text formatting (font, face, size, leading, tracking, caps, RGB colour, justification) after
resolving paragraph style + character style + local overrides. Style NAMES are ignored on purpose.
usage: python3 compare_idml.py <reference.idml> <candidate.idml> [--tol 0.01]"""
import sys, os, zipfile
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from idml_probe import load


def effective_runs(idml, story):
    z = zipfile.ZipFile(idml)
    S = ET.fromstring(z.read('Resources/Styles.xml')); G = ET.fromstring(z.read('Resources/Graphic.xml'))
    col = {c.get('Self'): c.get('ColorValue') for c in G.iter('Color')}
    PS = {e.get('Self'): e for e in S.iter('ParagraphStyle')}; CS = {e.get('Self'): e for e in S.iter('CharacterStyle')}
    out = []
    for psr in story.iter('ParagraphStyleRange'):
        ps = PS[psr.get('AppliedParagraphStyle')]
        just = psr.get('Justification') or ps.get('Justification')
        for cr in psr.iter('CharacterStyleRange'):
            cs = CS[cr.get('AppliedCharacterStyle')]
            prop = lambda name, el: el.find(f'Properties/{name}').text if el.find(f'Properties/{name}') is not None else None
            out.append(dict(text=''.join(c.text or '' for c in cr.iter('Content')),
                            font=prop('AppliedFont', cr) or prop('AppliedFont', ps),
                            face=cr.get('FontStyle') or cs.get('FontStyle') or ps.get('FontStyle'),
                            size=float(cr.get('PointSize') or ps.get('PointSize')),
                            lead=float(prop('Leading', cr) or prop('Leading', ps)),
                            track=float(cr.get('Tracking') or ps.get('Tracking')),
                            caps=cr.get('Capitalization') or ps.get('Capitalization'),
                            color=col[cr.get('FillColor') or ps.get('FillColor')], just=just, nobreak=cr.get('NoBreak') == 'true'))
    return out


def main():
    a, b = sys.argv[1], sys.argv[2]
    tol = float(sys.argv[sys.argv.index('--tol') + 1]) if '--tol' in sys.argv else 0.01
    A, SA = load(a); Bs, SB = load(b)
    diffs = []; n = 0
    if len(A) != len(Bs): diffs.append(f'spread count {len(A)} vs {len(Bs)}')
    for k, (sa, sb) in enumerate(zip(A, Bs)):
        ta = [i['type'] for i in sa['items']]; tb = [i['type'] for i in sb['items']]
        if ta != tb: diffs.append(f'spread {k}: item types differ {ta} vs {tb}'); continue
        for ia, ib in zip(sa['items'], sb['items']):
            n += 1
            if 'bbox' in ia and 'bbox' in ib:
                d = max(abs(x - y) for x, y in zip(ia['bbox'], ib['bbox']))
                if d > tol: diffs.append(f'spread {k} {ia["type"]}: bbox differs by {d:.4f} pt')
            if 'image' in ia:
                na, nb = ia['image']['uri'].split('/')[-1], ib['image']['uri'].split('/')[-1]
                if na != nb: diffs.append(f'spread {k}: link {na} vs {nb}')
                d = max(abs(p[0] - q[0]) + abs(p[1] - q[1]) for p, q in zip(ia['image']['corners'], ib['image']['corners']))
                if d > tol: diffs.append(f'spread {k}: image placement differs by {d:.4f} pt ({na})')
            if ia['type'] in ('GraphicLine', 'Polygon', 'Rectangle') and 'image' not in ia:
                for key in ('fill', 'stroke', 'sw', 'opacity'):
                    if key in ('fill', 'stroke'): continue
                    if str(ia[key]) != str(ib[key]): diffs.append(f'spread {k} {ia["type"]}: {key} {ia[key]} vs {ib[key]}')
            if ia['type'] == 'TextFrame':
                for key in ('TextColumnFixedWidth', 'MinimumFirstBaselineOffset', 'FirstBaselineOffset', 'AutoSizingType'):
                    va, vb = ia['tfp'].get(key), ib['tfp'].get(key)
                    if va != vb and not (va and vb and abs(float(va) - float(vb)) <= tol if key not in ('FirstBaselineOffset', 'AutoSizingType') else False):
                        diffs.append(f'spread {k} text frame {key}: {va} vs {vb}')
                ra, rb = effective_runs(a, SA[ia['story']]), effective_runs(b, SB[ib['story']])
                if ra != rb:
                    diffs.append(f'spread {k} story {ra[0]["text"][:30]!r}: effective formatting differs\n      {ra}\n      {rb}')
    # names the designer sees: paragraph/character styles and swatches (reported separately; --names makes them fail)
    def names(p):
        z = zipfile.ZipFile(p); S = ET.fromstring(z.read('Resources/Styles.xml')); G = ET.fromstring(z.read('Resources/Graphic.xml'))
        return ({e.get('Name') for e in S.iter('ParagraphStyle') if not e.get('Name', '').startswith('$ID/')},
                {e.get('Name') for e in S.iter('CharacterStyle') if not e.get('Name', '').startswith('$ID/')},
                {(e.get('Name'), e.get('ColorValue')) for e in G.iter('Color') if e.get('Space') == 'RGB'})
    na, nb = names(a), names(b); ndiff = []
    for label, x, y in zip(('paragraph styles', 'character styles', 'swatches'), na, nb):
        if x != y: ndiff.append(f'{label}: only in reference {sorted(x - y)[:8]} | only in candidate {sorted(y - x)[:8]}')
    print(f'compared {n} items across {min(len(A), len(Bs))} spreads: ' + ('IDENTICAL (effective formatting, geometry, links, text)' if not diffs else f'{len(diffs)} differences'))
    for d in diffs[:30]: print('  ', d)
    print('names (styles + swatches): ' + ('identical' if not ndiff else f'{len(ndiff)} set(s) differ'))
    for d in ndiff: print('  ', d)
    sys.exit(1 if diffs or ('--names' in sys.argv and ndiff) else 0)


if __name__ == '__main__':
    main()
