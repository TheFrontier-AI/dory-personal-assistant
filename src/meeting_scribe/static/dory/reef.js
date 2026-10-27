// The living reef behind the homepage hero: an original procedural scene (no downloaded models or
// textures). Contract: on capable devices it mounts a transparent canvas in #reef and adds `is-live`
// after the first frame; the CSS poster (reef-poster.webp) stays for everyone else. Layers: #reef (z 0)
// under #water (z 1, the light shafts) under the words (z 2). Nothing swims through .hero-copy or the
// header (+48 px) and the reef stays below the copy; the fog is the hero field (#0A5BAA), so nothing
// has an edge. Tests: tests/test_reef_js.py.
const THREE_URL = 'https://cdn.jsdelivr.net/npm/three@0.185.0/build/three.module.min.js';
const POSTER = new URL(import.meta.url).searchParams.has('poster'); // render one still (reef-poster.webp)
const host = document.getElementById('reef');
const html = document.documentElement;
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const coarse = matchMedia('(pointer: coarse)');
const motionOff = () => html.classList.contains('motion-off');
const FIELD = [10 / 255, 91 / 255, 170 / 255];
const MARGIN = 48;
const TAN = Math.tan((15 * Math.PI) / 180); // half the vertical field of view
const D0 = 9; // the floor at the bottom edge of the screen is this far away
const ss = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
const rng = (s) => () => {
  s = (s + 0x6d2b79f5) | 0;
  let t = Math.imul(s ^ (s >>> 15), s | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};
const floorY = (x, z) => 0.16 * Math.sin(x * 0.45 + z * 0.21) * Math.sin(z * 0.33 - x * 0.12) + 0.06 * Math.sin(x * 1.3 - z * 0.7);

function capable() {
  const n = navigator;
  if (n.connection && n.connection.saveData) return false;
  if (n.deviceMemory && n.deviceMemory < 4) return false;
  return (n.hardwareConcurrency || 0) >= 4 && 'WebGL2RenderingContext' in window;
}

// ---------- shaders: one program per kind (K) ----------
// 0 rock, 1 sand, 2 brain coral, 3 coral colony (staghorn; sea rods sway with SWAY), 4 plate coral,
// 5 sea fan, 6 sponge, 7 anemone (sways), 8 fish (tail beat), 9 whale (fluke beat).
const VS = `uniform float uT,uF;varying vec3 vO,vW,vN,vC;varying float vD,vS,vA;
#if K==3||K==5
attribute float a;
#endif
void main(){vec3 p=position;vA=0.;
#if K==3||K==5
vA=a;
#endif
float s=fract(sin(dot(instanceMatrix[3].xyz,vec3(12.9898,78.233,37.719)))*43758.5453);
#if K==8
s=fract(float(gl_InstanceID)*.618);p.z+=.12*pow(max(.25-p.x,0.),1.5)*sin(uT*uF+s*6.28+p.x*5.);
#elif K==9
float q=max(-.1-p.x,0.);p.y+=.9*q*q*sin(uT*.7);
#elif K==5
p.z+=p.y*p.y*.07*sin(uT*.45+s*6.28);
#elif K==7||defined(SWAY)
float h=max(p.y,0.);p.xz+=h*h*vec2(.07,.05)*sin(uT*vec2(.5,.37)+s*6.28+p.y*1.7);
#endif
vO=p;vS=s;vC=instanceColor;mat4 m=modelMatrix*instanceMatrix;vec4 w=m*vec4(p,1);vW=w.xyz;
vN=normalize(mat3(m)*normal);vec4 v=viewMatrix*w;vD=-v.z;gl_Position=projectionMatrix*v;}`;

const FS = `uniform float uT,uK,uA,uPx,uS;uniform vec3 uFog;uniform vec4 uR[3];uniform vec2 uRes;
varying vec3 vO,vW,vN,vC;varying float vD,vS,vA;
float h3(vec3 p){p=fract(p*.3183+.1);p*=17.;return fract(p.x*p.y*p.z*(p.x+p.y+p.z));}
float n3(vec3 x){vec3 i=floor(x),f=fract(x);f*=f*(3.-2.*f);
return mix(mix(mix(h3(i),h3(i+vec3(1,0,0)),f.x),mix(h3(i+vec3(0,1,0)),h3(i+vec3(1,1,0)),f.x),f.y),
mix(mix(h3(i+vec3(0,0,1)),h3(i+vec3(1,0,1)),f.x),mix(h3(i+vec3(0,1,1)),h3(i+1.),f.x),f.y),f.z);}
float fb(vec3 p){return .5*n3(p)+.3*n3(p*2.1)+.2*n3(p*4.3);}
float cau(vec2 p){p=mod(p,6.2832)-250.;vec2 i=p;float c=1.,t=uT*.22+23.;
for(int n=0;n<3;n++){float k=t*(1.-3.5/float(n+1));i=p+vec2(cos(k-i.x)+sin(k+i.y),sin(k-i.y)+cos(k+i.x));
c+=1./length(vec2(p.x/(sin(i.x+k)/.005),p.y/(cos(i.y+k)/.005)));}
c=1.17-pow(c/3.,1.4);return smoothstep(.36,.64,pow(abs(c),3.));}
float rd(vec4 r,vec2 p){vec2 d=max(r.xy-p,p-r.zw);return max(d.x,d.y);}
vec3 tilt(vec3 n,vec3 g,float k){return normalize(n-k*(g-dot(g,n)*n));}
vec3 gn(vec3 p,float h){return vec3(n3(p+vec3(.3,0,0))-h,n3(p+vec3(0,.3,0))-h,n3(p+vec3(0,0,.3))-h)/.3;}
float br(vec3 w){vec2 d=vec2(cos(vS*6.28),sin(vS*6.28));return .5+.5*sin(dot(w.xz,d)*84.+w.y*64.+fb(w*3.6+vS*7.)*34.);} // per coral: a small one gets fine grooves too
float lace(vec2 g,float t){g+=.4*vec2(n3(vec3(g*.8,1.)),n3(vec3(g.yx*.8,2.)));vec2 i=floor(g),f=fract(g);float d1=8.,d2=8.;
for(int y=-1;y<=1;y++)for(int x=-1;x<=1;x++){vec2 b=vec2(x,y),o=b+vec2(h3(vec3(i+b,3.)),h3(vec3(i+b,7.)))-f;
float e=dot(o,o);if(e<d1){d2=d1;d1=e;}else if(e<d2)d2=e;}float l=sqrt(d2)-sqrt(d1),fw=fwidth(l);return smoothstep(t+fw,t*.3,l);}
void main(){vec3 n=normalize(vN),c=vC,w=vW,o=vO;float a=1.,dt=smoothstep(34.,12.,vD);
if(!gl_FrontFacing)n=-n;
#if K!=1&&K<8
c*=.5+.5*smoothstep(0.,.3,o.y);
#endif
#if K==0
c*=.6+.7*fb(w*2.5)-.4*smoothstep(.62,.8,n3(w*11.))*dt;
c=mix(c,vec3(.36,.2,.22),smoothstep(.5,.66,fb(w*1.4+vS*9.)));c=mix(c,vec3(.2,.16,.08),smoothstep(.55,.7,fb(w*1.9-vS*5.))*smoothstep(0.,.7,n.y));c=mix(c,vec3(dot(c,vec3(.33))),.35);
#elif K==1
c*=.86+.12*sin(w.x*3.1+w.z*1.3+fb(w*.5)*7.)+.1*(n3(w*38.)-.5)*dt;
#elif K==2
float m=br(o);n=tilt(n,vec3(br(o+vec3(.004,0,0))-m,br(o+vec3(0,.004,0))-m,br(o+vec3(0,0,.004))-m)/.004,.009*dt);
m=smoothstep(.15,.85,m);c=mix(c*.32,mix(c,vec3(.62,.56,.42),.35*smoothstep(.6,1.,m)),mix(.65,m,dt));
#elif K==3
vec3 pq=w*40.+vS*9.;float pp=n3(pq);n=tilt(n,gn(pq,pp)*40.,.0022*dt);c*=.82+.3*smoothstep(.4,.85,pp)*dt;
c=mix(c,fract(vS*7.)<.5?vec3(.8,.72,.54):vec3(.66,.58,.76),smoothstep(.35,1.,vA));
#elif K==4
c*=.86+.16*sin(atan(o.z,o.x)*80.+n3(w*6.)*4.)*dt;c=mix(c,vec3(.5,.47,.38),(1.-abs(n.y))*.5);
#elif K==5
float lv=max(lace(o.xy*15.+vS*7.,mix(.12,.08,vA)),lace(o.xy*32.+3.,.08)*smoothstep(.3,.8,vA)),
rb=abs(fract(atan(o.x,o.y+.05)*3.5+n3(vec3(o.xy*5.,vS))*1.2)-.5)*vA*1.6;lv=max(lv,smoothstep(.014+fwidth(rb),0.,rb)*(1.-.6*vA));
a=(.1+.72*lv)*mix(.55,1.,dt)*smoothstep(1.,.82,vA+.12*n3(vec3(o.xy*7.,vS)));c*=.85+.4*lv;if(a<.03)discard;
#elif K==6
c*=(1.-.45*smoothstep(.6,.8,n3(w*30.))*dt)*(.85+.15*sin(atan(o.z,o.x)*18.));if(!gl_FrontFacing)c*=.3;
#elif K==7
c*=.75+.4*n3(w*24.)*dt;c=mix(c,vec3(.55,.5,.42),smoothstep(.6,1.1,o.y)*.5);
#elif K==8
c=mix(vec3(.7,.72,.72),c*1.5,smoothstep(-.04,.1,o.y));c*=1.-.8*smoothstep(.035,.02,length(o.xy-vec2(.35,.02)));
#elif K==9
c=mix(vec3(.42,.45,.47),c,smoothstep(-.07,.03,o.y)*step(abs(o.z),.12));
#endif
vec3 col=c*(mix(vec3(.05,.07,.1),vec3(.21,.25,.29),n.y*.5+.5)+vec3(.62,.6,.52)*max(dot(n,normalize(vec3(.3,1,.4))),0.)
+vec3(.9,.95,.92)*cau(w.xz*3.2)*smoothstep(-.1,.8,n.y)*smoothstep(40.,8.,vD))
+vec3(.01,.06,.16)*pow(1.-abs(dot(n,normalize(cameraPosition-w))),3.);
#if K==5
col+=c*vec3(.26,.27,.27);
#endif
col=pow(col*exp(-vec3(.02,.006,.003)*vD),vec3(.4545));
float fg=clamp(1.-exp(-max(vD-6.,0.)*uK),0.,1.);
#if K==1
fg=max(fg,smoothstep(40.,70.,vD));
#endif
col=mix(mix(col,vec3(dot(col,vec3(.2126,.7152,.0722))),fg*.4),uFog,fg);
vec2 p=gl_FragCoord.xy;float sf=24.*uPx,v=smoothstep(0.,sf,min(rd(uR[0],p),rd(uR[1],p)))*smoothstep(0.,uRes.y*.035,p.y);
col=mix(min(col,uFog),col,smoothstep(0.,uS,rd(uR[2],p)));
#if K>=8||K==5
gl_FragColor=vec4(col,a*v*uA);
#else
gl_FragColor=vec4(mix(uFog,col,v),1);
#endif
}`;

// ---------- the scene ----------
function buildScene(T) {
  const disposables = [];
  const keep = (x) => (disposables.push(x), x);
  const V = (x = 0, y = 0, z = 0) => new T.Vector3(x, y, z);
  const Y = V(0, 1, 0);
  const rnd = rng(7);
  const U = {
    uT: { value: 0 }, uPx: { value: 1 }, uS: { value: 24 }, uFog: { value: V(...FIELD) }, uRes: { value: new T.Vector2(1, 1) },
    uR: { value: [new T.Vector4(), new T.Vector4(), new T.Vector4()] },
  };
  const mat = (K, o = {}) => keep(new T.ShaderMaterial({
    defines: o.sw ? { K, SWAY: 1 } : { K }, vertexShader: VS, fragmentShader: FS, transparent: !!o.t, side: o.s ? T.DoubleSide : T.FrontSide,
    uniforms: { ...U, uK: { value: o.k || 0.06 }, uA: { value: 1 }, uF: { value: o.f || 0 } },
  }));

  // geometry helpers
  const merge = (gs) => {
    const pos = [], nor = [], idx = [];
    for (const g of gs) {
      const o = pos.length / 3, p = g.attributes.position.array, nm = g.attributes.normal.array;
      for (let i = 0; i < p.length; i++) { pos.push(p[i]); nor.push(nm[i]); }
      if (g.index) for (const i of g.index.array) idx.push(i + o);
      else for (let i = 0; i < p.length / 3; i++) idx.push(i + o);
      g.dispose();
    }
    const m = new T.BufferGeometry();
    m.setAttribute('position', new T.Float32BufferAttribute(pos, 3));
    m.setAttribute('normal', new T.Float32BufferAttribute(nor, 3));
    m.setIndex(idx);
    return m;
  };
  const warp = (g, f) => {
    const p = g.attributes.position, v = V();
    for (let i = 0; i < p.count; i++) { f(v.fromBufferAttribute(p, i)); p.setXYZ(i, v.x, v.y, v.z); }
    g.computeVertexNormals();
    return g;
  };
  const unit = (g) => { // base on y = 0, centred, one unit tall
    g.computeBoundingBox();
    const b = g.boundingBox, s = 1 / (b.max.y - b.min.y);
    g.translate(-(b.max.x + b.min.x) / 2, -b.min.y, -(b.max.z + b.min.z) / 2);
    return g.scale(s, s, s);
  };
  const lump = (v, a) => v.multiplyScalar(1 + a * (Math.sin(v.x * 3.1 + 1) * Math.sin(v.y * 2.7 + v.z * 3.3) + 0.5 * Math.sin(v.z * 6.1 - v.x * 4.7)));
  // living coral colonies: bending, tapering limbs with rounded tips; attribute `a` runs 0 (base) to 1 (tip)
  const colony = (n, len, rad, depth, spread, seg) => {
    const pos = [], nor = [], at = [], idx = [], RS = 6, u = V(), w = V(), q = V(), e = V();
    const ring = (c, d, r, a, s) => { // RS vertices around c facing d; s = sin of the cap angle
      u.set(1, 0, 0).cross(d).normalize();
      w.copy(d).cross(u);
      for (let j = 0; j < RS; j++) {
        const t = (j / RS) * 6.283;
        q.copy(u).multiplyScalar(Math.cos(t)).addScaledVector(w, Math.sin(t));
        pos.push(c.x + q.x * r, c.y + q.y * r, c.z + q.z * r);
        q.multiplyScalar(Math.sqrt(1 - s * s)).addScaledVector(d, s);
        nor.push(q.x, q.y, q.z);
        at.push(a);
      }
    };
    const limb = (p, d, l, r0, k, g) => {
      const b = pos.length / 3, axis = V(rnd() - 0.5, 0, rnd() - 0.5).normalize(), c = p.clone(), dd = d.clone();
      const r1 = r0 * 0.68, D = depth + 1;
      for (let i = 0; i <= seg; i++) {
        ring(c, dd, (r0 + (r1 - r0) * (i / seg)) * (1 + 0.08 * Math.sin(i * 2.3 + g * 1.7)), (g + i / seg) / D, 0);
        if (i < seg) { dd.applyAxisAngle(axis, (rnd() - 0.35) * 0.24).lerp(Y, 0.06).normalize(); c.addScaledVector(dd, l / seg); }
      }
      for (const s of [0.5, 0.87, 1]) ring(e.copy(c).addScaledVector(dd, r1 * s), dd, r1 * Math.sqrt(1 - s * s), (g + 1) / D, s);
      for (let i = 0; i < seg + 3; i++) for (let j = 0; j < RS; j++) {
        const a0 = b + i * RS, a1 = a0 + RS, j2 = (j + 1) % RS;
        idx.push(a0 + j, a0 + j2, a1 + j, a0 + j2, a1 + j2, a1 + j);
      }
      if (k) for (let i = 0, m = rnd() < 0.3 ? 3 : 2; i < m; i++) {
        const nd = dd.clone().add(V(rnd() - 0.5, rnd() * 0.4, rnd() - 0.5).multiplyScalar(spread)).normalize();
        nd.y = Math.max(nd.y, 0.35);
        limb(c, nd.normalize(), l * (0.65 + rnd() * 0.3), r1 * (0.85 + rnd() * 0.15), k - 1, g + 1);
      }
    };
    for (let i = 0; i < n; i++) {
      const a = (i / n) * 6.283 + rnd();
      limb(V(Math.cos(a) * 0.08, 0, Math.sin(a) * 0.08), V(Math.cos(a) * 0.5, 1, Math.sin(a) * 0.5).normalize(), len, rad * (0.8 + 0.4 * rnd()), depth, 0);
    }
    const g = new T.BufferGeometry();
    g.setAttribute('position', new T.Float32BufferAttribute(pos, 3));
    g.setAttribute('normal', new T.Float32BufferAttribute(nor, 3));
    g.setAttribute('a', new T.Float32BufferAttribute(at, 1));
    g.setIndex(idx);
    return unit(g);
  };
  const grid = (R, A, f, at) => { // a fan-shaped sheet, f(i, j) -> [x, y, z]; at: keep i as attribute `a`
    const pos = [], idx = [], ra = [];
    for (let i = 0; i <= R; i++) for (let j = 0; j <= A; j++) {
      pos.push(...f(i / R, j / A));
      ra.push(i / R);
      if (i < R && j < A) { const k = i * (A + 1) + j; idx.push(k, k + A + 1, k + 1, k + 1, k + A + 1, k + A + 2); }
    }
    const g = new T.BufferGeometry();
    g.setAttribute('position', new T.Float32BufferAttribute(pos, 3));
    if (at) g.setAttribute('a', new T.Float32BufferAttribute(ra, 1));
    g.setIndex(idx);
    g.computeVertexNormals();
    return g;
  };
  const tri = (pts) => {
    const g = new T.BufferGeometry();
    g.setAttribute('position', new T.Float32BufferAttribute(pts, 3));
    g.computeVertexNormals();
    return g;
  };
  const fishGeo = (h, w, fork, dorsal) => merge([ // one unit long, head at +x
    warp(new T.SphereGeometry(0.5, 12, 7), (v) => { const k = 0.45 + 0.75 * ss(-0.5, 0.3, v.x); v.y *= h * 2 * k; v.z *= w * 2 * k; }),
    tri([-0.4, 0, 0, -0.66, fork, 0, -0.55, 0, 0, -0.4, 0, 0, -0.55, 0, 0, -0.66, -fork, 0,
      0.12, h * 0.8, 0, -0.2, h * 0.7, 0, -0.1, h + dorsal, 0]),
  ]);

  const G = {
    rock: unit(warp(new T.SphereGeometry(1, 14, 9), (v) => { lump(v, 0.28); v.multiplyScalar(1 + 0.08 * Math.sin(v.x * 9 + v.z * 7)); v.y *= 0.6; })),
    brain: unit(warp(new T.SphereGeometry(1, 28, 10, 0, 6.283, 0, 1.75), (v) => { lump(v, 0.12); v.y *= 0.8; })),
    stag: colony(5, 0.3, 0.05, 2, 1.1, 3), // a branching thicket
    plate: unit(merge([warp(new T.SphereGeometry(0.3, 12, 8), (v) => { lump(v, 0.25); v.y *= 0.9; }).translate(0, 0.12, 0),
      ...[[0.8, 0.22, -0.25, 0.1], [0.65, 0.45, 0.2, -0.12], [0.5, 0.68, -0.1, 0.08], [0.36, 0.85, 0.15, 0]].map(([r, y, x, z], i) => warp(
        new T.CylinderGeometry(r, r * 0.85, 0.04, 26, 1), (v) => {
          const q = Math.hypot(v.x, v.z) / r;
          v.y += q * q * (0.06 * Math.sin(Math.atan2(v.z, v.x) * 4 + i * 2) + 0.04);
        }).rotateZ(0.12 * (i % 2 ? 1 : -1)).translate(x, y, z))])),
    fan: unit(grid(10, 18, (r, j) => {
      const a = (j - 0.5) * 2.3, q = r * (1 + 0.1 * Math.sin(a * 5 + 1.3) + 0.06 * Math.sin(a * 11 + 2) + 0.04 * Math.sin(a * 17));
      return [Math.sin(a) * q * 0.85, 0.06 + Math.cos(a) * q * 0.9, 0.08 * q * q * Math.cos(a * 2)];
    }, 1)),
    tube: unit(merge([[0, 0, 1], [0.3, 0.12, 0.75], [-0.26, -0.1, 0.62], [0.06, -0.3, 0.5]].map(([x, z, h]) =>
      new T.CylinderGeometry(0.2, 0.15, h, 12, 2, true).translate(0, h / 2, 0).rotateZ(-x * 0.7).rotateX(z * 0.7).translate(x, 0, z)))),
    barrel: unit(warp(new T.LatheGeometry([[0.2, 0], [0.34, 0.1], [0.42, 0.4], [0.5, 0.75], [0.56, 0.97], [0.54, 1]]
      .map(([x, y]) => new T.Vector2(x, y)), 18), (v) => {
      const s = 1 + 0.07 * Math.max(0, Math.sin(Math.atan2(v.z, v.x) * 9));
      v.x *= s; v.z *= s;
    })),
    soft: colony(7, 0.5, 0.042, 1, 0.6, 5), // sea rods: they sway
    anem: unit(merge([new T.CylinderGeometry(0.2, 0.24, 0.22, 12, 1).translate(0, 0.11, 0),
      ...Array.from({ length: 34 }, (_, i) => {
        const a = i * 2.4, r = 0.04 + 0.16 * Math.sqrt((i + 0.5) / 34);
        return new T.ConeGeometry(0.028, 0.4 + 0.12 * rnd(), 4, 3, true).translate(0, 0.2, 0).rotateZ(-r * 3)
          .rotateY(a).translate(Math.cos(a) * r, 0.2, -Math.sin(a) * r);
      })])),
  };

  // the seabed: one sheet from the bottom of the screen to the haze, wide enough for any screen
  const floor = grid(36, 48, (r, j) => {
    const d = 5.5 * Math.pow(90 / 5.5, r), x = (j * 2 - 1) * d * 1.05;
    return [x, floorY(x, -d), -d];
  });

  const scene = new T.Scene();
  const camera = new T.PerspectiveCamera(30, 1, 0.3, 160);
  scene.add(camera);
  const C = (h) => new T.Color(h);
  const inst = (geo, material, n, parent = scene) => {
    const m = new T.InstancedMesh(keep(geo), material, n);
    for (let i = 0; i < n; i++) m.setColorAt(i, C('#ffffff'));
    m.frustumCulled = false;
    parent.add(m);
    return m;
  };
  const R = { // the reef: [mesh, palette]
    rock: [inst(G.rock, mat(0), 120), ['#7A705C', '#686A5C', '#867464', '#6E6858'], 0.4],
    brain: [inst(G.brain, mat(2), 40), ['#B0905A', '#A89A62', '#C0A070', '#C8B288'], 0.42],
    stag: [inst(G.stag, mat(3), 12), ['#B8864E', '#C09050', '#B07C58', '#A88A5C'], 1],
    plate: [inst(G.plate, mat(4), 18), ['#949058', '#A68A60', '#868A60'], 0.7],
    fan: [inst(G.fan, mat(5, { t: 1, s: 1 }), 22), ['#A8707A', '#94708E', '#A88A5A', '#8C6E86'], 1.1],
    tube: [inst(G.tube, mat(6, { s: 1 }), 22), ['#86709A', '#A88258', '#7A8058'], 0.75],
    barrel: [inst(G.barrel, mat(6, { s: 1 }), 12), ['#A27866', '#98806E'], 0.65],
    soft: [inst(G.soft, mat(3, { sw: 1 }), 18), ['#B07A5C', '#9C6E8E', '#BC8E52', '#A4785E'], 0.9],
    anem: [inst(G.anem, mat(7), 24), ['#BCA47E', '#98A060', '#B48A84', '#A08498'], 0.42],
  };
  const sand = inst(floor, mat(1, { s: 1 }), 1);
  sand.setColorAt(0, C('#A2937A'));

  // schools: [geometry, count, view depth (x D0), length px, cruise px/s, tail beat, colour]
  const SPECIES = [
    [fishGeo(0.13, 0.06, 0.16, 0.05), 9, 1.3, 50, 40, 9, '#7E92A4'], // fusiliers, near
    [fishGeo(0.16, 0.06, 0.22, 0.08), 26, 2, 19, 22, 12, '#C08470'], // anthias over the reef
    [fishGeo(0.09, 0.045, 0.1, 0.02), 80, 3, 13, 18, 14, '#9AAEBE'], // bait ball, far
    [fishGeo(0.055, 0.04, 0.09, 0.04), 6, 2.7, 64, 14, 5, '#66737C'], // barracuda, slow
  ];
  const schools = SPECIES.map(([geo, n, d, len, v, f, col], k) => {
    const mesh = inst(geo, mat(8, { t: 1, s: 1, f, k: 0.045 }), n, camera);
    for (let i = 0; i < n; i++) mesh.setColorAt(i, C(col).offsetHSL(0, 0, (rnd() - 0.5) * 0.06));
    return { k, n, d: d * D0, len, v, mesh, P: new Float32Array(n * 3), W: new Float32Array(n * 3), live: n };
  });

  // the whale: humpback-like, far in the haze (pale belly, long pectoral fins, a gentle fluke beat)
  const fin = (sx, sy, sz, rx, ry, rz, x, y, z) => warp(new T.SphereGeometry(0.5, 10, 5), (v) => { v.x *= sx; v.y *= sy; v.z *= sz; })
    .rotateZ(rz).rotateX(rx).rotateY(ry).translate(x, y, z);
  const whaleGeo = merge([
    warp(new T.SphereGeometry(0.5, 32, 14), (v) => {
      const u = v.x + 0.5, k = 0.24 * (0.3 + 0.7 * ss(0.02, 0.6, u));
      v.y *= k * (v.y < 0 && u > 0.55 ? 1.18 : 1) * (v.y > 0 && u > 0.8 ? 0.8 : 1);
      v.z *= k * 0.92;
    }),
    fin(0.34, 0.08, 0.025, -0.5, 0, 0.75, 0.02, -0.13, 0.1), // long pectoral fins
    fin(0.34, 0.08, 0.025, 0.5, 0, 0.75, 0.02, -0.13, -0.1),
    fin(0.09, 0.012, 0.26, 0, -0.45, 0, -0.52, 0, 0.11), // flukes
    fin(0.09, 0.012, 0.26, 0, 0.45, 0, -0.52, 0, -0.11),
    new T.ConeGeometry(0.02, 0.05, 6).translate(-0.17, 0.07, 0),
  ]);
  const whale = inst(whaleGeo, mat(9, { t: 1, k: 0.02 }), 1, camera);
  whale.setColorAt(0, C('#55626C'));

  // ---------- composition: rebuilt on resize from the page's own rectangles ----------
  const m4 = new T.Matrix4(), q = new T.Quaternion(), e = new T.Euler(0, 0, 0, 'YZX'), sc = V(), ps = V(), pt = V();
  let W = 1, H = 1, avoid = [], hz = 0, whalePath = null;
  const toPx = (v) => { v.project(camera); return [(v.x + 1) * W / 2, (v.y + 1) * H / 2]; }; // y up from the bottom
  const floorPx = (d) => H / 2 + (H / 2) * Math.tan(Math.atan(camera.position.y / d) + camera.rotation.x) / TAN;

  function layout(w, h, rc) {
    W = w; H = h;
    const wide = rc.copy && rc.copy[0] > W * 0.3; // copy beside Dory (desktop) or above her (phone)
    const env = (x) => { // how high the reef may reach at screen x, px above the bottom
      let v = wide ? H * (0.15 + 0.3 * ss(0.62, 0.05, x / W)) : Math.min(H * 0.2, 230);
      const c = rc.copy;
      if (c && x > c[0] - MARGIN && x < c[2] + MARGIN) v = Math.min(v, H - c[3] - 8);
      if (POSTER && wide && x > W * 0.45) v = Math.min(v, H * 0.12); // the still is shown at other sizes too
      return Math.max(v, 0);
    };
    hz = wide ? Math.min(Math.max(0.55 * env(W * 0.9), 0.07 * H), 0.16 * H) : Math.min(0.1 * H, 110);
    const pitch = Math.atan((0.5 - hz / H) * 2 * TAN);
    camera.aspect = W / H;
    camera.position.set(0, Math.max(0.25, D0 * Math.tan(Math.atan(TAN) - pitch)), 0);
    camera.rotation.set(pitch, 0, 0);
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld();

    const r = rng(11), cnt = {};
    for (const k in R) cnt[k] = 0;
    const put = (k, x, d, size, yaw = r() * 6.283, sink = 0.04, ci = (r() * R[k][1].length) | 0) => {
      const [mesh, pal, f] = R[k];
      size *= f;
      if (cnt[k] >= mesh.instanceMatrix.count) return;
      const z = -d, y = floorY(x, z) - sink * size;
      const [bx, by] = toPx(ps.set(x, y, z)), top = toPx(pt.set(x, y + size, z))[1];
      if (bx < -200 || bx > W + 200) return;
      const room = env(bx) - by;
      if (room < 6) return;
      if (top - by > room) size *= room / (top - by);
      const s = size * (0.85 + 0.3 * r());
      m4.compose(ps.set(x, y, z), q.setFromEuler(e.set(0, yaw, 0)), sc.set(s * (0.85 + 0.3 * r()), size, s));
      mesh.setMatrixAt(cnt[k], m4);
      mesh.setColorAt(cnt[k]++, C(pal[ci]).offsetHSL(0, -0.04 * r(), 0.05 * (r() - 0.5)));
    };
    const upp = (d) => (2 * d * TAN) / H;
    const xAt = (s, d) => (s * 2 - 1) * d * TAN * camera.aspect; // screen fraction -> world x at depth d
    // [depth from, to (x D0), items per 100 px, size px, kinds (left half) | kinds (right half)]
    const BANDS = [
      [1.02, 1.35, 0.7, 190, 'stag brain brain rock soft anem rock', 'brain rock anem rock brain'],
      [1.35, 2.2, 1.3, 110, 'stag fan plate brain brain barrel anem rock tube soft rock', 'brain rock anem soft plate rock'],
      [2.2, 4.4, 2, 60, 'brain plate rock soft fan stag rock brain tube', 'brain rock plate rock'],
    ];
    if (wide) for (const [s, d, k, px, ci] of [[0.03, 1.7, 'fan', 430], [0.09, 1.12, 'stag', 300], [0.16, 1.03, 'soft', 250], [0.05, 1.3, 'barrel', 200],
      [0.24, 1.2, 'brain', 200], [0.21, 1.04, 'anem', 100, 2], [0.3, 1.08, 'anem', 120, 3], [0.36, 1.16, 'soft', 180, 1]]) {
      put(k, xAt(s, d * D0), d * D0, (px * upp(d * D0)) / R[k][2], k === 'fan' ? 0.3 : undefined, undefined, ci);
    }
    for (const [d0, d1, per, px, left, right] of BANDS) {
      const n = Math.round((W / 100) * per);
      for (let i = 0; i < n; i++) {
        const s = (i + r()) / n * 1.2 - 0.1, d = D0 * (d0 + (d1 - d0) * r());
        const kinds = (s < 0.5 ? left : right).split(' ');
        const k = kinds[(r() * kinds.length) | 0];
        const x = xAt(s, d), size = px * upp(d) * (0.7 + 0.6 * r()) * (wide ? 1 : 0.6);
        put(k, x, d, size, k === 'fan' ? (r() - 0.5) * 1.1 : undefined);
        if (k === 'stag' || k === 'soft') for (const c of [k, 'anem', r() < 0.5 ? k : 'brain']) { // living things grow in clumps
          put(c, x + (r() - 0.5) * size * 1.6, d + (r() - 0.3) * size * 1.5, size * (0.45 + 0.35 * r()));
        }
      }
    }
    for (let i = 0; i < W / 12; i++) { // rubble and boulders on the sand
      const d = D0 * (1 + 2.6 * r() * r());
      put('rock', xAt(r() * 1.2 - 0.1, d), d, (14 + 60 * r() * r()) * upp(d), undefined, 0.3);
    }
    for (const k in R) {
      const mesh = R[k][0];
      mesh.count = cnt[k];
      mesh.instanceMatrix.needsUpdate = true;
      mesh.instanceColor.needsUpdate = true;
    }

    // fish keep out of the copy and the header (+48), Dory's middle and the Pause button (+16)
    avoid = [rc.copy, rc.hd, rc.dory, rc.ctl].filter(Boolean);
    const few = W < 760;
    for (const s of schools) {
      s.live = s.k === 3 && few ? 0 : Math.round(s.n * (few ? 0.55 : 1));
      s.mesh.count = s.live;
      s.upp = upp(s.d);
      s.floor = floorPx(s.d);
      s.top = rc.hd ? rc.hd[3] : 0;
      s.r = Math.sqrt(s.live) * s.len * 0.45;
      s.home = [
        (t) => [W * (0.5 + 0.52 * Math.sin(t * 0.025 + 1)), H - hz - 0.08 * H + 0.03 * H * Math.sin(t * 0.07)],
        (t) => { const x = W * (wide ? 0.2 + 0.13 * Math.sin(t * 0.043) : 0.5 + 0.3 * Math.sin(t * 0.043)); return [x, H - env(x) - 0.03 * H]; },
        (t) => [W * (0.32 + 0.26 * Math.sin(t * 0.027)), wide ? 0.2 * H + 0.04 * H * Math.sin(t * 0.05) : H - hz - 0.3 * H],
        (t) => [W * (0.5 + 0.75 * Math.sin(t * 0.011 + 2)), H - hz - 0.15 * H],
      ][s.k];
      const [hx, hy] = s.home(0);
      for (let i = 0; i < s.n; i++) {
        s.P.set([hx + (r() - 0.5) * s.r * 2, hy + (r() - 0.5) * s.r, (r() - 0.5) * 60], i * 3);
        s.W.set([s.v * (r() < 0.5 ? -1 : 1), 0, 0], i * 3);
      }
    }

    // the whale's lane: above Dory and away into the haze before the copy (desktop); across under the
    // copy on a phone; none when there is no room
    const L = Math.min(Math.max(W * 0.3, 240), 520), dw = 10.5 * D0;
    const c = rc.copy, lo = c ? c[3] + 0.16 * L : 0, hi = H - hz - 0.12 * H - 0.16 * L;
    whalePath = wide
      ? { y: (rc.hd ? rc.hd[3] : 0) + 0.2 * L + 16, x0: -0.6 * L, x1: (c ? c[0] : W) - 0.5 * L }
      : hi > lo ? { y: (lo + hi) / 2, x0: -0.6 * L, x1: W + 0.6 * L } : null;
    if (whalePath) Object.assign(whalePath, { L, d: dw, upp: upp(dw) });
    whale.count = whalePath ? 1 : 0;
  }

  // nearest point outside every avoided rectangle grown by r (screen px, y down)
  const free = (x, y, r) => {
    for (const a of avoid) {
      const x0 = a[0] - r, y0 = a[1] - r, x1 = a[2] + r, y1 = a[3] + r;
      if (x > x0 && x < x1 && y > y0 && y < y1) {
        const m = Math.min(x - x0, x1 - x, y - y0, y1 - y);
        if (m === x - x0) x = x0; else if (m === x1 - x) x = x1; else if (m === y - y0) y = y0; else y = y1;
      }
    }
    return [x, y];
  };

  // boids: cohesion, alignment and separation, following a slow wandering leader
  function step(t, dt) {
    for (const s of schools) {
      const { P, W: Vl, live: n, v, len } = s;
      if (!n) continue;
      const [lx, ly] = free(...s.home(t), s.r * 0.6);
      let cx = 0, cy = 0, vx = 0, vy = 0;
      for (let i = 0; i < n; i++) { cx += P[i * 3]; cy += P[i * 3 + 1]; vx += Vl[i * 3]; vy += Vl[i * 3 + 1]; }
      cx /= n; cy /= n; vx /= n; vy /= n;
      const sep = len * 1.3, buf = 36;
      for (let i = 0; i < n; i++) {
        const j = i * 3, x = P[j], y = P[j + 1], z = P[j + 2];
        let ax = (cx - x) * 0.25 + (vx - Vl[j]) * 0.8 + (lx - x) * 0.05 + 8 * Math.sin(t * 0.9 + i * 1.7);
        let ay = (cy - y) * 0.25 + (vy - Vl[j + 1]) * 0.8 + (ly - y) * 0.06 + 5 * Math.sin(t * 0.7 + i * 2.3);
        let az = -z * 0.3 + 10 * Math.sin(t * 0.5 + i);
        for (let k = 0; k < n; k++) {
          const dx = x - P[k * 3], dy = y - P[k * 3 + 1], dz = z - P[k * 3 + 2], dd = Math.hypot(dx, dy, dz);
          if (k !== i && dd < sep && dd > 0.01) { const f = ((sep - dd) / dd) * 6; ax += dx * f; ay += dy * f; az += dz * f; }
        }
        for (const a of avoid) { // steer out of the clear areas
          const dl = x - a[0] + buf, dr = a[2] + buf - x, dtp = y - a[1] + buf, db = a[3] + buf - y, m = Math.min(dl, dr, dtp, db);
          if (m > 0) { const f = 40 + m * 4; if (m === dl) ax -= f; else if (m === dr) ax += f; else if (m === dtp) ay -= f; else ay += f; }
        }
        if (y > s.floor - len) ay -= (y - s.floor + len) * 3;
        if (y < s.top + buf) ay += (s.top + buf - y) * 3;
        let wx = Vl[j] + ax * dt, wy = Vl[j + 1] + ay * dt, wz = Vl[j + 2] + az * dt;
        const sp = Math.hypot(wx, wy, wz), c = Math.min(Math.max(sp, v * 0.45), v * 1.6) / (sp || 1);
        Vl[j] = wx *= c; Vl[j + 1] = wy *= c; Vl[j + 2] = wz *= c;
        P[j] = x + wx * dt; P[j + 1] = y + wy * dt; P[j + 2] = z + wz * dt;
      }
    }
  }

  function draw(t) {
    U.uT.value = t;
    for (const s of schools) {
      const { P, W: Vl, live: n, upp, len, d } = s;
      for (let i = 0; i < n; i++) {
        const j = i * 3, vx = Vl[j], vy = -Vl[j + 1], vz = Vl[j + 2];
        e.set(0, Math.atan2(-vz, vx), Math.max(-0.5, Math.min(0.5, Math.atan2(vy, Math.hypot(vx, vz)))));
        m4.compose(ps.set((P[j] - W / 2) * upp, (H / 2 - P[j + 1]) * upp, -d + P[j + 2] * upp), q.setFromEuler(e), sc.setScalar(len * upp));
        s.mesh.setMatrixAt(i, m4);
      }
      s.mesh.instanceMatrix.needsUpdate = true;
    }
    const wp = whalePath;
    if (wp) { // one slow crossing (80 s), then a long gap
      const u = ((t + 30) % 125) / 80, x = wp.x0 + (wp.x1 - wp.x0) * Math.min(u, 1);
      whale.material.uniforms.uA.value = u > 1 ? 0 : ss(0, 0.15, u) * ss(1, 0.7, u);
      e.set(0, 0.12, 0.03 * Math.sin(t * 0.1));
      m4.compose(ps.set((x - W / 2) * wp.upp, (H / 2 - wp.y - 8 * Math.sin(t * 0.09)) * wp.upp, -wp.d), q.setFromEuler(e), sc.setScalar(wp.L * wp.upp));
      whale.setMatrixAt(0, m4);
      whale.instanceMatrix.needsUpdate = true;
    }
  }

  // clear rectangles in drawing-buffer pixels (GL, y up): copy, header, controls
  function rects(rc, px) {
    U.uPx.value = px;
    U.uS.value = (POSTER ? 140 : 48) * px; // the shade behind Pause must not show an edge
    U.uRes.value.set(W * px, H * px);
    [rc.copy, rc.hd, rc.ctl].forEach((a, i) => U.uR.value[i].set(...(a ? [a[0] * px, (H - a[3]) * px, a[2] * px, (H - a[1]) * px] : [-9e4, -9e4, -9e4, -9e4])));
    avoid = [rc.copy, rc.hd, rc.dory, rc.ctl].filter(Boolean);
    for (const s of schools) s.top = rc.hd ? rc.hd[3] : 0;
  }

  return { scene, camera, layout, step, draw, rects, disposables };
}

// ---------- mount ----------
let app = null, booting = false;

async function boot() {
  if (booting || app || !host) return;
  booting = true;
  let renderer, world;
  try {
    const T = await import(THREE_URL);
    const canvas = document.createElement('canvas');
    canvas.setAttribute('aria-hidden', 'true');
    const gl = canvas.getContext('webgl2', { alpha: true, antialias: true, premultipliedAlpha: true });
    if (!gl) throw new Error('no webgl2');
    renderer = new T.WebGLRenderer({ canvas, context: gl, alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, POSTER ? 2 : 1.25));
    renderer.setClearColor(0x000000, 0);
    world = buildScene(T);
    host.appendChild(canvas);

    const els = { copy: document.querySelector('.hero-copy'), hd: document.getElementById('hd'),
      dory: document.getElementById('dory3d'), ctl: host.parentElement.querySelector('[data-motion-toggle]') };
    let size = '', laid = '', dirty = true;
    const measure = () => { // the page's rectangles, relative to the canvas (px, y down)
      dirty = false;
      const b = host.getBoundingClientRect(), w = Math.round(b.width) || 1, h = Math.round(b.height) || 1;
      const rel = (el, m) => { if (!el) return null; const r = el.getBoundingClientRect(); return [r.left - b.left - m, r.top - b.top - m, r.right - b.left + m, r.bottom - b.top + m]; };
      const d = rel(els.dory, 0), rc = { copy: rel(els.copy, MARGIN), hd: rel(els.hd, MARGIN), ctl: rel(els.ctl, 16) };
      if (d) { const iw = (d[2] - d[0]) * 0.22, ih = (d[3] - d[1]) * 0.22; rc.dory = [d[0] + iw, d[1] + ih, d[2] - iw, d[3] - ih]; }
      if (POSTER && rc.copy && rc.copy[0] > w * 0.3) rc.copy = [rc.copy[0], 0, w + 99, rc.copy[3]]; // a still must suit any screen
      if (POSTER && rc.ctl) rc.ctl = [w - (w > 700 ? 260 : 170), h - 130, w + 99, h + 99]; // Pause sits in this corner at any size
      if (`${w}x${h}` !== size) { size = `${w}x${h}`; renderer.setSize(w, h, false); }
      const key = `${size} ${rc.copy && rc.copy.map(Math.round)}`;
      if (key !== laid) { laid = key; world.layout(w, h, rc); }
      world.rects(rc, renderer.getPixelRatio());
    };

    const paused = new Set();
    let raf = 0, last = 0, t = 0, shown = false;
    const frame = (now) => {
      raf = 0;
      if (coarse.matches && last && now - last < 31) { raf = requestAnimationFrame(frame); return; } // 30 fps on phones
      const dt = Math.min(0.05, last ? (now - last) / 1000 : 0.016);
      last = now;
      t += dt;
      try {
        if (dirty) measure();
        world.step(t, dt);
        world.draw(t);
        renderer.render(world.scene, world.camera);
      } catch (err) {
        return fail(err);
      }
      if (!shown) { shown = true; host.classList.add('is-live'); }
      if (!paused.size && !POSTER) raf = requestAnimationFrame(frame);
    };
    const run = () => { if (!raf && !paused.size) { last = 0; raf = requestAnimationFrame(frame); } };
    const set = (why, on) => { on ? paused.add(why) : paused.delete(why); if (on && raf) { cancelAnimationFrame(raf); raf = 0; } run(); };
    const onScroll = () => { dirty = true; };
    const onVis = () => set('hidden', document.hidden);
    const io = new IntersectionObserver(([en]) => set('offscreen', !en.isIntersecting));
    const ro = new ResizeObserver(() => { dirty = true; if (paused.size && shown) { measure(); world.draw(t); renderer.render(world.scene, world.camera); } });
    addEventListener('scroll', onScroll, { passive: true });
    document.addEventListener('visibilitychange', onVis);
    io.observe(host);
    ro.observe(host);
    if (els.copy) ro.observe(els.copy);
    canvas.addEventListener('webglcontextlost', () => app && app.destroy());

    app = {
      pause: (why) => set(why, true),
      resume: (why) => set(why, false),
      destroy() {
        cancelAnimationFrame(raf);
        removeEventListener('scroll', onScroll);
        document.removeEventListener('visibilitychange', onVis);
        io.disconnect();
        ro.disconnect();
        dispose(renderer, world);
        host.classList.remove('is-live');
        app = null;
      },
    };
    if (POSTER) { measure(); for (let i = 0; i < 900; i++) world.step((t += 1 / 30), 1 / 30); }
    if (motionOff()) paused.add('motion');
    if (document.hidden) paused.add('hidden');
    paused.size || POSTER ? frame(performance.now()) : run(); // the first frame always renders (the crossfade needs it)
  } catch (err) {
    app ? fail(err) : (dispose(renderer, world), console.warn('reef: keeping the still image', err));
  } finally {
    booting = false;
  }
}

function fail(err) { // any runtime error: tear everything down, the still stays
  if (app) app.destroy();
  console.warn('reef: keeping the still image', err);
}

function dispose(renderer, world) {
  if (world) world.disposables.forEach((d) => d.dispose());
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
