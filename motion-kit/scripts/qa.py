#!/usr/bin/env python3
"""qa.py — the motion-kit gate. Run on every render; a FAIL means do not send.

Rules come from brand.json (the piece's own, else the kit's): copy rules, trademarks, safe area,
frame size, fps, loudness, accent colours.
  COPY    every string the piece ever shows (renders/text.json from cues.py --text) against the copy rules
          (regex + why) · the ™ law on brand.json "trademarks" · canon check: every display line must
          appear in --canon (COPY.md) if given (WARN, so a human confirms it isn't invented)
  SAFE    every visible text box, every 0.25 s, inside the safe area (9:16 story/reel UI chrome)
  VIDEO   size · fps · duration = data-duration ±0.1 s · AAC 48 kHz · loudness ±1 LU · true peak
          no flat/blank run > 0.5 s · no frozen run > 1.6 s before the final hold · accent coverage table
  SHEET   renders/<slug>-sheet.jpg — one frame per 0.5 s. LOOK AT IT. Every defect a rig like this has
          shipped was invisible in code and obvious in the picture.

    python3 qa.py <piece-dir> renders/<slug>.mp4 [--canon COPY.md] [--hold 1.2] [--brand brand.json]
Calibrate after changing it: break a copy of a piece on purpose (add a "!", push a label to y 1700)
and confirm it FAILS. A gate that passes an empty or broken input proves nothing.
"""
import argparse, json, os, re, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw

ap = argparse.ArgumentParser(); ap.add_argument("piece"); ap.add_argument("mp4")
ap.add_argument("--canon"); ap.add_argument("--brand")
ap.add_argument("--hold", type=float, default=1.2, help="final hold allowed to be frozen (s)")
a = ap.parse_args()
P = os.path.abspath(a.piece); fails, warns = [], []
F = lambda m: fails.append(m); Wn = lambda m: warns.append(m)
KIT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
bp = a.brand or next((x for x in (os.path.join(P, "brand.json"), os.path.join(KIT, "brand.json")) if os.path.exists(x)))
B = json.load(open(bp))

# ── COPY ────────────────────────────────────────────────────────────────────────────────────────
tj = os.path.join(P, "renders", "text.json")
frames = json.load(open(tj)) if os.path.exists(tj) else []
if not frames: F("no renders/text.json — run cues.py --text first (an empty copy check proves nothing)")
strings = sorted({x["s"] for f in frames for x in f["text"]})
if frames and len(strings) < 3: F(f"only {len(strings)} visible strings found — the text probe is blind, fix it before trusting COPY")
for rule in B.get("copy_rules", []):
    for s_ in strings:
        if re.search(rule["pattern"], s_, re.I): F(f'COPY {rule["why"]}: "{s_}"')
for s_ in strings:
    for tm in B.get("trademarks", []):
        for m in re.finditer(re.escape(tm), s_, re.I):
            if not s_[m.end():m.end() + 1] == "\u2122": F(f'COPY ™ law: "{tm}" without ™ in "{s_}"')
if a.canon and os.path.exists(a.canon):
    canon = re.sub(r"\s+", " ", open(a.canon).read()).lower()
    for s_ in strings:
        k = re.sub(r"\s+", " ", s_).lower().strip(" .,")
        if len(k) > 3 and k not in canon: Wn(f'COPY not found verbatim in canon: "{s_}" — confirm it is canon, not invented')

# ── SAFE AREA ───────────────────────────────────────────────────────────────────────────────────
SA = B.get("safe_area", {}); SX0, SX1, SY0, SY1 = SA.get("x0", 40), SA.get("x1", 1040), SA.get("y0", 250), SA.get("y1", 1580)
bad = {}
for f in frames:
    for x in f["text"]:
        if x["y0"] < SY0 - 1 or x["y1"] > SY1 + 1 or x["x0"] < SX0 - 1 or x["x1"] > SX1 + 1:
            bad.setdefault(x["s"], []).append((f["t"], round(x["x0"]), round(x["y0"]), round(x["x1"]), round(x["y1"])))
for s, hits in bad.items():
    t0, t1 = hits[0][0], hits[-1][0]
    if t1 - t0 >= 0.24 or len(hits) >= 2:           # a line passing through the edge in one sample is a move, not a layout
        F(f'SAFE "{s}" outside the safe area {t0:.2f}–{t1:.2f}s e.g. box {hits[len(hits)//2][1:]}')

# ── VIDEO ───────────────────────────────────────────────────────────────────────────────────────
def probe(args): return subprocess.run(args, capture_output=True, text=True).stdout
info = json.loads(probe(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", a.mp4]) or "{}")
vs = [s for s in info.get("streams", []) if s["codec_type"] == "video"]; au = [s for s in info.get("streams", []) if s["codec_type"] == "audio"]
dur = float(info.get("format", {}).get("duration", 0))
html = open(os.path.join(P, "index.html")).read()
m = re.search(r'data-duration="([\d.]+)"', html); want = float(m.group(1)) if m else None
if not vs: F("VIDEO no video stream")
else:
    v = vs[0]
    FR = B.get("frame", {}); FW, FH, FPS = FR.get("width", 1080), FR.get("height", 1920), FR.get("fps", 30)
    if (v["width"], v["height"]) != (FW, FH): F(f'VIDEO size {v["width"]}x{v["height"]} (want {FW}x{FH})')
    if v.get("r_frame_rate") != f"{FPS}/1": F(f'VIDEO fps {v.get("r_frame_rate")} (want {FPS})')
if want and abs(dur - want) > 0.12: F(f"VIDEO duration {dur:.2f}s ≠ data-duration {want}s")
if not au: F("VIDEO no audio stream")
elif au[0].get("sample_rate") != "48000": F(f'VIDEO audio {au[0].get("sample_rate")} Hz')
if au:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", a.mp4, "-map", "0:a", "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    I = re.findall(r"I:\s+(-?[\d.]+) LUFS", r); TP = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r)
    LU = B.get("loudness", {}); WANT, TPMAX = LU.get("lufs", -14), LU.get("true_peak_max", -1.0)
    if I and abs(float(I[-1]) - WANT) > 1.0: F(f"VIDEO loudness {I[-1]} LUFS (want {WANT} ±1)")
    if TP and float(TP[-1]) > TPMAX + 0.1: F(f"VIDEO true peak {TP[-1]} dBFS (want ≤ {TPMAX})")
    loud = f"{I[-1] if I else '?'} LUFS, TP {TP[-1] if TP else '?'}"
else: loud = "—"

# frames at 10 fps, 108×192, for flat/frozen/accent checks
raw = subprocess.run(["ffmpeg", "-v", "error", "-i", a.mp4, "-vf", "fps=10,scale=108:192", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
fr = np.frombuffer(raw, np.uint8).reshape(-1, 192, 108, 3).astype(np.int16) if raw else np.zeros((0, 192, 108, 3))
if len(fr) < 10: F(f"VIDEO decoded only {len(fr)} frames")
flat = [i for i in range(len(fr)) if fr[i].std() < 2.0]
run, runs = [], []
for i in flat:
    if run and i != run[-1] + 1: runs.append(run); run = []
    run.append(i)
if run: runs.append(run)
for r_ in runs:
    if len(r_) > 5 and r_[0] > 3: F(f"VIDEO flat/blank frames {r_[0]/10:.1f}–{r_[-1]/10:.1f}s")
d = [np.abs(fr[i] - fr[i - 1]).mean() for i in range(1, len(fr))]
still, s0 = 0, None
end_hold = (len(fr) / 10) - a.hold
for i, x in enumerate(d, 1):
    if x < 0.15:
        s0 = i if s0 is None else s0; still += 1
    else:
        if s0 is not None and still > 16 and s0 / 10 < end_hold: Wn(f"VIDEO frozen {s0/10:.1f}–{i/10:.1f}s (dead air?)")
        s0, still = None, 0
ACC = np.array(B.get("accent_rgb", [[59, 91, 219]]))
acc = [((np.abs(f[..., None, :] - ACC[None, None]).sum(-1).min(-1) < 60).mean() * 100) for f in fr]
per_s = [max(acc[i:i + 10]) for i in range(0, len(acc), 10)]
if per_s and max(per_s) > B.get("accent_max_pct", 4): Wn(f"VIDEO accent peaks at {max(per_s):.1f}% of frame (s{int(np.argmax(per_s))}) — one accent moment, not a flood")

# ── SHEET ───────────────────────────────────────────────────────────────────────────────────────
slug = os.path.splitext(os.path.basename(a.mp4))[0]
sheet = os.path.join(P, "renders", f"{slug}-sheet.jpg")
raw2 = subprocess.run(["ffmpeg", "-v", "error", "-i", a.mp4, "-vf", "fps=2,scale=180:320", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
if raw2:
    ims = np.frombuffer(raw2, np.uint8).reshape(-1, 320, 180, 3); cols = 9; rows = (len(ims) + cols - 1) // cols
    S = Image.new("RGB", (cols * 184, rows * 340), (28, 28, 30)); dr = ImageDraw.Draw(S)
    for i, im in enumerate(ims):
        x, y = (i % cols) * 184, (i // cols) * 340; S.paste(Image.fromarray(im), (x + 2, y + 2)); dr.text((x + 4, y + 324), f"{i/2:.1f}s", fill=(220, 220, 220))
    S.save(sheet, quality=85)

print(f"\nQA {slug}: {dur:.2f}s · {len(strings)} strings · {len(frames)} text samples · audio {loud}")
print("   accent % by second: " + " ".join(f"{x:.1f}" for x in per_s))
for w in warns: print("  WARN", w)
for f_ in fails: print("  FAIL", f_)
print(f"  sheet → {sheet}")
print("  ==> " + ("FAIL" if fails else "PASS") + f" ({len(fails)} fail, {len(warns)} warn)")
sys.exit(1 if fails else 0)
