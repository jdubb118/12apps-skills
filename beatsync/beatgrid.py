#!/usr/bin/env python3
"""beatgrid.py: measure a song's beat grid so motion graphics can be timed to it.

  python3 beatgrid.py <audio file | URL> [-o music/]
        [--start 0|drop|<seconds>] [--window A B] [--downbeat-phase N] [--click]

Writes, into -o (default: the audio file's folder, or ./music for a URL):
  beats.json   every detected beat time + the downbeat phase
  grid.json    {"bpm", "beat", "beat0", "downbeat_phase", "first_downbeat", "drops", "song_start",
                "reel": {"phase", "downbeat_mod4", "drop_beats"}, "fit": {...}}
  click-preview.wav (with --click)  the song from song_start with a click on every grid beat
               (high = downbeat, low = other beats). Audition the grid BY EAR before you build.
It also prints a bar-by-bar energy map, so the song's structure (intro, drop, breakdown) is visible.

Method (in production it put every cut of a 26 s reel within 0-47 ms of the song's beats):
- librosa beat_track gives the beat TIMES. A least-squares line through (beat index, time) over the
  window you'll use gives the tempo. Never use librosa's tempo NUMBER: its autocorrelation lags are
  quantized (it said 136.0 for a 137.94 BPM song, which drifts 0.4 s over a 26 s reel).
- OFF-BEAT LOCK: the tracker can lock onto loud off-beat hats and stay half a beat out all song. The
  low-end onsets (the kick) are compared on the beats vs the half-beats: >= 2x moves the beats
  automatically, 1.3-2x prints UNSURE (an off-beat bassline looks the same): audition with --click,
  then --offbeat-fix or leave it.
- Drops = beats where the next 4 beats' sub-bass (30-120 Hz) is >= 1.8x the previous 4 (intro -> drop,
  silent bar -> drop). Bars are anchored so the first drop is a ONE; the kick-energy phase is only the
  fallback. Override with --downbeat-phase when your ear (--click) disagrees.
- song_start = where the song is at reel t=0. Default 0 (the song starts at its start, which is what
  a phone app does when you add it to a reel). `--start drop` = one bar before the first drop.
- The "reel" block converts the grid to REEL time: beat n sits at t = phase + n * beat. Write the
  timeline with that helper, e.g. `const b = n => PHASE + n * BEAT`.
- ATTACK alignment: librosa puts a beat at its onset-envelope PEAK, which can sit tens of ms
  AFTER the audible attack (+51 ms on every beat of one dub track). Cuts timed to that land ~1.5 frames
  late, and the per-beat energy windows swallow the NEXT beat's transient, so a drop and the bar lines read
  ONE BEAT EARLY. So the beats are shifted onto the measured attacks before anything else; beats.json holds
  the shifted times (beatcheck's ground truth) and the raw ones as beats_raw. --no-attack turns it off.
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np
import librosa
import soundfile as sf

SR = 22050


def fetch(url, out):
    os.makedirs(out, exist_ok=True)
    cmd = ["yt-dlp", "--no-update", "-q", "--no-warnings", "-x", "--audio-format", "wav",
           "-o", os.path.join(out, "song.%(ext)s"), "--write-info-json", url]
    subprocess.run(cmd, check=True, timeout=300)
    info = json.load(open(os.path.join(out, "song.info.json")))
    print(f"fetched: {info.get('title')} | {info.get('channel') or info.get('uploader')} | {info.get('duration')} s")
    return os.path.join(out, "song.wav")


def band_env(y, lo, hi, hop=256):
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop))
    f = librosa.fft_frequencies(sr=SR, n_fft=2048)
    return S[(f > lo) & (f < hi)].sum(axis=0), librosa.frames_to_time(np.arange(S.shape[1]), sr=SR, hop_length=hop)


def attack_offset(y, beats, lo=-0.11, hi=0.06, min_db=3.0):
    """Median offset from each detected beat to the strongest broadband attack in [lo, hi] s around it
    (positive log-spectral flux). Returns (offset s or None, beats with an attack, IQR s). None = no
    consistent attack (soft/ambient material): the beats are left alone."""
    # A SHORT window: a centred STFT frame "hears" an attack as soon as the attack enters it, so log-energy
    # flux peaks about n_fft/2 BEFORE the sound. n_fft 1024 put every beat 20-23 ms early (measured on a
    # synthetic track with a known grid, selftest.py); 256 samples = 11.6 ms, so the lead is a few ms.
    S = np.abs(librosa.stft(y, n_fft=256, hop_length=32))
    full = 20 * np.log10(S.sum(axis=0) + 1e-9)
    on = np.maximum(0.0, np.diff(full, prepend=full[0]))
    tt = librosa.frames_to_time(np.arange(len(on)), sr=SR, hop_length=32)
    offs = []
    for t in beats:
        i0, i1 = np.searchsorted(tt, t + lo), np.searchsorted(tt, t + hi)
        if i1 - i0 < 3:
            continue
        k = i0 + int(np.argmax(on[i0:i1]))
        if on[k] >= min_db:
            offs.append(tt[k] - t)
    if len(offs) < max(16, 0.15 * len(beats)):          # half-time songs: only kick/snare beats have a sharp attack
        return None, len(offs), None
    offs = np.array(offs); iqr = float(np.percentile(offs, 75) - np.percentile(offs, 25))
    return (float(np.median(offs)) if iqr <= 0.02 else None), len(offs), iqr


def offbeat_lock(y, beats, ratio_min=2.0):
    """librosa's tracker can lock onto the OFF-beats (loud open hats between the kicks) and hold that phase
    through the whole song, so every beat, downbeat and drop comes out half a beat late. Test it on the
    LOW end, where the kick lives: kick onsets near the beats vs near the half-beats. Returns (shift s, ratio)."""
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=128))
    f = librosa.fft_frequencies(sr=SR, n_fft=2048)
    low = 20 * np.log10(S[(f > 30) & (f < 150)].sum(axis=0) + 1e-9)
    flux = np.maximum(0.0, np.diff(low, prepend=low[0]))
    tt = librosa.frames_to_time(np.arange(len(flux)), sr=SR, hop_length=128)
    p = float(np.median(np.diff(beats)))

    def strength(ts, w=0.04):
        v = []
        for t in ts:
            i0, i1 = np.searchsorted(tt, t - w), np.searchsorted(tt, t + w)
            if i1 > i0:
                v.append(flux[i0:i1].max())
        return float(np.mean(v)) if v else 0.0
    on, off = strength(beats), strength(beats + p / 2)
    ratio = off / max(on, 1e-9)
    return (p / 2 if ratio >= ratio_min else 0.0), ratio


def fit_grid(beats, window):
    """Least-squares tempo over the window. Beats are indexed by STEPS of the tracker's AVERAGE spacing
    (1 = next beat, 2 = a missed beat, 0 = a double detection, dropped). Never index against the MEDIAN
    gap: the tracker spaces beats at its own quantized tempo guess and catches up with short gaps, so
    the median is biased toward the wrong tempo (one track: median said 136.3, truth 137.94)."""
    w = beats[(beats >= window[0]) & (beats <= window[1])]
    if len(w) < 8:
        sys.exit(f"only {len(w)} beats in the fit window {window}; widen --window")
    p = (w[-1] - w[0]) / (len(w) - 1)
    for _ in range(3):
        steps = np.round(np.diff(w) / p)
        w = w[np.concatenate([[True], steps > 0])]
        steps = steps[steps > 0]
        k = np.concatenate([[0.0], np.cumsum(steps)])
        p, off = np.polyfit(k, w, 1)
    res = w - (p * k + off)
    return float(p), float(off), res, len(w)


def find_drops(grid, sub, ts, p):
    """Beat-level (no bar phase needed): sub-bass per beat, then the ratio of the next 4 beats to the
    previous 4. A drop = ratio >= 1.8 AND the next 4 beats at >= half the song's loudest 4-beat run."""
    # each beat's energy stops 60 ms short of the next beat: band_env's centred 2048-sample frames (93 ms)
    # hear the NEXT beat's kick early, so with a silent bar before it the drop read one beat early
    e1 = max(p - 0.06, p / 2)
    E = np.array([sub[(ts >= t) & (ts < t + e1)].mean() if ((ts >= t) & (ts < t + e1)).any() else 0.0 for t in grid])
    nxt = np.array([E[i:i + 4].mean() for i in range(len(E))])
    prv = np.array([E[max(0, i - 4):i].mean() if i >= 4 else np.inf for i in range(len(E))])
    top = nxt.max() or 1.0
    score = np.where(nxt >= 0.5 * top, nxt / np.maximum(prv, 1e-9), 0.0)
    drops = []
    for i in np.argsort(-score):
        if score[i] < 1.8:
            break
        # the 4-beat window flags the region; the HIT is the sharpest single-beat rise within +-2 beats
        # (without this, a bassy pickup beat before the drop wins and the drop reads one beat early)
        js = [j for j in range(max(1, i - 2), min(len(E), i + 3))]
        floor = 0.02 * (E.max() or 1.0)       # silence before a drop is ~0: never divide by it
        j = max(js, key=lambda j: E[j] / max(E[j - 1], floor))
        if all(abs(j - d) >= 8 for d in drops):
            drops.append(int(j))
    return sorted(drops), score


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help="audio file (wav/mp3/m4a) or a URL yt-dlp can fetch")
    ap.add_argument("-o", "--out", help="output folder")
    ap.add_argument("--start", default="0", help="0 (default) | drop | <seconds>: song position at reel t=0")
    ap.add_argument("--window", nargs=2, type=float, metavar=("A", "B"),
                    help="seconds of the song to fit the tempo over (default: song_start .. +60 s, whole song if unknown)")
    ap.add_argument("--downbeat-phase", type=int, choices=range(4), help="override the detected downbeat phase")
    ap.add_argument("--click", action="store_true", help="also write click-preview.wav (60 s from song_start)")
    ap.add_argument("--no-attack", action="store_true", help="keep librosa's beat times (no attack alignment)")
    ap.add_argument("--offbeat-fix", action="store_true",
                    help="move the beats half a beat (after --click told you the tracker sits on the off-beats)")
    ap.add_argument("--no-offbeat-fix", action="store_true", help="never move the beats by half a beat (see offbeat_lock)")
    ap.add_argument("--allow-loose", action="store_true",
                    help="write a grid even when the median fit error is over 20 ms (noise, a beatless intro, a drifting live take)")
    a = ap.parse_args()

    if a.src.startswith(("http://", "https://")):
        out = a.out or "music"
        path = fetch(a.src, out)
    else:
        path = a.src
        out = a.out or os.path.dirname(os.path.abspath(path))
    os.makedirs(out, exist_ok=True)

    y, _ = librosa.load(path, sr=SR, mono=True)
    dur = len(y) / SR
    tempo_est, beats = librosa.beat.beat_track(y=y, sr=SR, units="time", tightness=100)
    tempo_est = float(np.atleast_1d(tempo_est)[0])
    beats = np.asarray(beats, float)
    if len(beats) < 16:
        sys.exit(f"only {len(beats)} beats detected in {dur:.1f} s. Is this the right file?")

    # 0) a tracker locked on the off-beats is half a beat out everywhere: fix that first, then shift the beats
    #    onto the audible attacks (see ATTACK alignment above), BEFORE fits, drops and bars
    beats_raw = beats.copy()
    ob_shift, ob_ratio = (0.0, None) if a.no_offbeat_fix else offbeat_lock(y, beats, 0.0 if a.offbeat_fix else 2.0)
    if ob_shift:
        beats = beats + ob_shift
        beats = beats[beats < dur]
    att, att_n, att_iqr = (None, 0, None) if a.no_attack else attack_offset(y, beats)
    att_applied = att is not None and abs(att) >= 0.012
    if att_applied:
        beats = beats + att

    # 1) a whole-song fit first (to locate bars and drops), then the window fit (the one you time to)
    p_all, off_all, res_all, n_all = fit_grid(beats, (0, dur))
    grid_all = off_all + p_all * np.arange(-int(off_all / p_all), int((dur - off_all) / p_all) + 1)
    grid_all = grid_all[(grid_all >= 0) & (grid_all < dur)]

    # 2) drops, beat by beat, then the downbeat phase. A drop lands on a ONE: anchor the bars on the first
    #    drop. The kick-energy phase is only the fallback (a gospel/hip-hop groove kicks on most beats,
    #    so it's near a coin flip there: one gospel track scored 0.99 vs 1.00).
    sub, ts = band_env(y, 30, 120)
    drop_idx, drop_score = find_drops(grid_all, sub, ts, p_all)
    low, tl = band_env(y, 30, 150)

    def energy_at(t, w=0.06):
        m = (tl >= t - w) & (tl <= t + w)
        return float(low[m].max()) if m.any() else 0.0

    kick = np.array([energy_at(t) for t in grid_all])
    phase_scores = [float(kick[ph::4].mean()) for ph in range(4)]
    kick_ph = int(np.argmax(phase_scores))
    if a.downbeat_phase is not None:
        ph, ph_src = a.downbeat_phase, "override"
    elif drop_idx:
        ph, ph_src = drop_idx[0] % 4, "first drop"
    else:
        ph, ph_src = kick_ph, "kick energy (no drop found: CHECK BY EAR with --click)"
    downbeats = grid_all[ph::4]
    drops = [float(grid_all[i]) for i in drop_idx]

    # bar map (RMS + sub-bass per bar)
    rms = librosa.feature.rms(y=y, hop_length=256)[0]
    tr = librosa.frames_to_time(np.arange(len(rms)), sr=SR, hop_length=256)
    bars = []
    for i in range(len(downbeats) - 1):
        m = (ts >= downbeats[i]) & (ts < downbeats[i + 1])
        mr = (tr >= downbeats[i]) & (tr < downbeats[i + 1])
        bars.append((float(downbeats[i]), float(sub[m].mean()) if m.any() else 0.0, float(rms[mr].mean()) if mr.any() else 0.0))
    Lmax = max(b[1] for b in bars) or 1.0
    Rmax = max(b[2] for b in bars) or 1.0

    # song_start
    if a.start == "drop":
        if not drops:
            sys.exit("--start drop: no drop found; pass --start <seconds>")
        song_start = drops[0] - 4 * p_all
    else:
        song_start = float(a.start)

    # the fit you time to: the window the reel will actually play
    window = tuple(a.window) if a.window else (max(0.0, song_start - 2), min(dur, song_start + 60))
    p, off, res, n = fit_grid(beats, window)
    seg = []
    for s0 in np.arange(0, dur, 30):
        if ((beats >= s0) & (beats < s0 + 30)).sum() > 8:
            seg.append((int(s0), round(60 / fit_grid(beats, (s0, s0 + 30))[0], 2)))

    # re-anchor the downbeats and drops on the window grid (same bars, sharper times)
    k0 = np.round((downbeats[0] - off) / p)
    first_downbeat = float(off + p * k0)
    while first_downbeat - 4 * p >= 0:
        first_downbeat -= 4 * p
    drops = [round(float(off + p * np.round((d - off) / p)), 3) for d in drops]

    # reel view: beat n at t = phase + n*beat (phase = first grid beat at/after song_start, in reel time)
    phase = (off - song_start + p / 2) % p - p / 2      # centred: a start ON the grid reads ~0, never ~1 beat
    first_reel_beat_song_t = song_start + phase
    db_mod = int(np.round((first_downbeat - first_reel_beat_song_t) / p)) % 4
    drop_beats = [int(np.round((d - first_reel_beat_song_t) / p)) for d in drops if d >= song_start]

    print(f"\n{os.path.basename(path)}: {dur:.1f} s | {len(beats)} beats detected | librosa tempo estimate {tempo_est:.2f} (don't use it)")
    print(f"fit over {window[0]:.1f}-{window[1]:.1f} s: {60 / p:.3f} BPM (beat {p:.5f} s), grid anchor {off:.3f} s, "
          f"{n} beats, residual median {np.median(np.abs(res)) * 1000:.1f} ms, rms {np.sqrt((res ** 2).mean()) * 1000:.1f} ms, max {np.abs(res).max() * 1000:.0f} ms")
    if ob_ratio is not None:
        verdict = (" -> beats moved half a beat (--offbeat-fix)" if ob_shift and a.offbeat_fix
                   else " -> the tracker had locked on the OFF-beats: beats moved half a beat (--no-offbeat-fix to undo)" if ob_shift
                   else " -> UNSURE: an off-beat bassline or a half-beat lock. Audition with --click" if ob_ratio >= 1.3
                   else " -> phase OK")
        print(f"off-beat lock check: low-end onsets {ob_ratio:.2f}x stronger on the half-beats than on the beats{verdict}")
    if a.no_attack:
        print("attack alignment: off (--no-attack)")
    elif att is None:
        print(f"attack alignment: no consistent attack ({att_n} of {len(beats)} beats, IQR {att_iqr if att_iqr is None else round(att_iqr * 1000)} ms): beats left as detected. CHECK BY EAR.")
    else:
        print(f"attack alignment: librosa's beats sat {-att * 1000:+.0f} ms from the attacks ({att_n} of {len(beats)} beats, IQR {att_iqr * 1000:.0f} ms)"
              + (" -> beats SHIFTED onto the attacks" if att_applied else " -> under 12 ms, left alone"))
    print("tempo per 30 s:", "  ".join(f"{s}s:{b}" for s, b in seg),
          "(spread > 0.3 BPM = a live/drifting take: fit only the window you use)" if seg and (max(b for _, b in seg) - min(b for _, b in seg)) > 0.3 else "")
    print("kick by beat phase:", [round(x / max(phase_scores), 3) for x in phase_scores], f"(kick says {kick_ph})",
          f"-> downbeat phase {ph} from {ph_src}")
    print(f"first downbeat {first_downbeat:.3f} s | drops (low-end jumps, xN = next-4 vs previous-4 beats): "
          + ("  ".join(f"{d:.2f}s(x{max(drop_score[max(0, i - 2):i + 3]):.1f}{'' if bib == 1 else f', beat {bib}!'})"
                       for d, i, bib in zip(drops, drop_idx, [int(np.round((d - first_downbeat) / p)) % 4 + 1 for d in drops])) or "none found"))
    if any(int(np.round((d - first_downbeat) / p)) % 4 for d in drops[1:]):
        print("  'beat N!' = a drop off the ONE: a pickup, or a shortened bar (stop-time) that SHIFTS the bar lines after it.\n"
              "  Constant 4/4 is assumed; if your reel plays past one of these, re-run with --window starting after it.")
    print(f"\nbar | start  | energy (# = RMS, | = sub-bass)  {'<- DROP' if drops else ''}")
    for i, (t, L, R) in enumerate(bars):
        mark = "  <- DROP" if any(abs(t - d) < p for d in drops) else ""
        print(f"{i:3d} | {t:6.2f} | {'#' * int(30 * R / Rmax):<30} {'|' * int(20 * L / Lmax):<20}{mark}")
    print(f"\nREEL (song_start {song_start:.3f} s): beat n at t = {phase:.4f} + n * {p:.5f}; downbeats at n % 4 == {db_mod}; "
          f"drops at reel beats {drop_beats}" + (f" (first at t = {phase + drop_beats[0] * p:.3f} s)" if drop_beats else ""))

    med_ms = float(np.median(np.abs(res)) * 1000)       # median, not rms: a few mis-detected beats inflate rms
    if med_ms > 20 and not a.allow_loose:
        sys.exit(f"\nREFUSED: the grid misses the detected beats by {med_ms:.0f} ms (median; real songs sit at 5-16 ms, noise at 26+). "
                 "There is no steady beat in this window: noise, a beatless intro, or a live take. "
                 "Pick another --window, or pass --allow-loose if you know better. Nothing written.")
    json.dump({"beats": [float(b) for b in beats], "beats_raw": [float(b) for b in beats_raw], "attack_shift_ms": round(att * 1000, 1) if att_applied else 0.0,
               "downbeat_phase": ph, "downbeats": [float(d) for d in downbeats]},
              open(os.path.join(out, "beats.json"), "w"))
    grid = {"source": a.src, "duration": round(dur, 3), "bpm": round(60 / p, 4), "beat": round(p, 6), "beat0": round(off, 4),
            "downbeat_phase": ph, "first_downbeat": round(first_downbeat, 4), "drops": drops, "song_start": round(song_start, 4),
            "reel": {"phase": round(phase, 4), "downbeat_mod4": db_mod, "drop_beats": drop_beats},
            "fit": {"window": [round(window[0], 2), round(window[1], 2)], "n_beats": n,
                    "residual_median_ms": round(float(np.median(np.abs(res)) * 1000), 1),
                    "residual_rms_ms": round(float(np.sqrt((res ** 2).mean()) * 1000), 1),
                    "residual_max_ms": round(float(np.abs(res).max() * 1000), 1), "librosa_tempo_estimate": round(tempo_est, 2)},
            "attack": {"shift_ms": round(att * 1000, 1) if att_applied else 0.0, "measured_ms": None if att is None else round(att * 1000, 1),
                       "beats_with_attack": att_n, "iqr_ms": None if att_iqr is None else round(att_iqr * 1000, 1)}}
    json.dump(grid, open(os.path.join(out, "grid.json"), "w"), indent=1)
    print(f"wrote {out}/beats.json + grid.json")

    if a.click:
        y2, sr2 = librosa.load(path, sr=44100, mono=True, offset=song_start, duration=60.0)
        t = np.arange(int(0.03 * sr2)) / sr2

        def blip(freq):
            return np.sin(2 * np.pi * freq * t) * np.exp(-t / 0.008)
        out_y = y2 * 0.7
        for n_ in range(int((len(y2) / sr2 - phase) / p) + 1):
            s = int((phase + n_ * p) * sr2)
            c = blip(2400 if n_ % 4 == db_mod else 1300) * (0.45 if n_ % 4 == db_mod else 0.3)
            if s < 0:                      # a grid phase a few ms before t=0: clip the click, don't wrap the slice
                c, s = c[-s:], 0
            e = min(len(out_y), s + len(c))
            out_y[s:e] += c[: e - s]
        sf.write(os.path.join(out, "click-preview.wav"), np.clip(out_y, -1, 1), sr2)
        print(f"wrote {out}/click-preview.wav (listen: the high click must sit on the ONE of every bar)")


if __name__ == "__main__":
    main()
