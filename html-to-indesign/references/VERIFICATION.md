# How the output is verified (without InDesign)

## In production
A 44-page layflat book plus its cover wrap (189 live text frames, 53 linked images) was built with this skill,
delivered to a designer, and opened and edited in InDesign without problems. Rebuilding it through the current
skill matches that delivery under `compare_idml.py`: 272 items IDENTICAL on formatting, geometry, links and text.

## The checks, and why each exists
1. **The coordinate model, proven on InDesign's own output.** The model was tested against an InDesign-written IDML
   and the PDF exported from the same document (`idml_probe.py`): 46/46 text frames hold their text where the PDF
   has it, and 22/23 image draws match the visible placement within 2 pt (the 23rd is drawn uncropped inside a
   transparency group; its centre still matches). Facts established:
   - spread origin at the spine; pages vertically centred;
   - left page x ∈ [−W, 0], right page [0, W];
   - a child's ItemTransform is relative to its parent's inner coordinates;
   - image GraphicBounds = pixels × 72 / ActualPpi.
2. **Non-facing pages:** in InDesign-written letter-size files, the page is centred on the spread origin
   (ItemTransform −W/2, −H/2).
3. **Adobe's schema.** The RelaxNG that `app.generateIDMLSchema()` writes for InDesign 2026 (21.5), via
   github.com/metanorma/idml.
   - `jing` needs `-Djdk.xml.elementAttributeLimit=0`, because InDesign styles carry more than 200 attributes.
   - DOMVersion is rewritten from 21.0 to 21.5 for validation only.
   - Controls: an InDesign-written file passes; planted faults fail (a bogus attribute, a misspelled enum).
4. **Vocabulary.** Every element and attribute emitted was seen in InDesign-written IDML, except `NoBreak` on
   CharacterStyleRange, which the schema allows. `Composer="HL Single"` is the Adobe Single-line Composer.
   AutoSizing `HeightOnly` + `TopCenterPoint` is honoured on import (`BottomCenterPoint` made anchored frames invalid).
5. **Line breaks.** For each block, the extractor binary-searches the width window [longest line, next word fits]
   in which Chrome produces exactly the approved breaks, and sets the InDesign frame inside it. Greedy composer,
   no hyphenation, desired word spacing: with the same font files, InDesign reproduces the breaks.
6. **Baselines.** `FirstBaselineOffset=FixedHeight` + `MinimumFirstBaselineOffset` = Chrome's first-baseline offset
   (measured with a zero-size inline-block probe). Leading = the CSS line-height. In production: first baselines
   0.0000 pt off on 184 frames; 71 later baseline pairs, worst 0.0075 pt.
7. **Links.** `LinkResourceURI="file:Links/<name>"`, a relative URI. InDesign also searches the document folder
   and its `Links/` subfolder by filename.

## Deliberately avoided
- **Multiple layers:** layer order in designmap is unproven. One layer in paint order is always right.
- **Native gradient feathers and drop shadows:** untested, so they become exact PNG overlays.
- **Absolute link paths:** they would point at the build machine.

## Sources
- Adobe IDML RelaxNG (InDesign 2026): github.com/metanorma/idml `reference-docs/schemas/`
- IDML observed-schema tools: github.com/sungkhum/agent-skills (`skills/idml`)
- An open-source IDML generator's findings: github.com/Bingboom/auto-manual `tools/idml/`
- How InDesign resolves missing links in IDML: community.adobe.com (questions-671/idml-missing-links-838188)
