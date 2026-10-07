#!/usr/bin/env python3
"""selftest.py: prove beatgrid.py measures a song correctly before you trust it with a real one.

Synthesizes a track with a KNOWN grid (124 BPM, a first beat 0.37 s in, 4 quiet bars, then a drop),
runs beatgrid.py on it, and checks the answer against the truth:
  tempo within 0.05 BPM · first downbeat within 15 ms · the drop found on the right beat.
A second track is built to make the beat tracker lock onto the OFF-beats (loud full-range hats between
the kicks): beatgrid must flag it, and --offbeat-fix must land it on the truth.
Then it breaks the input on purpose (pure noise) and checks that beatgrid REFUSES it.

    python3 selftest.py            # exit 0 = pass
"""
import json, os, subprocess, sys, tempfile
import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 44100
BPM, T0, BARS_INTRO, BARS = 124.0, 0.37, 4, 16


def tone(f, d, decay):
    t = np.arange(int(d * SR)) / SR
    return np.sin(2 * np.pi * f * t) * np.exp(-t / decay)


def kick():
    t = np.arange(int(0.35 * SR)) / SR
    f = 45 + 90 * np.exp(-t / 0.03)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.12)


def hat(rng, broadband=False):
    """high-passed noise, like a real mix's hats. broadband=True = a loud full-range off-beat hit, the
    thing that makes librosa lock onto the OFF-beats (the adversarial case for the off-beat fix)."""
    from scipy.signal import butter, lfilter
    n = int(0.05 * SR)
    x = np.random.default_rng(int(rng.integers(1 << 30))).normal(0, 1, n)
    if not broadband:
        b, a_ = butter(4, 6000 / (SR / 2), "high"); x = lfilter(b, a_, x)
    return x * np.exp(-np.arange(n) / SR / 0.008) * (0.25 if broadband else 0.5)


def make_track(path, adversarial=False):
    rng = np.random.default_rng(7)
    beat = 60 / BPM
    n_beats = BARS * 4
    y = np.zeros(int((T0 + n_beats * beat + 1.0) * SR))

    def put(sig, t, g):
        i = int(round(t * SR)); j = min(len(y), i + len(sig)); y[i:j] += sig[: j - i] * g

    for b in range(n_beats):
        t = T0 + b * beat
        drop = b >= BARS_INTRO * 4
        put(hat(rng, adversarial), t + beat / 2, 0.6)          # off-beat hats all the way through
        put(tone(880 if b % 4 == 0 else 660, 0.12, 0.03), t, 0.25)   # a pluck that marks the ONE
        if drop:
            put(kick(), t, 1.4 if adversarial else 1.0)       # the drop: kick + sub on every beat
            put(tone(55, beat * 0.9, 0.25), t, 0.6)
    y /= np.max(np.abs(y)) * 1.12
    sf.write(path, y, SR)
    first_drop = T0 + BARS_INTRO * 4 * beat
    return {"bpm": BPM, "first_downbeat": T0, "drop": first_drop}


def run(args):
    return subprocess.run([sys.executable, os.path.join(HERE, "beatgrid.py")] + args, capture_output=True, text=True)


def check(d, name, adversarial, fails):
    truth = make_track(os.path.join(d, f"{name}.wav"), adversarial)
    if adversarial:
        # the tool must not pass a half-beat lock off as fine: it has to say UNSURE (or fix it itself) ...
        r0 = run([os.path.join(d, f"{name}.wav"), "-o", d])
        warned = "UNSURE" in r0.stdout or "beats moved half a beat" in r0.stdout
        print(f"[{name}] without the flag: {'warned' if warned else 'SILENT (passed a half-beat lock as fine)'}")
        if not warned: fails.append(f"{name} silent")
    # ... and after you have listened, --offbeat-fix must land the grid on the truth
    r = run([os.path.join(d, f"{name}.wav"), "-o", d] + (["--offbeat-fix"] if adversarial else []))
    if r.returncode:
        sys.exit(f"FAIL: beatgrid exited {r.returncode} on {name}\n{r.stderr[-800:]}")
    g = json.load(open(os.path.join(d, "grid.json")))
    bpm_err = abs(g["bpm"] - truth["bpm"])
    db_err = abs(g["first_downbeat"] - truth["first_downbeat"]) * 1000
    drop_err = min((abs(x - truth["drop"]) for x in g["drops"]), default=99) * 1000
    fixed = "beats moved half a beat" in r.stdout          # clean: must stay False; adversarial: forced True
    print(f"[{name}]")
    print(f"  tempo      {g['bpm']:.3f} BPM   (truth {truth['bpm']}, err {bpm_err:.3f})")
    print(f"  downbeat   {g['first_downbeat']:.3f} s   (truth {truth['first_downbeat']}, err {db_err:.1f} ms)")
    print(f"  drops      {g['drops']}   (truth {truth['drop']:.3f}, err {drop_err:.0f} ms)")
    print(f"  off-beat fix fired: {fixed}")
    if bpm_err > 0.05: fails.append(f"{name} tempo")
    if db_err > 15: fails.append(f"{name} downbeat")
    if drop_err > 15: fails.append(f"{name} drop")
    if fixed != adversarial: fails.append(f"{name} off-beat fix {'did not apply' if adversarial else 'fired on a clean track'}")


def main():
    fails = []
    with tempfile.TemporaryDirectory() as d:
        check(d, "clean", False, fails)
        check(d, "offbeat-lock", True, fails)       # loud full-range off-beat hats: the tracker locks on them

        # the negative control: noise has no beat, and beatgrid must not invent one
        rng = np.random.default_rng(1)
        sf.write(os.path.join(d, "noise.wav"), rng.normal(0, 0.1, SR * 20), SR)
        r2 = run([os.path.join(d, "noise.wav"), "-o", d])
        refused = r2.returncode != 0 and "REFUSED" in (r2.stderr + r2.stdout)
        print(f"noise      {'refused' if refused else 'ACCEPTED (it invented a grid)'}")
        if not refused:
            fails.append("noise control")
    print("PASS" if not fails else f"FAIL: {', '.join(fails)}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
