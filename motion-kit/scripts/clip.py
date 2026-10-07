#!/usr/bin/env python3
"""clip.py — cut a FOOTAGE scene for a motion piece: background video + transparent SUBJECT video (per-frame
Apple Vision lift) + the audio window + a union mask for word placement. The subject video goes ABOVE the giant
word, the background BELOW it: type behind a moving person, free, all local.

    python3 clip.py <master.mp4> --start 3.33 --dur 3.68 --out assets/footage/move [--slow 1.06] [--fps 24] [--person]

Writes <out>.mp4 (h264, 24 fps, same frames the subject was lifted from), <out>-subject.webm (VP9 + alpha,
feathered 1 px), <out>.wav (the clip's own sound, slowed with the picture), <out>-union.png (every frame's
subject mask OR'd — a word that clears it clears every frame) and <out>.json {frames, dur, slow, src, start}.
Slow-down ≤ ~1.08 is a plain re-time (frame dups). Beyond that add --interp (ffmpeg minterpolate, fine on slow
pans/tilts and fabric, risky on fast limbs) — e.g. a 2.55 s macro stretched 1.41× to fill a 3.6 s scene. ⚠️ The two videos MUST be authored from the same frames: cut once here, never trim
the mp4 and the webm separately, or they drift by a frame at the cut.
"""
import argparse, glob, json, os, shutil, subprocess, sys
import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("master"); ap.add_argument("--start", type=float, required=True); ap.add_argument("--dur", type=float, required=True)
ap.add_argument("--out", required=True); ap.add_argument("--slow", type=float, default=1.0); ap.add_argument("--fps", type=int, default=24)
ap.add_argument("--feather", type=float, default=1.0)
ap.add_argument("--person", action="store_true", help="person-only segmentation (a car or furniture is NOT the subject)")
ap.add_argument("--interp", action="store_true", help="motion-interpolate the slow-down (smooth pans/tilts; use when --slow > ~1.1)")
a = ap.parse_args()
out = a.out; os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
work = out + "-frames"; shutil.rmtree(work, ignore_errors=True); os.makedirs(work)
FF = "ffmpeg"

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode: sys.exit(f"{' '.join(cmd[:3])} failed: {r.stderr[-800:]}")

# 1. frames (the ONE source of truth for both videos), slowed if asked, exact fps
vf = f"setpts={a.slow}*PTS," + (f"minterpolate=fps={a.fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1" if a.interp else f"fps={a.fps}")
run([FF, "-v", "error", "-y", "-ss", f"{a.start:.3f}", "-t", f"{a.dur:.3f}", "-i", a.master, "-vf", vf, "-start_number", "0", f"{work}/f_%06d.png"])
frames = sorted(glob.glob(f"{work}/f_*.png"))
if len(frames) < a.fps: sys.exit(f"only {len(frames)} frames extracted")
# 2. per-frame subject masks (Apple Vision; compiled on first use)
VL = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "..", "vision-lift")   # sibling skill
lv = os.path.join(VL, "lift-video")
if not os.path.exists(lv):
    run(["swiftc", "-O", os.path.join(VL, "lift-video.swift"), "-o", lv])
r = subprocess.run([lv, work] + (["--person"] if a.person else []), capture_output=True, text=True); print(r.stdout.strip())
if r.returncode or "ok" not in r.stdout: sys.exit(f"lift-video failed: {r.stdout}{r.stderr}")
# 3. RGBA frames + union mask
union = None
for f in frames:
    m = Image.open(f.replace("/f_", "/m_")).convert("L")
    if a.feather > 0: m = m.filter(ImageFilter.GaussianBlur(a.feather))
    im = Image.open(f).convert("RGB"); im.putalpha(m); im.save(f.replace("/f_", "/a_"))
    arr = np.asarray(m) > 96
    union = arr if union is None else (union | arr)
Image.fromarray((union * 255).astype(np.uint8), "L").save(out + "-union.png")
# 4. encode: background h264 (yuv420p), subject VP9 alpha (yuva420p) — same frame count, same fps
run([FF, "-v", "error", "-y", "-framerate", str(a.fps), "-i", f"{work}/f_%06d.png", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out + ".mp4"])
run([FF, "-v", "error", "-y", "-framerate", str(a.fps), "-i", f"{work}/a_%06d.png", "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "24", "-row-mt", "1", "-auto-alt-ref", "0", out + "-subject.webm"])
# 5. the clip's own sound, re-timed with the picture (atempo < 1 slows)
tempo = 1.0 / a.slow
run([FF, "-v", "error", "-y", "-ss", f"{a.start:.3f}", "-t", f"{a.dur:.3f}", "-i", a.master, "-vn", "-af", f"atempo={tempo:.4f}", "-ar", "48000", "-ac", "2", out + ".wav"])
n = len(frames); dur = n / a.fps
def probe(p): return subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip()
nb, nw = probe(out + ".mp4"), probe(out + "-subject.webm")
if nb != str(n) or nw != str(n): sys.exit(f"frame count mismatch: frames {n} mp4 {nb} webm {nw}")
json.dump(dict(src=os.path.abspath(a.master), start=a.start, src_dur=a.dur, slow=a.slow, fps=a.fps, frames=n, dur=round(dur, 4),
               union_cover=round(float(union.mean()) * 100, 1)), open(out + ".json", "w"))
shutil.rmtree(work, ignore_errors=True)
print(f"{out}: {n} frames = {dur:.3f}s @ {a.fps} fps (slow {a.slow}) · mp4 + subject.webm + wav + union ({union.mean()*100:.1f}% of frame)")
