"""indesign-package / build: turn the extraction (work_dir/extract/*.json) into IDML document(s) + a designer package.

Every XML block is InDesign's own vocabulary: boilerplate copied verbatim from an InDesign 21 IDML (template/), element
and attribute sets mirrored from InDesign-written files and validated against Adobe's RNC schema (schemas/).
usage: python3 build.py <job.json> [--force]"""
import json, os, re, sys, shutil, struct, uuid, zipfile, datetime, math, urllib.parse
from collections import Counter, defaultdict
from xml.sax.saxutils import escape
from PIL import Image, ImageCms
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_job, TEMPLATE, page_sides, binding_location, page_transform, canvas_offset, expected_canvas, page_labels

B = json.load(open(os.path.join(TEMPLATE, 'boilerplate.json')))
OBJ_EXPORT, FLATTENER, TW_GRAPHIC, CLIPPING, IMAGEIO, TW_IMAGE, TW_TEXT, PAGE_GRID = (B[k] for k in
    ('OBJ_EXPORT', 'FLATTENER', 'TW_GRAPHIC', 'CLIPPING', 'IMAGEIO', 'TW_IMAGE', 'TW_TEXT', 'PAGE_GRID'))
INCOPY = '<InCopyExportOption IncludeGraphicProxies="true" IncludeAllResources="false" />'
COMMON = ('OverriddenPageItemProps="" FlexItemWidthMode="FlexFixed" FlexItemHeightMode="FlexFixed" Visible="true" Name="{name}" '
          'HorizontalLayoutConstraints="FlexibleDimension FixedDimension FlexibleDimension" VerticalLayoutConstraints="FlexibleDimension FixedDimension FlexibleDimension"')
GRAD = 'GradientFillStart="0 0" GradientFillLength="0" GradientFillAngle="0" GradientStrokeStart="0 0" GradientStrokeLength="0" GradientStrokeAngle="0"'
GRAD2 = 'LocalDisplaySetting="Default" GradientFillHiliteLength="0" GradientFillHiliteAngle="0" GradientStrokeHiliteLength="0" GradientStrokeHiliteAngle="0"'
CHANGE = 'ParentInterfaceChangeCount="" TargetInterfaceChangeCount="" LastUpdatedInterfaceChangeCount=""'
LAYER = 'ucc'
WARN = []


def rd(p): return open(os.path.join(TEMPLATE, p), encoding='utf-8').read()
def q(s): return escape(str(s), {'"': '&quot;'})


class Ids:
    def __init__(self, start=0x10000): self.n = start
    def __call__(self): self.n += 1; return 'u%x' % self.n


def f(v):  # 6 dp keeps scale factors on large images well under 0.01 pt
    v = round(float(v), 6)
    return ('%d' % v) if v == int(v) else ('%.6f' % v).rstrip('0').rstrip('.')


def path_rect(x0, y0, x1, y1):
    pts = [(x0, y0), (x0, y1), (x1, y1), (x1, y0)]
    s = ''.join(f'<PathPointType Anchor="{f(x)} {f(y)}" LeftDirection="{f(x)} {f(y)}" RightDirection="{f(x)} {f(y)}" />' for x, y in pts)
    return f'<Properties><PathGeometry><GeometryPathType PathOpen="false"><PathPointArray>{s}</PathPointArray></GeometryPathType></PathGeometry></Properties>'


def corners(r):
    if not r or r <= 0: return ''
    return ' '.join(f'{c}CornerOption="RoundedCorner" {c}CornerRadius="{f(r)}"' for c in ('TopLeft', 'TopRight', 'BottomLeft', 'BottomRight')) + ' '


def transp(op=None, fill=None, stroke=None):
    out = ''
    if op is not None and op < 0.999: out += f'<TransparencySetting><BlendingSetting Opacity="{f(op * 100)}" /></TransparencySetting>'
    if fill is not None and fill < 0.999: out += f'<FillTransparencySetting><BlendingSetting Opacity="{f(fill * 100)}" /></FillTransparencySetting>'
    if stroke is not None and stroke < 0.999: out += f'<StrokeTransparencySetting><BlendingSetting Opacity="{f(stroke * 100)}" /></StrokeTransparencySetting>'
    return out


# ---------------- fonts ----------------
def font_info(path):
    """What InDesign will call this font (Fonts.xml Font attributes), read from the file's name table."""
    from fontTools.ttLib import TTFont
    ft = TTFont(path, lazy=True)
    n = ft['name']
    g = lambda i: (n.getDebugName(i) or '').strip() or None
    fam, sty = g(16) or g(1), g(17) or g(2)
    cff = 'CFF ' in ft or 'CFF2' in ft
    ftype = 'OpenTypeCFF' if cff else ('OpenTypeTT' if path.lower().endswith('.otf') else 'TrueType')
    full = g(4) or f'{fam} {sty}'
    if sty == 'Regular' and full == f'{fam} Regular': full = fam      # InDesign's convention (Minion Pro, Myriad Pro, Geist Mono entries)
    return dict(family=fam, style=sty, ps=g(6), full=full, version=g(5) or '', type=ftype)


def css_weight_pick(cands, want):
    ws = sorted({c['weight'] for c in cands})
    if want in ws: w = want
    elif 400 <= want <= 500:
        up = [x for x in ws if want < x <= 500]; dn = [x for x in ws if x < want]; hi = [x for x in ws if x > 500]
        w = up[0] if up else (dn[-1] if dn else hi[0])
    elif want < 400:
        dn = [x for x in ws if x < want]; w = dn[-1] if dn else [x for x in ws if x > want][0]
    else:
        up = [x for x in ws if x > want]; w = up[0] if up else [x for x in ws if x < want][-1]
    return [c for c in cands if c['weight'] == w][0]


class Fonts:
    def __init__(self, job):
        self.entries = []
        for e in job['fonts']:
            info = font_info(e['file'])
            e = dict(e); e['weight'] = int(e.get('weight', 400))
            e['id_family'] = e.get('family') or info['family']; e['id_style'] = e.get('face') or info['style']; e['info'] = info
            self.entries.append(e)

    def resolve(self, st):
        fam = st['family'].split(',')[0].strip().strip('"\'')
        cands = [e for e in self.entries if e['css'].lower() == fam.lower()]   # CSS family names are case-insensitive
        if not cands:
            raise SystemExit(f'FONT NOT IN JOB: css family {fam!r} (add it to job.fonts with its OTF/TTF file)')
        it = st['style'] != 'normal'
        same = [e for e in cands if (e['style'] != 'normal') == it]
        if not same:
            WARN.append(f'{fam} {st["style"]} has no matching face; Chrome synthesised it, InDesign gets the upright face')
            same = cands
        e = css_weight_pick(same, int(st['weight']))
        return e['id_family'], e['id_style']

    def fonts_xml(self):
        fo = rd('Resources/Fonts.xml')
        fams = defaultdict(list)
        for e in self.entries:
            fams[e['id_family']].append(e)
        add = ''
        for i, (fam, es) in enumerate(fams.items()):
            fid = f'di{0x5000 + i:x}'
            add += f'\n\t<FontFamily Self="{fid}" Name="{q(fam)}">'
            for e in es:
                inf, sty = e['info'], e['id_style']
                nm = f'{fam} {sty}'
                add += (f'\n\t\t<Font Self="{fid}Fontn{q(nm)}" FontFamily="{q(fam)}" Name="{q(nm)}" PostScriptName="{q(inf["ps"])}" Status="Installed" '
                        f'FontStyleName="{q(sty)}" FontType="{inf["type"]}" WritingScript="0" FullName="{q(inf["full"])}" FullNameNative="{q(inf["full"])}" '
                        f'FontStyleNameNative="{q(sty)}" PlatformName="$ID/" Version="{q(inf["version"])}" TypekitID="$ID/" />')
            add += '\n\t</FontFamily>'
        i = fo.rfind('</FontFamily>') + len('</FontFamily>')
        return fo[:i] + add + fo[i:]


# ---------------- swatches ----------------
class Swatches:
    def __init__(self, names):
        self.names = {k.lower().lstrip('#'): v for k, v in names.items()}
        self.sw = {}; self.order = []

    def __call__(self, rgb, name=None):
        h = '%02x%02x%02x' % tuple(int(round(c)) for c in rgb[:3])
        if h not in self.sw:
            self.sw[h] = name or self.names.get(h) or f'R={int(h[0:2], 16)} G={int(h[2:4], 16)} B={int(h[4:6], 16)}'
            self.order.append(h)
        return 'Color/' + self.sw[h]


def blend(rgba, opacity, under):
    a = (rgba[3] if len(rgba) > 3 else 1) * opacity
    return [rgba[i] * a + under[i] * (1 - a) for i in range(3)]


# ---------------- links ----------------
class Links:
    def __init__(self, folder):
        self.folder = folder; self.by_src = {}; self.names = set()
        os.makedirs(folder, exist_ok=True)

    def _name(self, want):
        base, ext = os.path.splitext(want); n = want; k = 2
        while n.lower() in self.names: n = f'{base}_{k}{ext}'; k += 1
        self.names.add(n.lower()); return n

    def jpeg_rewrite(self, src, dst, ppi=300):
        """Lossless: keep scan data, ICC and Adobe APP14; JFIF at `ppi`; drop EXIF/XMP/Photoshop blocks (conflicting resolutions)."""
        b = open(src, 'rb').read(); assert b[:2] == b'\xff\xd8', src
        out = [b'\xff\xd8', b'\xff\xe0' + struct.pack('>H', 16) + b'JFIF\x00\x01\x02\x01' + struct.pack('>HH', ppi, ppi) + b'\x00\x00']
        i = 2; icc = False
        while i < len(b):
            assert b[i] == 0xFF, (src, i); m = b[i + 1]
            if m == 0xFF: i += 1; continue
            if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7: i += 2; continue
            L = struct.unpack('>H', b[i + 2:i + 4])[0]; seg = b[i:i + 2 + L]
            if m == 0xDA: out.append(b[i:]); break
            if m == 0xE2 and seg[4:15] == b'ICC_PROFILE': icc = True; out.append(seg)
            elif m == 0xEE: out.append(seg)
            elif 0xE0 <= m <= 0xEF or m == 0xFE: pass
            else: out.append(seg)
            i += 2 + L
        open(dst, 'wb').write(b''.join(out)); return icc

    def add(self, src, name=None, ppi=None):
        if src in self.by_src: return self.by_src[src]
        im = Image.open(src); w, h = im.size
        ext = os.path.splitext(src)[1].lower()
        orient = im.getexif().get(274) if hasattr(im, 'getexif') else None
        if ext in ('.jpg', '.jpeg') and im.mode == 'RGB' and orient in (None, 1):
            name = self._name(name or os.path.basename(src)); dst = os.path.join(self.folder, name)
            icc = self.jpeg_rewrite(src, dst, 300); ppi = 300; typ = '$ID/JPEG'
        elif ext in ('.jpg', '.jpeg'):
            # grey/CMYK-with-wrong-profile/EXIF-rotated JPEGs: normalise to plain sRGB so InDesign shows what Chrome showed
            from PIL import ImageOps
            im = ImageOps.exif_transpose(im).convert('RGB'); w, h = im.size
            name = self._name(name or os.path.basename(src)); dst = os.path.join(self.folder, name)
            im.save(dst, quality=95, subsampling=0, dpi=(300, 300), icc_profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes())
            icc = True; ppi = 300; typ = '$ID/JPEG'
            WARN.append(f're-encoded {os.path.basename(src)} as sRGB JPEG (was {Image.open(src).mode}, orientation {orient})')
        else:
            name = self._name(os.path.splitext(name or os.path.basename(src))[0] + '.png'); dst = os.path.join(self.folder, name)
            ppi = ppi or (im.info.get('dpi') or (72, 72))[0] or 72
            icc_b = im.info.get('icc_profile')
            if im.mode in ('LA', 'P', 'L', 'I;16', 'CMYK'): im = im.convert('RGBA')
            kw = dict(dpi=(ppi, ppi)); kw.update(icc_profile=icc_b) if icc_b else None
            im.save(dst, **kw); icc = bool(icc_b); typ = '$ID/Portable Network Graphics (PNG)'
        chk = Image.open(dst); assert chk.size == (w, h), (dst, chk.size, (w, h))
        st = os.stat(dst)
        L = dict(name=name, ppi=float(chk.info.get('dpi', (72, 72))[0]), w=w, h=h, type=typ,
                 profile='$ID/Embedded' if icc else '$ID/Use Document Default', size=st.st_size, mtime=st.st_mtime)
        self.by_src[src] = L
        return L


def filetime(ts): return int((ts + 11644473600) * 10_000_000)
def iso(ts): return datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%dT%H:%M:%S')


# ---------------- page items ----------------
def image_xml(ids, L, frame, place, name, radius=0, opacity=1):
    rid, iid, lid = ids(), ids(), ids()
    gw, gh = L['w'] * 72 / L['ppi'], L['h'] * 72 / L['ppi']
    sx, sy = place[2] / gw, place[3] / gh
    eff = round(L['ppi'] / max(sx, sy))
    uri = 'file:Links/' + q(urllib.parse.quote(L['name']))
    return (f'<Rectangle Self="{rid}" ContentType="GraphicType" StoryTitle="$ID/" {COMMON.format(name=q(name))} StrokeWeight="0" {corners(radius)}'
            f'{GRAD} ItemLayer="{LAYER}" Locked="false" {GRAD2} AppliedObjectStyle="ObjectStyle/$ID/[None]" ItemTransform="1 0 0 1 0 0" {CHANGE}>'
            f'{path_rect(*frame)}<FrameFittingOption FittingOnEmptyFrame="Proportionally" />{OBJ_EXPORT}{TW_GRAPHIC}{INCOPY}{transp(opacity)}'
            f'<Image Self="{iid}" Space="$ID/#Links_RGB" ActualPpi="{f(L["ppi"])} {f(L["ppi"])}" EffectivePpi="{eff} {eff}" ImageRenderingIntent="UseColorSettings" '
            f'OverriddenPageItemProps="" LocalDisplaySetting="Default" ImageTypeName="{L["type"]}" AppliedObjectStyle="ObjectStyle/$ID/[None]" '
            f'ItemTransform="{f(sx)} 0 0 {f(sy)} {f(place[0])} {f(place[1])}" FlexItemWidthMode="FlexFixed" FlexItemHeightMode="FlexFixed" Visible="true" Name="$ID/" '
            f'HorizontalLayoutConstraints="FlexibleDimension FixedDimension FlexibleDimension" VerticalLayoutConstraints="FlexibleDimension FixedDimension FlexibleDimension" '
            f'GradientFillStart="0 0" GradientFillLength="0" GradientFillAngle="0" GradientFillHiliteLength="0" GradientFillHiliteAngle="0" {CHANGE}>'
            f'<Properties><Profile type="string">{L["profile"]}</Profile><GraphicBounds Left="0" Top="0" Right="{f(gw)}" Bottom="{f(gh)}" /></Properties>'
            f'{CLIPPING}{IMAGEIO}{TW_IMAGE}'
            f'<Link Self="{lid}" AssetURL="$ID/" AssetID="$ID/" LinkResourceURI="{uri}" LinkResourceFormat="{L["type"]}" StoredState="Normal" LinkClassID="35906" LinkClientID="257" '
            f'LinkResourceModified="false" LinkObjectModified="false" ShowInUI="true" CanEmbed="true" CanUnembed="true" CanPackage="true" ImportPolicy="NoAutoImport" ExportPolicy="NoAutoExport" '
            f'LinkImportStamp="file {filetime(L["mtime"])} {L["size"]}" LinkImportModificationTime="{iso(L["mtime"])}" LinkImportTime="{iso(L["mtime"])}" LinkResourceSize="0~{L["size"]:x}" />'
            f'</Image></Rectangle>'), eff


def rect_xml(ids, frame, fill, name, radius=0, opacity=1):
    return (f'<Rectangle Self="{ids()}" ContentType="Unassigned" StoryTitle="$ID/" {COMMON.format(name=q(name))} FillColor="{q(fill)}" StrokeWeight="0" {corners(radius)}'
            f'{GRAD} ItemLayer="{LAYER}" Locked="false" {GRAD2} AppliedObjectStyle="ObjectStyle/$ID/[None]" ItemTransform="1 0 0 1 0 0" {CHANGE}>'
            f'{path_rect(*frame)}{OBJ_EXPORT}{TW_TEXT}{INCOPY}{transp(opacity)}</Rectangle>')


def line_xml(ids, p1, p2, weight, stroke, name, opacity=1):
    pts = ''.join(f'<PathPointType Anchor="{f(x)} {f(y)}" LeftDirection="{f(x)} {f(y)}" RightDirection="{f(x)} {f(y)}" />' for x, y in (p1, p2))
    return (f'<GraphicLine Self="{ids()}" ContentType="Unassigned" LockState="None" {COMMON.format(name=q(name))} StrokeWeight="{f(weight)}" StrokeColor="{q(stroke)}" '
            f'{GRAD} ItemLayer="{LAYER}" Locked="false" {GRAD2} AppliedObjectStyle="ObjectStyle/$ID/[None]" ItemTransform="1 0 0 1 0 0" {CHANGE}>'
            f'<Properties><PathGeometry><GeometryPathType PathOpen="true"><PathPointArray>{pts}</PathPointArray></GeometryPathType></PathGeometry></Properties>'
            f'{OBJ_EXPORT}{TW_TEXT}{transp(opacity)}</GraphicLine>')


def polygon_xml(ids, subs, ox, oy, fill, stroke, weight, name, op=1, fop=1, sop=1):
    geo = ''
    for s in subs:
        pts = ''.join(f'<PathPointType Anchor="{f(a[0] + ox)} {f(a[1] + oy)}" LeftDirection="{f(l[0] + ox)} {f(l[1] + oy)}" RightDirection="{f(r[0] + ox)} {f(r[1] + oy)}" />'
                      for a, l, r in s['pts'])
        geo += f'<GeometryPathType PathOpen="{"false" if s["closed"] else "true"}"><PathPointArray>{pts}</PathPointArray></GeometryPathType>'
    return (f'<Polygon Self="{ids()}" ContentType="Unassigned" StoryTitle="$ID/" {COMMON.format(name=q(name))} FillColor="{q(fill)}" StrokeWeight="{f(weight)}" '
            f'StrokeColor="{q(stroke)}" MiterLimit="10" {GRAD} ItemLayer="{LAYER}" Locked="false" {GRAD2} AppliedObjectStyle="ObjectStyle/$ID/[None]" '
            f'ItemTransform="1 0 0 1 0 0" {CHANGE}><Properties><PathGeometry>{geo}</PathGeometry></Properties>{OBJ_EXPORT}{TW_TEXT}{INCOPY}'
            f'{transp(op, fop, sop)}</Polygon>')


def group_xml(ids, inner, opacity, name):
    return (f'<Group Self="{ids()}" {COMMON.format(name=q(name))} {GRAD} ItemLayer="{LAYER}" Locked="false" {GRAD2} AppliedObjectStyle="ObjectStyle/$ID/[None]" '
            f'ItemTransform="1 0 0 1 0 0" {CHANGE}>{OBJ_EXPORT}{TW_TEXT}{transp(opacity)}{inner}</Group>')


# ---------------- text ----------------
def base_style(it):
    st = it['styles'][it['runs'][0]['st']]
    for r in it['runs']:
        s2 = it['styles'][r['st']]
        if s2['style'] == 'normal' and int(s2['weight']) <= 500: return s2
    return st


def char_attrs(it, st, fonts, sw):
    fam, sty = fonts.resolve(st)
    lead = it['lh'] if it['lh'] else _measured_lead(it)
    return dict(font=fam, style=sty, size=round(st['size'], 3), lead=round(lead, 3), track=round(st['ls'] / st['size'] * 1000, 1) if st['size'] else 0,
                caps=st['tt'] == 'uppercase', color=sw(st['color']))


def _measured_lead(it):
    bs = [l['base'] for l in it['lines'] if l['base'] is not None]
    if len(bs) > 1: return (bs[-1] - bs[0]) / (len(bs) - 1)
    return 1.2 * it['size']


def role_of(it, job, fonts):
    for tok in it['cls'].split():
        if tok in job['styles']: return job['styles'][tok]
    st = base_style(it); fam, sty = fonts.resolve(st)
    return f'{fam} {sty} {f(round(st["size"], 2))}pt'


def build_styles(items, job, fonts, sw):
    by = defaultdict(list)
    for it in items: by[role_of(it, job, fonts)].append(it)
    PS = {}
    for role, its in by.items():
        c = Counter(tuple(sorted(char_attrs(it, base_style(it), fonts, sw).items())) for it in its)
        PS[role] = dict(c.most_common(1)[0][0])
    return PS


def story_xml(sid, it, role, PS, CS, align, fonts, sw, job):
    P = PS[role]
    just = {'left': None, 'center': 'CenterAlign', 'right': 'RightAlign', 'justify': 'LeftJustified'}[align]
    out = [f'<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/{q(role)}"' + (f' Justification="{just}"' if just else '') + '>']
    for r in it['runs']:
        st = it['styles'][r['st']]
        a = char_attrs(it, st, fonts, sw)
        cs = None
        if a['style'] != P['style'] and a['font'] == P['font']:
            cs = job['char_styles'].get(f"{a['font']} {a['style']}") or f"{a['font']} {a['style']}"
            CS[cs] = dict(font=a['font'], style=a['style'])
        attrs = [f'AppliedCharacterStyle="CharacterStyle/{q(cs)}"' if cs else 'AppliedCharacterStyle="CharacterStyle/$ID/[No character style]"']
        props = []
        if a['color'] != P['color']: attrs.append(f'FillColor="{q(a["color"])}"')
        if abs(a['size'] - P['size']) > 0.001: attrs.append(f'PointSize="{f(a["size"])}"')
        if abs(a['track'] - P['track']) > 0.05: attrs.append(f'Tracking="{f(a["track"])}"')
        if a['caps'] != P['caps']: attrs.append('Capitalization="' + ('AllCaps' if a['caps'] else 'Normal') + '"')
        if st['ws'] == 'nowrap' and it['styles'][0]['ws'] != 'nowrap': attrs.append('NoBreak="true"')
        if a['font'] != P['font']: props.append(f'<AppliedFont type="string">{q(a["font"])}</AppliedFont>')
        if a['font'] != P['font'] and not cs: attrs.append(f'FontStyle="{q(a["style"])}"')
        if abs(a['lead'] - P['lead']) > 0.001: props.append(f'<Leading type="unit">{f(a["lead"])}</Leading>')
        text = r['text'].replace('\n', ' ')
        body = (f'<Properties>{"".join(props)}</Properties>' if props else '') + f'<Content>{escape(text)}</Content>'
        out.append(f'<CharacterStyleRange {" ".join(attrs)}>{body}</CharacterStyleRange>')
    out.append('</ParagraphStyleRange>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<idPkg:Story xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="21.0">\n'
            f'\t<Story Self="{sid}" UserText="true" IsEndnoteStory="false" AppliedTOCStyle="n" TrackChanges="false" StoryTitle="$ID/" AppliedNamedGrid="n">\n'
            '\t\t<StoryPreference OpticalMarginAlignment="false" OpticalMarginSize="12" FrameType="TextFrameType" StoryOrientation="Horizontal" StoryDirection="LeftToRightDirection" />\n'
            '\t\t<InCopyExportOption IncludeGraphicProxies="true" IncludeAllResources="false" />\n\t\t' + ''.join(out) + '\n\t</Story>\n</idPkg:Story>\n')


def text_frame(ids, it, role, PS, CS, ox, oy, report, fonts, sw, job):
    """Frame width sits inside the window [natural, next-word-fits) measured in Chrome, so InDesign's greedy single-line
    composer reproduces the same breaks; first baseline pinned with FixedHeight; height auto-sizes."""
    bx, by, bw, bh = it['box']
    lo, hi = it['lo'], it['hi']
    align = {'start': 'left', 'left': 'left', '-webkit-left': 'left', 'center': 'center', '-webkit-center': 'center', 'right': 'right',
             'end': 'right', '-webkit-right': 'right', 'justify': 'justify'}.get(it['align'], 'left')
    shrink = (bw - it['natural']) < 1.0
    if it['soft'] == 0 and hi is None and align == 'left' and it['anchor'] in ('right', 'center') and shrink:
        align = it['anchor']
    s = max(2.0, 0.015 * it['natural'])
    if hi is None: W = max(bw, lo + 2 * s)
    elif bw - lo >= s and hi - bw >= s: W = bw
    else: W = (lo + hi) / 2
    x = bx if align in ('left', 'justify') else (bx + bw / 2 - W / 2 if align == 'center' else bx + bw - W)
    n = len(it['lines'])
    d = it['base0'] - by
    lead = it['lh'] or _measured_lead(it)
    H = max(bh, d + (n - 1) * lead + 0.45 * it['size'])
    sid, fid = ids(), ids()
    if it['xf']:
        cx, cy = it['xf']['cx'] + ox, it['xf']['cy'] + oy
        th = math.radians(it['xf']['deg'])
        c, sn = round(math.cos(th), 12), round(math.sin(th), 12)
        geo = path_rect(-W / 2, -bh / 2, W / 2, -bh / 2 + H)
        tr = f'{f(c)} {f(sn)} {f(-sn)} {f(c)} {f(cx)} {f(cy)}'
        if align == 'left': align = 'center'
    else:
        geo = path_rect(x + ox, by + oy, x + W + ox, by + H + oy); tr = '1 0 0 1 0 0'
    xml = (f'<TextFrame Self="{fid}" ParentStory="{sid}" PreviousTextFrame="n" NextTextFrame="n" ContentType="TextType" {COMMON.format(name="$ID/")} '
           f'{GRAD} ItemLayer="{LAYER}" Locked="false" {GRAD2} AppliedObjectStyle="ObjectStyle/$ID/[Normal Text Frame]" ItemTransform="{tr}" {CHANGE}>'
           f'{geo}{OBJ_EXPORT}'
           f'<TextFramePreference TextColumnCount="1" TextColumnFixedWidth="{f(W)}" TextColumnMaxWidth="0" FirstBaselineOffset="FixedHeight" '
           f'MinimumFirstBaselineOffset="{f(d)}" VerticalJustification="TopAlign" AutoSizingType="HeightOnly" AutoSizingReferencePoint="TopCenterPoint" '
           f'UseMinimumHeightForAutoSizing="false" MinimumHeightForAutoSizing="0" UseMinimumWidthForAutoSizing="false" MinimumWidthForAutoSizing="0" UseNoLineBreaksForAutoSizing="false">'
           '<Properties><InsetSpacing type="list"><ListItem type="unit">0</ListItem><ListItem type="unit">0</ListItem><ListItem type="unit">0</ListItem><ListItem type="unit">0</ListItem></InsetSpacing></Properties>'
           f'</TextFramePreference>{TW_TEXT}</TextFrame>')
    report.append(dict(id=it['id'], text=it['text'][:40], W=W, bw=bw, lo=lo, hi=hi, grow=W - lo, pull=(hi - W) if hi else None, align=align))
    return xml, sid, story_xml(sid, it, role, PS, CS, align, fonts, sw, job)


# ---------------- document assembly ----------------
def page_xml(pid, name, num, master, side, doc, sect):
    W, H = doc['trim']; tx, ty = page_transform(doc, side); m = doc['margins']
    ml, mr = m['inside'], m['outside']      # IDML Left/Right = inside/outside on facing pages, left/right otherwise
    return (f'<Page Self="{pid}" TabOrder="" AppliedMaster="{master}" OverrideList="" MasterPageTransform="1 0 0 1 0 0" Name="{name}" '
            f'AppliedTrapPreset="TrapPreset/$ID/kDefaultTrapStyleName" GeometricBounds="0 0 {f(H)} {f(W)}" ItemTransform="1 0 0 1 {f(tx)} {f(ty)}" '
            f'AppliedAlternateLayout="{sect}" LayoutRule="Off" SnapshotBlendingMode="IgnoreLayoutSnapshots" OptionalPage="false" GridStartingPoint="TopOutside" UseMasterGrid="true">'
            '<Properties><PageColor type="enumeration">UseMasterColor</PageColor>'
            + ('' if num is None else '<Descriptor type="list"><ListItem type="string"></ListItem><ListItem type="enumeration">Arabic</ListItem><ListItem type="boolean">true</ListItem>'
               f'<ListItem type="boolean">false</ListItem><ListItem type="long">{num}</ListItem><ListItem type="long">{num}</ListItem><ListItem type="string"></ListItem></Descriptor>')
            + '</Properties>'
            f'<MarginPreference ColumnCount="1" ColumnGutter="12" Top="{f(m["top"])}" Bottom="{f(m["bottom"])}" Left="{f(ml)}" Right="{f(mr)}" ColumnDirection="Horizontal" ColumnsPositions="0 {f(W - ml - mr)}" />'
            f'{PAGE_GRID}</Page>')


def spread_xml(sid, idx, pages_xml, items_xml, count, binding, H):
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<idPkg:Spread xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="21.0">\n'
            f'\t<Spread Self="{sid}" PageTransitionType="None" PageTransitionDirection="NotApplicable" PageTransitionDuration="Medium" ShowMasterItems="true" '
            f'PageCount="{count}" BindingLocation="{binding}" SpreadHidden="false" AllowPageShuffle="true" ItemTransform="1 0 0 1 0 {f(idx * (H + 198))}" FlattenerOverride="Default">\n'
            f'\t\t{FLATTENER}\n\t\t' + '\n\t\t'.join(pages_xml + items_xml) + '\n\t</Spread>\n</idPkg:Spread>\n')


def file_of(url):
    if url.startswith('file://'): return urllib.parse.unquote(urllib.parse.urlparse(url).path)
    return url


def build_doc(job, doc, X, links, fonts, out_idml, facts):
    sw = Swatches(job['colors']); ids = Ids()
    labels = page_labels(doc)
    texts = [it for p in doc['pages'] for it in X[p['id']]['items'] if it['t'] == 'text']
    PS = build_styles(texts, job, fonts, sw); CS = {}
    sect, master = ids(), ids()
    spreads, stories, report = [], [], []
    num = 0; first_page = None
    for k, p in enumerate(doc['pages']):
        d = X[p['id']]; ox, oy = canvas_offset(doc, p)
        ew, eh = expected_canvas(doc, p)
        if abs(d['W'] - ew) > 0.6 or abs(d['H'] - eh) > 0.6:
            raise SystemExit(f"{p['id']}: canvas is {d['W']:.1f}x{d['H']:.1f}pt but a '{p['kind']}' page with trim {doc['trim']} + bleed {doc['bleed']} "
                             f"must be {ew:.1f}x{eh:.1f}pt. Wrong page kind or bleed: every item would land shifted, and gate 3 cannot see it.")
        pages = []
        for side in page_sides(doc, p):
            num += 1; pid = ids(); first_page = first_page or pid
            pages.append(page_xml(pid, str(num), num, master, side, doc, sect))
        label = labels[p['id']]
        tag = p.get('tag') or re.sub(r'\d+', lambda m: '%02d' % int(m.group()), label.replace('pp. ', 'p').replace('p. ', 'p'))
        root_rgb = None; painted = []; xs = []; k_ovl = Counter()
        def under_is_flat(bb):
            for kind, b2, col in painted:
                if b2[0] < bb[2] and bb[0] < b2[2] and b2[1] < bb[3] and bb[1] < b2[3]:
                    if kind != 'rect' or not (b2[0] <= bb[0] and b2[1] <= bb[1] and b2[2] >= bb[2] and b2[3] >= bb[3]): return None
                    return col
            return root_rgb or [255, 255, 255]
        for it in d['items']:
            t = it['t']
            if t == 'rect':
                x, y, w, h = it['box']; bb = (x, y, x + w, y + h)
                a = it['color'][3] * it['opacity']
                if it.get('root'):
                    root_rgb = it['color'][:3]
                    if a < 0.999: WARN.append(f"{p['id']}: page background is transparent-ish ({a:.2f}); drawn opaque");
                    xs.append(rect_xml(ids, (x + ox, y + oy, x + w + ox, y + h + oy), sw(it['color']), 'Page colour'))
                    continue
                flat = under_is_flat(bb) if a < 0.999 else None
                if a < 0.999 and flat is not None:
                    xs.append(rect_xml(ids, (x + ox, y + oy, x + w + ox, y + h + oy), sw(blend(it['color'], it['opacity'], flat)), 'Panel', max(it['radius'], 0)))
                    painted.append(('rect', bb, blend(it['color'], it['opacity'], flat)))
                else:
                    xs.append(rect_xml(ids, (x + ox, y + oy, x + w + ox, y + h + oy), sw(it['color']), 'Panel', max(it['radius'], 0), a))
                    painted.append(('rect' if a >= 0.999 else 'mix', bb, it['color'][:3]))
                if it['radius'] == -1: WARN.append(f"{p['id']}: non-uniform border-radius drawn square on {it['id']}")
            elif t == 'image':
                src = file_of(it['src'])
                L = links.add(src)
                fx, fy, fw, fh = it['frame']; px, py, pw, ph = it['place']
                if it['fit'] == 'fill':
                    ar = (it['nat'][0] / it['nat'][1]) / (pw / ph)
                    if abs(ar - 1) < 0.01:
                        s_ = max(pw / it['nat'][0], ph / it['nat'][1]); nw, nh = it['nat'][0] * s_, it['nat'][1] * s_
                        px, py, pw, ph = px + (pw - nw) / 2, py + (ph - nh) / 2, nw, nh
                    else:
                        WARN.append(f"{p['id']}: {os.path.basename(src)} is stretched {ar:.3f}:1 by object-fit:fill; kept stretched (non-uniform scale)")
                xml, eff = image_xml(ids, L, (fx + ox, fy + oy, fx + fw + ox, fy + fh + oy), (px + ox, py + oy, pw, ph), L['name'], max(it['radius'], 0), it['opacity'])
                xs.append(xml); painted.append(('image', (fx, fy, fx + fw, fy + fh), None))
                facts['images'].append(dict(doc=doc['idml'], page=label, name=L['name'], eff=eff))
                if eff < job['min_ppi']: WARN.append(f"LOW RES {L['name']} on {label}: {eff} ppi as placed (print wants >= {job['min_ppi']}); flag it before it goes to print")
            elif t == 'raster':
                cp = it['clipPx']; dsf = it['dsf']
                x0, y0, w0, h0 = cp['x'] * .75, cp['y'] * .75, cp['width'] * .75, cp['height'] * .75
                k_ovl[it['kind']] += 1
                if it['kind'] == 'mockup':
                    base = job['flatten'].get(it['sel']) or 'mockup'
                    nm = f'{base}.png'
                else:
                    pre = job['overlay_prefix'] if it['kind'] == 'gradient' else it['kind']
                    nm = f"{pre}_{tag}_{k_ovl[it['kind']]}.png"
                L = links.add(it['png'], name=nm, ppi=round(96 * dsf))
                im = Image.open(it['png']); assert im.size == (cp['width'] * dsf, cp['height'] * dsf), (it['png'], im.size, cp)
                xml, _ = image_xml(ids, L, (x0 + ox, y0 + oy, x0 + w0 + ox, y0 + h0 + oy), (x0 + ox, y0 + oy, L['w'] * 72 / L['ppi'], L['h'] * 72 / L['ppi']), L['name'])
                xs.append(xml); painted.append(('image', (x0, y0, x0 + w0, y0 + h0), None))
                facts['rasters'].append(dict(doc=doc['idml'], page=label, name=L['name'], kind=it['kind'], what=it.get('desc', '')))
            elif t == 'line':
                bb = (min(it['p1'][0], it['p2'][0]) - it['weight'], min(it['p1'][1], it['p2'][1]) - it['weight'],
                      max(it['p1'][0], it['p2'][0]) + it['weight'], max(it['p1'][1], it['p2'][1]) + it['weight'])
                a = it['color'][3] * it['opacity']; flat = under_is_flat(bb) if a < 0.999 else None
                if a < 0.999 and flat is not None: col_, op_ = sw(blend(it['color'], it['opacity'], flat)), 1
                else: col_, op_ = sw(it['color']), a
                xs.append(line_xml(ids, (it['p1'][0] + ox, it['p1'][1] + oy), (it['p2'][0] + ox, it['p2'][1] + oy), it['weight'], col_, 'Rule', op_))
                facts['natives'].append(dict(doc=doc['idml'], page=label, kind='rule'))
            elif t == 'vector':
                x, y, w, h = it['box']; bb = (x, y, x + w, y + h)
                flat = under_is_flat(bb)
                for pth in it['paths']:
                    op, fo, so = pth['opacity'], pth['fo'], pth['so']
                    fill = pth['fill']; stroke = pth['stroke']
                    fa = (fill[3] * fo) if fill else 1; sa = (stroke[3] * so) if stroke else 1
                    if flat is not None and (op * fa < 0.999 or op * sa < 0.999):     # flat ground: bake opacity into solid colours
                        fill_c = sw(blend(fill, op * fo, flat)) if fill else 'Swatch/None'
                        str_c = sw(blend(stroke, op * so, flat)) if stroke else 'Swatch/None'
                        xs.append(polygon_xml(ids, pth['subs'], ox, oy, fill_c, str_c, pth['sw'] if stroke else 0, 'Vector'))
                    else:
                        xs.append(polygon_xml(ids, pth['subs'], ox, oy, sw(fill) if fill else 'Swatch/None', sw(stroke) if stroke else 'Swatch/None',
                                              pth['sw'] if stroke else 0, 'Vector', op, fa, sa))
                painted.append(('image', bb, None))
                facts['natives'].append(dict(doc=doc['idml'], page=label, kind='vector'))
            elif t == 'text':
                role = role_of(it, job, fonts)
                xml, sid, sx = text_frame(ids, it, role, PS, CS, ox, oy, report, fonts, sw, job)
                alphas = {round(it['styles'][r['st']]['color'][3], 3) for r in it['runs']}
                op = it['opacity'] * (alphas.pop() if len(alphas) == 1 else 1)
                if op < 0.999:
                    xml = group_xml(ids, xml, op, f'Text {round(op * 100)}%')
                    facts['groups'].append(dict(doc=doc['idml'], page=label, text=it['text'], op=round(op * 100)))
                xs.append(xml); stories.append((sid, sx))
            else:
                raise ValueError(t)
        spreads.append((ids(), pages, xs, len(page_sides(doc, p)), binding_location(p)))
    W, H = doc['trim']; b = doc['bleed']; m = doc['margins']
    parts = {'mimetype': 'application/vnd.adobe.indesign-idml-package', 'META-INF/container.xml': rd('META-INF/container.xml')}
    now = datetime.datetime.now().astimezone().isoformat(timespec='seconds'); did = str(uuid.uuid4())
    parts['META-INF/metadata.xml'] = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description rdf:about="" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmlns:xmpMM="http://ns.adobe.com/xap/1.0/mm/">'
        f'<dc:format>application/x-indesign</dc:format><xmp:CreateDate>{now}</xmp:CreateDate><xmp:ModifyDate>{now}</xmp:ModifyDate><xmp:MetadataDate>{now}</xmp:MetadataDate>'
        f'<xmp:CreatorTool>indesign-package skill (IDML 21.0)</xmp:CreatorTool><xmpMM:DocumentID>xmp.did:{did}</xmpMM:DocumentID><xmpMM:InstanceID>xmp.iid:{did}</xmpMM:InstanceID>'
        f'<xmpMM:OriginalDocumentID>xmp.did:{did}</xmpMM:OriginalDocumentID></rdf:Description></rdf:RDF></x:xmpmeta>\n<?xpacket end="r"?>')
    g = rd('Resources/Graphic.xml'); last = [mm.end() for mm in re.finditer(r'<Color [^>]*/>', g)][-1]
    grp_base = 0x20
    g = g[:last] + ''.join(
        f'\n\t<Color Self="Color/{q(sw.sw[h])}" Model="Process" Space="RGB" ColorValue="{int(h[0:2], 16)} {int(h[2:4], 16)} {int(h[4:6], 16)}" ColorOverride="Normal" '
        f'ConvertToHsb="false" AlternateSpace="NoAlternateColor" AlternateColorValue="" Name="{q(sw.sw[h])}" ColorEditable="true" ColorRemovable="true" Visible="true" '
        f'SwatchCreatorID="7937" SwatchColorGroupReference="u18ColorGroupSwatch{grp_base + i:x}" />' for i, h in enumerate(sw.order)) + g[last:]
    parts['Resources/Graphic.xml'] = g
    parts['Resources/Fonts.xml'] = fonts.fonts_xml()
    st = rd('Resources/Styles.xml')
    cs_xml = ''.join(f'\n\t\t<CharacterStyle Self="CharacterStyle/{q(n)}" Imported="false" SplitDocument="false" EmitCss="true" StyleUniqueId="{uuid.uuid4()}" IncludeClass="true" '
                     f'ExtendedKeyboardShortcut="0 0 0" EpubAriaRole="" Name="{q(n)}" FontStyle="{q(v["style"])}" KeyboardShortcut="0 0">'
                     '<Properties><BasedOn type="string">$ID/[No character style]</BasedOn><PreviewColor type="enumeration">Nothing</PreviewColor></Properties></CharacterStyle>'
                     for n, v in sorted(CS.items()))
    st = st.replace('</RootCharacterStyleGroup>', cs_xml + '\n\t</RootCharacterStyleGroup>', 1)
    ps_xml = ''
    for role, P in sorted(PS.items()):
        ps_xml += (f'\n\t\t<ParagraphStyle Self="ParagraphStyle/{q(role)}" Name="{q(role)}" Imported="false" NextStyle="ParagraphStyle/{q(role)}" SplitDocument="false" '
                   f'EmitCss="true" StyleUniqueId="{uuid.uuid4()}" IncludeClass="true" ExtendedKeyboardShortcut="0 0 0" EpubAriaRole="" EmptyNestedStyles="true" '
                   f'EmptyLineStyles="true" EmptyGrepStyles="true" KeyboardShortcut="0 0" FillColor="{q(P["color"])}" FontStyle="{q(P["style"])}" PointSize="{f(P["size"])}" '
                   f'Tracking="{f(P["track"])}" Capitalization="{"AllCaps" if P["caps"] else "Normal"}" Composer="HL Single" Hyphenation="false" Justification="LeftAlign">'
                   f'<Properties><BasedOn type="string">$ID/[No paragraph style]</BasedOn><PreviewColor type="enumeration">Nothing</PreviewColor>'
                   f'<Leading type="unit">{f(P["lead"])}</Leading><AppliedFont type="string">{q(P["font"])}</AppliedFont></Properties></ParagraphStyle>')
    parts['Resources/Styles.xml'] = st.replace('</RootParagraphStyleGroup>', ps_xml + '\n\t</RootParagraphStyleGroup>', 1)
    pr = rd('Resources/Preferences.xml')
    def setattr_(s, tag, **kv):
        mm = re.search(rf'<{tag} [^>]*>', s); el = mm.group(0)
        for k_, v in kv.items():
            el, nsub = re.subn(rf' {k_}="[^"]*"', f' {k_}="{v}"', el); assert nsub == 1, (tag, k_)
        return s[:mm.start()] + el + s[mm.end():]
    pr = setattr_(pr, 'DocumentPreference', PageHeight=f(H), PageWidth=f(W), PagesPerDocument=str(num), FacingPages='true' if doc['facing'] else 'false',
                  DocumentBleedTopOffset=f(b['top']), DocumentBleedBottomOffset=f(b['bottom']), DocumentBleedInsideOrLeftOffset=f(b['inside']),
                  DocumentBleedOutsideOrRightOffset=f(b['outside']), DocumentBleedUniformSize='true' if len(set(b.values())) == 1 else 'false')
    pr = setattr_(pr, 'MarginPreference', Top=f(m['top']), Bottom=f(m['bottom']), Left=f(m['inside']), Right=f(m['outside']))
    parts['Resources/Preferences.xml'] = pr
    ms = rd('MasterSpreads/MasterSpread_ud6.xml')
    sides = ['left', 'right'] if doc['facing'] else ['single']
    mp = [page_xml(ids(), 'A', None, 'n', sd, doc, 'n') for sd in sides]
    mhead = re.search(r'<MasterSpread [^>]*>', ms).group(0).replace('Self="ud6"', f'Self="{master}"').replace('PageCount="2"', f'PageCount="{len(sides)}"')
    parts[f'MasterSpreads/MasterSpread_{master}.xml'] = (ms[:ms.find('<MasterSpread ')] + mhead +
        '\n\t\t<Properties>\n\t\t\t<PageColor type="enumeration">UseMasterColor</PageColor>\n\t\t</Properties>\n\t\t' + '\n\t\t'.join(mp) + '\n\t</MasterSpread>\n</idPkg:MasterSpread>\n')
    for i, (sid, pages, xs, count, binding) in enumerate(spreads):
        parts[f'Spreads/Spread_{sid}.xml'] = spread_xml(sid, i, pages, xs, count, binding, H)
    for sid, sx in stories: parts[f'Stories/Story_{sid}.xml'] = sx
    parts['XML/BackingStory.xml'] = rd('XML/BackingStory.xml'); parts['XML/Tags.xml'] = rd('XML/Tags.xml')
    dm = rd('designmap.xml')
    dm = re.sub(r'StoryList="[^"]*"', f'StoryList="{" ".join([s for s, _ in stories] + ["ub1"])}"', dm, count=1)
    dm = re.sub(r' Name="[^"]*\.indd"', f' Name="{q(doc["idml"])}.indd"', dm, count=1)
    dm = re.sub(r'\t<idPkg:MasterSpread src="[^"]*" />\n', f'\t<idPkg:MasterSpread src="MasterSpreads/MasterSpread_{master}.xml" />\n', dm)
    dm = re.sub(r'(\t<idPkg:Spread src="[^"]*" />\n)+', ''.join(f'\t<idPkg:Spread src="Spreads/Spread_{s[0]}.xml" />\n' for s in spreads), dm)
    sec = (f'\t<Section Self="{sect}" Length="{num}" Name="" ContinueNumbering="true" IncludeSectionPrefix="false" Marker="" PageStart="{first_page}" '
           f'SectionPrefix="" AlternateLayoutLength="{num}" AlternateLayout="Print">\n\t\t<Properties>\n\t\t\t<PageNumberStyle type="enumeration">Arabic</PageNumberStyle>\n\t\t</Properties>\n\t</Section>\n')
    dm, n_ = re.subn(r'\t<Section .*?</Section>\n', sec, dm, flags=re.S); assert n_ == 1
    dm, n_ = re.subn(r'(\t<idPkg:Story src="[^"]*" />\n)+', ''.join(f'\t<idPkg:Story src="Stories/Story_{s}.xml" />\n' for s, _ in stories), dm); assert n_ == 1
    dm = dm.replace('\t</ColorGroup>', ''.join(f'\t\t<ColorGroupSwatch Self="u18ColorGroupSwatch{grp_base + i:x}" SwatchItemRef="Color/{q(sw.sw[h])}" />\n'
                                               for i, h in enumerate(sw.order)) + '\t</ColorGroup>', 1)
    parts['designmap.xml'] = dm
    import xml.etree.ElementTree as ET
    for k_, v in parts.items():
        if k_.endswith('.xml'): ET.fromstring(v.encode('utf-8'))
    tmp = out_idml + '.tmp'
    with zipfile.ZipFile(tmp, 'w') as z:
        z.writestr(zipfile.ZipInfo('mimetype'), parts['mimetype'], compress_type=zipfile.ZIP_STORED)
        for k_, v in parts.items():
            if k_ != 'mimetype': z.writestr(k_, v.encode('utf-8'), compress_type=zipfile.ZIP_DEFLATED)
    os.replace(tmp, out_idml)
    unnamed = ['#' + h for h in sw.order if h not in sw.names]
    if unnamed: WARN.append(f"{doc['idml']}: {len(unnamed)} colour(s) have no swatch name in job.colors: {', '.join(unnamed)}")
    facts['docs'].append(dict(idml=doc['idml'], pages=num, spreads=len(spreads), stories=len(stories), styles=sorted(PS), char_styles=sorted(CS),
                              swatches=[sw.sw[h] for h in sw.order], trim=doc['trim'], bleed=b, margins=m, facing=doc['facing']))
    return report


def merge_reference(job, X):
    """Merge reference_pdf.mjs pages into <doc>_approved-layout.pdf, one per document, page boxes set to the exact canvas."""
    src = os.path.join(job['work_dir'], 'reference', 'pages')
    if job['reference_pdfs'] or not os.path.isdir(src): return []
    import fitz
    out = []
    for d in job['documents']:
        files = sorted(f for f in os.listdir(src) if f.startswith(d['idml'] + '__') and f.endswith('.pdf'))
        if len(files) != len(d['pages']): WARN.append(f"reference PDF for {d['idml']}: {len(files)} rendered pages for {len(d['pages'])} HTML pages; skipped"); continue
        doc = fitz.open()
        for f_, p in zip(files, d['pages']):
            one = fitz.open(os.path.join(src, f_)); pg = one[0]
            r = fitz.Rect(0, 0, X[p['id']]['W'], X[p['id']]['H'])
            pg.set_mediabox(r); pg.set_cropbox(r)
            doc.insert_pdf(one)
        name = f"{d['idml']}_approved-layout.pdf"
        doc.save(os.path.join(job['work_dir'], 'reference', name)); out.append(name)
    return out


def readme(job, facts, pkg):
    inch = lambda v: f'{v / 72:.4g}'
    R = job['readme']; L = []
    L.append(R.get('title', job['name']) + '  ·  InDesign package')
    if R.get('subtitle'): L.append(R['subtitle'])
    L.append(f'Built {datetime.date.today().isoformat()}.\n\n')
    L.append('WHAT\'S IN THIS FOLDER')
    for d in facts['docs']:
        L.append(f'  {d["idml"]}.idml'.ljust(44) + f'{d["pages"]} page{"s" if d["pages"] != 1 else ""}' + ('' if d['facing'] else ' (single pages)'))
    nphot = len({i['name'] for i in facts['images']}); ngen = len({r['name'] for r in facts['rasters']})
    L.append('  Links/'.ljust(44) + f'{nphot} image(s) at full resolution' + (f' + {ngen} generated overlay(s), listed below' if ngen else ''))
    shipped = sorted({e['id_family'] for e in facts['fonts'] if not e.get('system')}); sysf = sorted({e['id_family'] for e in facts['fonts'] if e.get('system')})
    if shipped: L.append('  Document fonts/'.ljust(44) + ', '.join(shipped))
    if sysf: L.append('  (not included)'.ljust(44) + ', '.join(sysf) + ': macOS system fonts, already on every Mac')
    if os.path.isdir(os.path.join(pkg, 'Reference PDFs')): L.append('  Reference PDFs/'.ljust(44) + 'The approved layout, for comparison')
    L.append('\nIDML is InDesign\'s interchange format. InDesign opens it like a normal document; you then save it as .indd.')
    L.append('These files were generated from the final print files and pass Adobe\'s InDesign 2026 IDML schema.\n\n')
    L.append('HOW TO OPEN')
    L.append('  1. Unzip and keep the folder together. The .idml files look for their images in the Links folder beside them.')
    L.append('  2. Fonts: if they aren\'t active on your machine, install the files in "Document fonts". They are included so the')
    L.append('     files open as designed; commercial typefaces still need your own licence.')
    L.append('  3. File > Open > the .idml. It opens as "Untitled". Save As .indd in this folder.')
    L.append('  4. Links panel: if any link shows a red "?", select all links, choose "Relink to Folder…" and pick the Links folder.')
    L.append('  5. When you\'re done: File > Package as usual.\n\n')
    for d in facts['docs']:
        W, H = d['trim']; b = d['bleed']; m = d['margins']
        L.append(f'DOCUMENT SETUP ({d["idml"]})')
        L.append(f'  Trim {inch(W)} x {inch(H)} in ({W:g} x {H:g} pt), {"facing pages" if d["facing"] else "single pages"}.')
        if len(set(b.values())) == 1: L.append(f'  Bleed {inch(b["top"])} in all round.')
        else: L.append(f'  Bleed {inch(b["top"])} in top, {inch(b["bottom"])} in bottom, {inch(b["inside"])} in {"inside" if d["facing"] else "left"}, {inch(b["outside"])} in {"outside" if d["facing"] else "right"}.')
        L.append(f'  Margins {inch(m["top"])} / {inch(m["bottom"])} / {inch(m["inside"])} / {inch(m["outside"])} in (top / bottom / {"inside / outside" if d["facing"] else "left / right"}).')
        L.append('  One parent page, empty. One layer, stacked in the same order as the approved layout.')
        L.append(f'  Paragraph styles: {" · ".join(d["styles"])}')
        if d['char_styles']: L.append(f'  Character styles: {" · ".join(d["char_styles"])}')
        L.append(f'  Swatches (RGB, the colours of the approved files): {", ".join(d["swatches"])}\n')
    L.append('\nTEXT')
    L.append('  All text is live type. Colour, alignment and a few sizes are local overrides on top of the styles.')
    L.append('  Frames use the Adobe Single-line Composer with hyphenation off and a fixed first baseline: that reproduces the')
    L.append('  approved line breaks exactly. Frames grow in height automatically. If you switch to the Paragraph Composer, check the rag.\n')
    if facts['images']:
        lo = min(i['eff'] for i in facts['images'])
        low = sorted({(i['eff'], i['name'], i['page']) for i in facts['images'] if i['eff'] < job['min_ppi']})
        L.append(f'IMAGES\n  Linked at full resolution. Lowest effective resolution as placed: {lo} ppi.')
        for e_, n_, p_ in low: L.append(f'  BELOW PRINT QUALITY ({job["min_ppi"]} ppi): {n_} on {p_} is {e_} ppi as placed. Replace or shrink before print.')
        L.append('')
    if facts['rasters']:
        L.append('WHAT CAME OVER AS IMAGES (and how to change them)')
        for r in facts['rasters']:
            what = {'gradient': 'gradient shade (transparent PNG)', 'mockup': 'flattened mock-up', 'svg': 'artwork too complex for native paths',
                    'bgimage': 'CSS background image', 'xform': 'rotated/scaled element'}.get(r['kind'], r['kind'])
            L.append(f'  {r["page"]:10} {r["name"]:44} {what}')
        L.append('  Delete, move or replace them like any image.\n')
    nat = Counter((n['page'], n['kind']) for n in facts['natives'])
    if nat:
        what = {'rule': 'rule', 'vector': 'vector artwork (editable paths)'}
        L.append('NATIVE VECTOR ITEMS (real InDesign paths and lines)\n  ' + '; '.join(f'{c} {what.get(k, k)}{"s" if c > 1 and k == "rule" else ""} on {p}' for (p, k), c in sorted(nat.items())) + '\n')
    if facts['groups']:
        short = lambda t: t if len(t) <= 48 else t[:48].rsplit(' ', 1)[0] + '…'
        L.append('TRANSPARENT TEXT\n  ' + '; '.join(f'"{short(g["text"])}" ({g["page"]}, {g["op"]}%)' for g in facts['groups']) +
                 '\n  Each sits in a group that carries the opacity.\n')
    for sec in R.get('sections', []):
        L.append(sec['heading'].upper()); L += ['  ' + x for x in sec['lines']]; L.append('')
    return '\n'.join(L).replace('\n\n\n\n', '\n\n\n') + '\n'


def main():
    job = load_job(sys.argv[1]); force = '--force' in sys.argv
    X = {}
    for d in job['documents']:
        for p in d['pages']:
            fp = os.path.join(job['work_dir'], 'extract', p['id'] + '.json')
            if not os.path.exists(fp): raise SystemExit(f'missing extraction {fp}: run extract.mjs first')
            X[p['id']] = json.load(open(fp))
    pkg = os.path.join(job['out_dir'], job['name'] + '_InDesign')
    if os.path.exists(pkg):
        if not force: raise SystemExit(f'{pkg} exists (use --force to rebuild)')
        shutil.rmtree(pkg)
    os.makedirs(pkg)
    links = Links(os.path.join(pkg, 'Links')); fonts = Fonts(job)
    facts = dict(docs=[], images=[], rasters=[], natives=[], groups=[], fonts=fonts.entries)
    reports = {}
    for d in job['documents']:
        reports[d['idml']] = build_doc(job, d, X, links, fonts, os.path.join(pkg, d['idml'] + '.idml'), facts)
    fd = os.path.join(pkg, 'Document fonts'); os.makedirs(fd)
    for e in fonts.entries:
        e['system'] = e['file'].startswith(('/System/Library/', '/Library/Fonts/')) and not job['copy_system_fonts']
        if e['system']: continue                    # macOS system fonts: already on every Mac, and their licence doesn't cover redistribution
        shutil.copyfile(e['file'], os.path.join(fd, os.path.basename(e['file'])))   # content only: font files can carry protected flags
    if not os.listdir(fd): os.rmdir(fd)
    auto = merge_reference(job, X)
    if not job['reference_pdfs'] and auto:
        rp = os.path.join(pkg, 'Reference PDFs'); os.makedirs(rp)
        for f_ in auto: shutil.copyfile(os.path.join(job['work_dir'], 'reference', f_), os.path.join(rp, f_))
    if job['reference_pdfs']:
        rp = os.path.join(pkg, 'Reference PDFs'); os.makedirs(rp)
        for p in job['reference_pdfs']: shutil.copyfile(p, os.path.join(rp, os.path.basename(p)))
    open(os.path.join(pkg, 'READ ME FIRST.txt'), 'w').write(readme(job, facts, pkg))
    out = dict(package=pkg, docs=facts['docs'], images=facts['images'], rasters=facts['rasters'], groups=facts['groups'],
               frames=reports, warnings=WARN, links=len(links.by_src),
               fonts=[dict(css=e['css'], weight=e['weight'], style=e['style'], indesign_family=e['id_family'], indesign_style=e['id_style'], file=e['file']) for e in fonts.entries])
    json.dump(out, open(os.path.join(job['work_dir'], 'build_report.json'), 'w'), indent=1, default=str)
    for d in facts['docs']: print(f"{d['idml']}.idml: {d['pages']} pages, {d['spreads']} spreads, {d['stories']} text stories, {len(d['styles'])} paragraph styles, {len(d['swatches'])} swatches")
    print(f'Links: {len(links.by_src)} files · Document fonts: {len(fonts.entries)} · package: {pkg}')
    for w in WARN: print('WARN', w)


if __name__ == '__main__':
    main()
