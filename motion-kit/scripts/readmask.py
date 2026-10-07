#!/usr/bin/env python3
"""readmask.py — the READ-WINDOW mask of a footage scene: the subject's alpha (from clip.py's -subject.webm) OR'd over
the frames in which the word must be legible, i.e. from the scene's first frame to --until seconds in (wipe + ~1.3 s
of reading). A whole-clip union over-constrains: someone walking toward camera fills the frame by the end, long after
the word has been read. Feed the output to wordfit.py.

    python3 readmask.py assets/footage/move-subject.webm --until 1.9 --out assets/footage/move-read.png
"""
import argparse, subprocess
import numpy as np
from PIL import Image
ap = argparse.ArgumentParser(); ap.add_argument("webm"); ap.add_argument("--until", type=float, default=1.9)
ap.add_argument("--out", required=True); ap.add_argument("--from", dest="frm", type=float, default=0.0)
a = ap.parse_args()
W, H = 1080, 1920
# ffmpeg's native vp9 decoder drops VP9 alpha; libvpx-vp9 keeps it
raw = subprocess.run(["ffmpeg", "-v", "error", "-c:v", "libvpx-vp9", "-ss", f"{a.frm:.3f}", "-t", f"{a.until - a.frm:.3f}", "-i", a.webm,
                      "-f", "rawvideo", "-pix_fmt", "rgba", "-"], capture_output=True).stdout
fr = np.frombuffer(raw, np.uint8).reshape(-1, H, W, 4)[..., 3]
if len(fr) < 3: raise SystemExit(f"only {len(fr)} frames decoded — check the webm/alpha")
u = (fr > 96).any(0)
Image.fromarray((u * 255).astype(np.uint8), "L").save(a.out)
print(f"{a.out}: union of {len(fr)} frames ({a.frm:.2f}–{a.until:.2f}s) covers {u.mean()*100:.1f}% of frame")
