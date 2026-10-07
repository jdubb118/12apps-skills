// indesign-package / reference_pdf: when the job lists no reference PDFs, render the approved layout itself:
// one PDF page per HTML page at its exact canvas size (bleed included), merged per document by build.py.
// usage: node reference_pdf.mjs <work_dir>/job.resolved.json
import { createRequire } from 'module';
import fs from 'fs';
import path from 'path';
const PW = process.env.PLAYWRIGHT_REQUIRE || new URL('./package.json', import.meta.url).pathname;   // npm install in scripts/
const { chromium } = createRequire(PW)('playwright');
const job = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
if (job.reference_pdfs && job.reference_pdfs.length) { console.log('job lists reference PDFs; nothing to render'); process.exit(0); }
const O = path.join(job.work_dir, 'reference', 'pages'); fs.mkdirSync(O, { recursive: true });
const browser = await chromium.launch();
const tab = await (await browser.newContext()).newPage();
let n = 0;
for (const d of job.documents) for (const p of d.pages) {
  const ex = JSON.parse(fs.readFileSync(path.join(job.work_dir, 'extract', p.id + '.json'), 'utf8'));
  const wpx = ex.W / 0.75, hpx = ex.H / 0.75;
  await tab.setViewportSize({ width: Math.ceil(wpx), height: Math.ceil(hpx) });
  await tab.goto('file://' + path.join(job.html_root, p.html));
  await tab.evaluate(async () => { await Promise.all([...document.fonts].map(f => f.load().catch(() => null))); await document.fonts.ready;
    await Promise.all([...document.images].map(i => i.complete ? 0 : new Promise(r => { i.onload = i.onerror = r; }))); });
  // Playwright's page.pdf takes px/in, not pt; the page box is set exactly by build.py afterwards
  await tab.pdf({ path: path.join(O, `${d.idml}__${String(n).padStart(3, '0')}__${p.id}.pdf`), width: `${wpx}px`, height: `${hpx}px`, printBackground: true, pageRanges: '1' });
  n++;
}
await browser.close();
console.log(`rendered ${n} reference page(s) -> ${O}`);
