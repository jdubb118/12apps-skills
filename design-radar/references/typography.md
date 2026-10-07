# Typography Intel

Harvested from 31 Awwwards SOTD winners, 2026-09-05. **29/31 ship custom webfont files.**
Exactly **one** shipped Inter. This is the highest-leverage finding in the whole corpus.

---

## The pattern

The award-winning look is built on **neo-grotesks and indie foundry faces**, not on
Google Fonts defaults. Three families dominate the field:

1. **Neo-grotesk sans** (the workhorse) — Neue Haas, Diatype, Founders, Graphik, Degular
2. **A contrast serif** for editorial moments — Signifier, Teodor, Instrument Serif
3. **A mono** for labels/meta/counters — Geist Mono, IBM Plex Mono, Chivo Mono, PP Neue Montreal Mono

The mono-for-metadata move (6 sites) is cheap and instantly signals "designed":
small caps mono for section numbers, timestamps, captions, nav labels.

---

## What they actually shipped

| Typeface | Sites | Foundry | Cost |
|---|---|---|---|
| Die Grotesk C/D | 2 | Die Gestalten | Paid |
| Geist / Geist Mono | 3 | Vercel | **Free** |
| IBM Plex Mono | 2 | IBM | **Free** |
| Instrument Serif | 2 | Instrument | **Free** |
| DM Sans | 3 | Colophon | **Free** |
| Archivo | 2 | Omnibus-Type | **Free** |
| SemiSqueezed | 2 | indie | Paid |
| Neue Haas Grotesk | 1 | Linotype | Paid ($$) |
| ABC Diatype Plus | 1 | Dinamo | Paid ($$) |
| Founders Grotesk | 1 | Klim | Paid ($$) |
| Graphik | 1 | Commercial Type | Paid ($$) |
| Signifier | 1 | Klim | Paid ($$) |
| Degular | 2 | OH no Type Co | Paid |
| Teodor | 2 | Newglyph | Paid |
| PP Neue Montreal Mono | 1 | Pangram Pangram | Paid |
| Beausite Classic | 2 | Atipo | Paid |
| Overused Grotesk | 1 | RandomMaerks | **Free** |
| LayGrotesk | 1 | indie | Paid |
| Chivo Mono | 2 | Omnibus-Type | **Free** |
| Roboto Flex | 1 | Google | **Free** |
| Champ | 1 | indie | Paid |
| Nekst | 1 | indie | Paid |
| F37 Analog | 1 | F37 | Paid |

---

## Free substitutes that hold up  ★ use these

You do not need a $600 license to get 90% of the effect. These are the honest swaps:

| If you want… | Buy | Free substitute |
|---|---|---|
| Neue Haas / Helvetica Now | $$$ | **Inter Tight**, **Geist**, **Archivo** |
| ABC Diatype | $$$ | **Overused Grotesk** ★ closest free match |
| Founders Grotesk | $$$ | **Archivo**, **Space Grotesk** |
| Graphik | $$$ | **DM Sans**, **Geist** |
| Signifier / Teodor (contrast serif) | $$ | **Instrument Serif** ★, **Fraunces**, **Newsreader** |
| PP Neue Montreal Mono | $$ | **Geist Mono** ★, **Chivo Mono**, **IBM Plex Mono** |
| A condensed display | $$ | **Archivo Expanded/Condensed** (variable), **Anton** |

**Geist + Geist Mono** (Vercel, free, variable, excellent) is the single best
zero-cost pairing in this whole corpus — and two winners already use it.

**Fraunces** is another strong editorial serif, and it is free.

---

## Recommended house pairings

**Light / editorial** — for fashion, books, long-form:
```
Display : Instrument Serif  (or Fraunces at optical size 144)
Body    : Geist / DM Sans
Meta    : Geist Mono, uppercase, 11px, +0.08em tracking
```

**Dark / immersive** — for tech, sport, product microsites:
```
Display : Archivo Expanded, 700–800, tracking -0.04em
Body    : Geist
Meta    : Chivo Mono
```

---

## Loading rules winners follow

```html
<link rel="preload" href="/fonts/Geist-Variable.woff2" as="font"
      type="font/woff2" crossorigin>
```
```css
@font-face {
  font-family: 'Geist';
  src: url('/fonts/Geist-Variable.woff2') format('woff2-variations');
  font-weight: 100 900;          /* one file, every weight */
  font-display: swap;            /* never block render */
}
```

- **Self-host.** Almost no winner used a Google Fonts CDN link — they ship the file.
  Faster, and it dodges the EU-GDPR Google Fonts issue entirely.
- **Variable fonts**: one request covers the whole weight range.
- **Subset** to Latin unless you need more — often 70% smaller.
- `font-display: swap` always; the fallback flash beats invisible text.

⚠️ Match the fallback's metrics or the swap causes visible reflow:
```css
font-family: 'Geist', system-ui, sans-serif;
size-adjust: 96%;   /* tune until the swap doesn't jump */
```
