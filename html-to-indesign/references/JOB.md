# The job file

One JSON file describes the whole package. Relative paths resolve against the job file's folder. Worked example: `examples/sample-linesheet/linesheet.job.json` (single pages). The block below sketches a facing book + cover.

```jsonc
{
  "name": "Sample_Book",                 // package folder = <name>_InDesign, archive = <name>_InDesign_<date>.zip
  "html_root": "/abs/or/relative/dir",   // where the page HTML files live
  "work_dir": ".../indesign-work",       // extraction JSON, overlay PNGs, build_report.json, visual/  (WORKSPACE, not /tmp)
  "out_dir":  ".../indesign-out",        // the package folder + archive land here
  "root_selector": ".spread, .page1",    // the element that IS the canvas (incl. bleed) on every page; default "body > *"
  "flatten": {".card": "ad-mockup_meta-feed"},   // selector -> PNG base name; flattened with everything inside it
  "overlay_prefix": "shade",             // gradient overlays are named <prefix>_<pages>_<n>.png (default "overlay")
  "fonts": [                             // EVERY face the pages use, with a real OTF/TTF file
    {"css": "Sample Serif", "weight": 500, "style": "normal", "file": ".../SampleSerif-Medium.otf"},
    {"css": "Sample Serif", "weight": 500, "style": "italic", "file": ".../SampleSerif-MediumItalic.otf"}
    // optional "family"/"face" override what InDesign calls it; default = the file's name table (ids 16/17, else 1/2)
  ],
  "styles": {"kick": "Kicker", "h70": "Headline 70"},   // CSS class -> paragraph style name; unmatched blocks get "<Font> <Face> <size>pt"
  "colors": {"#000033": "Ink"},                          // #rgb or #rrggbb -> swatch name; unnamed colours become "R=.. G=.. B=.." and are listed as a warning
  "char_styles": {"Sample Serif Medium Italic": "Italic"},     // "<InDesign family> <face>" -> character style name (default: that string)
  "min_ppi": 250,                                       // images below this effective ppi as placed are flagged LOW RES
  "copy_system_fonts": false,                           // macOS system fonts are listed, not shipped (licence); true copies them anyway
  "reference_pdfs": [".../approved.pdf"],               // copied into Reference PDFs/; omit and the approved layout is rendered from the HTML
  "readme": {"title": "...", "subtitle": "...",          // README header
             "sections": [{"heading": "Cover", "lines": ["..."]}]},   // job-specific notes appended to the README
  "documents": [                         // one IDML per document (e.g. interior + cover)
    {
      "idml": "Sample_Book",              // the .idml file name (the package folder comes from the job's "name")
      "trim": [900, 765],                // page trim in pt (inches x 72)
      "bleed": {"top": 9, "bottom": 9, "inside": 0, "outside": 9},   // or one number for all sides; single pages may say left/right
                                                                     // (= inside/outside). Unknown or missing keys are an ERROR
      "margins": {"top": 18, "bottom": 18, "inside": 45, "outside": 18},
      "facing": true,
      "pages": [
        {"html": "p01_opener.html", "kind": "right"},
        {"html": "p02_pause.html"},      // default kind: "spread" in facing docs, "single" otherwise
        {"html": "p23_colophon.html", "kind": "left"}
      ]
    }
  ]
}
```

## Page kinds and the canvas each HTML file must be

The extractor measures in canvas points from the top-left of `root_selector`. The canvas must include the bleed.

| Document | `kind` | Canvas width | Spine / origin |
|---|---|---|---|
| facing | `spread` | 2·trim + 2·outside bleed | spine at outside bleed + trim |
| facing | `right` | trim + inside + outside bleed | spine at x = inside bleed |
| facing | `left` | trim + inside + outside bleed | spine at x = outside bleed + trim |
| non-facing | `single` | trim + left + right bleed | page centred on the spread origin |

The canvas height is always trim + top + bottom bleed. `build.py` REFUSES a canvas that doesn't match its kind + trim + bleed. A wrong bleed or kind shifts every item, and the geometry gate cannot see it, because it compares through the same offset. Two per-page overrides exist:
- `"spine_x"` forces the origin.
- `"tag"` names the page's overlays (e.g. `"cover"`).

### Common setups
- **Blurb Layflat Large Landscape book:**
  - trim 900 × 765, bleed 9 top/bottom/outside, 0 inside;
  - page 1 `right`, then spreads, last page `left`.
- **Cover wrap:** a separate document, `facing: true`, one `right` page.
  - The trim is the whole wrap: back + spine + front.
  - Uniform bleed. Blurb ImageWrap: 0.306 in = 22.03 pt.
  - Describe the spine in the README.
- **Line sheet / spec sheet / poster:** `facing: false`.
  - Pages are `single`, e.g. trim 612 × 792 (US Letter) with uniform bleed.
- **Hangtag:** a `single` page at the tag's trim, with bleed per the printer's spec.
  - Put the die line and hole as a flattened PNG or a native vector on its own, and say so in the README.

## Fonts: how CSS faces map to InDesign
The extractor records each run's computed `font-family`, weight and style. `build.py` picks the job entry by CSS font matching:
- **Family:** same family, case-insensitive.
- **Style:** italic and oblique match italic entries first.
- **Weight:** nearest by the CSS Fonts 4 rules.

The InDesign family and face come from the font file. If Chrome had to synthesise a face, the build warns, because InDesign will show the real face instead.

Fonts.xml entries are generated from the files; the generator reproduces InDesign's own entries exactly for the OTF and TTF families tested (serif, sans and mono). All job fonts are copied to `Document fonts/`.

## Outputs in `work_dir`
- `extract/<page>.json`: everything measured, in paint order.
- `overlays/*.png`: rasterised items.
- `build_report.json`:
  - per-frame wrap window and chosen width;
  - image ppi;
  - rasters, groups, warnings and fonts.
- `visual/`: the src / idml / heat PNGs and `sheet.jpg`.
