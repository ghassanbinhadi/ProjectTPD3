/* ============================================================
   When to Listen — 3D model visualisation for panel 003.
   Two labeled 3D point-lattice globes (Llama left, Qwen right)
   with a critique stream between them.

   State driven from script.js via window.PeerGPTModels:
     setDirection('lq'|'ql') -> which way the stream flows + color
     setOutcome(...)         -> brighten the receiving globe
     setActive(true|false)   -> only animate while panel 3 is open
   ============================================================ */
(function(){
  'use strict';
  if (window.PeerGPTModels) return;

  const canvas = document.getElementById('model-scene');
  if (typeof THREE === 'undefined' || !canvas) return;

  let webglOK = false;
  try {
    const test = document.createElement('canvas');
    webglOK = !!(test.getContext && (test.getContext('webgl2') || test.getContext('webgl')));
  } catch (e) { webglOK = false; }
  if (!webglOK) return;

  const COLORS = {
    lq: { r: 226/255, g: 162/255, b: 51/255  },
    ql: { r: 62/255,  g: 192/255, b: 174/255 }
  };

  const renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(0x000000, 0);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 40);
  camera.position.set(0, 0, 6.4);
  camera.lookAt(0, 0, 0);

  const GROUP = new THREE.Group();
  scene.add(GROUP);

  const nodeMats = [];

  // ---- Build a spherical point-lattice globe (short-arc links) ----
  function buildGlobe(centerX, label) {
    const g = new THREE.Group();
    g.position.x = centerX;
    GROUP.add(g);

    const R = 1.35;
    const count = 90;
    const positions = [];
    let s = centerX < 0 ? 11 : 23;
    const rand = function(){ s = (s * 16807) % 2147483647; return s / 2147483647; };

    // fibonacci-sphere-like distribution for even coverage
    const golden = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < count; i++) {
      const y = 1 - (i / (count - 1)) * 2;
      const rad = Math.sqrt(1 - y * y);
      const th = golden * i;
      const x = Math.cos(th) * rad;
      const z = Math.sin(th) * rad;
      const mat = new THREE.MeshBasicMaterial({ color: 0xECE8DC, transparent: true, opacity: 0.8 });
      const pt = new THREE.Mesh(new THREE.SphereGeometry(0.028 + 0.02 * rand(), 10, 10), mat);
      pt.position.set(x * R, y * R, z * R);
      g.add(pt);
      positions.push({ v: pt.position, mat: mat, base: mat.opacity });
      nodeMats.push(mat);
    }

    // connect points whose angular distance is small (short arcs)
    const segs = [];
    for (let i = 0; i < positions.length; i++) {
      for (let j = i + 1; j < positions.length; j++) {
        if (positions[i].v.distanceTo(positions[j].v) < R * 1.05) {
          segs.push(positions[i].v.x, positions[i].v.y, positions[i].v.z,
                    positions[j].v.x, positions[j].v.y, positions[j].v.z);
        }
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(segs, 3));
    const linkMat = new THREE.LineBasicMaterial({
      color: 0xffffff, transparent: true, opacity: 0.14
    });
    const link = new THREE.LineSegments(geo, linkMat);
    g.add(link);

    // soft inner core glow (matches the hero scene's cluster glow)
    const coreMat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.08 });
    const core = new THREE.Mesh(new THREE.SphereGeometry(R * 0.9, 24, 24), coreMat);
    g.add(core);

    return { group: g, nodes: positions, core: core, linkMat: linkMat, coreMat: coreMat };
  }

  const LLAMA = buildGlobe(-2.1, 'Llama');
  const QWEN  = buildGlobe( 2.1, 'Qwen');

  // ---- Critique stream (Critic -> Solver, changes with direction) ----
  const PCOUNT = 60;
  const pPos = new Float32Array(PCOUNT * 3);
  const pGeo = new THREE.BufferGeometry();
  pGeo.setAttribute('position', new THREE.BufferAttribute(pPos, 3));
  const streamMat = new THREE.PointsMaterial({
    size: 0.13, transparent: true, opacity: 0,
    color: new THREE.Color(COLORS.lq.r, COLORS.lq.g, COLORS.lq.b),
    depthWrite: false, blending: THREE.AdditiveBlending
  });
  const streamPoints = new THREE.Points(pGeo, streamMat);
  scene.add(streamPoints);

  let direction = document.body.getAttribute('data-direction') || 'lq';
  let outcome = 'idle';
  let active = true;
  let deflectAmt = 0;

  function streamCurve() {
    // In 'lq': Llama solves (left), Qwen criticises (right) -> right to left.
    // In 'ql': Qwen solves (right), Llama criticises (left) -> left to right.
    const start = direction === 'lq' ? 2.1 : -2.1;
    const end   = direction === 'lq' ? -2.1 : 2.1;
    return [
      new THREE.Vector3(start, 0, 0),
      new THREE.Vector3(start * 0.4, 1.7, 0.8),
      new THREE.Vector3(end * 0.4, -0.6, -0.8),
      new THREE.Vector3(end, 0, 0)
    ];
  }

  function applyColor(){
    const c = new THREE.Color(COLORS[direction].r, COLORS[direction].g, COLORS[direction].b);
    streamMat.color.copy(c);
    // tint the globe lattice links + cores with the same accent as the scene
    LLAMA.linkMat.color.copy(c);
    LLAMA.coreMat.color.copy(c);
    QWEN.linkMat.color.copy(c);
    QWEN.coreMat.color.copy(c);
  }
  applyColor();

  const api = {
    mode: 'webgl',
    setDirection: function(dir){
      if (COLORS[dir]) { direction = dir; applyColor(); }
    },
    setOutcome: function(o){
      outcome = (o === 'helped' || o === 'hurt') ? o : 'idle';
      deflectAmt = (o === 'hurt') ? 1 : 0;
    },
    setActive: function(on){ active = !!on; }
  };
  window.PeerGPTModels = api;

  const clock = new THREE.Clock();
  const receiver = () => (direction === 'lq' ? LLAMA : QWEN);
  const sender   = () => (direction === 'lq' ? QWEN : LLAMA);

  let flash = 0;

  function frame(){
    const dt = Math.min(clock.getDelta(), 0.05);
    if (!active) {
      // keep paused, but render one static frame occasionally not needed
      renderer.render(scene, camera);
      return;
    }
    const t = clock.elapsedTime;

    LLAMA.group.rotation.y = Math.sin(t * 0.4) * 0.6 + t * 0.15;
    QWEN.group.rotation.y  = Math.sin(t * 0.36 + 1.7) * 0.6 + t * 0.12;
    LLAMA.group.rotation.x = Math.sin(t * 0.25) * 0.12;
    QWEN.group.rotation.x  = Math.cos(t * 0.22) * 0.12;

    // subtle node shimmer
    [LLAMA, QWEN].forEach(cl => {
      for (let i = 0; i < cl.nodes.length; i++) {
        const n = cl.nodes[i];
        const s = Math.sin(t * 1.4 + i * 1.9);
        const target = n.base + s * 0.15;
        n.mat.opacity += (target - n.mat.opacity) * 0.08;
      }
    });

    // outcome flash on the receiver (solver) globe
    if (outcome !== 'idle' && active && flash < 1) flash += dt * 2;
    if (outcome === 'idle' && flash > 0) flash = Math.max(0, flash - dt * 2);
    if (flash > 0) {
      const r = receiver();
      r.nodes.forEach(function(n){ n.mat.opacity = Math.min(1.2, n.base + flash * 0.5); });
      r.core.scale.setScalar(1 + flash * 0.6);
      const s = sender();
      s.core.scale.setScalar(1 - flash * 0.35);
    }

    // deflect when hurt
    const deflectTarget = (outcome === 'hurt' && active) ? 1 : 0;
    deflectAmt += (deflectTarget - deflectAmt) * 0.06;

    // stream
    const streamTarget = active ? 1 : 0;
    streamMat.opacity += (streamTarget * (1 - deflectAmt) - streamMat.opacity) * 0.08;

    const curvePts = streamCurve();
    const CURVE = new THREE.CatmullRomCurve3(curvePts);
    if (streamMat.opacity > 0.002) {
      for (let i = 0; i < PCOUNT; i++) {
        const phase = (t * 0.55 + i / PCOUNT) % 1;
        const bend = deflectAmt * 1.8;
        const p = CURVE.getPoint(phase);
        p.x += bend * Math.max(0, (phase - 0.4)) * Math.sin(phase * 28);
        pPos[i*3]   = p.x;
        pPos[i*3+1] = p.y + Math.sin(phase * 60 + i) * 0.16;
        pPos[i*3+2] = p.z;
      }
      pGeo.attributes.position.needsUpdate = true;
    }

    renderer.render(scene, camera);
  }

  function size(){
    const box = canvas.parentElement.getBoundingClientRect();
    const w = Math.max(box.width, 1);
    const h = Math.max(box.height, 1);
    renderer.setSize(w, h);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    const mid = Math.min(w, h);
    camera.position.z = 6.4 * (mid / 300 > 1 ? 1 : 300 / mid);
  }
  window.addEventListener('resize', size);
  size();
  renderer.setAnimationLoop(frame);
})();
