---
name: motion-kit
description: Make 9:16 motion graphics videos (Instagram Reels, TikTok, Stories, Shorts) from HTML + GSAP, rendered frame-exact with HyperFrames, timed to the beat of a song, with real motion blur, synthesized sound effects, type placed BEHIND a person or product, and an automated QA gate (safe areas, loudness, banned copy, frozen frames). Use for "make a motion graphics reel", "animate this announcement", "kinetic typography video", "product promo video", "time the cuts to this song", or any short-form branded video built from text, photos and footage.
---

# motion-kit: beat-synced motion graphics from HTML

Write the video as a web page (HTML + CSS + one GSAP timeline). The kit renders it frame by frame with
[HyperFrames](https://github.com/heygen-com/hyperframes), adds motion blur, builds the sound from the
timeline itself, mixes it under your music, and refuses to ship a render that breaks the rules.

| Piece | What it does |
|---|---|
| `kit/mk.js` | Helpers for deterministic timelines: stacked headlines that rise out of masks, labels, stroke drawing, a line wipe, film grain, procedural "drivers", sound cues, `MK.hard()` for cuts that must land on a beat |
| `kit/mk.css`, `brand.json` | Your tokens (colours, type), safe area, loudness target and copy rules. Placeholder values out of the box |
| `scripts/render.sh` | lint → cues → sound → render (draft 30 fps, or final 240 fps blended to a 180° shutter at 30 fps) → loudness → QA → beat check |
| `scripts/cues.py` | Loads the composition headless and dumps every sound cue and every visible string with its box |
| `scripts/sfx.py` | Synthesizes the sound design from those cues (ticks, whooshes, wipes, impacts, a chime): no samples, nothing to license. With music, every effect is normalized against the track and the music ducks under impacts |
| `scripts/qa.py` | The gate: copy rules, ™ marks, approved-copy check, safe area every 0.25 s, size, fps, duration, LUFS, true peak, blank or frozen runs, accent coverage. Writes a contact sheet |
| `scripts/wordfit.py` | Where a giant word can sit behind a subject and still read (scores each letter; E, L and Z by full height) |
| `scripts/clip.py`, `readmask.py`, `sync-footage.py` | Footage scenes: a background clip + a transparent subject clip cut from the same frames, so type can sit behind a moving person |
| `templates/piece/` | A piece that renders and passes QA as-is: headline → wipe → end card |

Works with the sibling skills: **beatsync** (the beat grid + the on-beat proof) and **vision-lift** (subject masks).

## Install
```bash
pip install -r requirements.txt && python -m playwright install chromium
npm install                       # gsap (render.sh also does this on first run)
# Node 18+, ffmpeg (with libvpx-vp9 for footage scenes). Subject masks need macOS 14+ (vision-lift).
```

## Make a piece
1. `scripts/new.sh pieces/launch` — scaffolds a piece with its own `brand.json`.
2. **Brief first** (`BRIEF.md`): the one idea in a sentence, 3-4 acts, a beat table (beat · visual · words · sound).
   Method: `references/NARRATIVE-TO-BEATS.md`.
3. **Copy** (`COPY.md`): every string the video will show, approved in advance. QA warns on anything else.
4. **Music** (optional): `python ../beatsync/beatgrid.py song.wav -o music --click`, listen to the click track,
   then write the timeline in beats: `const b = n => PHASE + n * BEAT`.
5. **Assets**: `../vision-lift/subject.py photo.jpg --out assets/hero`, then `scripts/wordfit.py assets/hero-subject.png "WORD."`.
   Put every command in `prep.sh` so the piece rebuilds from source.
6. **Build** `index.html` with the kit. Declare every sound where it happens: `MK.cue(t, "wipe", {d})`.
7. `scripts/render.sh pieces/launch draft` (~1 min). Read `renders/<slug>-sheet.jpg` every time.
8. `scripts/render.sh pieces/launch final` (~2.5 min per 20 s). A QA FAIL means don't publish. Then check
   full-resolution frames at the fast moments, where blur and occlusion problems show.

## Rules the gate enforces (edit them in brand.json)
Text stays inside the platform-safe area (y 250-1580 at 1080×1920) · loudness −14 LUFS, true peak ≤ −1 dBFS ·
no exclamation points or discount language by default · trademarks carry ™ · one accent colour, used sparingly ·
the end card holds at least a second, so the reel loops cleanly · with music, every planned hard cut lands within 50 ms of a beat.

## Read before editing a composition
`references/BUILD-NOTES.md`: the traps that make a frame-by-frame renderer go wrong (seek-safe timelines,
hidden initial states, masks, motion blur, footage alpha, audio).
