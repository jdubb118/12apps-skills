"""Shared job loading + page geometry for the indesign-package skill.

Coordinates: everything the extractor measures is in CANVAS points (CSS px x 0.75) from the top-left of the page's
root element, which must include the bleed. InDesign page items live in SPREAD coordinates:
  facing documents      spine at x = 0; left page x in [-W, 0], right page x in [0, W]; pages vertically centred (y in [-H/2, H/2])
  non-facing documents  the page is centred on the spread origin: x in [-W/2, W/2], y in [-H/2, H/2]
(both proven against InDesign-written IDML; see references/PROOF.md). spread_xy = canvas_xy + (ox, oy)."""
import json, os

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(SKILL, 'template')
SCHEMAS = os.path.join(SKILL, 'schemas')


def _box(v, what, keys=('top', 'bottom', 'inside', 'outside')):
    """One number, or {top, bottom, inside, outside}; 'left'/'right' are accepted as inside/outside (non-facing pages).
    Unknown keys are an ERROR: a silently-zero bleed shifts every page item and still passes the geometry gate."""
    if isinstance(v, (int, float)):
        return {k: float(v) for k in keys}
    alias = {'left': 'inside', 'right': 'outside'}
    out = {}
    for k, x in v.items():
        kk = alias.get(k, k)
        if kk not in keys: raise SystemExit(f'{what}: unknown key {k!r} (use top/bottom/inside/outside, or left/right)')
        if kk in out: raise SystemExit(f'{what}: {k!r} given twice (left = inside, right = outside)')
        out[kk] = float(x)
    missing = [k for k in keys if k not in out]
    if missing: raise SystemExit(f'{what}: missing {missing} (give all four, or one number)')
    return out


def norm_hex(h):
    h = h.strip().lower().lstrip('#')
    if len(h) == 3: h = ''.join(c * 2 for c in h)
    if len(h) != 6 or any(c not in '0123456789abcdef' for c in h): raise SystemExit(f'colour key {h!r} is not #rgb or #rrggbb')
    return h


def load_job(path):
    job = json.load(open(path))
    base = os.path.dirname(os.path.abspath(path))
    rel = lambda p: p if (p is None or os.path.isabs(p)) else os.path.normpath(os.path.join(base, p))
    job['_path'] = os.path.abspath(path)
    job['html_root'] = rel(job['html_root'])
    job['work_dir'] = rel(job['work_dir'])
    job['out_dir'] = rel(job['out_dir'])
    job.setdefault('root_selector', 'body > *')
    job.setdefault('flatten', {})
    job.setdefault('styles', {})
    job['colors'] = {norm_hex(k): v for k, v in job.get('colors', {}).items()}
    job.setdefault('char_styles', {})
    job.setdefault('min_ppi', 250)
    job.setdefault('copy_system_fonts', False)
    job.setdefault('overlay_prefix', 'overlay')
    job.setdefault('reference_pdfs', [])
    job.setdefault('readme', {})
    for f in job['fonts']:
        f['file'] = rel(f['file'])
        f.setdefault('style', 'normal')
    job['reference_pdfs'] = [rel(p) for p in job['reference_pdfs']]
    assert job['documents'], 'job needs at least one document'
    for d in job['documents']:
        d['trim'] = [float(d['trim'][0]), float(d['trim'][1])]
        d['bleed'] = _box(d.get('bleed', 0), f"{d['idml']}.bleed")
        d['margins'] = _box(d.get('margins', 36), f"{d['idml']}.margins")
        d.setdefault('facing', True)
        for p in d['pages']:
            p.setdefault('kind', 'spread' if d['facing'] else 'single')
            p['id'] = os.path.splitext(os.path.basename(p['html']))[0]
            assert p['kind'] in (('spread', 'right', 'left') if d['facing'] else ('single',)), \
                f"{p['html']}: kind {p['kind']!r} not valid for a {'facing' if d['facing'] else 'non-facing'} document"
    return job


def page_sides(doc, page):
    """InDesign pages carried by this canvas, in spread order: list of 'left' | 'right' | 'single'."""
    return {'spread': ['left', 'right'], 'right': ['right'], 'left': ['left'], 'single': ['single']}[page['kind']]


def binding_location(page):
    return {'spread': 1, 'right': 0, 'left': 1, 'single': 0}[page['kind']]


def page_transform(doc, side):
    W, H = doc['trim']
    return {'left': (-W, -H / 2), 'right': (0.0, -H / 2), 'single': (-W / 2, -H / 2)}[side]


def canvas_offset(doc, page):
    """(ox, oy) with spread = canvas + offset."""
    W, H = doc['trim']; b = doc['bleed']
    oy = -(b['top'] + H / 2)
    if 'spine_x' in page:
        return -float(page['spine_x']), oy
    k = page['kind']
    if k == 'spread': ox = -(b['outside'] + W)
    elif k == 'right': ox = -b['inside']
    elif k == 'left': ox = -(b['outside'] + W)
    else: ox = -(b['inside'] + W / 2)          # non-facing: inside = left bleed
    return ox, oy


def expected_canvas(doc, page):
    W, H = doc['trim']; b = doc['bleed']
    h = H + b['top'] + b['bottom']
    k = page['kind']
    if k == 'spread': w = 2 * W + 2 * b['outside']
    elif k in ('right', 'left'): w = W + b['inside'] + b['outside']
    else: w = W + b['inside'] + b['outside']
    return w, h


def page_labels(doc):
    """page id -> human label ('p. 1', 'pp. 2-3'), numbering pages in document order."""
    n = 0; out = {}
    for p in doc['pages']:
        k = len(page_sides(doc, p))
        out[p['id']] = f'p. {n + 1}' if k == 1 else f'pp. {n + 1}-{n + k}'
        n += k
    return out


if __name__ == '__main__':
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == 'resolve':
        job = load_job(sys.argv[2])
        os.makedirs(job['work_dir'], exist_ok=True)
        out = os.path.join(job['work_dir'], 'job.resolved.json')
        json.dump(job, open(out, 'w'), indent=1)
        print(out)
    else:
        raise SystemExit('usage: common.py resolve <job.json>')
