---
name: design-radar
description: Award-winning web design intelligence — the techniques, stack, typography and motion vocabulary that actually ship on Awwwards Site-of-the-Day winners, harvested from real rendered evidence. Use when building or restyling ANY web UI (landing page, hero section, marketing site, portfolio, product page, microsite, component) and the goal is "make this look genuinely high-end / cutting-edge / expensive", or when asked for 'design radar', 'make it look awwwards', 'cool web design', 'wow factor', 'refresh the radar', or what's current in web design. Complements frontend-design (which covers general taste); this skill covers what award winners specifically do.
---

# Design Radar

Evidence-based playbook for building web UI that reads as *expensive*. Every claim here
comes from rendering real Awwwards Site-of-the-Day winners in a headless browser and
reading their network + runtime, not from opinion.

**Corpus:** 31/31 SOTD winners, harvested 2026-09-05. See `references/corpus.md`.
**Refresh:** `bash scripts/harvest.sh` (~6 min, re-scans the current SOTD page).

---

## Read this first: the single biggest lever

**Typography does more work than WebGL.** 29/31 winners ship custom webfont files.
Only 1 shipped Inter. Almost none use Google Fonts defaults. The "expensive" look is
bought at the typeface, then amplified by motion — not by a shader.

If you have one move to spend, spend it on the typeface. Then `SplitText` it.

---

## The Award Stack (what winners actually load)

| Layer | Winner | Share | Note |
|---|---|---|---|
| Motion | **GSAP + ScrollTrigger** | 9/31 | The single most-loaded pair |
| Text | **SplitText** | 6/31 | Appears on nearly every GSAP site |
| Easing | **CustomEase** | 4/31 | They do *not* use default eases |
| Scroll | **Lenis** | 5/31 | Beat Locomotive completely — 0 sites |
| Page transition | **barba.js** | 4/31 | SPA-feel on multipage sites |
| Framework | Vue/Nuxt 8, Next 6 | 45% | **Half ship no framework at all** |

**The non-obvious finding:** the award stack is *vanilla JS + GSAP*, not React.
Reaching for Next.js by default is not what the top of this field does.

### 3D is less universal than the aesthetic implies
- WebGL canvas present: **21/31 (67%)**
- Ships actual `.glb` models: **11/31 (35%)**
- Ships compressed KTX2 textures: **4/31**
- **10/31 have no canvas at all** and still won.

You do **not** need three.js to win. Video (18/31) is more common than 3D models.

---

## Detection trap (cost me a wrong read tonight)

`window.THREE` was detected on **1/31** sites — but **11** ship `.glb` models.
Modern bundlers hide every library global. **Never conclude "no three.js" from a
global sniff.** Judge the stack by its *asset pipeline*:

| Evidence | Means |
|---|---|
| `.glb` / `.gltf` | three.js or an engine, near-certainly |
| `draco_decoder.wasm` | compressed geometry |
| `basis_transcoder.wasm` + `.ktx2` | GPU-compressed textures (serious pipeline) |
| `.exr` / `.hdr` | image-based lighting → the "real material" look |
| `rive.wasm` | Rive, not Lottie (Decathlon does this) |

---

## The technique ladder — cheap to expensive

Full recipes with code in `references/techniques.md`. Ranked by *look-per-hour*.

**Tier 1 — hours, huge payoff. Do these every time.**
1. **A real typeface** (not Inter). The whole game. → `references/typography.md`
2. **Lenis smooth scroll** — 6 lines. Instantly reads premium.
3. **SplitText line/char reveals** with a stagger on scroll-in.
4. **CustomEase** — kill `ease: "power2.out"`. Winners author their own curves.
5. **Generous type scale** — hero at `clamp(3rem, 11vw, 12rem)`, tight `0.9` leading, negative tracking.

**Tier 2 — a day, strong differentiation.**
6. **barba.js page transitions** — multipage that feels like an app.
7. **Custom cursor with lag** — lerp toward the pointer, scale on hover targets.
8. **Video-as-texture / fullbleed loops** — 18/31 do this; cheaper than 3D.
9. **Sticky-section scroll storytelling** — ScrollTrigger `pin` + scrub.
10. **Marquee + scroll-velocity skew** — reads expensive, ~20 lines.

**Tier 3 — expensive. Only with a real budget.**
11. Displacement / refraction shaders on hover.
12. Full R3F scenes with GLB + KTX2 + EXR lighting.
13. WebGPU / TSL. ⚠️ Corpus can't yet confirm any winner *ships* it — the inspector's
    `webgpu` flag is a Chromium capability check (`'gpu' in navigator`), true on all
    31, so it proves nothing. Treat as emerging, not established.

---

## Palette reality check

13 dark / 13 light / 5 indeterminate. **Dark is not required.** The dark-glow
aesthetic is one dialect, not the standard. Winners commit hard to *either*
near-black (`#000`, `#111`, `#0E0E0E`, `#181818`) or warm off-white
(`#FBFAF4`, `#F7F7F5`, `#F3F0ED`) — the losing move is mid-grey mush.

Pure `#FFF` (9 sites) and pure `#000` (5) are both used unapologetically.

---

## How to apply this

When building web UI:
1. Pick the dialect first — dark-immersive or light-editorial. Commit fully.
2. Choose the typeface before any layout. Check `references/typography.md`
   for the licensed faces winners use and the **free substitutes**.
3. Take all of Tier 1. It's a few hours and gets most of the perceived quality.
4. Add Tier 2 only where it serves the story.
5. Reach for Tier 3 only if the brand is the experience (fashion, music, film).

**A sane default:** heavy custom WebGL stays admired-not-cloned. The high-ROI lifts
are Tier 1 + selective Tier 2.

## Install
```bash
cd scripts && npm install && npx playwright install chromium   # the headless renderer
python3 radar-run.py --dry-run --no-render                     # smoke test: fetches, writes nothing
python3 radar-run.py                                           # a real run (~2-4 min)
```
Weekly runs: `launchd/design-radar.plist.example` (macOS) or a cron line calling `scripts/radar-run.py`.
The repo ships with a research snapshot (58 award winners, 37 techniques); runs add to it, never reset it.

## References
- `references/ideas.md` ★ — **the shelf.** Named experimental techniques accumulated
  weekly from Codrops, newest first. Check here FIRST when someone says "we're building X"
  and you want a wow-factor move — the research is already done and waiting.
  **Every entry carries a ▶ live-demo URL and usually a GitHub link**, so you can
  always show the actual thing rather than describing it.
- `references/techniques.md` — copy-paste recipes for the proven techniques above
- `references/typography.md` — the actual typefaces, with free substitutes
- `references/corpus.md` — every inspected site with its **full live URL** (written in
  plain text, not just an href) + Awwwards write-up link, stack and asset evidence.
  This is the "show me an example of that" table — pull real URLs from here, never
  invent one. Raw per-site evidence is kept in `state/sites/<slug>.json`.
- `references/trends.md` — stack share over time (is Lenis still winning? is 3D rising?)

## The accumulator

`scripts/radar-run.py` runs **weekly via launchd**, silently. Deterministic — no LLM
call, no API key, $0 per run. It only processes items it hasn't already seen, so it
stays cheap after the first pass:

- **Codrops RSS → `ideas.md`** — new implementable techniques, with writeup links
- **Awwwards SOTD → `corpus.md` + `trends.md`** — renders only newly-listed winners

State lives in `state/` (`seen-sites.json`, `seen-articles.json`, `history.jsonl`,
`heartbeat.txt`). Run manually anytime: `python3 scripts/radar-run.py`.
Flags: `--dry-run`, `--no-render`, `--max-render N`.

⚠️ Deliberately **silent**: no notifications, no digest. The library accumulates in the
background and gets read on demand. `state/heartbeat.txt` is how you confirm it's alive.
