---
name: beatsync
description: Measure a song's beat grid (tempo, downbeats, drops) so video edits and motion graphics can be cut ON the beat, then prove a finished render actually lands its cuts on the beat. Use when timing a reel, edit, slideshow or animation to music, when asked "what BPM is this", "where's the drop", "cut this to the beat", or to check whether an edit is on beat.
---

# beatsync: cut on the beat, then prove it

Two tools:

| | |
|---|---|
| `beatgrid.py <song> [-o music/]` | measures the grid: tempo to 0.01 BPM, the first downbeat, the drops, a bar-by-bar energy map. Writes `grid.json` + `beats.json`. |
| `beatcheck.py <render.mp4> --grid music/grid.json [--cuts 4,8,12]` | finds the hard cuts in a finished video and reports each one's offset to the nearest beat. Exits 1 if a planned cut is more than 50 ms off. |

`selftest.py` proves the measurement on synthetic tracks with a known grid. Run it once after install.

## Install
```bash
pip install -r requirements.txt      # librosa, numpy, scipy, soundfile
python3 selftest.py                  # PASS = tempo, downbeat and drop all within 15 ms of the truth
```
`ffmpeg` must be on PATH for beatcheck. `yt-dlp` is optional (beatgrid can fetch a URL you have the rights to).

## Workflow
1. **Measure.** `python3 beatgrid.py song.wav -o music --click`
   Read the printout: tempo, attack alignment, the off-beat check, the drops and the bar map.
2. **Listen.** Play `music/click-preview.wav`. The high click must land on the ONE of every bar.
   If it lands between the kicks, re-run with `--offbeat-fix`. If it lands on beat 2, use `--downbeat-phase`.
3. **Pick the section.** `--start drop` begins one bar before the first drop. `--start 34.2` begins at a
   chosen point in the song. The `reel` block in grid.json converts to video time.
4. **Write the edit in beats, not seconds:** `const b = n => PHASE + n * BEAT` (both from `grid.json → reel`).
   Hard cuts on whole beats, fast flurries on 8ths or 16ths, the big moment on a drop beat.
5. **Prove it.** `python3 beatcheck.py render.mp4 --grid music/grid.json --cuts 0,4,8,16`
   Every planned cut should land within 50 ms (1.5 frames at 30 fps) of a detected beat.

## What it gets right that a plain beat tracker doesn't
- **Tempo from a fit, not from the tracker's number.** librosa's tempo estimate is quantized (136.0 for a
  137.94 BPM song, 0.4 s of drift over 26 s). beatgrid fits a line through the detected beats instead.
- **Beats on the ATTACK.** Trackers put a beat at the peak of the onset curve, often 30-50 ms after you
  hear it. beatgrid shifts every beat onto the measured attack, using a short window so the correction
  doesn't overshoot.
- **Off-beat lock detection.** Loud open hats between the kicks can make the tracker sit half a beat out for
  the whole song. beatgrid compares the kick onsets on the beats vs the half-beats. At 2x or more it fixes it.
  Between 1.3 and 2x it warns UNSURE, because an off-beat bassline looks the same; listen, then decide.
- **Drops on the right beat.** A drop is a jump in sub-bass. Each beat is measured short of the next one, so
  a silent bar before a drop can't make it read one beat early.
- **It refuses to guess.** If the detected beats sit more than 20 ms (median) off any steady grid (noise, a
  beatless intro, a drifting live take), it writes nothing and says so. `--allow-loose` overrides.
- **beatcheck won't pass on nothing.** It needs at least 3 beats inside the render and a non-empty list of cuts.

## Limits
- Constant 4/4 is assumed. Stop-time bars and tempo changes need a `--window` that avoids them.
- beatcheck finds HARD changes (cuts, flashes, slams). A slow dissolve has no spike; leave it out of `--cuts`.
  A drumless section has no detected beats to compare against.
- With motion blur made by averaging sub-frames, a hard cut exactly ON a beat blends the two shots into
  the beat frame. Put hard cuts a sub-frame early.
