/* Dory homepage water ("Dory Descent", 27 Oct 2026): marine snow down the depth chapters, sunlight
   caustics and shafts, the pointer as Dory's lantern. WebGL2, no library. #water is transparent: it
   draws light and flakes only, the chapter colours stay in the HTML. Off without WebGL2, with
   Save-Data or without #water; draws nothing under html.motion-off (or reduced motion until the
   visitor turns motion on), in a hidden tab, or with only surface / lantern on screen.
   API: doryWater.drop(x, y) one glow flake (~2.5 s); doryWater.lantern(x, y) moves the pool. */
(() => {
  'use strict';
  const api = (window.doryWater = { drop() {}, lantern() {} });
  // chapter: [snow density 0-1, fall speed, lantern strength, caustics, shafts, light from below]
  const CH = {
    sunlight: [0.3, 1, 0.45, 0.16, 0.16, 0],
    twilight: [1, 0.9, 0.75, 0, 0, 0],
    midnight: [0.55, 0.8, 1, 0, 0, 0],
    seabed: [0.6, 0.7, 0.2, 0, 0, 0],
    ascent: [0.18, 1, 0.45, 0.07, 0.04, 1],
  };
  const NONE = [0, 1, 0];
  const MAX = 400;

  // Flakes: x, y, size (CSS px), alpha | seed, lantern pool, drop (0/1), settled (0-1)
  const VS = `#version 300 es
layout(location=0) in vec4 a;layout(location=1) in vec4 b;uniform vec3 R;out vec4 v;out float e;
void main(){gl_Position=vec4(a.x/R.x*2.-1.,1.-a.y/R.y*2.,0,1);float z=a.z*R.z*(1.+b.y*1.2);gl_PointSize=max(z,2.);v=vec4(a.w*min(1.,z*.5),b.xyz);e=b.w;}`;
  // Irregular flake, flat once settled; foam on dark fields, sand ink in the seabed band S.
  const FS = `#version 300 es
precision mediump float;in vec4 v;in float e;uniform vec2 S;out vec4 o;
void main(){vec2 p=(gl_PointCoord*2.-1.)*vec2(1,1.+e*1.2);float s=v.y*40.,t=atan(p.y,p.x+1e-4),l=length(p),
d=step(S.x,gl_FragCoord.y)*step(gl_FragCoord.y,S.y),
r=l/(.8+.12*sin(3.*t+s)+.08*sin(5.*t-s)),
m=v.x*mix(smoothstep(1.,.55,r),max(smoothstep(.4,.3,r),pow(max(1.-l,0.),2.)*.7),v.w)*(1.-.15*d);
vec3 c=mix(vec3(.92,.95,1),vec3(.36,.28,.19),d);
c=mix(c,fract(s)>.75?vec3(.37,.95,.88):vec3(1,.77,.42),min(v.z,1.)*.85*(1.-d));
c=mix(c,vec3(.37,.95,.88),v.w);m=min(m,1.);o=vec4(c*m,m);}`;
  const VL = `#version 300 es
void main(){vec2 v=vec2((gl_VertexID<<1)&2,gl_VertexID&2);gl_Position=vec4(v*2.-1.,0,1);}`;
  // Full-screen triangle scissored to a band B (bottom, top in GL px, caustic, shaft weights):
  // caustics + three slow slanted shafts, capped at alpha .12 so foam text keeps AA contrast.
  const FL = `#version 300 es
precision highp float;uniform vec4 B;uniform vec3 R;uniform float T,D;out vec4 o;
float cau(vec2 q,float t){vec2 p=mod(q,6.2832)-250.,i=p;float c=1.;for(int n=0;n<4;n++){float k=t*(1.-3.5/float(n+1));
i=p+vec2(cos(k-i.x)+sin(k+i.y),sin(k-i.y)+cos(k+i.x));
c+=1./length(vec2(p.x/(sin(i.x+k)/.005),p.y/(cos(i.y+k)/.005)));}
c=1.17-pow(c/4.,1.4);return pow(abs(c),8.);}
void main(){vec2 f=gl_FragCoord.xy;float h=clamp((f.y-B.x)/(B.y-B.x),0.,1.),w=mix(h,1.-h,D),
a=cau(vec2(f.x,B.y-f.y)/R.z/48.,T*.3+23.)*B.z*w*w,u=f.x/R.x-(1.-h)*.22,s=0.;
for(int n=0;n<3;n++){float q=float(n);
s+=exp(-pow((u-.16-q*.32-.03*sin(T*.05+q*2.))/(.03+.02*q),2.))*(.6+.4*sin(T*.21+q*1.7));}
a=min(a+s*B.w*smoothstep(0.,1.,w),.12);o=vec4(vec3(.86,.95,1)*a,a);}`;

  const start = () => {
    const cv = document.getElementById('water');
    if (!cv || (navigator.connection || {}).saveData) return;
    const gl = cv.getContext('webgl2', { antialias: false, powerPreference: 'low-power' });
    if (!gl) return;
    cv.style.width = cv.style.height = '100%'; // a fixed canvas is sized by its attributes otherwise
    const html = document.documentElement;
    const reduce = matchMedia('(prefers-reduced-motion: reduce)');
    const smallQ = matchMedia('(pointer: coarse), (max-width: 760px)');
    const hoverless = matchMedia('(hover: none)');
    const fewer = navigator.deviceMemory < 4;
    const data = new Float32Array((MAX + 8) * 8);
    let P = [], drops = [], bands = [], span = null, sea = [-1, -1], prevTop = null;
    let W = 0, H = 0, k = 1, small = false, raf = 0, last = 0, t = 0, fade = 0, measured = -1e9;
    let dead = false, clean = false, chose = false, dirty = true, needSize = true;
    let lx = 0, ly = 0, tx = 0, ty = 0, lamp = 0, hold = 0;
    let sp, lp, us, ul, vao, buf;

    const prog = (vs, fs) => {
      const p = gl.createProgram();
      for (const [type, src] of [[gl.VERTEX_SHADER, vs], [gl.FRAGMENT_SHADER, fs]]) {
        const s = gl.createShader(type);
        gl.shaderSource(s, src);
        gl.compileShader(s);
        gl.attachShader(p, s);
      }
      gl.linkProgram(p);
      return gl.getProgramParameter(p, gl.LINK_STATUS) && p;
    };
    const uni = (p, names) => Object.fromEntries(names.map((n) => [n, gl.getUniformLocation(p, n)]));
    const setup = () => {
      sp = prog(VS, FS);
      lp = prog(VL, FL);
      if (!sp || !lp) return false;
      us = uni(sp, ['R', 'S']);
      ul = uni(lp, ['B', 'R', 'T', 'D']);
      vao = gl.createVertexArray();
      gl.bindVertexArray(vao);
      buf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, data.byteLength, gl.DYNAMIC_DRAW);
      gl.enableVertexAttribArray(0);
      gl.vertexAttribPointer(0, 4, gl.FLOAT, false, 32, 0);
      gl.enableVertexAttribArray(1);
      gl.vertexAttribPointer(1, 4, gl.FLOAT, false, 32, 16);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
      gl.clearColor(0, 0, 0, 0);
      return true;
    };

    const spawn = (p, y) => {
      const s = 1.2 + Math.random() ** 3 * 6; // mostly small; big = near: faster, dimmer
      return Object.assign(p, {
        x: Math.random() * W, y, s, v: 4 + s * 4, a: (0.2 + Math.random() * 0.4) * Math.min(1, 3 / s),
        r: Math.random(), seed: Math.random(), ph: Math.random() * 6.3,
        f: 0.15 + Math.random() * 0.35, sw: 3 + s * 3, k: 0.15 + Math.random() * 0.3, L: 5 + Math.random() * 7,
        vis: 0, fade: 0, settle: 0, rest: 0,
      });
    };
    const resize = () => {
      small = smallQ.matches;
      W = cv.clientWidth || innerWidth;
      H = cv.clientHeight || innerHeight;
      k = Math.min(devicePixelRatio || 1, 1.5) * (small ? 0.5 : 1);
      cv.width = Math.round(W * k);
      cv.height = Math.round(H * k);
      gl.viewport(0, 0, cv.width, cv.height);
      const n = Math.min(MAX, Math.round(Math.max(120, (W * H) / 3600) / (fewer ? 2 : 1)));
      while (P.length < n) P.push(spawn({}, Math.random() * H));
      P.length = n;
    };
    // The only layout reads: after scroll / resize, and once a second for late reflows.
    const measure = (now) => {
      measured = now;
      dirty = false;
      bands = [];
      sea = [-1, -1];
      let top = Infinity, bot = -Infinity, first = null;
      for (const el of document.querySelectorAll('section[data-chapter]')) {
        const r = el.getBoundingClientRect(), c = CH[el.dataset.chapter];
        if (first === null) first = r.top;
        if (!c) continue;
        bands.push([r.top, r.bottom, c]);
        top = Math.min(top, r.top);
        bot = Math.max(bot, r.bottom);
        if (c === CH.seabed) sea = [(H - r.bottom) * k, (H - r.top) * k];
      }
      // parallax: small (far) flakes move less than the page, settled ones move with it
      const dy = prevTop === null || first === null ? 0 : first - prevTop;
      prevTop = first;
      if (dy && Math.abs(dy) < H) {
        for (const p of P) p.y += dy * ((0.25 + p.s * 0.12) * (1 - p.settle) + p.settle);
        for (const d of drops) d.y += dy;
      }
      span = top < H && bot > 0 ? [Math.max(0, top), Math.min(H, bot)] : null;
    };
    const clip = (top, bot) => {
      const y0 = Math.floor(Math.max(0, (H - bot) * k)), y1 = Math.ceil(Math.min(cv.height, (H - top) * k));
      gl.scissor(0, y0, cv.width, Math.max(0, y1 - y0));
      return y1 > y0;
    };

    const step = (now, dt) => {
      if (needSize) {
        needSize = false;
        resize();
        dirty = true;
      }
      if (dirty || now - measured > 1000) measure(now);
      if (!span) return stop(); // only the surface / lantern chapters on screen: clear once, idle
      t += dt;
      fade = Math.min(1, fade + dt / 0.6);
      lamp += (hold - lamp) * Math.min(1, dt * (hold ? 2.5 : 0.9));
      lx += (tx - lx) * Math.min(1, dt * 5);
      ly += (ty - ly) * Math.min(1, dt * 5);
      const rr = Math.max(110, Math.min(260, Math.min(W, H) * 0.28)) ** 2;
      let i = 0;
      for (const p of P) {
        const b = bands.find((b) => p.y >= b[0] && p.y < b[1]), c = b ? b[2] : NONE;
        p.settle = c === CH.seabed ? Math.min(1, p.settle + dt * p.k) : Math.max(0, p.settle - dt);
        const still = 1 - p.settle, dx = p.x - lx, dy = p.y - ly;
        const pool = lamp * c[2] * Math.max(0, 1 - (dx * dx + dy * dy) / rr);
        p.y += dt * p.v * c[1] * still;
        p.rest = p.settle < 1 ? 0 : p.rest + dt;
        // the lantern reveals flakes the dark hid: light catching particles, not a glow
        p.vis += (+(p.r < c[0] + pool * 0.5) - p.vis) * Math.min(1, dt * 2);
        p.fade = Math.min(1, p.fade + dt);
        const life = Math.min(1, Math.max(0, (p.L - p.rest) / 3)); // lies 2-9 s on the sand, fades 3 s
        if (!life || p.y > H + 9 || p.y < -9) {
          spawn(p, life ? (p.y < 0 ? H + 8 : -8) : Math.random() * H);
          continue;
        }
        const al = Math.min(1, p.a * p.vis * p.fade * life * fade * (1 + pool * 3));
        if (al < 0.004) continue;
        data.set([p.x + Math.sin(t * p.f + p.ph) * p.sw * still, p.y, p.s, al, p.seed, pool, 0, p.settle], i++ * 8);
      }
      drops = drops.filter((d) => (d.age += dt) < 2.5);
      for (const d of drops) {
        d.y += dt * 40 * (1 - d.age / 2.8);
        data.set([d.x, d.y, 18, fade * (1 - d.age / 2.5) ** 1.5, 0.5, 0, 1, 0], i++ * 8);
      }

      gl.disable(gl.SCISSOR_TEST);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.enable(gl.SCISSOR_TEST);
      gl.useProgram(lp);
      gl.bindVertexArray(null);
      gl.uniform3f(ul.R, cv.width, cv.height, k);
      gl.uniform1f(ul.T, t);
      for (const [top, bot, c] of bands) {
        if (!c[3] || !clip(top, bot)) continue;
        gl.uniform4f(ul.B, (H - bot) * k, (H - top) * k, c[3] * fade, c[4] * fade);
        gl.uniform1f(ul.D, c[5]);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
      }
      if (i && clip(span[0], span[1])) {
        gl.useProgram(sp);
        gl.bindVertexArray(vao);
        gl.bindBuffer(gl.ARRAY_BUFFER, buf);
        gl.bufferSubData(gl.ARRAY_BUFFER, 0, data, 0, i * 8);
        gl.uniform3f(us.R, W, H, k * (small ? 1.3 : 1)); // a little larger at half resolution
        gl.uniform2f(us.S, sea[0], sea[1]);
        gl.drawArrays(gl.POINTS, 0, i);
      }
      clean = false;
    };

    const off = () =>
      dead || document.hidden || html.classList.contains('motion-off') || (reduce.matches && !chose);
    const stop = () => {
      cancelAnimationFrame(raf);
      raf = 0;
      fade = 0;
      if (!clean) {
        gl.disable(gl.SCISSOR_TEST);
        gl.clear(gl.COLOR_BUFFER_BIT);
      }
      clean = true;
    };
    const frame = (now) => {
      raf = 0;
      if (off()) return stop();
      raf = requestAnimationFrame(frame);
      if (now - last < (small ? 30 : 14)) return; // 30 fps on phones, at most 60 elsewhere
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      try {
        step(now, dt);
      } catch (e) {
        dead = true; // never throw into the page
        stop();
      }
    };
    const kick = () => (off() ? stop() : raf || (raf = requestAnimationFrame(frame)));
    const aim = (x, y, follow) => {
      if (!follow) [lx, ly, tx, ty, lamp, hold] = [x, y, x, y, 1, 0];
      else {
        if (lamp < 0.05) [lx, ly] = [x, y];
        [tx, ty, hold] = [x, y, 1];
      }
    };

    if (!setup()) return;
    const touched = () => {
      dirty = true;
      kick();
    };
    document.addEventListener('scroll', touched, { capture: true, passive: true });
    addEventListener('resize', () => {
      needSize = true;
      touched();
    });
    document.addEventListener('visibilitychange', kick);
    reduce.addEventListener('change', () => {
      chose = false;
      kick();
    });
    // under reduced motion the page adds .motion-off; removing it is the visitor's choice
    new MutationObserver((ms) => {
      if (!html.classList.contains('motion-off') && ms.some((m) => /\bmotion-off\b/.test(m.oldValue))) chose = true;
      kick();
    }).observe(html, { attributes: true, attributeFilter: ['class'], attributeOldValue: true });
    addEventListener('pointermove', (e) => e.pointerType === 'touch' || aim(e.clientX, e.clientY, 1), { passive: true });
    addEventListener('pointerdown', (e) => e.pointerType === 'touch' && aim(e.clientX, e.clientY, 0), { passive: true });
    document.addEventListener('mouseout', (e) => e.relatedTarget || (hold = 0));
    cv.addEventListener('webglcontextlost', (e) => {
      e.preventDefault();
      dead = true;
      stop();
    });
    cv.addEventListener('webglcontextrestored', () => {
      dead = !setup();
      needSize = true;
      kick();
    });
    api.drop = (x, y) => {
      if (off() || drops.length > 7) return;
      drops.push({ x: +x || 0, y: +y || 0, age: 0 });
      kick();
    };
    api.lantern = (x, y) => aim(+x || 0, +y || 0, !hoverless.matches);
    kick();
  };

  const boot = () => {
    try {
      start();
    } catch (e) {} // no water: the page is complete without it
  };
  const idle = () => (window.requestIdleCallback ? requestIdleCallback(boot, { timeout: 1500 }) : setTimeout(boot, 200));
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', idle);
  else idle();
})();
