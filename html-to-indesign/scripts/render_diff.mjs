// indesign-package / render_diff: screenshot each approved page and its IDML re-render (1 css px = 0.75 pt).
// usage: node render_diff.mjs <pages.json> <out_dir>
import { createRequire } from 'module';
import fs from 'fs';
const PW = process.env.PLAYWRIGHT_REQUIRE || new URL('./package.json', import.meta.url).pathname;   // npm install in scripts/
const { chromium } = createRequire(PW)('playwright');
const pages = JSON.parse(fs.readFileSync(process.argv[2], 'utf8')); const O = process.argv[3];
const browser = await chromium.launch();
const tab = await (await browser.newContext({ deviceScaleFactor: 1 })).newPage();
const settle = () => tab.evaluate(async () => {
  await Promise.all([...document.fonts].map(f => f.load().catch(() => null))); await document.fonts.ready;
  await Promise.all([...document.images].map(i => i.complete ? 0 : new Promise(r => { i.onload = i.onerror = r; })));
  return [...document.images].filter(i => !(i.complete && i.naturalWidth)).map(i => i.src);
});
for (const p of pages) {
  await tab.setViewportSize({ width: Math.ceil(p.W / 0.75), height: Math.ceil(p.H / 0.75) });
  await tab.goto('file://' + p.src); let bad = await settle();
  if (bad.length) console.log('SOURCE IMAGES MISSING', p.id, bad);
  await tab.screenshot({ path: `${O}/${p.id}_src.png` });
  await tab.goto('file://' + p.idml); bad = await settle();
  await tab.evaluate(() => {   // FixedHeight first baseline: pin the first baseline to frame top + MinimumFirstBaselineOffset
    for (const tf of document.querySelectorAll('.tf')) { const pr = tf.querySelector('.probe'); tf.style.marginTop = (parseFloat(tf.dataset.d) / 0.75 - pr.offsetTop) + 'px'; }
  });
  if (bad.length) console.log('LINKS MISSING', p.id, bad);
  await tab.screenshot({ path: `${O}/${p.id}_idml.png` });
}
await browser.close();
