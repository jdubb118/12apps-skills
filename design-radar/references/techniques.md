# Technique Recipes

Copy-paste implementations of what SOTD winners actually ship. Ordered cheap → expensive.

---

## 1. Lenis smooth scroll  ★ highest look-per-line in web design

5/31 winners. Locomotive: 0. Lenis won this category outright.

```js
import Lenis from 'lenis'          // npm i lenis
const lenis = new Lenis({ duration: 1.1, smoothWheel: true })
function raf(t){ lenis.raf(t); requestAnimationFrame(raf) }
requestAnimationFrame(raf)
```

Wire it to GSAP so ScrollTrigger stays in sync — **skip this and pinning drifts:**
```js
lenis.on('scroll', ScrollTrigger.update)
gsap.ticker.add((t) => lenis.raf(t * 1000))
gsap.ticker.lagSmoothing(0)
```

⚠️ Always honour reduced motion:
```js
if (matchMedia('(prefers-reduced-motion: reduce)').matches) lenis.destroy()
```

---

## 2. SplitText reveals  ★ the signature award-site move

6/31 — appears on nearly every GSAP site in the corpus. GSAP is fully free
including SplitText since v3.13 (Webflow acquisition).

```js
gsap.registerPlugin(SplitText, ScrollTrigger)
const split = SplitText.create('h1', { type: 'lines', mask: 'lines' })
gsap.from(split.lines, {
  yPercent: 110, opacity: 0, duration: 1.1, stagger: 0.08,
  ease: 'expo.out',
  scrollTrigger: { trigger: 'h1', start: 'top 85%' },
})
```

`mask: 'lines'` is the detail that separates pro from amateur — lines slide out
from behind a clipping mask instead of just fading.

**Free alternative (no GSAP):** `Splitting.js` + CSS transitions.

---

## 3. CustomEase — stop using stock eases

4/31 load CustomEase. This is a real differentiator: default `power2.out` reads
as "template". Winners author curves.

```js
gsap.registerPlugin(CustomEase)
CustomEase.create('brand', 'M0,0 C0.16,1 0.3,1 1,1')   // heavy overshoot-free snap
gsap.to(el, { y: 0, duration: 1.2, ease: 'brand' })
```

Pure-CSS equivalent worth memorizing:
```css
--ease-out-expo:  cubic-bezier(0.16, 1, 0.3, 1);     /* the "expensive" ease */
--ease-out-quart: cubic-bezier(0.25, 1, 0.5, 1);
--ease-in-out-cubic: cubic-bezier(0.65, 0, 0.35, 1);
```
`--ease-out-expo` alone makes most UI feel considerably more premium.

---

## 4. Editorial type scale

```css
h1 {
  font-size: clamp(3rem, 11vw, 12rem);
  line-height: 0.88;              /* tight — the single biggest "designed" tell */
  letter-spacing: -0.035em;       /* negative tracking at display sizes */
  text-wrap: balance;
}
p { max-width: 62ch; line-height: 1.55; }
```

Rules winners follow:
- Display type: leading **below 1.0**, tracking **negative**.
- Body: leading 1.5–1.6, measure 60–70ch.
- Two weights of one family beats two families.

---

## 5. Custom cursor with lag

```js
const c = document.querySelector('.cursor')
let x = 0, y = 0, tx = 0, ty = 0
addEventListener('pointermove', e => { tx = e.clientX; ty = e.clientY })
;(function loop(){
  x += (tx - x) * 0.15                        // 0.15 = the lag; 0.1 slower, 0.3 tighter
  y += (ty - y) * 0.15
  c.style.transform = `translate3d(${x}px,${y}px,0) translate(-50%,-50%)`
  requestAnimationFrame(loop)
})()
```
```css
.cursor { position: fixed; inset: 0 auto auto 0; width: 14px; height: 14px;
  border-radius: 50%; background: #fff; mix-blend-mode: difference;
  pointer-events: none; z-index: 9999; transition: width .3s, height .3s; }
```
`mix-blend-mode: difference` is what makes it work over any background.
**Hide it on touch devices** — `@media (hover: none) { .cursor { display: none } }`.

---

## 6. Scroll-velocity skew / marquee

Reads expensive, costs ~20 lines.

```js
let vel = 0
lenis.on('scroll', ({ velocity }) => { vel = velocity })
gsap.ticker.add(() => {
  const skew = gsap.utils.clamp(-12, 12, vel * 0.6)
  gsap.to('.skewable', { skewY: skew, duration: 0.4, ease: 'power3.out' })
})
```

Infinite marquee that reacts to scroll direction:
```js
const tl = gsap.to('.marquee-inner', { xPercent: -50, duration: 20,
  ease: 'none', repeat: -1 })
lenis.on('scroll', ({ velocity }) => {
  tl.timeScale(gsap.utils.clamp(0.2, 4, 1 + Math.abs(velocity) * 0.3))
  tl.vars.ease // direction flip: tl.reversed(velocity < 0)
})
```

---

## 7. Sticky scroll storytelling

```js
ScrollTrigger.create({
  trigger: '.chapter', start: 'top top', end: '+=200%',
  pin: true, scrub: 1,
  animation: gsap.timeline()
    .to('.layer-bg', { scale: 1.15 })
    .from('.layer-copy', { yPercent: 40, opacity: 0 }, 0),
})
```
`scrub: 1` (not `true`) adds a 1s catch-up — noticeably smoother.

---

## 8. barba.js page transitions

4/31. Makes a multipage site feel like an app without becoming an SPA.

```js
barba.init({
  transitions: [{
    leave: ({ current }) => gsap.to(current.container, { opacity: 0, duration: .5 }),
    enter: ({ next })   => gsap.from(next.container, { opacity: 0, duration: .5 }),
  }],
})
```
Pair with `@barba/prefetch` (1 site did) so the next page is warm before click.

⚠️ Re-init ScrollTrigger and Lenis on every `enter`, or the second page scrolls dead.

---

## 9. Video as the cheap 3D substitute

18/31 ship video — **more common than 3D models (11)**. A pre-rendered loop of the
thing you'd have built in WebGL costs a fraction and never drops frames.

```html
<video autoplay muted loop playsinline preload="metadata"
       poster="hero.jpg" class="hero-video"></video>
```
- Always `muted` + `playsinline` or iOS refuses to autoplay.
- Ship `.webm` (VP9/AV1) with `.mp4` fallback.
- `poster` is mandatory — it's what shows during load.

---

## 10. Displacement hover shader (Tier 3, but contained)

The desaturate→colour + warp on image hover. Cheapest real shader win.
Use `ogl` (~10kb) rather than pulling in all of three.js for one effect.

```glsl
// fragment — sample the image, offset UV by a noise texture scaled by hover
vec2 uv = vUv + (texture2D(uDisp, vUv).rg - 0.5) * uHover * 0.12;
vec3 col = texture2D(uTex, uv).rgb;
float g = dot(col, vec3(0.299, 0.587, 0.114));
gl_FragColor = vec4(mix(vec3(g), col, uHover), 1.0);
```

---

## 11. Full 3D pipeline (Tier 3 — what the heaviest winners ship)

Trevor Noah's site is the reference implementation in this corpus:
10 `.glb` models + 6 `.ktx2` textures + 1 `.exr` + `basis_transcoder.wasm`, 88 requests.

```
Model    → glTF, Draco-compressed        (draco_decoder.wasm)
Textures → KTX2/Basis, GPU-compressed    (basis_transcoder.wasm)
Lighting → .exr / .hdr environment map
```
KTX2 stays compressed *in VRAM* — the difference between a site that runs on a
mid phone and one that doesn't. If you ship 3D, ship KTX2.

---

## Non-negotiables

Award sites get judged on these too. Skipping them is how a beautiful build fails.

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: .01ms !important;
    transition-duration: .01ms !important; scroll-behavior: auto !important; }
}
```
- Every scroll-reveal must have a **no-JS visible state** — never ship content at
  `opacity: 0` that only JS can reveal. That is invisible to crawlers and breaks on error.
- Keyboard focus must survive custom cursors and smooth scroll.
- Lazy-load below-fold media; `preload` only the hero.
- **ScrollTrigger: never trigger on the element its own `gsap.from` moves.** It measures the
  element at progress 0 (already shifted), so `end: 'bottom bottom'` lands past the page end and
  the scrub never finishes (12apps footer wordmark, 2026-10-04). Trigger on an untransformed wrapper.
- **Canvas text drawn with a webfont needs `document.fonts.load()` first** (fonts load lazily):
  without it the first frame rasterises the fallback face.
