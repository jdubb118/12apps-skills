# Designing print HTML that converts cleanly to InDesign

These rules make the conversion exact and leave the designer with tidy, editable files. Each one exists because the converter maps CSS boxes onto InDesign frames one-to-one.

## Canvas
- **One HTML file per spread (facing) or per page.** Its root element is the full canvas *including bleed*, sized in pt, with `position: relative; overflow: hidden`. Put the background colour on that root: it becomes a "Page colour" rectangle.
- **Re-compose for print; never scale a screen layout.** The fold is the canvas centre on spreads; keep text off it (Blurb layflat: 45 pt either side).

## Text
- **Every text block is an element whose children are all inline** (`<span>`, `<i>`, `<b>`, `<br>`, text).
  - Each such block becomes one InDesign text frame + story.
  - Text sitting directly beside block children ("anonymous text") is skipped with a warning, so wrap it in its own element.
- **Position blocks absolutely, or in simple flex/flow containers.** The frame is the block's content box.
  - Shrink-to-fit blocks (flex items, `left:` without `width:`) are fine: the converter detects which edge is anchored.
- **Give every font face its own `@font-face`, pointing at a real OTF/TTF**, the same file InDesign will use.
  - Never use a generic family name (`Serif`, `Sans`, `Monospace`) as your font's name.
- **Set explicit `line-height` per class.** `normal` works but warns.
- **Use classes for typographic roles** (`.kick`, `.lede`, `.h70`…). The job maps class → paragraph style name, so the designer gets real styles.
  - Blocks styled inline, with no class, get a fallback name like "Georgia Regular 9.5pt".
  - One-off inline font sizes become local overrides.
- **Allowed, and carried:**
  - `letter-spacing` → tracking;
  - `text-transform: uppercase` → All Caps (the source text keeps its case);
  - `white-space: nowrap` spans → No Break;
  - `&nbsp;`;
  - `<br>` → forced line break;
  - opacity on a text block → a group with opacity;
  - 90°-style rotations via `transform` (spines, edge labels).
- **Not carried (warned):** text-decoration, vertical-align (super/sub), text-shadow, CSS columns, multi-paragraph flows. Use one block per paragraph.

## Images
- `<img>` with `object-fit: cover|contain|fill` and `object-position` maps exactly to an image frame and its placement.
  - Clipping by an `overflow: hidden` ancestor is honoured.
  - `border-radius` becomes rounded frame corners.
  - A `background-color` on the `<img>` becomes a panel behind it.
- **Link the full-resolution file you want printed.** Under 250 ppi as placed (`min_ppi`) is flagged LOW RES.
  - JPEGs are copied losslessly; their metadata is set to 300 ppi.
  - Greyscale JPEGs, EXIF-rotated JPEGs and other formats are converted to sRGB with a warning.
- Avoid `object-fit: fill` stretches. Under 1% is snapped to proportional; more is kept stretched and warned.

## Shapes and effects
- **Solid backgrounds become rectangles** with named swatches. Semi-transparent ones are handled two ways:
  - over a flat colour, they are blended into a solid swatch;
  - over photos, they keep real InDesign opacity.
- **Borders become InDesign lines.** Only solid borders; dashed and dotted are drawn solid with a warning.
- **Simple SVG paths become native vectors** (fill, stroke, opacity, non-scaling strokes). Supported commands: M L H V C S Q T Z.
  - Arcs (`A`), masks, clip paths, gradient fills and `<text>` in SVG flatten the whole SVG to a PNG.
- **CSS gradients become transparent PNG overlays at 192 ppi.** Give each gradient its own element, so it stays a separate, deletable overlay.
- **UI mock-ups (ad frames, phone screens) should be listed in `flatten`.** They become one 384 ppi PNG each.
  - Their system UI fonts aren't available in InDesign anyway.
- **Not carried (warned):** box-shadow, blend modes, CSS filters, z-index.
  - Paint order = DOM order, so order the DOM the way the layers should stack.
