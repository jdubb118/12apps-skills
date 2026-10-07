#!/usr/bin/env python3
"""selftest.py: prove the Vision lift finds a subject you KNOW the outline of.

Draws a shaded ball on a gradient backdrop (its true mask is a known circle), lifts it, and checks the
mask against the truth (IoU >= 0.85). Then it writes 6 video frames with the ball moving, one of them an
EMPTY backdrop, and checks lift-video returns a mask for every frame: the empty one all black.

    python3 selftest.py          # exit 0 = pass (macOS 14+, Xcode Command Line Tools for swiftc)
"""
import glob, os, subprocess, sys, tempfile
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, R = 900, 1200, 210


def scene(cx, cy, ball=True):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    bg = np.stack([210 - yy / H * 60, 205 - yy / H * 60, 198 - yy / H * 55], -1)   # warm studio sweep
    truth = ((xx - cx) ** 2 + (yy - cy) ** 2) <= R ** 2
    if ball:
        d = np.sqrt(np.clip(1 - ((xx - cx) ** 2 + (yy - cy) ** 2) / R ** 2, 0, 1))      # sphere normal z
        lx, ly = (xx - cx) / R, (yy - cy) / R
        shade = np.clip(0.25 + 0.75 * (d * 0.7 - lx * 0.35 - ly * 0.45), 0, 1)
        col = np.stack([40 + 190 * shade, 60 + 120 * shade, 160 + 90 * shade], -1)      # a blue ball
        spec = np.clip((d - 0.93) * 14, 0, 1)[..., None] * 255
        col = np.clip(col + spec, 0, 255)
        bg = np.where(truth[..., None], col, bg)
        shadow = np.exp(-(((xx - cx) / (R * 1.1)) ** 2 + ((yy - cy - R * 1.02) / (R * 0.12)) ** 2)) * 0.35
        bg = bg * (1 - shadow[..., None] * (~truth)[..., None])
    return Image.fromarray(bg.astype(np.uint8)), truth & ball


def build(src, out):
    if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(src):
        subprocess.run(["swiftc", "-O", src, "-o", out], check=True)
    return out


def main():
    lift = build(os.path.join(HERE, "lift.swift"), os.path.join(HERE, "lift"))
    liftv = build(os.path.join(HERE, "lift-video.swift"), os.path.join(HERE, "lift-video"))
    fails = []
    with tempfile.TemporaryDirectory() as d:
        im, truth = scene(450, 560)
        im.save(f"{d}/ball.png")
        r = subprocess.run([lift, f"{d}/ball.png", f"{d}/ball-mask.png"], capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"FAIL: lift exited {r.returncode}: {r.stdout}{r.stderr}")
        m = np.asarray(Image.open(f"{d}/ball-mask.png").convert("L").resize((W, H))) > 128
        iou = (m & truth).sum() / max((m | truth).sum(), 1)
        print(f"photo   IoU {iou:.3f} vs the true outline (want >= 0.85)  [{r.stdout.strip()}]")
        if iou < 0.85: fails.append("photo IoU")

        fr = os.path.join(d, "frames"); os.makedirs(fr)
        for i in range(6):
            img, _ = scene(300 + i * 60, 560, ball=(i != 3))           # frame 3 = empty backdrop
            img.save(f"{fr}/f_{i:06d}.png")
        r = subprocess.run([liftv, fr], capture_output=True, text=True)
        masks = sorted(glob.glob(f"{fr}/m_*.png"))
        cover = [float((np.asarray(Image.open(p).convert("L")) > 128).mean()) for p in masks]
        print(f"video   {len(masks)}/6 masks · cover per frame {[round(c, 3) for c in cover]}  [{r.stdout.strip()}]")
        if len(masks) != 6: fails.append("video frame count")
        elif cover[3] > 0.01: fails.append("empty frame not black")
        elif min(cover[:3] + cover[4:]) < 0.05: fails.append("ball missed in a frame")
    print("PASS" if not fails else f"FAIL: {', '.join(fails)}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
