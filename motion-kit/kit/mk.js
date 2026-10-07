/* motion-kit — mk.js
   Helpers for deterministic HyperFrames + GSAP compositions (9:16 motion graphics, timed to music).
   Contract (HyperFrames renders by SEEKING every frame):
     · ONE paused gsap timeline, registered LAST via MK.finish(tl).
     · Everything placed at ABSOLUTE times. No clocks, no Math.random, no onUpdate (callbacks can be
       suppressed on seek — HyperFrames' own docs ban them). Procedural motion goes through an EASE
       function: GSAP evaluates eases on every render, so MK.driver() is seek-safe.
     · Measure layout once (after document.fonts.ready), before any tween touches a transform.
   GSAP names eases by power, not degree: power1=quad, power2=CUBIC, power3=QUART, power4=quint. */
(function () {
  const MK = {};
  MK.W = 1080; MK.H = 1920; MK.FPS = 30;
  MK.$ = id => document.getElementById(id);
  MK.place = (el, x, y) => { el.style.left = x + "px"; el.style.top = y + "px"; return el; };
  MK.size = (el, w, h) => { el.style.width = w + "px"; if (h != null) el.style.height = h + "px"; return el; };
  MK.el = (tag, cls, parent, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; if (parent) parent.appendChild(e); return e; };
  MK.clamp01 = u => u < 0 ? 0 : u > 1 ? 1 : u;
  MK.lerp = (a, b, u) => a + (b - a) * u;
  // pure eases (u in 0..1) for driver maths — names say the DEGREE
  MK.e = {
    lin: u => u,
    smooth: u => u * u * (3 - 2 * u),
    out3: u => 1 - Math.pow(1 - u, 3), in3: u => u * u * u,
    inOut3: u => u < .5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2,
    out4: u => 1 - Math.pow(1 - u, 4), in4: u => u * u * u * u,
    inOut4: u => u < .5 ? 8 * u * u * u * u : 1 - Math.pow(-2 * u + 2, 4) / 2,
    out5: u => 1 - Math.pow(1 - u, 5),
    inOut5: u => u < .5 ? 16 * Math.pow(u, 5) : 1 - Math.pow(-2 * u + 2, 5) / 2,
    sine: u => -(Math.cos(Math.PI * u) - 1) / 2,
  };
  MK.seg = (t, t0, t1, ease) => (ease || MK.e.lin)(MK.clamp01((t - t0) / (t1 - t0)));

  // ── sound: declare every audible event where it happens. scripts/cues.py dumps MK.cues,
  //    scripts/sfx.py synthesizes them. Never hand-copy times into the sound script.
  MK.cues = [];
  MK.cue = (t, kind, o) => { MK.cues.push(Object.assign({ t: Math.round(t * 1e4) / 1e4, kind }, o || {})); };

  // ── initial states: applied NOW (frame 0 — a zero-duration set at 0 does not render while the playhead
  //    sits at 0) AND on the timeline at 0 (so a backward seek restores them). Use for every hidden start.
  MK.hide = (tl, targets, vars) => { gsap.set(targets, vars); tl.set(targets, vars, 0); };

  // ── a procedural driver: fn(t) runs on EVERY seek with the composition time t.
  MK.driver = (tl, dur, fn) => {
    const proxy = { v: 0 };
    tl.fromTo(proxy, { v: 0 }, { v: 1, duration: dur, immediateRender: false, ease: p => { fn(p * dur); return p; } }, 0);
  };

  // ── stacked headline: each line in its own overflow mask. o = {x, y, width, size (max), accent: index|[i],
  //    color, accentColor, leading (px between masks), weight}. Font size is FIT so the widest line = width.
  MK.headline = (parent, lines, o) => {
    const box = MK.el("div", "abs", parent); MK.place(box, o.x, o.y);
    const acc = [].concat(o.accent == null ? [] : o.accent);
    const els = lines.map((txt, i) => {
      const m = MK.el("div", "m", box); const ln = MK.el("div", "ln", m); ln.textContent = txt;
      if (acc.includes(i)) ln.style.color = o.accentColor || "var(--accent)"; else if (o.color) ln.style.color = o.color;
      return ln;
    });
    box.style.fontSize = "100px";
    const wmax = Math.max(...els.map(e => e.getBoundingClientRect().width));
    const size = Math.min(o.size || 999, 100 * o.width / wmax);
    box.style.fontSize = size + "px";
    if (o.leading != null) [...box.children].forEach((m, i) => { if (i) m.style.marginTop = o.leading + "px"; });
    return { box, lines: els, size, height: box.getBoundingClientRect().height };
  };
  // lines rise out of their masks. Optional weight tween on a variable font: {from: 300, to: 650}
  MK.linesIn = (tl, els, t, o) => {
    o = o || {}; const st = o.stagger ?? 0.11, w0 = o.from ?? null, w1 = o.to ?? null;
    els.forEach((el, i) => {
      const ti = t + i * st;
      MK.hide(tl, el, { yPercent: 108 });                              // hidden from frame 0 (any seek order)
      tl.fromTo(el, { yPercent: 108 }, { yPercent: 0, duration: o.dur ?? 0.62, ease: "expo.out", immediateRender: false }, ti);
      if (w0 != null && w1 != null)
        tl.fromTo(el, { fontVariationSettings: `"wght" ${w0}` }, { fontVariationSettings: `"wght" ${w1}`, duration: 0.8, ease: "power3.out", immediateRender: false }, ti);
      if (o.cue !== false) MK.cue(ti + 0.03, o.cue || "type", { i });
    });
    return t + (els.length - 1) * st + (o.dur ?? 0.62);
  };
  MK.linesOut = (tl, els, t, o) => {
    o = o || {};
    tl.to(els, { yPercent: -108, duration: o.dur ?? 0.34, ease: "power3.in", stagger: o.stagger ?? 0.045 }, t);
    if (o.cue !== false) MK.cue(t + 0.12, "out");
  };
  // distance from an element's box top to the top of its CAPITALS (ink), so a word can be placed where
  // scripts/wordfit.py measured it. The element must contain a <span class="bl"></span> baseline marker.
  MK.inkTop = el => {
    const bl = el.querySelector(".bl"), base = bl.getBoundingClientRect().top - el.getBoundingClientRect().top;
    const cs = getComputedStyle(el), c = document.createElement("canvas").getContext("2d");
    c.font = `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
    return base - c.measureText(el.textContent.trim().toUpperCase()).actualBoundingBoxAscent;
  };
  // label: fades in while its letter-spacing settles (px + autoRound:false — GSAP rounds letterSpacing otherwise)
  MK.label = (parent, text, o) => {
    const e = MK.el("div", "lbl abs", parent); e.textContent = text; o = o || {};
    if (o.size) { e.style.fontSize = o.size + "px"; e.style.letterSpacing = (o.size * (o.track ?? 0.02)) + "px"; }
    if (o.color) e.style.color = o.color;
    if (o.x != null) MK.place(e, o.x, o.y);
    return e;
  };
  MK.labelIn = (tl, el, t, o) => {
    o = o || {}; const fs = parseFloat(getComputedStyle(el).fontSize), tr = fs * (o.track ?? 0.02);
    MK.hide(tl, el, { opacity: 0 });
    tl.fromTo(el, { opacity: 0, letterSpacing: tr + fs * 0.12 + "px" }, { opacity: o.opacity ?? 1, letterSpacing: tr + "px", duration: 0.9, ease: "power3.out", autoRound: false, immediateRender: false }, t);
    if (o.cue !== false) MK.cue(t + 0.02, "tick", { g: 0.6 });
  };
  // stroke-draw SVG paths/lines (dash = measured length)
  MK.draw = (tl, paths, t, dur, o) => {
    o = o || {};
    paths.forEach((p, i) => {
      const L = Math.ceil(p.getTotalLength()) + 2;
      MK.hide(tl, p, { strokeDasharray: L, strokeDashoffset: L });
      tl.fromTo(p, { strokeDasharray: L, strokeDashoffset: L }, { strokeDashoffset: 0, duration: dur, ease: o.ease || "power2.inOut", immediateRender: false }, t + i * (o.stagger || 0));
    });
    if (o.cue !== false) MK.cue(t, "draw", { d: dur });
  };
  // THE LINE WIPE — the house transition. The accent line drops down the frame and the next scene is
  // revealed ABOVE it. Its hit (the fastest frame) is the MIDDLE of the sweep: centre that on the beat.
  // layer must be a .full element.
  MK.wipe = (tl, line, layer, t, o) => {
    o = o || {}; const d = o.dur ?? 0.58, H = MK.H;
    MK.hide(tl, layer, { clipPath: "inset(0px 0px 1920px 0px)" });
    MK.hide(tl, line, { opacity: 0 });
    tl.fromTo(layer, { clipPath: "inset(0px 0px 1920px 0px)" }, { clipPath: "inset(0px 0px 0px 0px)", duration: d, ease: "power3.inOut", immediateRender: false }, t)
      .fromTo(line, { y: -4, opacity: 1 }, { y: H + 4, duration: d, ease: "power3.inOut", immediateRender: false }, t)
      .set(line, { opacity: 0 }, t + d);
    tl.set(line, { opacity: 1 }, t);
    if (o.cue !== false) MK.cue(t, "wipe", { d });
  };
  // film grain: a new offset every frame, pure function of the frame index
  MK.grain = (tl, el, dur) => {
    const hash = k => { const s = Math.sin(k * 12.9898 + 78.233) * 43758.5453; return s - Math.floor(s); };
    tl.fromTo(el, { backgroundPositionX: "0px" }, { backgroundPositionX: "256px", duration: dur, ease: p => hash(Math.floor(p * dur * MK.FPS)), immediateRender: false }, 0)
      .fromTo(el, { backgroundPositionY: "0px" }, { backgroundPositionY: "256px", duration: dur, ease: p => hash(Math.floor(p * dur * MK.FPS) + 999), immediateRender: false }, 0);
  };
  // call LAST, right after the composition registers its timeline IN ITS OWN SOURCE (HyperFrames lint
  // looks for the literal `window.__timelines["main"] = tl`): exposes cues + debug numbers for the gates.
  MK.finish = (tl, debug) => {
    window.__mk = Object.assign({ cues: MK.cues, duration: tl.duration() }, debug || {});
    if (window.__hfForceTimelineRebind) window.__hfForceTimelineRebind();
    window.__mkReady = true;
  };
  // a HARD cut that must land on a beat: with the 240-fps motion blur (4 sub-frames averaged per output
  // frame) a cut exactly ON the beat blends both shots into the beat frame. Move it 4 sub-frames early.
  MK.hard = t => t - 4 / 240;
  window.MK = MK;
})();
