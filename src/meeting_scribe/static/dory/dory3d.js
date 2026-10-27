// Dory in 3D: an original procedural model for the homepage hero (no downloaded models or textures).
// Contract: mounts a transparent canvas in #dory3d on capable devices, adds `is-3d` after the first
// frame and dispatches `dory3d:ready`; the <picture> inside stays as the fallback. Tests:
// tests/test_dory3d.py.
const THREE_URL = 'https://cdn.jsdelivr.net/npm/three@0.185.0/build/three.module.min.js';
const POSTER = new URL(import.meta.url).searchParams.has('poster'); // render one still (dory3d-poster.webp)
const host = document.getElementById('dory3d');
const html = document.documentElement;
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const motionOff = () => html.classList.contains('motion-off');
const R = Math.PI / 180;

function capable() {
  const n = navigator;
  if (n.connection && n.connection.saveData) return false;
  if (n.deviceMemory && n.deviceMemory < 4) return false;
  return (n.hardwareConcurrency || 0) >= 4 && 'WebGL2RenderingContext' in window;
}

// ---------- the model ----------
function buildDory(T) {
  const disposables = [];
  const keep = (x) => (disposables.push(x), x);
  const col = (h) => new T.Color(h);
  const std = (o) => keep(new T.MeshStandardMaterial(o));
  const glow = (h) => keep(new T.MeshBasicMaterial({ color: h, toneMapped: false }));
  const mesh = (g, m) => new T.Mesh(keep(g), m);
  const ss = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
  const V = (x, y, z) => new T.Vector3(x, y, z);

  // Body: unit sphere, laterally flattened, tapered into a short peduncle behind (forward = +Z, left = +X).
  const deform = (x, y, z) => {
    const t = z < 0 ? -z : 0, k = 1 - 0.52 * Math.pow(t, 2.2);
    return V(x * 0.9 * k, y * k, z * (1 + 0.3 * t));
  };
  const surf = (d) => { const u = d.clone().normalize(); return deform(u.x, u.y, u.z); };
  const frame = (d) => { // point, normal, tangent (+X side) and up tangent at original direction d
    const u = d.clone().normalize(), t = V(0, 1, 0).cross(u).normalize();
    if (t.lengthSq() < 1e-6) t.set(1, 0, 0);
    const b = u.clone().cross(t).normalize(), e = 0.01;
    const p = surf(u);
    const n = surf(u.clone().addScaledVector(t, e)).sub(surf(u.clone().addScaledVector(t, -e)))
      .cross(surf(u.clone().addScaledVector(b, e)).sub(surf(u.clone().addScaledVector(b, -e)))).normalize();
    return { p, n, t, b, u };
  };
  const capLine = (z) => 0.14 + 0.55 * z; // blue back above this height (unit-sphere space)
  const cheeks = [V(0.6, -0.2, 0.76), V(-0.6, -0.2, 0.76)].map((v) => v.normalize());

  const root = new T.Group();
  const swim = new T.Group(); // hover + look + tilt act here
  root.add(swim);

  const bodyGeo = new T.SphereGeometry(1, 72, 54);
  {
    const pos = bodyGeo.attributes.position, c = [], white = col('#FFFFFF'), belly = col('#D9E4F7');
    const blueHi = col('#3C74EE'), blueLo = col('#1734A0'), line = col('#E6F3FF'), blush = col('#FF9FAE');
    const tmp = new T.Color();
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i), y = pos.getY(i), z = pos.getZ(i);
      const edge = capLine(z), m = ss(-0.035, 0.035, y - edge);
      tmp.copy(white).lerp(belly, ss(0.1, -1, y) * 0.55);
      tmp.lerp(blueHi.clone().lerp(blueLo, ss(edge + 0.05, 1, y)), m);
      tmp.lerp(line, (1 - ss(0, 0.05, Math.abs(y - edge - 0.045))) * 0.55);
      for (const ch of cheeks) {
        const d = Math.hypot(x - ch.x, (y - ch.y) * 1.6, z - ch.z);
        tmp.lerp(blush, (1 - ss(0.03, 0.27, d)) * 0.85);
      }
      c.push(tmp.r, tmp.g, tmp.b);
      const p = deform(x, y, z);
      pos.setXYZ(i, p.x, p.y, p.z);
    }
    bodyGeo.setAttribute('color', new T.Float32BufferAttribute(c, 3));
    bodyGeo.computeVertexNormals();
  }
  const body = mesh(bodyGeo, keep(new T.MeshPhysicalMaterial({
    vertexColors: true, roughness: 0.45, sheen: 0.7, sheenRoughness: 0.45, sheenColor: col('#BFE6FF'),
  })));
  swim.add(body);

  // Photophores: two loose rows of glowing dots along the blue back, both sides.
  {
    const pts = [];
    for (const s of [1, -1]) {
      for (let k = 0; k < 14; k++) {
        const z = 0.62 - k * 0.11 + (k % 2) * 0.03;
        for (const [off, every] of [[0.08, 1], [0.2, 1], [0.34, 2], [0.5, 2], [0.68, 3]]) {
          if (k % every) continue;
          const y = capLine(z) + off, xx = 1 - y * y - z * z;
          if (xx > 0.02) pts.push(V(s * Math.sqrt(xx), y, z));
        }
      }
    }
    const dot = keep(new T.SphereGeometry(1, 8, 6));
    const core = new T.InstancedMesh(dot, glow('#A6FFF3'), pts.length);
    const halo = new T.InstancedMesh(dot, keep(new T.MeshBasicMaterial({
      color: '#5FF2E0', transparent: true, opacity: 0.28, depthWrite: false, blending: T.AdditiveBlending,
    })), pts.length);
    const m4 = new T.Matrix4(), q = new T.Quaternion();
    pts.forEach((d, i) => {
      const p = surf(d), r = 0.014 + 0.007 * Math.sin(i * 2.3);
      core.setMatrixAt(i, m4.compose(p, q, V(r, r, r)));
      halo.setMatrixAt(i, m4.compose(p, q, V(r * 2.6, r * 2.6, r * 2.6)));
    });
    swim.add(core, halo);
  }

  // Fins: a fan of rays from a root segment; pleated, cupped, blue -> lavender -> peach, ray streaks.
  const finMat = keep(new T.MeshStandardMaterial({
    vertexColors: true, transparent: true, side: T.DoubleSide, roughness: 0.3,
  }));
  finMat.onBeforeCompile = (sh) => { // the membrane glows with its own colour, like the painting
    sh.fragmentShader = sh.fragmentShader.replace('#include <emissivemap_fragment>',
      '#include <emissivemap_fragment>\n totalEmissiveRadiance += vColor.rgb * 0.42;');
  };
  const finBlue = col('#2457EE'), finLav = col('#C3A4F2'), finPeach = col('#FFC497'), finWhite = col('#FFFFFF');
  function fin({ p0, p1, a0, a1, len, bend = () => 0, n = 44, m = 12, cup = 0.12, pleat = 0.025, rays = 7 }) {
    const pos = [], c = [], idx = [], tmp = new T.Color();
    for (let i = 0; i <= n; i++) {
      const f = i / n, a = a0 + (a1 - a0) * f, L = len(f), bf = bend(f);
      const rx = p0[0] + (p1[0] - p0[0]) * f, ry = p0[1] + (p1[1] - p0[1]) * f;
      const ray = Math.pow(0.5 + 0.5 * Math.cos(f * rays * 2 * Math.PI), 6);
      for (let j = 0; j <= m; j++) {
        const s = j / m;
        const ab = a + bf * s; // rays curve as they grow: flowing, not a rigid fan
        pos.push(rx + Math.cos(ab) * L * s, ry + Math.sin(ab) * L * s,
          cup * s * s * Math.sin(Math.PI * f) + 0.6 * pleat * s * Math.cos(f * rays * 2 * Math.PI)); // soft pleats: silk, not a shell
        tmp.copy(finBlue).lerp(finLav, ss(0.35, 0.75, s) * (0.7 + 0.3 * f)).lerp(finPeach, ss(0.5, 1, s) * (0.8 + 0.2 * f));
        tmp.lerp(finWhite, ray * 0.24 * ss(0.1, 0.6, s) + ss(0.92, 1, s) * 0.3);
        c.push(tmp.r, tmp.g, tmp.b, 0.96 - 0.24 * ss(0.3, 1, s));
        if (i < n && j < m) {
          const k = i * (m + 1) + j;
          idx.push(k, k + m + 1, k + 1, k + 1, k + m + 1, k + m + 2);
        }
      }
    }
    const g = new T.BufferGeometry();
    g.setAttribute('position', new T.Float32BufferAttribute(pos, 3));
    g.setAttribute('color', new T.Float32BufferAttribute(c, 4));
    g.setIndex(idx);
    g.computeVertexNormals();
    return mesh(g, finMat);
  }
  const sinp = (f, e = 1) => Math.pow(Math.sin(Math.PI * f), e);
  const bump = (f, at, w) => Math.exp(-(((f - at) / w) ** 2));
  // A fin lives in its pivot's XY plane; the pivot is posed with a basis (x = rays' main direction).
  const mount = (m, at, ex, ey) => {
    const pivot = new T.Group(), x = ex.clone().normalize();
    const y = ey.clone().addScaledVector(x, -ey.dot(x)).normalize();
    pivot.quaternion.setFromRotationMatrix(new T.Matrix4().makeBasis(x, y, x.clone().cross(y)));
    pivot.position.copy(at);
    pivot.add(m);
    swim.add(pivot);
    return m;
  };
  const caudal = mount(fin({
    p0: [0, -0.18], p1: [0, 0.18], a0: -0.7, a1: 0.74, n: 64, cup: 0.14, pleat: 0.02, rays: 9,
    len: (f) => 1.3 * (0.55 + 0.6 * (bump(f, 0.2, 0.2) + 0.9 * bump(f, 0.8, 0.2)) + 0.5 * (bump(f, 0.1, 0.06) + 0.9 * bump(f, 0.9, 0.06))),
    bend: (f) => (f - 0.5) * 0.7,
  }), V(0, 0.02, -1.15), V(-0.85, 0, -1), V(0, 1, 0));
  const dorsal = mount(fin({
    p0: [-0.25, 0], p1: [0.7, -0.55], a0: 1.75, a1: 0.3, n: 52, cup: 0.08, pleat: 0.018, rays: 8,
    len: (f) => 0.3 + 0.95 * sinp(Math.min(1, f * 1.25), 0.6) * (1 - 0.4 * f) + 0.62 * bump(f, 0.34, 0.07),
    bend: () => -0.45,
  }), V(0, 0.97, 0.05), V(-0.22, 0, -1), V(0, 1, 0));
  const anal = mount(fin({
    p0: [0, 0], p1: [0.4, 0.14], a0: -1.8, a1: -0.5, n: 32, m: 9, cup: 0.06, pleat: 0.015, rays: 5,
    len: (f) => 0.4 + 0.45 * sinp(f, 0.8), bend: () => -0.3,
  }), V(0, -0.62, -0.45), V(0, 0, -1), V(0, 1, 0));
  const pecs = [1, -1].map((s) => mount(fin({
    p0: [-0.08, 0], p1: [0.18, 0.02], a0: 0.05, a1: 1.5, n: 44, m: 11, cup: 0.12, pleat: 0.016, rays: 6,
    len: (f) => 0.65 + 0.38 * sinp(f, 0.7) + 0.15 * f + 0.55 * bump(f, 0.1, 0.07), bend: (f) => -0.3 * (1 - f),
  }), frame(V(s * 0.8, -0.45, 0.25)).p.multiplyScalar(0.96), V(0, -0.45, -1), V(s * 0.45, -1, 0.3)));

  // Eyes: tall glossy sclera, painted iris cap (canvas), lash line, three lashes; blink squashes.
  const cv = (w, h, draw) => {
    const c = document.createElement('canvas');
    c.width = w; c.height = h;
    draw(c.getContext('2d'));
    const t = keep(new T.CanvasTexture(c));
    t.colorSpace = T.SRGBColorSpace;
    t.anisotropy = 4;
    return t;
  };
  const irisTex = cv(256, 256, (g) => {
    const lin = g.createLinearGradient(0, 8, 0, 248);
    lin.addColorStop(0, '#0B1D5C'); lin.addColorStop(0.5, '#1E4FC4'); lin.addColorStop(1, '#6CB4FF');
    g.fillStyle = '#0A1640'; g.beginPath(); g.arc(128, 128, 126, 0, 7); g.fill();
    g.fillStyle = lin; g.beginPath(); g.arc(128, 128, 116, 0, 7); g.fill();
    g.fillStyle = '#050A1E'; g.beginPath(); g.arc(128, 122, 62, 0, 7); g.fill();
    g.fillStyle = '#FFFFFF'; g.beginPath(); g.ellipse(84, 78, 34, 30, -0.5, 0, 7); g.fill();
    g.beginPath(); g.arc(170, 178, 14, 0, 7); g.fill();
  });
  const irisMat = keep(new T.MeshPhysicalMaterial({ map: irisTex, roughness: 0.15, clearcoat: 1 }));
  const scleraMat = keep(new T.MeshPhysicalMaterial({ color: '#FFFFFF', roughness: 0.2, clearcoat: 1 }));
  const navy = std({ color: '#14244F', roughness: 0.5 });
  const IRIS = 1.02; // iris cap half-angle (rad) on the unit eyeball
  const irisGeo = keep(new T.SphereGeometry(1.012, 40, 16, 0, Math.PI * 2, 0, IRIS).rotateX(Math.PI / 2));
  {
    const p = irisGeo.attributes.position, uv = irisGeo.attributes.uv, k = 1 / (2 * Math.sin(IRIS));
    for (let i = 0; i < p.count; i++) uv.setXY(i, 0.5 + p.getX(i) * k, 0.5 + p.getY(i) * k);
  }
  const eyes = [1, -1].map((s) => {
    const far = s > 0, f = frame(far ? V(0.47, 0.2, 0.86) : V(-0.6, 0.2, 0.77)); // her left eye is the far one in the hero pose
    const z = f.n.clone().lerp(V(0, 0, 1), far ? 0.2 : 0.3).normalize(); // far eye sits on the face curve, inside the outline
    const x = V(0, 1, 0).cross(z).normalize(), y = z.clone().cross(x);
    const g = new T.Group();
    g.quaternion.setFromRotationMatrix(new T.Matrix4().makeBasis(x, y, z));
    g.position.copy(f.p).addScaledVector(f.n, far ? -0.12 : -0.1);
    const ball = new T.Group(); // non-uniform scale: tall oval, shallow
    ball.scale.set(0.33, 0.38, 0.17);
    g.add(ball);
    ball.add(mesh(new T.SphereGeometry(1, 40, 28), scleraMat));
    const look = new T.Group();
    look.add(new T.Mesh(irisGeo, irisMat));
    ball.add(look);
    const arc = [];
    for (let i = 0; i <= 24; i++) {
      const a = (8 + 166 * i / 24) * R;
      arc.push(V(Math.cos(a) * 1.02, Math.sin(a) * 1.02, 0.28));
    }
    ball.add(mesh(new T.TubeGeometry(new T.CatmullRomCurve3(arc), 32, 0.09, 6), navy));
    for (let k = 0; k < 3; k++) {
      const a = (18 + k * 17) * R, ox = s * Math.cos(a), oy = Math.sin(a);
      const lash = mesh(new T.ConeGeometry(0.075, 0.42, 6), navy);
      lash.position.set(ox * 1.12, oy * 1.12, 0.26);
      lash.rotation.z = Math.atan2(oy, ox) - Math.PI / 2 + s * 0.35;
      ball.add(lash);
    }
    // Brow: a thin arc on the skin above the eye.
    const brow = [];
    for (let i = 0; i <= 12; i++) {
      const u = i / 12 - 0.5;
      const d = f.u.clone().addScaledVector(f.t, u * 0.36).addScaledVector(f.b, 0.42 + 0.05 * (1 - 4 * u * u));
      brow.push(surf(d).multiplyScalar(1.012));
    }
    swim.add(mesh(new T.TubeGeometry(new T.CatmullRomCurve3(brow), 16, 0.016, 5), navy));
    swim.add(g);
    return { g, ball, look, s };
  });

  // Mouth: open smile with tongue, a canvas decal wrapped onto the face.
  {
    const tex = cv(256, 160, (g) => {
      const path = new Path2D('M18 36Q128 58 238 36C236 120 190 150 128 150C66 150 20 120 18 36Z');
      const grad = g.createLinearGradient(0, 30, 0, 150);
      grad.addColorStop(0, '#3E0A1C'); grad.addColorStop(0.5, '#8E2440'); grad.addColorStop(1, '#B23A55');
      g.fillStyle = grad; g.fill(path);
      g.save(); g.clip(path);
      const tongue = g.createRadialGradient(126, 128, 8, 136, 152, 96);
      tongue.addColorStop(0, '#FFA3B1'); tongue.addColorStop(1, '#E35E78');
      g.fillStyle = tongue; g.beginPath(); g.ellipse(136, 152, 92, 60, 0, 0, 7); g.fill();
      g.fillStyle = 'rgba(255,255,255,.4)'; g.beginPath(); g.ellipse(118, 120, 24, 8, -0.1, 0, 7); g.fill();
      const lip = g.createLinearGradient(0, 34, 0, 76); // the upper lip's shadow gives the mouth depth
      lip.addColorStop(0, 'rgba(20,0,10,.6)'); lip.addColorStop(1, 'rgba(20,0,10,0)');
      g.fillStyle = lip; g.fillRect(0, 0, 256, 80);
      g.restore();
      g.lineWidth = 7; g.lineJoin = 'round'; g.lineCap = 'round'; g.strokeStyle = '#1A2F5C'; g.stroke(path);
      g.lineWidth = 6; g.stroke(new Path2D('M8 27Q15 38 24 42M248 27Q241 38 232 42')); // corner tucks
    });
    const f = frame(V(-0.1, -0.4, 0.91)), W = 0.74, H = 0.46, geo = keep(new T.PlaneGeometry(W, H, 20, 12));
    const p = geo.attributes.position;
    for (let i = 0; i < p.count; i++) {
      const d = f.u.clone().addScaledVector(f.t, p.getX(i)).addScaledVector(f.b, p.getY(i));
      p.setXYZ(i, ...surf(d).multiplyScalar(1.006).toArray());
    }
    geo.computeVertexNormals();
    swim.add(new T.Mesh(geo, keep(new T.MeshStandardMaterial({
      map: tex, transparent: true, roughness: 0.4, polygonOffset: true, polygonOffsetFactor: -2,
    }))));
  }

  // Headset: band over the crown, two ear cups (white shell, navy face, cyan ring + bars), boom mic.
  const white = std({ color: '#F4F7FD', roughness: 0.28, metalness: 0.05 });
  const ringMat = glow('#5FF2E0'), ringBase = ringMat.color.clone();
  const cups = [1, -1].map((s) => {
    const f = frame(V(s * 0.97, 0.16, -0.12));
    const g = new T.Group();
    g.position.copy(f.p).addScaledVector(f.n, 0.04);
    g.quaternion.setFromUnitVectors(V(0, 0, 1), f.n);
    g.scale.setScalar(1.12);
    const shell = mesh(new T.CylinderGeometry(0.3, 0.33, 0.16, 48).rotateX(Math.PI / 2), white);
    const rim = mesh(new T.TorusGeometry(0.3, 0.05, 12, 48), white);
    rim.position.z = 0.08;
    const face = mesh(new T.CircleGeometry(0.26, 48), std({ color: '#0E1C44', roughness: 0.35 }));
    face.position.z = 0.1;
    const ring = mesh(new T.TorusGeometry(0.215, 0.02, 8, 64), ringMat);
    ring.position.z = 0.105;
    g.add(shell, rim, face, ring);
    [[-0.085, 0.09], [0, 0.17], [0.085, 0.09]].forEach(([x, h]) => {
      const bar = mesh(new T.CapsuleGeometry(0.02, h, 4, 8), ringMat);
      bar.position.set(x, 0, 0.11);
      g.add(bar);
    });
    swim.add(g);
    return { g, f };
  });
  {
    const a = cups[0].g.position, b = cups[1].g.position, arc = [];
    for (let i = 0; i <= 24; i++) {
      const t = (i / 24) * Math.PI, d = V(Math.cos(t) * 0.97, 0.16 + Math.sin(t) * 0.9, -0.12 + 0.12 * Math.sin(t));
      arc.push(i === 0 ? a.clone() : i === 24 ? b.clone() : surf(d).multiplyScalar(1.05));
    }
    swim.add(mesh(new T.TubeGeometry(new T.CatmullRomCurve3(arc), 48, 0.065, 8), white));
    // Boom mic on her right (the side that faces the viewer in the hero pose).
    const c = cups[1], start = c.g.position.clone().add(V(0.02, -0.22, 0.1));
    const end = frame(V(-0.78, -0.3, 0.52)).p.multiplyScalar(1.12);
    const boom = new T.CatmullRomCurve3([start, start.clone().lerp(end, 0.5).add(V(-0.08, -0.1, 0)), end]);
    swim.add(mesh(new T.TubeGeometry(boom, 24, 0.024, 6), navy));
    const tip = mesh(new T.CapsuleGeometry(0.045, 0.07, 4, 10), navy);
    tip.position.copy(end);
    tip.quaternion.setFromUnitVectors(V(0, 1, 0), boom.getTangent(1));
    const led = mesh(new T.SphereGeometry(0.03, 10, 8), ringMat);
    led.position.set(0, 0.06, 0);
    tip.add(led);
    swim.add(tip);
  }

  // Hero pose: three-quarter view facing screen-right (toward the headline), a slight head tilt.
  swim.rotation.set(-4 * R, 44 * R, 6 * R);
  const rest = swim.rotation.clone();
  let look = { x: 0, y: 0 }, tilt = 0, nextBlink = 2.5, blinkAt = -1;
  const w = (2 * Math.PI) / 1.5;
  function update(t, dt, target) {
    const e = 1 - Math.exp(-dt * 4);
    look.x += (target.x - look.x) * e;
    look.y += (target.y - look.y) * e;
    tilt += (target.tilt - tilt) * e;
    swim.position.y = 0.045 * Math.sin(w * t);
    swim.rotation.set(rest.x - look.y * 4 * R + tilt * 6 * R + 0.8 * R * Math.sin(w * t - 1),
      rest.y + look.x * 5 * R, rest.z + 1 * R * Math.sin(w * t - 0.5));
    caudal.rotation.y = 6 * R * Math.sin(w * t - 1.2);
    dorsal.rotation.x = 3 * R * Math.sin(w * t - 0.6);
    anal.rotation.x = 4 * R * Math.sin(w * t - 1.8);
    pecs.forEach((p, i) => { p.rotation.x = 9 * R * Math.sin(w * t + 0.4 + i * 0.7); });
    if (t > nextBlink) { blinkAt = t; nextBlink = t + 3 + Math.random() * 3; }
    const b = blinkAt >= 0 && t - blinkAt < 0.16 ? Math.sin(Math.PI * (t - blinkAt) / 0.16) : 0;
    eyes.forEach((eye) => {
      eye.ball.scale.y = 0.38 * (1 - 0.9 * b);
      eye.look.rotation.set(-look.y * 12 * R, look.x * 12 * R, 0);
    });
    ringMat.color.copy(ringBase).multiplyScalar(0.85 + 0.2 * Math.sin((2 * Math.PI * t) / 3.2));
  }
  update(0, 1, { x: 0, y: 0, tilt: 0 });
  return { root, update, disposables };
}

// ---------- mount ----------
let app = null, booting = false;

async function boot() {
  if (booting || app || !host) return;
  booting = true;
  let renderer, model;
  try {
    const T = await import(THREE_URL);
    const canvas = document.createElement('canvas');
    canvas.setAttribute('aria-hidden', 'true');
    canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;display:block';
    const gl = canvas.getContext('webgl2', { alpha: true, antialias: true, premultipliedAlpha: true });
    if (!gl) throw new Error('no webgl2');
    renderer = new T.WebGLRenderer({ canvas, context: gl, alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, POSTER ? 2 : 1.5));
    renderer.setClearColor(0x000000, 0);
    renderer.toneMapping = T.NeutralToneMapping;
    const scene = new T.Scene();
    model = buildDory(T);
    scene.add(model.root);
    scene.add(new T.HemisphereLight('#D6ECFF', '#2F64B4', 1.5));
    const light = (c, i, x, y, z) => { const l = new T.DirectionalLight(c, i); l.position.set(x, y, z); scene.add(l); };
    light('#FFF5E8', 2.3, 3, 4, 5); // key: upper right, toward the headline
    light('#B4D6FF', 1.1, -4, -3, 4); // fill, lifts the white belly
    light('#B8FFF6', 3, -3, 3, -5); // rim, reads the silhouette against the reef blue

    const camera = new T.PerspectiveCamera(26, 1, 0.1, 50);
    const box = new T.Box3().setFromObject(model.root), centre = box.getCenter(new T.Vector3());
    const size = box.getSize(new T.Vector3());
    const fit = () => { // frames exactly like the square poster under object-fit: contain
      const w = host.clientWidth || 1, h = host.clientHeight || 1, a = w / h;
      const half = (1.02 * Math.max(size.y, size.x) / 2 + 0.05) / Math.min(1, a);
      camera.aspect = a;
      camera.position.set(centre.x, centre.y, centre.z + size.z / 2 + half / Math.tan((camera.fov * R) / 2));
      camera.lookAt(centre);
      camera.updateProjectionMatrix();
      renderer.setSize(w, h, false);
    };
    fit();
    host.appendChild(canvas);

    const target = { x: 0, y: 0, tilt: 0 };
    const paused = new Set();
    let raf = 0, last = 0, t = 0, shown = false;
    const frame = (now) => {
      raf = 0;
      const dt = Math.min(0.05, last ? (now - last) / 1000 : 0.016);
      last = now;
      t += dt;
      try {
        model.update(t, dt, target);
        renderer.render(scene, camera);
      } catch (err) {
        return fail(err);
      }
      if (!shown) {
        shown = true;
        host.classList.add('is-3d');
        window.dispatchEvent(new CustomEvent('dory3d:ready'));
      }
      if (!paused.size && !POSTER) raf = requestAnimationFrame(frame);
    };
    const run = () => { if (!raf && !paused.size) { last = 0; raf = requestAnimationFrame(frame); } };
    const set = (why, on) => { on ? paused.add(why) : paused.delete(why); if (on && raf) { cancelAnimationFrame(raf); raf = 0; } run(); };

    const onPointer = (ev) => {
      const r = host.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      target.x = Math.max(-1, Math.min(1, (ev.clientX - cx) / (innerWidth / 2)));
      target.y = Math.max(-1, Math.min(1, (ev.clientY - cy) / (innerHeight / 2)));
    };
    const onScroll = () => { target.tilt = Math.max(0, Math.min(1, scrollY / (innerHeight || 1))); };
    const onVis = () => set('hidden', document.hidden);
    const io = new IntersectionObserver(([e]) => set('offscreen', !e.isIntersecting));
    const ro = new ResizeObserver(() => { fit(); if (paused.size) renderer.render(scene, camera); });
    addEventListener('pointermove', onPointer, { passive: true });
    addEventListener('scroll', onScroll, { passive: true });
    document.addEventListener('visibilitychange', onVis);
    io.observe(host);
    ro.observe(host);
    canvas.addEventListener('webglcontextlost', () => app && app.destroy());

    app = {
      pause: (why) => set(why, true),
      resume: (why) => set(why, false),
      destroy() {
        cancelAnimationFrame(raf);
        removeEventListener('pointermove', onPointer);
        removeEventListener('scroll', onScroll);
        document.removeEventListener('visibilitychange', onVis);
        io.disconnect();
        ro.disconnect();
        dispose(renderer, model);
        host.classList.remove('is-3d');
        app = null;
      },
    };
    if (motionOff()) paused.add('motion');
    if (document.hidden) paused.add('hidden');
    paused.size ? frame(performance.now()) : run(); // the first frame always renders (the crossfade needs it)
  } catch (err) {
    app ? fail(err) : (dispose(renderer, model), console.warn('dory3d: keeping the still image', err));
  } finally {
    booting = false;
  }
}

function fail(err) { // any runtime error: tear everything down, the still stays
  if (app) app.destroy();
  console.warn('dory3d: keeping the still image', err);
}

function dispose(renderer, model) {
  if (model) model.disposables.forEach((d) => d.dispose());
  if (renderer) {
    renderer.dispose();
    renderer.forceContextLoss();
    renderer.domElement.remove();
  }
}

if (host && capable()) {
  let off = motionOff();
  new MutationObserver(() => {
    if (off === motionOff()) return; // another class changed
    off = !off;
    if (app) off ? app.pause('motion') : app.resume('motion');
    else if (!off) whenIdle(boot); // the visitor turned motion on
  }).observe(html, { attributes: true, attributeFilter: ['class'] });
  if (POSTER || (!motionOff() && !reduced.matches)) whenIdle(boot);
}

function whenIdle(fn) {
  const go = () => ('requestIdleCallback' in window ? requestIdleCallback(fn, { timeout: 1500 }) : setTimeout(fn, 200));
  document.readyState === 'complete' ? go() : addEventListener('load', go, { once: true });
}

export { buildDory }; // for the offline turntable review and poster renders
