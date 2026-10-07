#!/usr/bin/env python3
"""cues.py — load a motion-kit composition headless and dump what its timeline declared:
window.__mk = { cues:[{t, kind, ...}], duration, ...debug }.  Sound is built FROM this, so picture and
sound can never drift (a hand-copied table of times in the sound script is the drift bug this replaces).

Also dumps the text QA reads (every text node + its box at sampled times) with --text.

    python3 cues.py <piece-dir> [--out renders/cues.json] [--text renders/text.json]
"""
import argparse, functools, http.server, json, os, socketserver, sys, threading
from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser(); ap.add_argument("piece")
ap.add_argument("--out"); ap.add_argument("--text"); ap.add_argument("--step", type=float, default=0.25)
a = ap.parse_args()
piece = os.path.abspath(a.piece)
out = a.out or os.path.join(piece, "renders", "cues.json")
os.makedirs(os.path.dirname(out), exist_ok=True)

# serve over http: Chrome blocks @font-face from file:// (origin null), and the layout must use the real font
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
Handler = functools.partial(Quiet, directory=piece)
srv = socketserver.TCPServer(("127.0.0.1", 0), Handler); port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

TEXT_JS = """(t) => {
  const tl = window.__timelines.main; tl.seek(t, false);
  const R = document.getElementById('root').getBoundingClientRect(), out = [];
  const walker = document.createTreeWalker(document.getElementById('root'), NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const n = walker.currentNode, s = n.textContent.trim(); if (!s) continue;
    const el = n.parentElement; let op = 1, e = el, clipped = false;
    for (; e && e.id !== 'root'; e = e.parentElement) { const cs = getComputedStyle(e); op *= +cs.opacity; if (cs.visibility === 'hidden' || cs.display === 'none') op = 0; }
    if (op < 0.05) continue;
    const rg = document.createRange(); rg.selectNodeContents(n); const b = rg.getBoundingClientRect();
    if (b.width < 1) continue;
    // visible part only: intersect with every overflow-hidden / clip-path ancestor box
    let x0 = b.left, y0 = b.top, x1 = b.right, y1 = b.bottom;
    for (e = el; e && e.id !== 'root'; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.overflow === 'hidden' || cs.clipPath !== 'none') { const r = e.getBoundingClientRect();
        let cx0 = r.left, cy0 = r.top, cx1 = r.right, cy1 = r.bottom;
        const m = cs.clipPath.match(/inset\\(([-\\d.]+)px(?: ([-\\d.]+)px)?(?: ([-\\d.]+)px)?(?: ([-\\d.]+)px)?/);
        if (m) { const v = m.slice(1).map(q => q == null ? null : +q); const [tt, rr = tt, bb = tt, ll = rr] = v.map((q, i) => q ?? v[i === 3 ? 1 : 0]);
          cy0 += tt; cx1 -= rr; cy1 -= bb; cx0 += ll; }
        x0 = Math.max(x0, cx0); y0 = Math.max(y0, cy0); x1 = Math.min(x1, cx1); y1 = Math.min(y1, cy1); }
    }
    if (x1 - x0 < 2 || y1 - y0 < 2) continue;
    out.push({ s, x0: x0 - R.left, y0: y0 - R.top, x1: x1 - R.left, y1: y1 - R.top, op: Math.round(op * 100) / 100 });
  }
  return out;
}"""

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1080, "height": 1920})
    pg.add_init_script("window.__timelines = window.__timelines || {};")
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/index.html")
    pg.wait_for_function("window.__mkReady === true", timeout=30000)
    dm = pg.evaluate("window.__mk")
    json.dump(dm, open(out, "w"), indent=1)
    print(f"{len(dm['cues'])} cues · duration {dm['duration']:.2f}s → {out}")
    if a.text:
        frames, t = [], 0.0
        while t <= dm["duration"] + 1e-6:
            frames.append({"t": round(t, 3), "text": pg.evaluate(TEXT_JS, t)}); t += a.step
        json.dump(frames, open(a.text, "w")); print(f"text at {len(frames)} times → {a.text}")
    if errs: print("PAGE ERRORS:", *errs, sep="\n  "); sys.exit(1)
    b.close()
srv.shutdown()
