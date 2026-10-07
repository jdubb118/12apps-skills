"""Parse an IDML package into page-space geometry (spread coords -> pages), for verification.
Used two ways: (1) on a designer's InDesign-written IDML vs the PDF exported from it, to prove the coordinate model;
(2) on our generated IDML, to re-derive where every frame/image/text lands and diff it against the HTML source."""
import re, sys, zipfile, math
import xml.etree.ElementTree as ET

def mat(s):
    a = [float(v) for v in s.split()]
    return a

def mul(m, n):
    """compose: apply n first, then m.  points p' = m(n(p))"""
    a, b, c, d, e, f = m; A, B, C, D, E, F = n
    return [a*A + c*B, b*A + d*B, a*C + c*D, b*C + d*D, a*E + c*F + e, b*E + d*F + f]

def ap(m, x, y):
    a, b, c, d, e, f = m
    return (a*x + c*y + e, b*x + d*y + f)

ID = [1, 0, 0, 1, 0, 0]

class Pkg:
    def __init__(self, path):
        self.z = zipfile.ZipFile(path) if path.endswith('.idml') else None
        self.dir = None if self.z else path
    def read(self, name):
        if self.z: return self.z.read(name)
        return open(f'{self.dir}/{name}', 'rb').read()
    def xml(self, name):
        return ET.fromstring(self.read(name))

def paths(el):
    out = []
    for gp in el.iter('GeometryPathType'):
        pts = []
        for pp in gp.iter('PathPointType'):
            pts.append(tuple(tuple(float(v) for v in pp.get(k).split()) for k in ('Anchor', 'LeftDirection', 'RightDirection')))
        out.append((gp.get('PathOpen') == 'true', pts))
    return out

def own_paths(el):
    props = el.find('Properties')
    if props is None: return []
    pg = props.find('PathGeometry')
    return paths(pg) if pg is not None else []

def bbox(pts):
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))

def load(path):
    P = Pkg(path)
    dm = P.xml('designmap.xml')
    spreads = [e.get('src') for e in dm if e.tag.endswith('Spread') and e.tag.startswith('{') and 'MasterSpread' not in e.tag]
    stories = {}
    for e in dm:
        if e.tag.endswith('}Story'):
            st = P.xml(e.get('src')).find('Story')
            stories[st.get('Self')] = st
    out = []
    for si, src in enumerate(spreads):
        sp = P.xml(src).find('Spread')
        pages = []
        for pg in sp.findall('Page'):
            gb = [float(v) for v in pg.get('GeometricBounds').split()]  # top left bottom right
            m = mat(pg.get('ItemTransform'))
            x0, y0 = ap(m, gb[1], gb[0]); x1, y1 = ap(m, gb[3], gb[2])
            pages.append(dict(name=pg.get('Name'), rect=(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)), self=pg.get('Self')))
        items = []
        def walk(el, M, depth=0):
            for ch in el:
                t = ch.tag
                if t not in ('Rectangle', 'TextFrame', 'Polygon', 'GraphicLine', 'Group', 'Oval'):
                    continue
                m = mul(M, mat(ch.get('ItemTransform', '1 0 0 1 0 0')))
                geo = [[(ap(m, *a), ap(m, *l), ap(m, *r)) for a, l, r in pts] for _, pts in own_paths(ch)]
                op = None
                ts = ch.find('TransparencySetting')
                if ts is not None and ts.find('BlendingSetting') is not None:
                    op = float(ts.find('BlendingSetting').get('Opacity', '100'))
                it = dict(type=t, self=ch.get('Self'), geo=geo, M=m, fill=ch.get('FillColor'), stroke=ch.get('StrokeColor'),
                          radius=float(ch.get('TopLeftCornerRadius') or 0) if ch.get('TopLeftCornerOption') == 'RoundedCorner' else 0,
                          sw=ch.get('StrokeWeight'), opacity=op, layer=ch.get('ItemLayer'), depth=depth)
                if geo:
                    it['bbox'] = bbox([a for path in geo for a, _, _ in path])
                img = ch.find('Image')
                if img is not None:
                    mi = mul(m, mat(img.get('ItemTransform')))
                    gbx = img.find('Properties/GraphicBounds')
                    L, T, R, B = (float(gbx.get(k)) for k in ('Left', 'Top', 'Right', 'Bottom'))
                    corners = [ap(mi, L, T), ap(mi, R, T), ap(mi, R, B), ap(mi, L, B)]
                    link = img.find('Link')
                    it['image'] = dict(M=mi, bounds=(L, T, R, B), corners=corners, ppi=img.get('ActualPpi'),
                                       uri=link.get('LinkResourceURI') if link is not None else None)
                if t == 'TextFrame':
                    tfp = ch.find('TextFramePreference')
                    it['story'] = ch.get('ParentStory')
                    it['tfp'] = dict(tfp.attrib) if tfp is not None else {}
                items.append(it)
                if t == 'Group':
                    walk(ch, m, depth + 1)
        walk(sp, ID)
        out.append(dict(src=src, pages=pages, items=items))
    return out, stories

def story_text(st):
    s = []
    for el in st.iter():
        if el.tag == 'Content' and el.text: s.append(el.text)
        elif el.tag == 'Br': s.append('\n')
    return ''.join(s)

if __name__ == '__main__':
    sp, stories = load(sys.argv[1])
    for i, s in enumerate(sp):
        print(i, s['src'], [p['rect'] for p in s['pages']], len(s['items']))
