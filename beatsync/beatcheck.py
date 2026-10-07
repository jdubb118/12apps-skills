#!/usr/bin/env python3
"""beatcheck.py: prove a rendered video is on the beat of its song.

  python3 beatcheck.py <render.mp4> --grid music/grid.json
        [--beats music/beats.json] [--cuts 4,6,8,12,16] [--max-ms 50]

Measures the frame-to-frame change of the render (downscaled luma), finds the spikes (hard cuts,
slams, flashes) and reports each one's offset to the nearest DETECTED song beat, in reel time
(beat time - song_start). Detected beats are the ground truth, not the fitted grid: this checks the
grid too.
  --cuts   the hard cuts you PLANNED, in reel beats (the n in `PHASE + n * BEAT`). Each is looked up
           within +-0.2 s of its planned time. Exit 1 if any is off by more than --max-ms.
  (none)   auto mode: every spike above median + 8 MAD, 0.15 s apart. It reports them all, which
           catches the cuts you didn't mean to put off the beat.
1 frame at 30 fps = 33 ms. Up to about 50 ms reads as on-beat; a well-cut reel measures 0-47 ms.
The check refuses to pass on nothing: it needs >= 3 beats in range and a non-empty spike list.
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate", "-of", "json", path], capture_output=True, text=True, check=True)
    st = json.loads(out.stdout)["streams"][0]
    n, d = st["r_frame_rate"].split("/")
    return int(st["width"]), int(st["height"]), float(n) / float(d)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--grid", required=True, help="grid.json from beatgrid.py (or the older {beat, song_start} form)")
    ap.add_argument("--beats", help="beats.json (detected beats); default: next to grid.json")
    ap.add_argument("--cuts", help="comma-separated planned cut beats, in reel beats")
    ap.add_argument("--max-ms", type=float, default=50.0)
    ap.add_argument("--subdiv", type=int, default=2, choices=(1, 2, 4),
                    help="targets: 1 = beats only, 2 = beats + 8ths (default), 4 = 16ths")
    a = ap.parse_args()

    g = json.load(open(a.grid))
    beat, s0 = float(g["beat"]), float(g.get("song_start", 0.0))
    phase = float(g.get("reel", {}).get("phase", 0.0))
    bpath = a.beats or os.path.join(os.path.dirname(os.path.abspath(a.grid)), "beats.json")
    det = np.array(json.load(open(bpath))["beats"]) - s0

    W, H, fps = probe(a.video)
    w, h = max(16, W // 10), max(16, H // 10)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", a.video, "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, h, w).astype(np.int16)
    diff = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2))          # diff[i] = change INTO frame i+1
    dur = len(fr) / fps
    det = det[(det > -0.1) & (det < dur + 0.1)]
    if len(det) < 3:
        sys.exit(f"FAIL: only {len(det)} detected beats inside the {dur:.1f} s render. Wrong grid or song_start?")
    # targets = detected beats, subdivided between neighbours (8ths/16ths are legit hit points too)
    tg = [det]
    for j in range(1, a.subdiv):
        tg.append(det[:-1] + np.diff(det) * j / a.subdiv)
    targets = np.sort(np.concatenate(tg))

    rows = []
    if a.cuts:
        for cb in [float(x) for x in a.cuts.split(",") if x.strip()]:
            t = phase + cb * beat
            lo, hi = max(0, int((t - 0.2) * fps)), min(len(diff), int((t + 0.2) * fps) + 1)
            if hi <= lo:
                rows.append((cb, t, None, None)); continue
            k = lo + int(np.argmax(diff[lo:hi]))
            rows.append((cb, t, (k + 1) / fps, float(diff[k])))
    else:
        med = np.median(diff); mad = np.median(np.abs(diff - med)) or 1e-6
        idx = [i for i in np.argsort(-diff) if diff[i] > med + 8 * mad]
        keep = []
        for i in idx:
            if all(abs(i - j) >= 0.15 * fps for j in keep):
                keep.append(i)
        rows = [(None, None, (k + 1) / fps, float(diff[k])) for k in sorted(keep)]
    if not rows:
        sys.exit("FAIL: no spikes found, so nothing was checked. A still or a pure fade has no hard cuts; pass --cuts.")

    print(f"{a.video}: {dur:.2f} s @ {fps:g} fps | grid {60 / beat:.3f} BPM, song_start {s0:.3f} s, phase {phase:+.4f} s")
    print(f" planned beat | planned t | spike t  | nearest {'beat' if a.subdiv == 1 else 'beat/' + {2: '8th', 4: '16th'}[a.subdiv]} | offset")
    errs = []
    for cb, t, ts, mag in rows:
        if ts is None:
            print(f"  b{cb:>5g} | {t:7.3f}s | (outside the render)"); continue
        nb = targets[np.argmin(np.abs(targets - ts))]
        e = ts - nb; errs.append(e)
        flag = "" if abs(e) * 1000 <= a.max_ms else "  <-- OFF BEAT"
        print(f"  {('b' + format(cb, 'g')) if cb is not None else '(auto)':>11} | {'' if t is None else format(t, '7.3f') + 's':>9} | "
              f"{ts:7.3f}s | {nb:7.3f}s | {1000 * e:+5.0f} ms{flag}")
    errs = np.array(errs)
    bad = int((np.abs(errs) * 1000 > a.max_ms).sum())
    print(f"\n{len(errs)} spikes: mean {1000 * errs.mean():+.0f} ms, max |offset| {1000 * np.abs(errs).max():.0f} ms, "
          f"{bad} over {a.max_ms:g} ms")
    if a.cuts and bad:
        sys.exit(1)


if __name__ == "__main__":
    main()
