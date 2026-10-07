---
name: vision-lift
description: Cut the subject out of a photo or a video on a Mac, free and offline, with Apple's Vision framework (the subject-lifting model behind "Copy Subject" in Photos). Gives a full-resolution mask, background + subject layers for putting type BEHIND a person or object, and per-frame masks for video (a transparent subject clip). Use for "remove the background", "cut out the subject", "put the text behind the person", depth/parallax effects, or any mask/matte job on macOS.
---

# vision-lift: subject masks on a Mac, no model, no cost

| | |
|---|---|
| `lift <photo> <mask.png>` | one photo → a full-resolution grayscale mask (white = subject). Exit 3 = no subject found. |
| `lift-video <frames-dir> [--person]` | every `f_NNNNNN.png` in a folder → `m_NNNNNN.png`. Every frame gets a mask, empty ones all black, so counts always match. |
| `python3 subject.py <photo> --out layers/scene [--size 1080x1920]` | photo → `scene.jpg` (cover-fit) + `scene-subject.png` (RGBA cut-out) + `scene.json` (subject bbox, top, % of frame). |
| `python3 selftest.py` | draws a ball with a known outline, lifts it, checks IoU ≥ 0.85; runs the video tool over 6 frames incl. an empty one. |

## Requirements
macOS 14+, the Xcode Command Line Tools (`xcode-select --install`, for `swiftc`), Python 3 with numpy + Pillow.
The Swift tools compile on first use (`subject.py` and `selftest.py` do it for you), or by hand:
```bash
swiftc -O lift.swift -o lift && swiftc -O lift-video.swift -o lift-video
```

## Type behind a subject (the depth move)
1. `python3 subject.py photo.jpg --out layers/hero --size 1080x1920`
2. Stack three layers: `hero.jpg` at the bottom, your headline in the middle, `hero-subject.png` on top.
3. Place the word so the subject overlaps roughly 12-35% of it. Less looks flat; more and the word stops
   reading. Readers recognise letters by their TOP half: a head over the top of a letter kills it, a
   shoulder over the bottom of a word usually doesn't.
4. Judge the result at full resolution, not a thumbnail.

## Video
```bash
ffmpeg -i clip.mp4 -vf fps=24 frames/f_%06d.png
./lift-video frames --person            # people only; drop --person to lift every salient object
```
Then build the RGBA frames (frame + mask as alpha) and encode a transparent clip:
`ffmpeg -framerate 24 -i a_%06d.png -c:v libvpx-vp9 -pix_fmt yuva420p subject.webm`.
Cut the background clip and the subject clip from the SAME extracted frames, or they drift by a frame.

## Traps
- **Foreground mode lifts everything salient.** A car, a chair or a dog all count as subject. For people
  use `--person` (video) or crop first.
- **ffmpeg's native VP9 decoder drops the alpha channel.** Decode transparent webm with `-c:v libvpx-vp9`.
  Chrome plays VP9 alpha natively.
- **A mirror shot lifts the reflection.** Treat a subject in a mirror as part of the room.
- The mask edge is soft by design; a 0.8-1 px blur on the alpha hides the stair-step at 1080p.
