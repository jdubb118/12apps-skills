#!/usr/bin/env python3
"""subject.py — split a photo into BACKGROUND + SUBJECT layers for depth moves (type behind the
subject, 2.5D parallax). Apple Vision lift (lift.swift, compiled on first use) gives a soft alpha.

    python3 subject.py <photo.jpg> --out layers/scene [--size 1080x1920] [--mask cached.png]
Writes <out>.jpg (the full photo, cover-fit to --size), <out>-subject.png (RGBA, same size) and
<out>.json {head: y of the subject's top, bbox:[x0,y0,x1,y1], cover:%}. Stack them: photo, then your
type, then the subject PNG on top, and the type sits BEHIND the subject.
"""
import argparse, json, os, subprocess, sys
import numpy as np
from PIL import Image, ImageFilter
HERE = os.path.dirname(os.path.abspath(__file__))
def _lift_bin():   # Apple Vision subject lift; compiled on first use (swiftc ships with the Xcode Command Line Tools)
    b = os.path.join(HERE, "lift")
    if not os.path.exists(b):
        subprocess.run(["swiftc", "-O", os.path.join(HERE, "lift.swift"), "-o", b], check=True)
    return b
ap = argparse.ArgumentParser(); ap.add_argument("photo"); ap.add_argument("--out", required=True)
ap.add_argument("--size", default="1080x1920"); ap.add_argument("--mask")
a = ap.parse_args()
W, H = map(int, a.size.split("x"))
mp = a.mask or a.out + "-mask.png"
if not (a.mask and os.path.exists(mp)):
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    r = subprocess.run([_lift_bin(), a.photo, mp], capture_output=True, text=True)
    if r.returncode: sys.exit(f"lift failed: {r.stdout}{r.stderr}")
im = Image.open(a.photo).convert("RGB"); m = Image.open(mp).convert("L").resize(im.size, Image.BILINEAR)
s = max(W / im.width, H / im.height); nw, nh = round(im.width * s), round(im.height * s)
ox, oy = (nw - W) // 2, (nh - H) // 2
im = im.resize((nw, nh), Image.LANCZOS).crop((ox, oy, ox + W, oy + H))
m = m.resize((nw, nh), Image.BILINEAR).crop((ox, oy, ox + W, oy + H)).filter(ImageFilter.GaussianBlur(0.8))
im.save(a.out + ".jpg", quality=92)
sub = im.copy(); sub.putalpha(m); sub.save(a.out + "-subject.png", optimize=True)
A = np.asarray(m) > 128; ys, xs = np.where(A)
meta = dict(head=int(ys.min()), bbox=[int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())], cover=round(float(100 * A.mean()), 1))
json.dump(meta, open(a.out + ".json", "w")); print(a.out, meta)
