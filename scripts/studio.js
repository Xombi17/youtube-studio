// studio.js: deterministic single clock for CreatorRadar HTML5/GSAP scenes.
// Load after GSAP and before the scene script.
// Scene calls STUDIO.play(render). render(t) must draw the whole frame from t alone.
(function () {
  const R = () => document.querySelector('[data-composition-id]');
  const num = (k) => +R().dataset[k];
  const cache = {};
  const S = {
    get root() { return R(); },
    get D() { return num('duration'); },
    get W() { return num('width'); },
    get H() { return num('height'); },
    get V() { return S.H > S.W; },
    get u() { return Math.min(S.W, S.H) / 1080; },
    ease(name) { return cache[name] || (cache[name] = name === 'none' ? (p) => p : gsap.parseEase(name)); },
    seg(t, start, dur, ease) {
      if (dur <= 0) return t >= start ? 1 : 0;
      const p = Math.min(1, Math.max(0, (t - start) / dur));
      return S.ease(ease || 'power3.out')(p);
    },
    mix(a, b, p) { return a + (b - a) * p; },
    wave(t, cycles, offset) { return Math.sin(2 * Math.PI * ((cycles || 1) * t / S.D + (offset || 0))); },
    rng(seed) {
      let a = seed >>> 0;
      return function () {
        a = (a + 0x6d2b79f5) | 0;
        let t = Math.imul(a ^ (a >>> 15), 1 | a);
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
      };
    },
    play(render, opts) {
      const loop = !opts || opts.loop !== false;
      const D = S.D, root = S.root;
      const clock = { t: 0 };
      const tl = gsap.timeline({ paused: true });
      const wrap = loop && !window.STUDIO_NO_WRAP;
      const draw = () => render(wrap ? clock.t % D : Math.min(D, Math.max(0, clock.t)));
      tl.to(clock, { t: D, duration: D, ease: 'none', onUpdate: draw }, 0);
      draw();
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(draw);
      window.addEventListener('load', draw);
      window.__timelines = window.__timelines || {};
      window.__timelines[root.dataset.compositionId] = tl;
      window.__studioRender = render;
      return tl;
    },
  };
  window.STUDIO = S;
})();
