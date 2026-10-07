#!/usr/bin/env python3
"""wordfit.py — where does a giant word go BEHIND the subject and still read?

Renders the word in the kit's variable TTF (Inter, wght axis) at a width, slides it down the frame, and
scores every band against the subject mask (subject.py's <out>-subject.png alpha):
  worst  = the most-hidden single LETTER, measured on its TOP 55% (> ~40% hidden there = unreadable)
  total  = share of the word's ink behind the subject (want ~12–35%: less = no depth, more = no word)
Prints the best bands; use the top one's y as the word box top and CHECK THE SNAPSHOT.

    python3 wordfit.py assets/hero-subject.png "DEPTH." [--width 1000] [--y0 250] [--y1 1500] [--weight 700]
    python3 wordfit.py assets/footage/walk-read.png "MOVE."     # footage: readmask.py's read-window mask
"""
import argparse, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser(); ap.add_argument("subject"); ap.add_argument("word")
ap.add_argument("--width", default="1000,900,800,700", help="candidate widths, px"); ap.add_argument("--weight", type=int, default=700)
ap.add_argument("--track", type=float, default=-0.045, help="letter-spacing in em (kit .word = -0.045)")
ap.add_argument("--margin", type=int, default=60, help="min distance from the frame edge");
ap.add_argument("--y0", type=int, default=250); ap.add_argument("--y1", type=int, default=1500)
ap.add_argument("--font", default=os.path.join(HERE, "..", "kit", "fonts", "Inter-variable.ttf"))
ap.add_argument("--json", help="write the best placement here (width, size, x, y, glyph_offset, hidden, worst)")
a = ap.parse_args()

_im = Image.open(a.subject)
# accepts subject.py's RGBA (alpha = subject) OR an L mask (clip.py -union.png / readmask.py: every frame OR'd,
# so a placement that clears it reads in every frame of the footage)
alpha = (np.asarray(_im.split()[-1]) if _im.mode == "RGBA" else np.asarray(_im.convert("L"))).astype(np.float32) / 255 > 0.5
H, W = alpha.shape
word = a.word.upper()
FEET = set("ELZ2")       # letters whose identity lives in their bottom stroke

def render(size):
    f = ImageFont.truetype(a.font, size)
    try: f.set_variation_by_axes([32, a.weight])          # Inter axes: opsz, wght
    except Exception: pass
    xs, x = [], 0.0
    for ch in word:
        xs.append(x); x += f.getlength(ch) + a.track * size
    wpx = int(x - a.track * size) + 4
    asc, desc = f.getmetrics()
    img = Image.new("L", (wpx, asc + desc), 0); d = ImageDraw.Draw(img)
    letters = []
    for ch, x0 in zip(word, xs):
        li = Image.new("L", img.size, 0); ImageDraw.Draw(li).text((x0, 0), ch, font=f, fill=255)
        letters.append((ch, np.asarray(li) > 127)); d.text((x0, 0), ch, font=f, fill=255)
    return np.asarray(img) > 127, letters, wpx

def fitted(width):
    size = 200
    for _ in range(3):                                     # fit the word to width
        _, _, wpx = render(size); size = size * width / wpx
    full, letters, wpx = render(int(size))
    rows = np.where(full.any(1))[0]; top, bot = rows.min(), rows.max()
    ls = [(ch, l[top:bot + 1]) for ch, l in letters if l.sum() > 50]
    # legibility lives in the TOP of a word: readers recognise letters from their upper ~55% (a shoulder over
    # the bottoms of a word still reads; a head over the top of a "V" does not). Score that band per letter.
    # EXCEPT letters defined by their FEET: an E with its bottom bar covered reads as F, an L as I, a Z as 7.
    # Those are scored over their full height (a demo's "DEPTH." read "DFPTH." with a top-55% check).
    band = int(0.55 * (bot - top + 1))
    ls_top = []
    for ch, l in ls:
        l = l.copy()
        if ch not in FEET: l[band:] = False
        ls_top.append(l)
    return int(size), full[top:bot + 1], ls_top, wpx, int(top)

res = []
for width in [int(v) for v in str(a.width).split(",")]:
    size, full, letters, wpx, top = fitted(width)
    h = full.shape[0]; ink = full.sum()
    for x0 in range(a.margin, W - a.margin - wpx + 1, 20):
        for y in range(a.y0, min(a.y1, H - h), 10):
            under = alpha[y:y + h, x0:x0 + wpx]
            total = (full & under).sum() / ink
            worst = max((l & under).sum() / l.sum() for l in letters if l.any())
            score = worst + 2 * (0 if 0.12 <= total <= 0.35 else min(abs(total - 0.12), abs(total - 0.35))) - 0.00004 * width
            res.append((score, width, size, x0, y, total, worst, top))
res.sort()
print(f"word {word!r} — best placements (x/y = INK box top-left; CSS box top = y − glyph offset):")
seen = 0
for s_, width, size, x0, y, tot, wst, top in res:
    if seen >= 8: break
    seen += 1
    ok = "OK" if wst < 0.40 and 0.08 <= tot <= 0.4 else "—"
    print(f"  width {width:4d} font {size:3d}px  x={x0:4d} y={y:4d} (glyph offset {top})  hidden {tot:5.1%}  worst letter {wst:5.1%}  {ok}")
if a.json and res:
    import json
    s_, width, size, x0, y, tot, wst, top = res[0]
    json.dump(dict(word=word, width=width, size=size, x=x0, y=y, glyph_offset=int(top), hidden=round(float(tot), 3),
                   worst=round(float(wst), 3), ok=bool(wst < 0.40 and 0.08 <= tot <= 0.4)), open(a.json, "w"))
    print(f"best → {a.json}")
