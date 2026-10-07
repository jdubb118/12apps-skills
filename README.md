# 12apps skills — free Claude Code skills for video, motion design, computer vision and web design

Open-source **Agent Skills for Claude Code** (and any agent that reads `SKILL.md`): beat-synced video editing,
motion graphics from HTML, on-device subject cut-outs with Apple Vision, and award-winning web design research.
Each skill is a folder with a `SKILL.md` the agent reads, plus the scripts it runs. Everything runs locally:
no API keys and no paid services.

| Skill | What it does | Good for |
|---|---|---|
| [**beatsync**](beatsync/) | Measures a song's beat grid (tempo to 0.01 BPM, downbeats, drops) and proves a finished video lands its cuts on the beat | Cutting reels, TikToks, slideshows and motion graphics to music |
| [**vision-lift**](vision-lift/) | Cuts the subject out of a photo or video on a Mac with Apple's Vision framework: masks, transparent cut-outs, background + subject layers | Background removal, "text behind the person" effects, parallax, video mattes |
| [**motion-kit**](motion-kit/) | Builds 9:16 motion graphics as HTML + GSAP, renders frame-exact with HyperFrames, adds motion blur and synthesized sound, and gates every render with automated QA | Instagram Reels, Stories, Shorts, product promos, kinetic typography |
| [**design-radar**](design-radar/) | Studies Awwwards Site-of-the-Day winners in a headless browser and keeps a growing, evidence-based library of what high-end websites actually ship | Making a website look expensive: typography, motion stack, techniques with live demos |

## Install
```bash
git clone https://github.com/jdubb118/12apps-skills.git
ln -s "$PWD/12apps-skills/beatsync" ~/.claude/skills/beatsync        # repeat per skill you want
```
Keep the folders side by side: motion-kit calls beatsync and vision-lift by relative path.
Each `SKILL.md` lists its own requirements. Most need Python 3.10+ and ffmpeg; vision-lift needs macOS 14+.

## Why these exist
- **beatsync** fixes the failure modes of plain beat trackers: tempo numbers that drift, beats placed 30-50 ms
  after you hear them, half-beat lock on loud off-beat hi-hats, and drops read one beat early. It refuses to
  invent a grid for audio that has no steady beat. `selftest.py` proves it against synthetic tracks with a known answer.
- **vision-lift** wraps the same subject-lifting model as "Copy Subject" in Photos in two small Swift tools.
  No model download, no GPU setup, no cost. `selftest.py` checks the mask against a shape with a known outline.
- **motion-kit** treats a video like code: one deterministic timeline, sound declared where it happens, and a QA
  gate for safe areas, loudness, copy rules and frozen frames that fails the render instead of trusting your eyes.
- **design-radar** answers "what do award-winning sites actually use?" with measured evidence (fonts, GSAP, Lenis,
  3D asset pipelines) instead of opinion, and grows by itself every week.

## License
MIT. Bundled third-party files keep their own licenses (Inter: SIL Open Font License 1.1, see `motion-kit/kit/fonts/`).
Built and maintained at [12apps.io](https://12apps.io).
