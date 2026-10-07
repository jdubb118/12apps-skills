# BUILD NOTES — the traps of a frame-by-frame renderer

## HyperFrames determinism (it renders by SEEKING every frame, in parallel workers)
- ONE `gsap.timeline({paused:true})`, registered **literally in the composition**:
  `window.__timelines = window.__timelines || {}; window.__timelines["main"] = tl;` (the lint is static and
  can't see a registration inside a helper). Then `MK.finish(tl, debug)`.
- **Initial hidden states: `MK.hide(tl, el, vars)`** (= `gsap.set` now + `tl.set` at 0). A zero-duration
  `tl.set` at 0 does NOT render while the playhead sits at 0, so frame 0 shows the un-hidden state.
  A `fromTo(..., {immediateRender:false})` without a hide leaves the element visible until its start.
- **No `onUpdate`, no `tl.call`**: seeks can suppress callbacks. Procedural motion goes through
  `MK.driver(tl, DUR, t => …)`, an ease function with side effects evaluated on every seek. Make it span
  exactly `DUR`: a longer driver silently lengthens the video.
- Measure layout once, after `document.fonts.ready`, before any tween touches a transform. No `Math.random`,
  clocks, `repeat:-1` or relative (`+=`) positions.
- Assets must live inside the piece folder (the renderer serves it). `render.sh` copies the kit in on each run.
- GSAP names eases by power, not degree: `power2` = cubic, `power3` = quartic.

## Layout traps
- **An overflow mask needs an in-flow child.** An absolutely positioned word inside `.m` gives the mask zero
  height and the word vanishes.
- Put spacing on the MASK, never on the line inside it, or a sliver stays visible after the line exits.
- Place a giant word by its INK, not its box: `MK.inkTop(el)` (needs a `<span class="bl"></span>` baseline
  marker) converts wordfit's ink position into a CSS top. Use the font size wordfit fitted.
- Move things with transforms (`y`, `scale`), never `top`/`left` tweens: layout properties reflow.
- Labels under ~24 px at 1080 wide vanish on a phone.
- The same image file in several `<img>` tags is flagged as duplicate media: use CSS backgrounds for repeats.

## Assets
- **wordfit is a guide, not a verdict.** It scores the top 55% of each letter (that's how people read),
  except E, L and Z, which are identified by their feet and scored over their full height. Parallax grows the
  subject over the word as a shot plays: keep subject scale ≤ 1.05 and judge the LAST frame of the beat at full resolution.
- A subject in a mirror lifts its reflection. Give it the room's scale.

## Render / QA
- **Motion blur: render 240 fps and average 4 of every 8 frames** (`tmix=frames=4`, `select=not(mod(n\,8))`)
  = a 180° shutter at 30 fps. 120 fps with 2 of 4 DOUBLE-PRINTS anything moving more than ~10 px per sub-frame.
- **Hard cuts on a beat: use `MK.hard(t)`** (4 sub-frames early), or the blur blends both shots into the beat frame.
- `cues.py` serves the piece over http: Chrome blocks `@font-face` from `file://`, and the probe must see the real font.
- The text probe knows masks, clip-paths and opacity, but not occlusion by a later opaque layer.
- **Calibrate the gate after editing qa.py**: break a copy of a piece on purpose (add a "!", push a label out of
  the safe area) and confirm it FAILS. A gate that passes broken input proves nothing.
- One-pass loudnorm undershoots sparse mixes (−15.3 on an 8 s piece): render.sh does two passes.
- zsh does not word-split `$VAR`: build argument lists explicitly.

## Music
- **A wipe's hit is its fastest frame, the MIDDLE of the sweep** (power3.inOut). Wipes that END on the beat
  measure 45-87 ms early. Start a wipe at `beat − d/2`.
- beatcheck finds hits by frame-difference spikes. A dissolve is not a spike, and a drumless section has no
  detected beats. List only HARD hits in `cuts`.
- Effect levels in music mode: the per-cue `g` is intent (clamped 0.5-1.25); the class level lives in sfx.py `REL`
  (dB relative to the music's loudest 4 s). Quiet booms disappear under a drop: give impacts more.
- A `// comment` appended to a line that also closes a call (`…});`) can swallow the close. The lint says
  "inline script syntax": check the extracted script with `node --check`.

## Footage scenes (type behind a moving person)
- **Timed `<video>` tags must be STATIC in index.html.** The renderer pre-extracts frames from the HTML; a video
  created in JS renders nothing. Write `data-start` as a literal, `data-media-start="0"`, `muted playsinline`,
  no timed ancestor. `sync-footage.py` rewrites every `data-duration` from the clip JSON after any re-cut.
- Background mp4 BELOW the word, subject VP9-alpha webm ABOVE it, both cut from the SAME frames by `clip.py`,
  mounted with identical timing. Never scale or move the two layers separately.
- **ffmpeg's native VP9 decoder drops alpha.** Decode with `-c:v libvpx-vp9`. Chrome plays VP9 alpha natively.
- Foreground-instance masks take every salient object (a car counts). Use `--person` for people.
- Fit the word against the READ WINDOW (`readmask.py --until 1.9`: wipe + ~1.3 s of reading), not the whole
  clip: someone walking toward camera fills the frame long after the word was read.
- **Shot choice is the real lever.** Type reads behind a person only when they fill ≲ 35% of the frame in the
  read window. When every shot is tight, end the sequence on a detail shot with the word in front.
- Slow-downs up to ~1.08× are a plain re-time; beyond that use `--interp` (motion interpolation) on slow
  camera moves, not on fast limbs.
