---
name: html-to-indesign
description: Convert HTML/CSS print designs (books, lookbooks, catalogues, line sheets, posters, flyers, spec sheets, hangtags, cover wraps) into an editable Adobe InDesign file — IDML that opens in InDesign and saves as .indd — packaged like InDesign's File > Package, with live text, paragraph and character styles, named swatches, linked full-resolution images, fonts, a reference PDF and a READ ME. Every file is validated against Adobe's own IDML schema and a geometry round-trip, no InDesign required. Use for "convert HTML to InDesign", "make an INDD / IDML", "package this for a designer", "editable InDesign version of this layout", or handing an AI- or code-designed print piece to a design team.
---

# html-to-indesign: HTML print layouts → a packaged, editable InDesign file

AI tools and developers increasingly design print pieces in HTML/CSS. Designers and printers still work in
InDesign. PDF-to-InDesign converters guess at structure and produce a pile of outlined fragments. This skill
starts from the HTML itself, so it knows every text block, font, colour and image exactly, and writes a real
InDesign document:

- **Live, editable text** in frames, with **paragraph styles named from your CSS classes**, character styles for
  bold/italic face changes, and **named RGB swatches**.
- **Line breaks preserved.** Each frame is set to a width inside the window where Chrome produces exactly the
  approved breaks, using InDesign's Single-line Composer with hyphenation off.
- **Linked full-resolution images** with their crop and placement (`object-fit`, `object-position`, rounded corners).
- **Native vectors** for simple SVG paths; gradients, mock-ups and complex SVG become separate transparent PNGs.
- **A package folder** like InDesign's own: the `.idml`, `Links/`, `Document fonts/`, `Reference PDFs/` and
  `READ ME FIRST.txt`, plus a dated zip.

No InDesign needed to build it. Open the `.idml` in InDesign and **Save As .indd**.

## Install
```bash
cd scripts && npm install && npx playwright install chromium     # the Chromium extractor
pip install pillow numpy fonttools                                # Python 3.10+
brew install jing-trang                                           # the Adobe-schema gate (Java)
bash scripts/selftest.sh                                          # builds the sample line sheet; every gate must PASS
```
Adobe's IDML schemas are fetched on first use (`scripts/fetch_schemas.sh`, pinned). You need a real **OTF/TTF
file for every font face** the pages use: InDesign needs the same fonts, and woff2 alone won't do.

## Workflow
1. **Design for conversion** (`references/DESIGN-RULES.md`): one HTML file per page or spread whose root element is
   the full canvas *including bleed*; absolutely positioned blocks; text blocks with inline-only children; a CSS
   class per typographic role; one `@font-face` per face pointing at a real font file; gradients on their own
   elements. Never scale a screen layout to print: re-compose it.
2. **Write the job file** (`references/JOB.md`, example in `examples/sample-linesheet/`): trim, bleed, margins,
   facing pages, page kinds, fonts with their files, class → paragraph-style names, hex → swatch names, mock-ups
   to flatten, README notes.
3. **Preflight:** `python3 scripts/common.py resolve job.json`, then `node scripts/extract.mjs <work_dir>/job.resolved.json`.
   Fix every WARN line.
4. **Build:** `bash scripts/run.sh job.json` (about 15-40 s per page): resolve → extract → build → five gates →
   visual round-trip → archive, with a test of the expanded copy.
5. **All five gates must PASS**, then look at `<work_dir>/visual/sheet.jpg`: approved page, a re-render of what
   the IDML says, and the difference, page by page.

## The five gates (`scripts/check.py`)
| Gate | Checks | If it fails |
|---|---|---|
| 1 schema | Every XML part against Adobe's InDesign 2026 RelaxNG schema (`jing`). | A builder bug: read the jing line and fix `build.py`. Never hand-edit the IDML. |
| 2 integrity | Unique ids; every story, style, swatch, master, layer, font and link resolves; link files exist at the recorded size. | Usually a missing font in the job, or a broken link copy. |
| 3 geometry | Re-derives every frame from the IDML (`idml_probe.py`) and diffs it against the extraction: frames, image placement, text anchor, first baseline, every later baseline, rotated frames. | Over 0.01 pt (0.05 pt for leading) is a mapping bug. A canvas that doesn't match its page kind + trim + bleed is refused at build time. |
| 4 text | Every story's text equals the HTML's rendered text, character for character. | Anonymous text or whitespace in the source: wrap the text in its own element. |
| 5 wraps | Each frame has at least 1 pt of slack before a line could re-wrap (warns under 2 pt). | Nudge the HTML box width, or accept the forced width. Different font files between Chrome and InDesign show up here. |

`scripts/compare_idml.py A.idml B.idml [--names]` diffs two IDMLs item by item (formatting, geometry, links, text):
rebuild a job you have delivered after changing the builder, and it must say IDENTICAL.

## Known limits (they become warnings or images, never silent errors)
- **Flattened to transparent PNGs:** CSS gradients and background images, mock-ups listed in `flatten`, SVGs with
  arcs, clip paths, masks, gradients or `<text>`, `<img src=*.svg>`, `<canvas>`, `<video>`, transformed images.
- **Not carried:** box-shadow, text-shadow, blend modes, CSS filters, text-decoration, vertical-align, CSS columns,
  z-index (paint order = DOM order).
- **Opacity:** semi-transparent colours over a flat background are pre-blended into solid swatches; over photos
  they stay real InDesign transparency; transparent text sits in a group carrying the opacity.
- **One layer**, in paint order, so text can never end up under a photo.
- **Links** are relative (`file:Links/<name>`). The READ ME covers "Relink to Folder" in case InDesign asks.
- **Fonts:** every job font is copied to `Document fonts/`; the READ ME reminds the recipient that commercial
  typefaces need their own licence. macOS system fonts are listed but not copied (`"copy_system_fonts": true` overrides).

## Files
`scripts/run.sh` (one-command pipeline) · `extract.mjs` (Chromium extraction) · `build.py` (IDML writer + package) ·
`check.py` (gates) · `visual.py` + `render_diff.mjs` (visual round-trip) · `reference_pdf.mjs` (approved-layout PDF) ·
`package.py` (archive + expanded-copy test) · `compare_idml.py` (regression diff) · `idml_probe.py` (IDML geometry
parser) · `schema_check.sh` + `fetch_schemas.sh` · `common.py` (job + page geometry) · `selftest.sh`.
`template/`: InDesign boilerplate (stock swatches, styles and preferences). `references/`: JOB.md, DESIGN-RULES.md,
VERIFICATION.md (how each claim was proven).

## Traps
- macOS deletes `/tmp` files untouched for ~3 days. Keep jobs, sources and output somewhere permanent.
- A CSS family named `Serif`, `Sans`, `Monospace`… is the generic keyword, not your face: quote real names.
- System fonts carry protected file flags, so the build copies font content only.
- Run `selftest.sh` after touching any script.
