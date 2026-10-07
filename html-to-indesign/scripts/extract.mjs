// html-to-indesign / extract: render every print page of a job in Chromium and dump what InDesign needs, in paint order.
//   solid rects (+ radius, alpha), borders (lines), <img> placements (object-fit/position + ancestor clips),
//   SVG as true vector paths (via getScreenCTM) or rasterised when unsupported, gradients / background images /
//   flattened UI mock-ups as hi-dpi transparent PNGs (whole-px clips), and text blocks with runs, first baseline,
//   line starts and the WIDTH WINDOW [natural, next-word-fits) that reproduces Chrome's line breaks.
// usage: node extract.mjs <work_dir>/job.resolved.json [pageId,pageId...]
import { createRequire } from 'module';
import fs from 'fs';
import path from 'path';
const PW = process.env.PLAYWRIGHT_REQUIRE || new URL('./package.json', import.meta.url).pathname;   // npm install in scripts/
const { chromium } = createRequire(PW)('playwright');

const job = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const only = process.argv[3] ? new Set(process.argv[3].split(',')) : null;
const O = path.join(job.work_dir, 'extract'), OV = path.join(job.work_dir, 'overlays');
fs.mkdirSync(O, { recursive: true }); fs.mkdirSync(OV, { recursive: true });
const pages = [];
for (const d of job.documents) for (const p of d.pages) if (!pages.find(q => q.id === p.id) && (!only || only.has(p.id))) pages.push(p);
const FLAT = Object.keys(job.flatten || {});

const browser = await chromium.launch();
const ctxs = { 1: await browser.newContext({ deviceScaleFactor: 1 }), 2: await browser.newContext({ deviceScaleFactor: 2 }), 4: await browser.newContext({ deviceScaleFactor: 4 }) };
const tabs = { 1: await ctxs[1].newPage(), 2: await ctxs[2].newPage(), 4: await ctxs[4].newPage() };

async function load(tab, p) {
  const url = 'file://' + path.join(job.html_root, p.html);
  await tab.setViewportSize({ width: 4000, height: 3000 });
  await tab.goto(url);
  const size = await tab.evaluate(sel => { const r = document.querySelector(sel).getBoundingClientRect(); return [Math.ceil(r.right), Math.ceil(r.bottom)]; }, job.root_selector);
  await tab.setViewportSize({ width: size[0], height: size[1] });
  await tab.goto(url);
  const bad = await tab.evaluate(async () => {
    await Promise.all([...document.fonts].map(f => f.load().catch(() => null)));
    await document.fonts.ready;
    await Promise.all([...document.images].map(i => i.complete ? 0 : new Promise(r => { i.onload = i.onerror = r; })));
    return { fonts: [...document.fonts].filter(f => f.status === 'error').map(f => `${f.family} ${f.weight} ${f.style}`),
             images: [...document.images].filter(i => !(i.complete && i.naturalWidth)).map(i => i.getAttribute('src')) };
  });
  return bad;
}

function extractInPage(args) {
  const { rootSel, flat } = args;
  const PT = 0.75;
  const root = document.querySelector(rootSel);
  const R0 = root.getBoundingClientRect();
  const X = v => (v - R0.left) * PT, Y = v => (v - R0.top) * PT;
  const box = r => [X(r.left), Y(r.top), r.width * PT, r.height * PT];
  const items = [], warns = [];
  let uid = 0;
  const mark = el => { if (!el.dataset.idml) el.dataset.idml = 'e' + (uid++); return el.dataset.idml; };
  const FLAT = new Map(); flat.forEach(sel => document.querySelectorAll(sel).forEach(e => FLAT.has(e) || FLAT.set(e, sel)));
  const col = c => { const m = c && c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[,\s/]+/).filter(Boolean).map(parseFloat); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const effOp = el => { let o = 1; for (let e = el; e && e.nodeType === 1; e = e.parentElement) o *= parseFloat(getComputedStyle(e).opacity); return o; };
  const desc = el => el.tagName.toLowerCase() + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).join('.') : '') + (el.id ? '#' + el.id : '');
  const radius = cs => { const r = ['borderTopLeftRadius', 'borderTopRightRadius', 'borderBottomRightRadius', 'borderBottomLeftRadius'].map(k => cs[k]);
    if (r.every(v => v === '0px')) return 0; if (r.some(v => v !== r[0] || /%| /.test(v))) return -1; return parseFloat(r[0]) * PT; };
  function clipOf(el) {
    let l = -1e9, t = -1e9, r = 1e9, b = 1e9;
    for (let e = el.parentElement; e && e !== document.documentElement; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.overflowX !== 'visible' || cs.overflowY !== 'visible') { const q = e.getBoundingClientRect(); l = Math.max(l, q.left); t = Math.max(t, q.top); r = Math.min(r, q.right); b = Math.min(b, q.bottom); }
    }
    return { left: l, top: t, right: r, bottom: b };
  }
  function xformOf(el) {
    for (let e = el; e && e !== document.documentElement; e = e.parentElement) { const tr = getComputedStyle(e).transform; if (tr && tr !== 'none') return { el: e, tr }; }
    return null;
  }
  function inlineOnly(el) {
    for (const ch of el.childNodes) {
      if (ch.nodeType !== 1) continue;
      if (ch.tagName === 'BR') continue;
      if (['IMG', 'svg', 'SVG', 'CANVAS', 'VIDEO', 'IFRAME'].includes(ch.tagName)) return false;
      if (getComputedStyle(ch).display !== 'inline') return false;
      if (!inlineOnly(ch)) return false;
    }
    return true;
  }
  const raster = (el, kind) => items.push({ t: 'raster', kind, id: mark(el), box: box(el.getBoundingClientRect()), opacity: effOp(el), sel: FLAT.get(el) || null, desc: desc(el) });
  function pos(v, free) { if (v.endsWith('%')) return free * parseFloat(v) / 100; if (v === 'center') return free / 2; if (v === 'left' || v === 'top') return 0; if (v === 'right' || v === 'bottom') return free; return parseFloat(v); }
  function pushImg(el, cs) {
    const r = el.getBoundingClientRect(), nw = el.naturalWidth, nh = el.naturalHeight;
    if (!nw) { warns.push('image not loaded ' + el.getAttribute('src')); return; }
    if (/\.svg(\?|#|$)/i.test(el.currentSrc || el.src)) return raster(el, 'svg');
    if (xformOf(el)) { warns.push('transformed image rasterised: ' + el.getAttribute('src')); return raster(el, 'xform'); }
    const fit = cs.objectFit; const [opx, opy] = cs.objectPosition.split(' ');
    let pw = r.width, ph = r.height;
    if (fit !== 'fill') {
      let s = fit === 'cover' ? Math.max(r.width / nw, r.height / nh) : fit === 'none' ? 1 : Math.min(r.width / nw, r.height / nh);
      if (fit === 'scale-down') s = Math.min(1, s);
      pw = nw * s; ph = nh * s;
    }
    const px = r.left + pos(opx, r.width - pw), py = r.top + pos(opy, r.height - ph);
    const c = clipOf(el);
    const fl = Math.max(r.left, c.left), ft = Math.max(r.top, c.top), fr = Math.min(r.right, c.right), fb = Math.min(r.bottom, c.bottom);
    if (fr - fl < 0.5 || fb - ft < 0.5) { warns.push('image fully clipped ' + el.getAttribute('src')); return; }
    items.push({ t: 'image', id: mark(el), src: el.currentSrc || el.src, attr: el.getAttribute('src'), nat: [nw, nh], fit,
      frame: [X(fl), Y(ft), (fr - fl) * PT, (fb - ft) * PT], place: [X(px), Y(py), pw * PT, ph * PT], opacity: effOp(el), radius: radius(cs) });
  }
  // ---- SVG as vector: paths only (M L H V C S Q T Z, abs/rel); anything else -> raster
  function parsePath(d) {
    const tok = d.match(/[a-zA-Z]|-?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?/g); if (!tok) return null;
    let i = 0, cmd = null, cx = 0, cy = 0, sx = 0, sy = 0, pc = null, pq = null;
    const subs = []; let cur = null;
    const num = () => parseFloat(tok[i++]);
    const start = (x, y) => { cur = { closed: false, pts: [[[x, y], [x, y], [x, y]]] }; subs.push(cur); sx = x; sy = y; };
    const lineTo = (x, y) => { if (!cur) start(cx, cy); cur.pts.push([[x, y], [x, y], [x, y]]); };
    const curveTo = (x1, y1, x2, y2, x, y) => { if (!cur) start(cx, cy); cur.pts[cur.pts.length - 1][2] = [x1, y1]; cur.pts.push([[x, y], [x2, y2], [x, y]]); };
    while (i < tok.length) {
      if (/[a-zA-Z]/.test(tok[i])) cmd = tok[i++];
      const rel = cmd === cmd.toLowerCase(), C = cmd.toUpperCase();
      const ox = rel ? cx : 0, oy = rel ? cy : 0;
      if (C === 'M') { const x = num() + ox, y = num() + oy; start(x, y); cx = x; cy = y; cmd = rel ? 'l' : 'L'; pc = pq = null; }
      else if (C === 'L') { const x = num() + ox, y = num() + oy; lineTo(x, y); cx = x; cy = y; pc = pq = null; }
      else if (C === 'H') { const x = num() + (rel ? cx : 0); lineTo(x, cy); cx = x; pc = pq = null; }
      else if (C === 'V') { const y = num() + (rel ? cy : 0); lineTo(cx, y); cy = y; pc = pq = null; }
      else if (C === 'C') { const x1 = num() + ox, y1 = num() + oy, x2 = num() + ox, y2 = num() + oy, x = num() + ox, y = num() + oy; curveTo(x1, y1, x2, y2, x, y); pc = [x2, y2]; pq = null; cx = x; cy = y; }
      else if (C === 'S') { const x2 = num() + ox, y2 = num() + oy, x = num() + ox, y = num() + oy; const x1 = pc ? 2 * cx - pc[0] : cx, y1 = pc ? 2 * cy - pc[1] : cy; curveTo(x1, y1, x2, y2, x, y); pc = [x2, y2]; pq = null; cx = x; cy = y; }
      else if (C === 'Q' || C === 'T') {
        let qx, qy; if (C === 'Q') { qx = num() + ox; qy = num() + oy; } else { qx = pq ? 2 * cx - pq[0] : cx; qy = pq ? 2 * cy - pq[1] : cy; }
        const x = num() + ox, y = num() + oy;
        curveTo(cx + 2 / 3 * (qx - cx), cy + 2 / 3 * (qy - cy), x + 2 / 3 * (qx - x), y + 2 / 3 * (qy - y), x, y); pq = [qx, qy]; pc = null; cx = x; cy = y;
      }
      else if (C === 'Z') {
        if (cur) { cur.closed = true; const f = cur.pts[0], l = cur.pts[cur.pts.length - 1];
          if (cur.pts.length > 1 && Math.abs(f[0][0] - l[0][0]) < 1e-6 && Math.abs(f[0][1] - l[0][1]) < 1e-6) { f[1] = l[1]; cur.pts.pop(); } }
        cx = sx; cy = sy; cur = null; pc = pq = null;
      }
      else return null;           // A/a (arcs) and anything unknown
      if (isNaN(cx) || isNaN(cy)) return null;
    }
    return subs;
  }
  function pushSvg(el) {
    const r = el.getBoundingClientRect(), paths = [];
    for (const e of el.querySelectorAll('*')) {
      const tag = e.tagName.toLowerCase();
      if (['g', 'title', 'desc'].includes(tag)) { if (e.getAttribute('clip-path') || e.getAttribute('mask') || e.getAttribute('filter')) return raster(el, 'svg'); continue; }
      if (tag !== 'path') return raster(el, 'svg');
      const cs = getComputedStyle(e);
      if (/url\(/.test(cs.fill + cs.stroke) || cs.clipPath !== 'none' || cs.mask !== 'none' || cs.filter !== 'none' || (cs.strokeDasharray && cs.strokeDasharray !== 'none') || cs.markerStart !== 'none' || cs.markerEnd !== 'none') return raster(el, 'svg');
      const subs = parsePath(e.getAttribute('d') || ''); if (!subs) return raster(el, 'svg');
      const m = e.getScreenCTM();
      const T = ([x, y]) => { const p = new DOMPoint(x, y).matrixTransform(m); return [X(p.x), Y(p.y)]; };
      const scale = Math.sqrt(Math.abs(m.a * m.d - m.b * m.c));
      const swUser = parseFloat(cs.strokeWidth) || 0;
      const sw = (cs.vectorEffect === 'non-scaling-stroke' ? swUser : swUser * scale) * PT;
      paths.push({ subs: subs.map(s => ({ closed: s.closed, pts: s.pts.map(pt => pt.map(T)) })),
        stroke: cs.stroke === 'none' ? null : col(cs.stroke), fill: cs.fill === 'none' ? null : col(cs.fill), sw,
        so: parseFloat(cs.strokeOpacity), fo: parseFloat(cs.fillOpacity), opacity: parseFloat(cs.opacity) * effOp(el), rule: cs.fillRule });
    }
    if (!paths.length) return;
    items.push({ t: 'vector', id: mark(el), box: box(r), paths, desc: desc(el) });
  }
  function pushBox(el, cs) {
    const r = el.getBoundingClientRect();
    if (r.width < 0.01 || r.height < 0.01) return;
    const bg = col(cs.backgroundColor);
    if (bg && bg[3] > 0) items.push({ t: 'rect', id: mark(el), box: box(r), color: bg, opacity: effOp(el), radius: radius(cs), root: el === root });
    const bi = cs.backgroundImage;
    if (bi && bi !== 'none') raster(el, /gradient/.test(bi) ? 'gradient' : 'bgimage');
    for (const side of ['Top', 'Right', 'Bottom', 'Left']) {
      const w = parseFloat(cs[`border${side}Width`]); const c = col(cs[`border${side}Color`]);
      if (!(w > 0) || ['none', 'hidden'].includes(cs[`border${side}Style`]) || !c || c[3] === 0) continue;
      if (cs[`border${side}Style`] !== 'solid') warns.push(`border ${cs[`border${side}Style`]} drawn solid on ${desc(el)}`);
      const h = w / 2; let x1, y1, x2, y2;
      if (side === 'Top') { x1 = r.left; x2 = r.right; y1 = y2 = r.top + h; }
      if (side === 'Bottom') { x1 = r.left; x2 = r.right; y1 = y2 = r.bottom - h; }
      if (side === 'Left') { y1 = r.top; y2 = r.bottom; x1 = x2 = r.left + h; }
      if (side === 'Right') { y1 = r.top; y2 = r.bottom; x1 = x2 = r.right - h; }
      items.push({ t: 'line', id: mark(el), side, p1: [X(x1), Y(y1)], p2: [X(x2), Y(y2)], weight: w * PT, color: c, opacity: effOp(el) });
    }
    if (cs.boxShadow !== 'none') warns.push('box-shadow ignored on ' + desc(el));
  }
  const rng = document.createRange();
  function pushText(el, cs) {
    const xf = xformOf(el);
    let xinfo = null;
    if (xf) {
      const rt = el.getBoundingClientRect();
      const m = xf.tr.match(/matrix\(([^)]+)\)/); const a = m ? m[1].split(',').map(parseFloat) : null;
      if (!a || Math.abs(Math.hypot(a[0], a[1]) - 1) > 1e-3) warns.push('text transform with scale/skew on ' + desc(el));
      xinfo = { cx: X((rt.left + rt.right) / 2), cy: Y((rt.top + rt.bottom) / 2), deg: a ? Math.round(Math.atan2(a[1], a[0]) * 180 / Math.PI * 1000) / 1000 : 0, on: desc(xf.el) };
      xf.el.dataset.savedTransform = xf.el.style.transform; xf.el.style.transform = 'none';
    }
    const styles = [], skey = new Map();
    const stOf = e => {
      const s = getComputedStyle(e);
      const k = [s.fontFamily, s.fontWeight, s.fontStyle, s.fontSize, s.letterSpacing, s.textTransform, s.color, s.whiteSpace, s.lineHeight, s.textDecorationLine, s.verticalAlign].join('|');
      if (!skey.has(k)) { skey.set(k, styles.length); styles.push({ family: s.fontFamily, weight: s.fontWeight, style: s.fontStyle, size: parseFloat(s.fontSize) * PT,
        ls: s.letterSpacing === 'normal' ? 0 : parseFloat(s.letterSpacing) * PT, tt: s.textTransform, color: col(s.color), ws: s.whiteSpace,
        lh: s.lineHeight === 'normal' ? null : parseFloat(s.lineHeight) * PT, deco: s.textDecorationLine, va: s.verticalAlign, tag: e === el ? 'self' : e.tagName.toLowerCase(), opacity: effOp(e) }); }
      return skey.get(k);
    };
    const chars = [];
    (function collect(node) {
      for (const ch of node.childNodes) {
        if (ch.nodeType === 3) {
          const st = stOf(ch.parentElement);
          const pre = /^pre/.test(getComputedStyle(ch.parentElement).whiteSpace);
          for (let i = 0; i < ch.data.length; i++) {
            const c = ch.data[i];
            if (c >= '\uD800' && c <= '\uDFFF') warns.push('surrogate pair (emoji?) in ' + desc(el));
            if (!pre && /[ \t\n\r\f]/.test(c)) { const last = chars[chars.length - 1]; if (!last || last.ch === ' ' || last.ch === '\n') continue; chars.push({ ch: ' ', node: ch, off: i, st }); }
            else chars.push({ ch: c === '\n' ? '\n' : c, node: c === '\n' ? null : ch, off: i, st });
          }
        } else if (ch.nodeType === 1) {
          if (ch.tagName === 'BR') { while (chars.length && chars[chars.length - 1].ch === ' ') chars.pop(); chars.push({ ch: '\n', node: null, off: -1, st: stOf(node) }); }
          else collect(ch);
        }
      }
    })(el);
    while (chars.length && chars[chars.length - 1].ch === ' ') chars.pop();
    while (chars.length && chars[0].ch === ' ') chars.shift();
    const measure = () => chars.map(c => { if (!c.node) return null; rng.setStart(c.node, c.off); rng.setEnd(c.node, c.off + 1); const r = rng.getBoundingClientRect(); return (r.width === 0 && r.height === 0) ? null : r; });
    const linesOf = rs => {
      const L = []; let cur = null, forced = true;
      for (let i = 0; i < chars.length; i++) {
        const c = chars[i];
        if (c.ch === '\n') { forced = true; continue; }
        const r = rs[i]; if (!r || c.ch === ' ') continue;
        if (cur && !forced) {
          const ov = Math.min(cur.b, r.bottom) - Math.max(cur.t, r.top), h = Math.min(cur.b - cur.t, r.height);
          if (ov > 0.5 * h) { cur.x1 = Math.max(cur.x1, r.right); cur.x0 = Math.min(cur.x0, r.left); cur.end = i; continue; }
        }
        cur = { start: i, end: i, x0: r.left, x1: r.right, t: r.top, b: r.bottom, forced: forced && L.length > 0, st: c.st }; L.push(cur); forced = false;
      }
      return L;
    };
    const sigOf = L => L.map(l => l.start).join(',');
    const pad = k => parseFloat(cs[`padding${k}`]) + parseFloat(cs[`border${k}Width`]);
    const r0 = el.getBoundingClientRect();
    const cb = { left: r0.left + pad('Left'), right: r0.right - pad('Right'), top: r0.top + pad('Top'), bottom: r0.bottom - pad('Bottom') };
    const probe = document.createElement('span'); probe.style.cssText = 'display:inline-block;width:0;height:0;vertical-align:baseline;margin:0;padding:0;border:0';
    el.insertBefore(probe, el.firstChild); const base0 = probe.getBoundingClientRect().bottom; probe.remove();
    const rs0 = measure(), L0 = linesOf(rs0), sig0 = sigOf(L0);
    const w0 = cb.right - cb.left;
    const natural = L0.length ? Math.max(...L0.map(l => l.x1 - l.x0)) : 0;
    const soft = L0.filter((l, k) => k > 0 && !l.forced).length;
    const saved = el.getAttribute('style');
    const setW = w => { el.style.boxSizing = 'content-box'; el.style.width = w + 'px'; el.style.minWidth = '0'; el.style.maxWidth = 'none'; el.style.flex = 'none'; };
    setW(w0 + 20); const r1 = el.getBoundingClientRect();
    const dl = r1.left - r0.left, dr = r1.right - r0.right;
    const anchor = Math.abs(dl) < 0.3 ? 'left' : Math.abs(dr) < 0.3 ? 'right' : Math.abs(dl + dr) < 0.6 ? 'center' : 'other';
    setW(natural + 0.05); const lowOk = sigOf(linesOf(measure())) === sig0;
    let lo = natural;
    if (!lowOk) { let a = natural, b = w0; for (let k = 0; k < 18; k++) { const m = (a + b) / 2; setW(m); if (sigOf(linesOf(measure())) === sig0) b = m; else a = m; } lo = b; }
    let hi = Infinity;
    if (soft > 0) {
      setW(w0 + 900);
      if (sigOf(linesOf(measure())) !== sig0) { let a = w0, b = w0 + 900; for (let k = 0; k < 20; k++) { const m = (a + b) / 2; setW(m); if (sigOf(linesOf(measure())) === sig0) a = m; else b = m; } hi = b; }
    }
    if (saved === null) el.removeAttribute('style'); else el.setAttribute('style', saved);
    if (sigOf(linesOf(measure())) !== sig0) warns.push('RESTORE FAILED ' + desc(el));
    const runs = [];
    for (const c of chars) { const last = runs[runs.length - 1]; if (last && last.st === c.st) last.text += c.ch; else runs.push({ st: c.st, text: c.ch }); }
    const d0 = L0.length ? rs0[L0[0].start].bottom - base0 : 0;
    const lines = L0.map(l => ({ start: l.start, end: l.end, x0: X(l.x0), x1: X(l.x1), top: Y(l.t), bottom: Y(l.b), forced: l.forced,
      base: l.st === L0[0].st ? Y(rs0[l.start].bottom - d0) : null }));
    for (const s of styles) { if (s.va !== 'baseline') warns.push(`vertical-align ${s.va} flattened to baseline in ${desc(el)}`); if (s.deco && s.deco !== 'none') warns.push(`text-decoration ${s.deco} not carried in ${desc(el)}`); }
    items.push({ t: 'text', id: mark(el), desc: desc(el), cls: typeof el.className === 'string' ? el.className : '', dataset: { ...el.dataset },
      box: [X(cb.left), Y(cb.top), (cb.right - cb.left) * PT, (cb.bottom - cb.top) * PT], align: cs.textAlign, base0: Y(base0),
      lh: cs.lineHeight === 'normal' ? null : parseFloat(cs.lineHeight) * PT, size: parseFloat(cs.fontSize) * PT,
      natural: natural * PT, lo: lo * PT, hi: hi === Infinity ? null : hi * PT, soft, anchor, lowOk,
      text: chars.map(c => c.ch).join(''), runs, styles, lines, opacity: effOp(el), xf: xinfo });
    if (xf) { xf.el.style.transform = xf.el.dataset.savedTransform; delete xf.el.dataset.savedTransform; }
    const plain = el.textContent.replace(/\s+/g, ''), got = items[items.length - 1].text.replace(/\s+/g, '');
    if (plain !== got) warns.push('TEXT MISMATCH ' + desc(el) + ' [' + plain.slice(0, 40) + '] vs [' + got.slice(0, 40) + ']');
    if (cs.lineHeight === 'normal') warns.push('line-height: normal on ' + desc(el) + ' (leading taken from measured lines)');
  }
  function walk(el) {
    if (FLAT.has(el)) return raster(el, 'mockup');
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    const tag = el.tagName.toLowerCase();
    if (tag === 'img') { pushBox(el, cs); return pushImg(el, cs); }   // an <img> can carry its own background/border
    if (tag === 'svg') return pushSvg(el);
    if (['canvas', 'video', 'iframe', 'picture'].includes(tag)) { warns.push(tag + ' rasterised'); return raster(el, tag); }
    if (cs.mixBlendMode !== 'normal' || cs.filter !== 'none') warns.push(`${cs.mixBlendMode !== 'normal' ? 'mix-blend-mode' : 'filter'} on ${desc(el)} not carried`);
    pushBox(el, cs);
    if (el.textContent.trim() && inlineOnly(el)) return pushText(el, cs);
    for (const ch of el.childNodes) {
      if (ch.nodeType === 3 && ch.data.trim()) warns.push('anonymous text skipped in ' + desc(el) + ': "' + ch.data.trim().slice(0, 40) + '" (wrap it in its own element)');
      else if (ch.nodeType === 1) walk(ch);
    }
  }
  walk(root);
  const zi = [...root.querySelectorAll('*')].filter(e => !['auto', '0'].includes(getComputedStyle(e).zIndex)).map(desc);
  if (zi.length) warns.push('z-index used (IDML keeps DOM order): ' + zi.slice(0, 6).join(', '));
  return { W: R0.width * PT, H: R0.height * PT, items, warns };
}

async function shoot(tab, id, kind, file) {
  const clip = await tab.evaluate(([id, kind, rootSel]) => {
    const el = document.querySelector(`[data-idml="${id}"]`);
    const root = document.querySelector(rootSel);
    document.documentElement.style.background = 'transparent'; document.body.style.background = 'transparent';
    if (el !== root) root.style.background = 'transparent';
    root.style.visibility = 'hidden';
    el.style.visibility = 'visible';
    const showKids = ['mockup', 'svg', 'xform', 'canvas', 'video', 'iframe', 'picture'].includes(kind);
    for (const e of el.querySelectorAll('*')) e.style.visibility = showKids ? 'visible' : 'hidden';
    if (!showKids) { el.style.backgroundColor = 'transparent'; el.style.borderColor = 'transparent'; el.style.boxShadow = 'none'; }
    const r = el.getBoundingClientRect(), R = root.getBoundingClientRect();
    const l = Math.floor(Math.max(r.left, R.left)), t = Math.floor(Math.max(r.top, R.top)), rr = Math.ceil(Math.min(r.right, R.right)), b = Math.ceil(Math.min(r.bottom, R.bottom));
    return { x: l, y: t, width: rr - l, height: b - t };
  }, [id, kind, job.root_selector]);
  await tab.screenshot({ path: file, clip, omitBackground: true });
  return clip;
}

let failed = 0;
for (const p of pages) {
  const bad = await load(tabs[1], p);
  if (bad.fonts.length || bad.images.length) { console.log(`${p.id}: LOAD FAILED fonts=${bad.fonts} images=${bad.images}`); failed++; continue; }
  const res = await tabs[1].evaluate(extractInPage, { rootSel: job.root_selector, flat: Object.keys(job.flatten || {}) });
  res.page = p.id; res.html = p.html;
  for (const r of res.items.filter(i => i.t === 'raster')) {
    const dsf = r.kind === 'gradient' ? 2 : 4;
    await load(tabs[dsf], p);
    await tabs[dsf].evaluate(extractInPage, { rootSel: job.root_selector, flat: Object.keys(job.flatten || {}) });   // same walk => same ids
    const file = path.join(OV, `${p.id}_${r.id}_${r.kind}.png`);
    r.clipPx = await shoot(tabs[dsf], r.id, r.kind, file); r.png = file; r.dsf = dsf;
  }
  fs.writeFileSync(path.join(O, `${p.id}.json`), JSON.stringify(res, null, 1));
  const c = res.items.reduce((a, i) => (a[i.t] = (a[i.t] || 0) + 1, a), {});
  console.log(`${p.id.padEnd(22)} ${Object.entries(c).map(([k, v]) => k + '=' + v).join(' ')}${res.warns.length ? '\n    WARN ' + res.warns.join('\n    WARN ') : ''}`);
}
await browser.close();
process.exit(failed ? 1 : 0);
