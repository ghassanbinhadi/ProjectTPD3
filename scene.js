/* ============================================================
   PeerGPT — 3D hero scene
   Two abstract neural node-clusters (Solver left, Critic right)
   critiquing each other, rendered with Three.js.

   States driven from script.js via window.PeerGPTScene:
     setDirection('lq'|'ql')   -> recolor the critique stream
     setStream(true|false)     -> show the stream (Method in view)
     setOutcome('helped'|'hurt'|'idle') -> land/brighten vs deflect

   Fallbacks:
     - No WebGL / low-power / mobile            -> CSS-only version (body.no-webgl)
     - prefers-reduced-motion on a capable device -> single static frame (no RAF loop)
   ============================================================ */
(function(){
  'use strict';
  if (window.PeerGPTScene) return;

  const REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const MOBILE  = window.innerWidth < 620 || window.matchMedia('(pointer: coarse)').matches;
  const LOWPOWER = (typeof navigator.hardwareConcurrency === 'number' &&
                    navigator.hardwareConcurrency > 0 &&
                    navigator.hardwareConcurrency <= 3);

  let webglOK = false;
  if (typeof THREE !== 'undefined') {
    try {
      const test = document.createElement('canvas');
      webglOK = !!(test.getContext && (test.getContext('webgl2') || test.getContext('webgl')));
    } catch (e) { webglOK = false; }
  }

  // ---- Decide engine -------------------------------------------------
  const useCss = !webglOK || LOWPOWER || MOBILE || REDUCED;
  if (useCss || !webglOK) {
    document.body.classList.add('no-webgl');
    // CSS fallback still receives stream/outcome/direction signals.
    window.PeerGPTScene = {
      setDirection: function(dir){ document.body.setAttribute('data-direction', dir); },
      setStream: function(on){ document.getElementById('scene-fallback').classList.toggle('stream-on', !!on); },
      setOutcome: function(){}, // CSS fallback keeps it simple
      mode: 'css'
    };
    return;
  }

  // ---- Three.js scene ------------------------------------------------
  const canvas = document.getElementById('hero-scene');
  if (!canvas) { document.body.classList.add('no-webgl'); return; }

  const COLORS = {
    lq: { r: 226/255, g: 162/255, b: 51/255  },   // amber
    ql: { r: 69/255,  g: 179/255, b: 170/255 }   // cyan
  };

  const renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setClearColor(0x0B1521, 0);

  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x0B1521, 9, 16);

  const camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.1, 60);
  camera.position.set(0, 0.2, 7);
  camera.lookAt(0, 0, 0);

  const GROUP = new THREE.Group();
  scene.add(GROUP);

  // Shared node material cache for brightness pulses
  const nodeMats = [];

  // ---- Build one neural cluster -------------------------------------
  function buildCluster(centerX, nodeColor, linkColor, count, radius) {
    const g = new THREE.Group();
    g.position.x = centerX;
    GROUP.add(g);

    const positions = [];
    const nodes = [];
    const seed = centerX < 0 ? 7 : 13;
    let s = seed;
    const rand = function(){ s = (s * 16807) % 2147483647; return s / 2147483647; };

    for (let i = 0; i < count; i++) {
      // roughly spherical shell, biased toward a loose cloud
      const theta = Math.acos(rand()*2 - 1);
      const phi = rand() * Math.PI * 2;
      const r = radius * (0.55 + 0.45 * rand());
      const x = r * Math.sin(theta) * Math.cos(phi);
      const y = r * Math.sin(theta) * Math.sin(phi) * 0.85;
      const z = r * Math.cos(theta) * 0.7;
      const mat = new THREE.MeshBasicMaterial({ color: nodeColor, transparent: true, opacity: 0.75 });
      const sph = new THREE.Mesh(new THREE.SphereGeometry(0.05 + 0.05 * rand(), 12, 12), mat);
      sph.position.set(x, y, z);
      g.add(sph);
      positions.push({ v: sph.position, mat: mat, base: mat.opacity });
      nodeMats.push(mat);
    }

    // edges between close nodes
    const segs = [];
    for (let i = 0; i < positions.length; i++) {
      for (let j = i + 1; j < positions.length; j++) {
        const d = positions[i].v.distanceTo(positions[j].v);
        if (d < radius * 1.15) {
          segs.push(positions[i].v.x, positions[i].v.y, positions[i].v.z,
                    positions[j].v.x, positions[j].v.y, positions[j].v.z);
        }
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(segs, 3));
    const seg = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: linkColor, transparent: true, opacity: 0.28 }));
    g.add(seg);
    // centered core glow
    const core = new THREE.Mesh(
      new THREE.SphereGeometry(0.20, 24, 24),
      new THREE.MeshBasicMaterial({ color: nodeColor, transparent: true, opacity: 0.10 })
    );
    g.add(core);

    return { group: g, nodes: positions, core: core };
  }

  const SOLVER = buildCluster(-2.6, 0xECE8DC, 0xE2A233, 9, 1.15);
  const CRITIC = buildCluster( 2.6, 0xECE8DC, 0x45B3AA, 9, 1.15);

  // ---- Critique stream (curve from Critic -> Solver) ----------------
  const CURVE = new THREE.CatmullRomCurve3([
    new THREE.Vector3(2.6, 0, 0),
    new THREE.Vector3(0.6, 2.4, 0.6),
    new THREE.Vector3(-1.6, 1.6, -0.4),
    new THREE.Vector3(-2.6, 0, 0)
  ]);

  const PCOUNT = 46;
  const pPos = new Float32Array(PCOUNT * 3);
  const pGeo = new THREE.BufferGeometry();
  pGeo.setAttribute('position', new THREE.BufferAttribute(pPos, 3));
  const streamMat = new THREE.PointsMaterial({
    size: 0.14, transparent: true, opacity: 0,
    color: new THREE.Color(COLORS.lq.r, COLORS.lq.g, COLORS.lq.b),
    depthWrite: false, blending: THREE.AdditiveBlending
  });
  const streamPoints = new THREE.Points(pGeo, streamMat);
  scene.add(streamPoints);

  // ---- State ---------------------------------------------------------
  let direction = document.body.getAttribute('data-direction') || 'lq';
  let streamOn = false;
  let outcome = 'idle';         // 'helped' | 'hurt' | 'idle'
  let outcomeFlash = 0;         // decays after a helped/hurt event
  let deflectAmt = 0;           // >0 when hurting (stream fades before reaching solver)

  function applyColor() {
    const c = new THREE.Color(COLORS[direction].r, COLORS[direction].g, COLORS[direction].b);
    streamMat.color.copy(c);
    canvas.dataset.streamColor = '#' + c.getHexString();
  }

  const api = {
    mode: 'webgl',
    setDirection: function(dir){
      if (COLORS[dir]) { direction = dir; applyColor(); }
    },
    setStream: function(on){
      streamOn = !!on;
      if (on && outcome === 'idle') { deflectAmt = 0; }
    },
    setOutcome: function(o){
      if (o !== 'helped' && o !== 'hurt' && o !== 'idle') return;
      if (o !== outcome) {
        outcome = o;
        outcomeFlash = o === 'idle' ? 0 : 1;
        if (o === 'hurt') deflectAmt = 1;
        else deflectAmt = 0;
      }
    }
  };
  window.PeerGPTScene = api;
  applyColor();

  // ---- Scroll / mouse reactivity ------------------------------------
  document.addEventListener('scroll', function(){
    var m = document.documentElement.scrollTop || document.body.scrollTop || 0;
    GROUP.rotation.z = m * 0.0004;
  }, { passive: true });

  const targetY = camera.position.y;
  let mouseX = 0;
  window.addEventListener('pointermove', function(e){
    mouseX = (e.clientX / window.innerWidth - 0.5) * 2;
  }, { passive: true });

  window.addEventListener('resize', function(){
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });

  // ---- Animation loop ------------------------------------------------
  const clock = new THREE.Clock();

  function frame(){
    const dt = Math.min(clock.getDelta(), 0.05);
    const t = clock.elapsedTime;

    // independent idle rotation + node pulse
    SOLVER.group.rotation.y = Math.sin(t * 0.28) * 0.4;
    SOLVER.group.rotation.x = Math.cos(t * 0.22) * 0.18;
    CRITIC.group.rotation.y = Math.sin(t * 0.24 + 2.1) * 0.4;
    CRITIC.group.rotation.x = Math.cos(t * 0.20 + 1.2) * 0.18;

    ([SOLVER, CRITIC]).forEach(function(cl){
      for (var i = 0; i < cl.nodes.length; i++) {
        var n = cl.nodes[i];
        var s = Math.sin(t * 1.2 + i * 1.7);
        n.v.y += Math.cos(t * 0.9 + i) * 0.0004;
        var targetOp = n.base + s * 0.18;
        n.mat.opacity += (targetOp - n.mat.opacity) * 0.06;
      }
    });

    // outcome effect on solver cluster brightness
    if (outcomeFlash > 0) {
      outcomeFlash = Math.max(0, outcomeFlash - dt * 1.4);
      SOLVER.nodes.forEach(function(n){
        n.mat.opacity = Math.min(1.2, n.base + outcomeFlash * 0.55);
      });
      SOLVER.core.scale.setScalar(1 + outcomeFlash * 1.2);
    } else if (outcome === 'idle') {
      SOLVER.core.scale.lerp(new THREE.Vector3(1,1,1), 0.05);
    }

    // deflect target when hurting
    const deflectTarget = (outcome === 'hurt' && streamOn) ? 1 : 0;
    deflectAmt += (deflectTarget - deflectAmt) * 0.06;

    // stream
    const streamTarget = streamOn ? 1 : 0;
    streamMat.opacity += (streamTarget * (1 - deflectAmt) - streamMat.opacity) * 0.08;

    if (streamMat.opacity > 0.001) {
      for (let i = 0; i < PCOUNT; i++) {
        const phase = (t * 0.5 + i / PCOUNT) % 1;
        // deflect: bend the last leg of the path away before reaching solver
        const bend = deflectAmt * 1.6;
        const p = CURVE.getPoint(phase);
        p.x += bend * Math.max(0, (phase - 0.45)) * Math.sin(phase * 30);
        pPos[i*3]   = p.x;
        pPos[i*3+1] = p.y + Math.sin(phase * 60 + i) * 0.18;
        pPos[i*3+2] = p.z;
      }
      pGeo.attributes.position.needsUpdate = true;
    }

    // gentle camera parallax with pointer
    camera.position.x += (mouseX * 0.7 - camera.position.x) * 0.04;
    camera.position.y += (targetY - camera.position.y) * 0.04;
    camera.lookAt(0, 0, 0);

    renderer.render(scene, camera);
  }

  if (REDUCED) {
    // static single frame (reduced motion)
    clock.getDelta();
    frame();
  } else {
    renderer.setAnimationLoop(frame);
  }
})();
