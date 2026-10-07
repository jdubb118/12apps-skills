#!/usr/bin/env python3
"""sfx.py — the house sound palette, synthesized (no samples, no licences), placed on the composition's
own cues (renders/cues.json from cues.py). Engineered, not loud: a watch tick, paper, a zipper, air,
one clean chime. A quiet pad glues it; a sub pulse on 120 BPM carries the middle. With --music, every
effect is NORMALIZED against the track instead (see MUSIC MODE below).

    python3 sfx.py renders/cues.json renders/sfx.wav [--bed 1] [--pulse 5.0:16.3]

Cue kinds: type out tick draw print zip land whoosh card line flick wipe boom chime amb  (+ g gain, pan, d, k)
  amb = a footage clip's own sound: {file, start, d} — mixed under the music at REL["amb"] (clip.py writes <out>.wav)
Add a kind here, not in a piece. Unknown kinds FAIL loudly (a silent cue is a bug you will not hear).
"""
import argparse, json, sys, wave
import numpy as np
from scipy.signal import butter, lfilter

ap = argparse.ArgumentParser(); ap.add_argument("cues"); ap.add_argument("out")
ap.add_argument("--bed", type=float, default=1.0, help="pad level multiplier (0 = off)")
ap.add_argument("--pulse", default="", help="t0:t1 window for the 120-BPM sub pulse (empty = off)")
ap.add_argument("--music", help="a track to mix under: turns the pad/pulse OFF and NORMALIZES every effect against it")
ap.add_argument("--music-start", type=float, default=0.0, help="song time at reel t=0")
ap.add_argument("--fade", default="", help="music fade-out window a:b (reel s)")
ap.add_argument("--report", action="store_true", help="print every effect's level vs the music")
a = ap.parse_args()
dm = json.load(open(a.cues))
SR = 48000; DUR = float(dm["duration"]) + 0.3; N = int(SR * DUR)
L, R = np.zeros(N), np.zeros(N)
rng = np.random.default_rng(1026)


def tt(d): return np.arange(max(1, int(d * SR))) / SR
def noise(n): return rng.normal(0, 1, n)
def filt(kind, fc, x, order=2):
    wn = [f / (SR / 2) for f in fc] if isinstance(fc, (list, tuple)) else fc / (SR / 2)
    b, a_ = butter(order, wn, btype=kind); return lfilter(b, a_, x)
def add(sig, t, g=1.0, pan=0.0):
    i = int(round(t * SR))
    if i >= N: return
    if i < 0: sig, i = sig[-i:], 0
    j = min(N, i + len(sig)); ang = (pan + 1) * np.pi / 4
    L[i:j] += sig[:j - i] * g * np.cos(ang); R[i:j] += sig[:j - i] * g * np.sin(ang)


# ── the palette ───────────────────────────────────────────────────────────────────────────────────
def tick(k=1.0):                       # a watch tick — precision
    t = tt(0.06)
    s = np.sin(2 * np.pi * 2400 * k * t) * np.exp(-t / 0.006) + 0.45 * np.sin(2 * np.pi * 4100 * k * t) * np.exp(-t / 0.004)
    return s + filt("high", 3500, noise(len(t)) * np.exp(-t / 0.0012)) * 0.35
def type_(k=1.0):                      # a line of type landing — soft, low, short (not a slam)
    t = tt(0.22); f = 48 + 70 * np.exp(-t / 0.018)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.07)
    return s + filt("band", (600, 2600), noise(len(t)) * np.exp(-t / 0.006)) * 0.25
def air(d, lo=200, hi=2600, peak=0.55, bright=1.0):
    t = tt(d); u = t / d
    env = np.where(u < peak, (u / peak) ** 2, ((1 - u) / (1 - peak)) ** 1.7); n = noise(len(t))
    return env * ((1 - env) * filt("low", lo * 2, n) * 0.7 + env * filt("band", (lo * 3, hi), n) * bright)
def out_(): return air(0.28, 400, 5000, 0.2, 0.8) * 0.6
def draw(d):                           # a fine pen on paper
    t = tt(d); am = 0.6 + 0.4 * np.abs(filt("low", 18, noise(len(t))) * 6).clip(0, 1)
    return filt("band", (2200, 7000), noise(len(t))) * am * np.sin(np.pi * t / d) ** 0.6 * 0.5
def print_(d):                         # the photo resolving — a scanner sweep
    t = tt(d); u = t / d; out = np.zeros(len(t)); n = noise(len(t))
    for lo, hi in [(700, 1400), (1400, 2800), (2800, 5600)]:
        out += filt("band", (lo, hi), n) * np.exp(-((u - (lo - 700) / 4900 - 0.2) / 0.25) ** 2)
    return out * np.sin(np.pi * u) * 0.5 + 0.12 * np.sin(2 * np.pi * 120 * t) * np.sin(np.pi * u)
def zip_(d):                           # a zipper whose teeth rate follows a moving element's speed
    t = tt(d); u = t / d
    speed = np.where(u < 0.13, 0.25, 6 * ((u - 0.13) / 0.87) * (1 - (u - 0.13) / 0.87)).clip(0.05, None)
    phase = np.cumsum(speed * 180 / SR); teeth = np.diff(np.floor(phase), prepend=0) > 0
    click = np.zeros(len(t)); click[teeth] = 1.0
    k = tt(0.004); ker = np.sin(2 * np.pi * 3200 * k) * np.exp(-k / 0.0009)
    clicks = np.convolve(click, ker)[:len(t)]
    swish = filt("band", (900, 4200), noise(len(t))) * (speed / speed.max()) * 0.35
    return (clicks * 0.6 + swish) * np.minimum(1, (1 - u) * 12)
def land():                            # something lands: a soft deep thud, cloth, one faint ting
    t = tt(0.6); f = 38 + 60 * np.exp(-t / 0.03)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.16)
    s += filt("low", 700, noise(len(t)) * np.exp(-t / 0.035)) * 0.6
    return s + 0.08 * np.sin(2 * np.pi * 2793 * t) * np.exp(-t / 0.25)
def card():                            # a card set down on a table
    t = tt(0.12)
    return filt("low", 2200, noise(len(t)) * np.exp(-t / 0.01)) * 0.8 + np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.03) * 0.5
def line(d):                           # the accent line drawing itself — a hairline "sss" and a rising glint
    t = tt(d); u = t / d
    s = filt("band", (5000, 11000), noise(len(t))) * np.sin(np.pi * u) ** 1.5 * 0.35
    return s + 0.05 * np.sin(2 * np.pi * np.cumsum(1200 + 500 * u) / SR) * np.sin(np.pi * u)
def flick():                           # a configurator step — a shutter
    t = tt(0.07); c = lambda s0: (np.sin(2 * np.pi * 1800 * (t - s0)) * np.exp(-(t - s0).clip(0) / 0.004)) * (t >= s0)
    return c(0) + 0.7 * c(0.028) + filt("high", 2500, noise(len(t)) * np.exp(-t / 0.01)) * 0.3
def wipe(d):                           # the line wipe: cloth falling past + a sub drop at its HIT (the mid-sweep)
    t = tt(d + 0.35); u = (t / d).clip(0, 1)
    sw = filt("band", (300, 3200), noise(len(t))) * np.sin(np.pi * u) ** 2 * (t <= d) * 0.8
    sub = np.zeros(len(t)); i = int(d * 0.5 * SR); k = tt(0.35); f = 36 + 40 * np.exp(-k / 0.04)
    sub[i:i + len(k)] = (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-k / 0.12))[:len(sub) - i]
    return sw + sub * 0.7
def boom():
    t = tt(0.9); f = 32 + 55 * np.exp(-t / 0.05)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.3) + filt("low", 900, noise(len(t)) * np.exp(-t / 0.04)) * 0.3
def chime():                           # the signature: one clean, expensive tone
    t = tt(2.4)
    s = np.sin(2 * np.pi * 1318.5 * t) + 0.5 * np.sin(2 * np.pi * 1975.5 * t) * np.exp(-t / 0.6) + 0.25 * np.sin(2 * np.pi * 659.25 * t)
    return s * np.exp(-t / 0.9) * np.minimum(1, t / 0.003)

def amb(c):                            # a footage clip's own sound (street, keys, a car): ffmpeg → 48k stereo, faded
    import subprocess, io
    f, st, d = c["file"], float(c.get("start", 0)), float(c.get("d", 3.0))
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{st:.3f}", "-t", f"{d:.3f}", "-i", f, "-ar", str(SR), "-ac", "2", "-f", "s16le", "-"], capture_output=True)
    x = np.frombuffer(r.stdout, "<i2").reshape(-1, 2).astype(np.float64) / 32768 if r.stdout else np.zeros((int(d * SR), 2))
    fi, fo = int(0.15 * SR), int(0.35 * SR); n = len(x)
    env = np.ones(n); env[:fi] = np.linspace(0, 1, fi); env[-fo:] = np.linspace(1, 0, fo)
    return (x * env[:, None]).mean(1)      # mono into the panner; stereo width is not worth a frame of phase trouble

BANK = {"amb": amb,
    "tick": lambda c: tick(c.get("k", 1.0)), "type": lambda c: type_(), "out": lambda c: out_(),
    "draw": lambda c: draw(c.get("d", 1.0)), "print": lambda c: print_(c.get("d", 0.7)), "zip": lambda c: zip_(c.get("d", 1.4)),
    "land": lambda c: land(), "whoosh": lambda c: air(c.get("d", 0.6)), "card": lambda c: card(),
    "line": lambda c: line(c.get("d", 0.7)), "flick": lambda c: flick(), "wipe": lambda c: wipe(c.get("d", 0.58)),
    "boom": lambda c: boom(), "chime": lambda c: chime(),
}
GAIN = {"tick": 0.30, "type": 0.55, "out": 0.25, "draw": 0.22, "print": 0.28, "zip": 0.55, "land": 0.9, "whoosh": 0.35,
        "card": 0.45, "line": 0.5, "flick": 0.35, "wipe": 0.6, "boom": 0.55, "chime": 0.32, "amb": 0.25}
unknown = sorted({c["kind"] for c in dm["cues"]} - set(BANK))
if unknown: sys.exit(f"sfx.py: unknown cue kinds {unknown} — add them to BANK")

# ── MUSIC MODE: every effect NORMALIZED to a consistent level for its class, measured against the track.
#    Level = the effect's loudest 100-ms RMS; target is dB relative to the music's body (its loudest 4 s).
#    Accents sit under the music, impacts come through it, and it is the same every time, whatever the synth made.
REL = {"tick": -12, "flick": -12, "card": -11, "type": -9, "out": -14, "draw": -16, "print": -14, "zip": -9,
       "land": -4, "whoosh": -12, "line": -12, "wipe": -7, "boom": -6, "chime": -8, "amb": -15}
def rms_db(x, win=0.1):
    x = np.asarray(x); w = max(1, int(win * SR))
    if len(x) < w: return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)
    c = np.cumsum(np.r_[0, x ** 2]); r = np.sqrt((c[w:] - c[:-w]) / w)
    return 20 * np.log10(r.max() + 1e-9)
music = None
if a.music:
    import wave as _w
    with _w.open(a.music) as w:
        msr = w.getframerate(); mx = np.frombuffer(w.readframes(w.getnframes()), "<i2").reshape(-1, w.getnchannels()).astype(np.float64) / 32768
    if mx.shape[1] == 1: mx = np.repeat(mx, 2, 1)
    if msr != SR:
        from scipy.signal import resample_poly
        mx = resample_poly(mx, SR, msr, axis=0)
    i0 = int(a.music_start * SR); mx = mx[i0:i0 + N]
    music = np.zeros((N, 2)); music[:len(mx)] = mx
    if a.fade:
        f0, f1 = map(float, a.fade.split(":")); t = np.arange(N) / SR
        music *= np.clip((f1 - t) / (f1 - f0), 0, 1)[:, None] ** 1.5
    mono = music.mean(1); w4 = int(4 * SR); c = np.cumsum(np.r_[0, mono ** 2])
    M_BODY = 10 * np.log10(((c[w4:] - c[:-w4]) / w4).max() + 1e-12)          # dBFS RMS of the loudest 4 s
    a.bed, a.pulse = 0, ""                                                     # the track IS the bed
duck = np.ones(N); rows = []
for c in dm["cues"]:
    sig = BANK[c["kind"]](c)
    if music is None:
        add(sig, c["t"], GAIN[c["kind"]] * c.get("g", 1.0), c.get("pan", 0.0)); continue
    target = M_BODY + REL[c["kind"]] + 20 * np.log10(max(0.5, min(1.25, c.get("g", 1.0))))  # g = intent, clamped
    gain = 10 ** ((target - rms_db(sig)) / 20)
    add(sig, c["t"], gain, c.get("pan", 0.0))
    if c["kind"] == "amb": rows.append((c["t"], "amb", target - M_BODY, 0)); continue
    if c["kind"] in ("land", "boom", "wipe", "chime"):                        # impacts: tuck the music under them
        hit = c["t"] + (0.5 * c.get("d", 0.58) if c["kind"] == "wipe" else 0.0)
        tt_ = np.arange(N) / SR - hit
        env = np.where(tt_ < 0, np.exp(tt_ / 0.03), np.exp(-tt_ / 0.28))
        duck = np.minimum(duck, 1 - (1 - 10 ** (-3.5 / 20)) * env)
    i = int(c["t"] * SR); j = min(N, i + int(0.4 * SR))
    rows.append((c["t"], c["kind"], target - M_BODY, rms_db(music[i:j].mean(1)) - M_BODY if j > i else 0))

# ── bed: a quiet A-minor-add9 pad (sines, slow swell) + optional 120-BPM sub pulse ─────────────────
if a.bed > 0:
    t = np.arange(N) / SR
    pad = sum(amp * np.sin(2 * np.pi * f * t + ph) for f, amp, ph in
              [(110, .5, 0), (164.81, .35, 1), (246.94, .25, 2), (261.63, .18, 3), (392.0, .10, 4)])
    pad *= 0.75 + 0.25 * np.sin(2 * np.pi * 0.11 * t)
    env = np.minimum(1, t / 1.2) * np.minimum(1, (DUR - t) / 1.5).clip(0)
    add(filt("low", 1200, pad) * env, 0, 0.045 * a.bed, 0)
if a.pulse:
    t0, t1 = map(float, a.pulse.split(":")); bt = t0
    while bt < t1:
        k = tt(0.16); f = 42 + 30 * np.exp(-k / 0.02)
        add(np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-k / 0.06), bt, 0.16, 0); bt += 0.5

mix = np.stack([L, R], 1)
if music is not None:
    stem = mix.copy()
    mix = music * duck[:, None] + mix
    if a.report:
        print(f"music body {M_BODY:.1f} dBFS RMS · effect levels vs body (target) and the music under each:")
        for t_, k, rel, loc in rows: print(f"  {t_:6.2f}s {k:7s} {rel:+5.1f} dB   music there {loc:+5.1f} dB")
    with wave.open(a.out.replace(".wav", "-stem.wav"), "wb") as w:                  # effects only, same gains
        pk = np.max(np.abs(stem)) or 1; w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((stem / pk * 10 ** (-1 / 20) * 32767).astype("<i2").tobytes())
mix = np.tanh(mix * 1.3) / np.tanh(1.3)
fade = np.ones(N); fade[-int(0.3 * SR):] = np.linspace(1, 0, int(0.3 * SR)); mix *= fade[:, None]
peak = np.max(np.abs(mix)); mix *= 10 ** (-1 / 20) / (peak or 1)
with wave.open(a.out, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((mix * 32767).astype("<i2").tobytes())
kinds = {}
for c in dm["cues"]: kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
print(f"wrote {a.out}: {DUR:.1f}s · {len(dm['cues'])} cues {kinds}")
