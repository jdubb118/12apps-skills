#!/usr/bin/env node
// Deep technical inspector for studying award-winning WebGL sites.
// Renders a URL, scrolls it, and dumps: loaded libraries, asset pipeline
// (glb/ktx2/hdr/wasm/shaders), WebGL/canvas info, scroll tech, fonts, and
// notable script sources. Output: JSON to stdout.
//
// Usage: node site-inspect.mjs <url> [--wait 6000]
// Run from this folder after `npm install` (playwright).

import { chromium } from 'playwright';

const url = process.argv[2];
const waitArg = process.argv.indexOf('--wait');
const WAIT = waitArg > -1 ? parseInt(process.argv[waitArg + 1], 10) : 6500;
if (!url) { console.error('usage: site-inspect.mjs <url>'); process.exit(1); }

const browser = await chromium.launch({
  args: ['--use-gl=angle', '--use-angle=swiftshader', '--ignore-gpu-blocklist', '--enable-webgl'],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });

const requests = [];
page.on('request', (r) => requests.push({ url: r.url(), type: r.resourceType() }));
const consoleErrs = [];
page.on('console', (m) => { if (m.type() === 'error') consoleErrs.push(m.text().slice(0, 120)); });

try {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
} catch (e) {
  console.log(JSON.stringify({ url, error: 'navigation: ' + e.message }, null, 2));
  await browser.close();
  process.exit(0);
}
await page.waitForTimeout(WAIT);
// scroll through to trigger lazy scenes
for (const f of [0.2, 0.45, 0.7, 0.95, 0]) {
  await page.evaluate((y) => window.scrollTo(0, document.body.scrollHeight * y), f).catch(() => {});
  await page.waitForTimeout(900);
}

const detected = await page.evaluate(() => {
  const w = window;
  const has = (k) => { try { return k in w && w[k] != null; } catch { return false; } };
  // canvas / webgl
  const canvases = [...document.querySelectorAll('canvas')];
  let glInfo = null;
  for (const c of canvases) {
    const gl = c.getContext('webgl2') || c.getContext('webgl');
    if (gl) {
      const dbg = gl.getExtension('WEBGL_debug_renderer_info');
      glInfo = {
        version: gl.getParameter(gl.VERSION),
        glsl: gl.getParameter(gl.SHADING_LANGUAGE_VERSION),
        renderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : null,
        maxTexture: gl.getParameter(gl.MAX_TEXTURE_SIZE),
        extensions: (gl.getSupportedExtensions() || []).filter((e) =>
          /float|compress|aniso|draw_buffers|color_buffer/i.test(e)).slice(0, 12),
      };
      break;
    }
  }
  // fonts
  const fonts = new Set();
  document.querySelectorAll('h1,h2,h3,p,body').forEach((el) => {
    try { fonts.add(getComputedStyle(el).fontFamily); } catch {}
  });
  // scroll-tech DOM fingerprints
  const attr = (sel) => document.querySelector(sel) != null;
  return {
    title: document.title,
    libGlobals: {
      THREE: has('THREE'),
      gsap: has('gsap') || has('GSAP') || has('TweenMax'),
      ScrollTrigger: has('ScrollTrigger') || (has('gsap') && !!w.gsap?.core?.globals?.()?.ScrollTrigger),
      Lenis: has('Lenis') || has('__lenis'),
      locomotive: has('LocomotiveScroll') || attr('[data-scroll-container]'),
      PIXI: has('PIXI'),
      Matter: has('Matter'),
      Rapier: has('RAPIER'),
      barba: has('barba'),
      react: has('React') || attr('#__next') || attr('[data-reactroot]') || !!document.querySelector('script[src*="react"]'),
      next: attr('#__next') || !!document.querySelector('script[src*="/_next/"]'),
      nuxt: has('__NUXT__'),
      vue: has('Vue') || attr('#__nuxt'),
      webgpu: 'gpu' in navigator,
      OGL: has('ogl'),
      curtains: has('Curtains'),
    },
    canvasCount: canvases.length,
    glInfo,
    scrollFingerprints: {
      dataScroll: attr('[data-scroll]'),
      dataLenis: attr('[data-lenis], html.lenis'),
      smoothWrapper: attr('[data-scroll-container],[data-smooth],.smooth-scroll'),
    },
    fonts: [...fonts].slice(0, 10),
    bodyBg: getComputedStyle(document.body).backgroundColor,
  };
});

// classify network assets
const assetExt = (u) => (u.split('?')[0].match(/\.[a-z0-9]+$/i) || [''])[0].toLowerCase();
const buckets = { js: [], wasm: [], models: [], textures: [], hdr: [], video: [], audio: [], fonts: [], shaders: [] };
const notableJs = new Set();
for (const r of requests) {
  const e = assetExt(r.url);
  if (['.glb', '.gltf', '.fbx', '.obj', '.draco', '.drc'].includes(e)) buckets.models.push(r.url);
  else if (['.ktx2', '.basis', '.dds'].includes(e)) buckets.textures.push(r.url);
  else if (['.hdr', '.exr', '.env'].includes(e)) buckets.hdr.push(r.url);
  else if (e === '.wasm') buckets.wasm.push(r.url);
  else if (['.mp4', '.webm', '.m4v'].includes(e)) buckets.video.push(r.url);
  else if (['.mp3', '.ogg', '.wav', '.m4a'].includes(e)) buckets.audio.push(r.url);
  else if (['.woff', '.woff2', '.ttf', '.otf'].includes(e)) buckets.fonts.push(r.url);
  else if (['.glsl', '.vert', '.frag', '.wgsl'].includes(e)) buckets.shaders.push(r.url);
  else if (e === '.js' || e === '.mjs') {
    if (/three|gsap|scrolltrigger|lenis|locomotive|pixi|ogl|tween|barba|rapier|matter|curtains|postprocessing|drei|fiber|theatre|rive|lottie|splitting|webgl|shader/i.test(r.url))
      notableJs.add(r.url.split('/').slice(-1)[0].slice(0, 60));
  }
}
const dedupe = (a) => [...new Set(a)];

console.log(JSON.stringify({
  url,
  title: detected.title,
  stack: detected.libGlobals,
  canvasCount: detected.canvasCount,
  webgl: detected.glInfo,
  scroll: detected.scrollFingerprints,
  fonts: detected.fonts,
  bodyBg: detected.bodyBg,
  assets: {
    models: dedupe(buckets.models).slice(0, 10),
    compressedTextures: dedupe(buckets.textures).slice(0, 6),
    hdrEnv: dedupe(buckets.hdr).slice(0, 6),
    wasm: dedupe(buckets.wasm).slice(0, 6),
    video: dedupe(buckets.video).slice(0, 6),
    audio: dedupe(buckets.audio).slice(0, 4),
    externalShaders: dedupe(buckets.shaders).slice(0, 6),
    fontFiles: dedupe(buckets.fonts).slice(0, 6),
  },
  notableLibScripts: [...notableJs].slice(0, 20),
  totalRequests: requests.length,
  consoleErrors: consoleErrs.slice(0, 4),
}, null, 2));

await browser.close();
