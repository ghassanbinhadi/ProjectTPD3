/* ============================================================
   When to Listen — Corvus-style 3D hero
   Glowing wireframe bounding box ("two brains in a box"):
   - sparse starfield + 1-2 faint topology contour lines (atmosphere)
   - wireframe box (Edged box + soft glow)
   - two neural clusters (Solver & Critic) inside box, independent
     rotation/pulse + subtle vertical drift
   - critique particle stream Critic -> Solver, direction-colored
   - box auto-rotation + mouse-parallax tilt
   - Bloom simulated via additive blending + glow halos (no postprocess
     dependency needed for deploy robustness)
   Signals from script.js via window.PeerGPTScene:
     setDirection('lq'|'ql') -> recolor stream
     setStream(bool)         -> show/hide stream (Method in view)
     setOutcome('helped'|'hurt'|'idle') -> land vs deflect

   Fallbacks:
     - No WebGL / low-power / mobile -> CSS fallback (body.no-webgl)
     - prefers-reduced-motion -> static single frame
   ============================================================ */
(function(){
  'use strict';
  if (window.PeerGPTScene) return;

  const REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const MOBILE  = window.innerWidth < 680 || window.matchMedia('(pointer: coarse)').matches;
  const LOWPOWER = (typeof navigator.hardwareConcurrency === 'number' &&
                    navigator.hardwareConcurrency > 0 &&
                    navigator.hardwareConcurrency <= 3);

  let webglOK = false;
  if (typeof THREE !== 'undefined') {
    try {
      const c = document.createElement('canvas');
      webglOK = !!(c.getContext && (c.getContext('webgl2') || c.getContext('webgl')));
    } catch(e){ webglOK = false; }
  }

  const useCss = !webglOK || LOWPOWER || MOBILE || REDUCED;
  if (useCss || !webglOK) {
    document.body.classList.add('no-webgl');
    window.PeerGPTScene = {
      setDirection: function(d){ document.body.setAttribute('data-direction', d); },
      setStream: function(on){ var el=document.getElementById('scene-fallback'); if(el) el.classList.toggle('stream-on', !!on); },
      setOutcome: function(){},
      mode:'css'
    };
    return;
  }

  // ---- Scene (hero-only) ----
  const canvas = document.getElementById('scene-canvas');
  const heroWrap = document.getElementById('heroBoxWrap');
  if (!canvas || !heroWrap) { document.body.classList.add('no-webgl'); return; }

  const COLORS = {
    lq: { r:226/255, g:162/255, b:51/255 },
    ql: { r:69/255,  g:179/255, b:170/255 }
  };

  function heroSize(){
    const r = heroWrap.getBoundingClientRect();
    return { w: Math.max(r.width, 300), h: Math.max(r.height, 300) };
  }
  let _sz = heroSize();
  const renderer = new THREE.WebGLRenderer({ canvas:canvas, antialias:true, alpha:true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio||1, 1.8));
  renderer.setSize(_sz.w, _sz.h);
  renderer.setClearColor(0x000000, 0);

  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x000000, 9, 22);

  const camera = new THREE.PerspectiveCamera(46, _sz.w/_sz.h, 0.1, 80);
  camera.position.set(0, 0.45, 8.8);
  camera.lookAt(0, 0, 0);

  // Root — no offset, box centered in hero stage
  const WORLD = new THREE.Group();
  scene.add(WORLD);

  // ============ Atmosphere: starfield ============
  (function(){
    const n = 180;
    const pos = new Float32Array(n*3);
    let s=29;
    function rnd(){ s=(s*16807)%2147483647; return s/2147483647; }
    for(let i=0;i<n;i++){
      pos[i*3]   = (rnd()*2-1)*22;
      pos[i*3+1] = (rnd()*2-1)*14;
      pos[i*3+2] = (rnd()*2-1)*10 - 4;
    }
    const g=new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos,3));
    const m=new THREE.PointsMaterial({ size:0.06, color:0xffffff, transparent:true, opacity:0.38, depthWrite:false });
    const pts=new THREE.Points(g,m);
    pts.userData.basePos = pos.slice();
    pts.name='starfield';
    WORLD.add(pts);
  })();

  // ============ Topology contour lines (upper viewport) ============
  (function(){
    function makeContour(yBase, amp, freq, phase){
      const segs=64;
      const arr=new Float32Array(segs*3);
      for(let i=0;i<segs;i++){
        const t=i/(segs-1);
        const x=(t*2-1)*18;
        const y=yBase + Math.sin(t*Math.PI*freq + phase)*amp + Math.cos(t*Math.PI*1.2)*0.2;
        const z=(Math.sin(t*Math.PI*2 + phase*0.7)*0.6) - 2.5;
        arr[i*3]=x; arr[i*3+1]=y; arr[i*3+2]=z;
      }
      const g=new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.BufferAttribute(arr,3));
      const m=new THREE.LineBasicMaterial({ color:0xffffff, transparent:true, opacity:0.07 });
      const line=new THREE.Line(g,m);
      line.userData.phase = phase;
      line.userData.baseY = yBase;
      line.userData.arr = arr;
      WORLD.add(line);
    }
    makeContour(4.2, 0.65, 2.4, 0.6);
    makeContour(5.0, 0.45, 1.8, 2.1);
  })();

  // ============ Wireframe box — centered in hero stage ============
  const BOX = new THREE.Group();
  BOX.position.set(0, 0, 0);
  WORLD.add(BOX);

  const boxW=4.6, boxH=3.0, boxD=2.6;
  const boxGeo = new THREE.BoxGeometry(boxW, boxH, boxD);
  const edges = new THREE.EdgesGeometry(boxGeo);
  const lineMat = new THREE.LineBasicMaterial({ color:0xE8E6E1, transparent:true, opacity:0.55 });
  const boxLines = new THREE.LineSegments(edges, lineMat);
  BOX.add(boxLines);
  // soft outer glow (second wireframe slightly larger, additive, lower opacity)
  const glowMat = new THREE.LineBasicMaterial({ color:0xffffff, transparent:true, opacity:0.07, blending:THREE.AdditiveBlending, depthWrite:false });
  const glowLines = new THREE.LineSegments(edges, glowMat);
  glowLines.scale.set(1.03,1.03,1.03);
  BOX.add(glowLines);

  // faint inner box fill hint
  const innerBox = new THREE.Mesh(
    new THREE.BoxGeometry(boxW*0.98, boxH*0.98, boxD*0.98),
    new THREE.MeshBasicMaterial({ color:0xffffff, transparent:true, opacity:0.015, blending:THREE.AdditiveBlending, depthWrite:false })
  );
  BOX.add(innerBox);

  // ============ Two 3D Brain Point Clouds (solver / critic) — talking to each other ============
  // Each brain is a BufferGeometry + PointsMaterial dual-hemisphere cloud, facing inward
  function buildBrain(cx, count, radius, tint){
    const g=new THREE.Group();
    g.position.set(cx,0,0);
    BOX.add(g);
    let s = cx<0? 7:13;
    function rnd(){ s=(s*16807)%2147483647; return s/2147483647; }
    const facing = cx < 0 ? 1 : -1; // left brain faces right, right faces left
    function insideBrain(x,y){
      const fx = x * facing;
      const oval = (fx/0.62)*(fx/0.62) + (y/0.42)*(y/0.42);
      if (oval > 1) return false;
      if (fx > 0.18 && Math.abs(y) < 0.22) {
        const bulge = ((fx-0.18)/0.38)*((fx-0.18)/0.38) + (y/0.28)*(y/0.28);
        if (bulge < 1) return true;
      }
      if (fx > 0.12 && y < -0.30) {
        if (y < -0.33 - (fx-0.12)*0.28) return false;
      }
      return oval <= 1;
    }
    const posArray = new Float32Array(count*3);
    const colArray = new Float32Array(count*3);
    const baseColor = new THREE.Color(tint);
    let attempts=0;
    for(let i=0;i<count;i++){
      let x,y;
      do {
        x=(rnd()*2-1)*0.70; y=(rnd()*2-1)*0.50;
        attempts++; if(attempts>500) break;
      } while(!insideBrain(x,y));
      x*=radius*1.05; y*=radius*1.15;
      const z=(rnd()*2-1)*0.22*radius;
      posArray[i*3]=x; posArray[i*3+1]=y; posArray[i*3+2]=z;
      // subtle color variation per particle
      const v = 0.92 + rnd()*0.08;
      colArray[i*3]=baseColor.r*v; colArray[i*3+1]=baseColor.g*v; colArray[i*3+2]=baseColor.b*v;
    }
    const geo=new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(posArray,3));
    geo.setAttribute('color', new THREE.BufferAttribute(colArray,3));
    const mat=new THREE.PointsMaterial({
      size:0.095, vertexColors:true, transparent:true, opacity:0.92,
      blending:THREE.AdditiveBlending, depthWrite:false, sizeAttenuation:true
    });
    const points=new THREE.Points(geo, mat);
    g.add(points);
    // faint inner glow core (additive sphere)
    const core=new THREE.Mesh(
      new THREE.SphereGeometry(radius*0.24,16,16),
      new THREE.MeshBasicMaterial({ color:tint, transparent:true, opacity:0.07, blending:THREE.AdditiveBlending, depthWrite:false })
    );
    g.add(core);
    // internal edges as faint wire between nearby brain points (like sulci)
    // keep light: connect only a few nearest
    return { group:g, geo:geo, mat:mat, core:core, posArray:posArray };
  }

  const SOLVER = buildBrain(-1.05, 110, 1.02, 0xECE8DC);
  const CRITIC = buildBrain( 1.05, 110, 1.02, 0xECE8DC);

  // ============ Bidirectional communication stream (brains talking) ============
  // Two opposing neon streams + pulsing wave rings
  const CURVE_A = new THREE.CatmullRomCurve3([
    new THREE.Vector3(-1.05, 0.10, 0.12), // solver -> critic
    new THREE.Vector3(-0.25, 0.85, 0.32),
    new THREE.Vector3( 0.30, 0.70,-0.18),
    new THREE.Vector3( 1.05, 0.12, 0.14)
  ]);
  const CURVE_B = new THREE.CatmullRomCurve3([
    new THREE.Vector3( 1.05, 0.12, 0.14), // critic -> solver
    new THREE.Vector3( 0.30, 0.95, 0.38),
    new THREE.Vector3(-0.30, 0.78,-0.14),
    new THREE.Vector3(-1.05, 0.10, 0.12)
  ]);
  const PCOUNT=42;
  const pPosA=new Float32Array(PCOUNT*3);
  const pPosB=new Float32Array(PCOUNT*3);
  const pGeoA=new THREE.BufferGeometry(); pGeoA.setAttribute('position', new THREE.BufferAttribute(pPosA,3));
  const pGeoB=new THREE.BufferGeometry(); pGeoB.setAttribute('position', new THREE.BufferAttribute(pPosB,3));
  const streamMatA=new THREE.PointsMaterial({
    size:0.11, transparent:true, opacity:0,
    color:new THREE.Color(COLORS.lq.r, COLORS.lq.g, COLORS.lq.b), // amber
    depthWrite:false, blending:THREE.AdditiveBlending
  });
  const streamMatB=new THREE.PointsMaterial({
    size:0.11, transparent:true, opacity:0,
    color:new THREE.Color(COLORS.ql.r, COLORS.ql.g, COLORS.ql.b), // cyan
    depthWrite:false, blending:THREE.AdditiveBlending
  });
  const streamA=new THREE.Points(pGeoA, streamMatA);
  const streamB=new THREE.Points(pGeoB, streamMatB);
  BOX.add(streamA); BOX.add(streamB);
  // pulsing signal waves (ring-like via small torus wire or expanding circles)
  const waveGeo=new THREE.RingGeometry(0.12,0.14,20);
  waveGeo.rotateX(Math.PI/2);
  const waveMatA=new THREE.MeshBasicMaterial({ color:0xE2A233, transparent:true, opacity:0, side:THREE.DoubleSide, blending:THREE.AdditiveBlending, depthWrite:false });
  const waveMatB=new THREE.MeshBasicMaterial({ color:0x3EC0AE, transparent:true, opacity:0, side:THREE.DoubleSide, blending:THREE.AdditiveBlending, depthWrite:false });
  const waveA=new THREE.Mesh(waveGeo, waveMatA);
  const waveB=new THREE.Mesh(waveGeo, waveMatB);
  BOX.add(waveA); BOX.add(waveB);

  // ---- State (bidirectional) ----
  let direction = document.body.getAttribute('data-direction')||'lq';
  let streamOn=false;
  let outcome='idle';
  let outcomeFlash=0;
  let deflectAmt=0;

  function applyColor(){
    const c=new THREE.Color(COLORS[direction].r, COLORS[direction].g, COLORS[direction].b);
    canvas.dataset.streamColor='#'+c.getHexString();
    // subtle tint pulse on the brain that is currently solver
    const solverIsLeft = direction==='lq';
    SOLVER.mat.color.set(solverIsLeft ? 0xFFF0C0 : 0xE8E6E1);
    CRITIC.mat.color.set(solverIsLeft ? 0xE8E6E1 : 0xC0FFF0);
  }
  const api={
    mode:'webgl',
    setDirection:function(d){ if(COLORS[d]){ direction=d; applyColor(); } },
    setStream:function(on){
      streamOn=!!on;
      if(on && outcome==='idle') deflectAmt=0;
      const fb=document.getElementById('scene-fallback');
      if(fb) fb.classList.toggle('stream-on', !!on);
    },
    setOutcome:function(o){
      if(o!=='helped'&&o!=='hurt'&&o!=='idle') return;
      if(o!==outcome){
        outcome=o;
        outcomeFlash = o==='idle'?0:1;
        if(o==='hurt') deflectAmt=1; else deflectAmt=0;
      }
    }
  };
  window.PeerGPTScene=api;
  applyColor();

  // ---- Pointer parallax ----
  const targetY=camera.position.y;
  let mouseX=0, mouseY=0;
  window.addEventListener('pointermove', function(e){
    mouseX=(e.clientX/window.innerWidth-0.5)*2;
    mouseY=(e.clientY/window.innerHeight-0.5)*2;
  },{passive:true});
  window.addEventListener('resize', function(){
    const s=heroSize();
    camera.aspect=s.w/s.h;
    camera.updateProjectionMatrix();
    renderer.setSize(s.w, s.h);
  });
  // also observe heroWrap resize
  if (typeof ResizeObserver !== 'undefined') {
    new ResizeObserver(()=>{
      const s=heroSize();
      camera.aspect=s.w/s.h; camera.updateProjectionMatrix(); renderer.setSize(s.w,s.h);
    }).observe(heroWrap);
  }

  // ---- Loop ----
  const clock=new THREE.Clock();
  function frame(){
    const dt=Math.min(clock.getDelta(),0.05);
    const t=clock.elapsedTime;

    // Box slow auto-rotation + parallax tilt
    BOX.rotation.y = t*0.06 + mouseX*0.18;
    BOX.rotation.x = Math.sin(t*0.12)*0.08 + mouseY*0.10;
    BOX.rotation.z = Math.cos(t*0.08)*0.03;

    // Independent cluster rotation/pulse + vertical drift
    SOLVER.group.rotation.y = Math.sin(t*0.28)*0.35;
    SOLVER.group.rotation.x = Math.cos(t*0.22)*0.16;
    CRITIC.group.rotation.y = Math.sin(t*0.24+2.1)*0.35;
    CRITIC.group.rotation.x = Math.cos(t*0.20+1.2)*0.16;

    // starfield slow drift
    const star = WORLD.children.find(c=>c.name==='starfield');
    if(star){
      star.rotation.y = t*0.004;
      star.rotation.x = Math.sin(t*0.01)*0.02;
    }
    // topology lines gentle drift
    WORLD.children.forEach(ch=>{
      if(ch.isLine && ch.userData.arr){
        ch.position.x = Math.sin(t*0.06 + ch.userData.phase)*0.25;
      }
    });

    // brain pulse + subtle drift (PointsMaterial opacity + tiny pos jitter)
    const pulseA = 0.88 + Math.sin(t*1.3)*0.10;
    const pulseB = 0.88 + Math.sin(t*1.1+1.7)*0.10;
    SOLVER.mat.opacity = pulseA + (outcomeFlash>0 ? outcomeFlash*0.18 : 0);
    CRITIC.mat.opacity = pulseB;
    // faint vertical drift via small group bob
    SOLVER.group.position.y = Math.sin(t*0.9)*0.05;
    CRITIC.group.position.y = Math.cos(t*0.85)*0.05;

    // outcome brighten — solver brain that is currently active solver
    if(outcomeFlash>0){
      outcomeFlash=Math.max(0, outcomeFlash - dt*1.35);
      const activeBrain = (direction==='lq') ? SOLVER : CRITIC;
      activeBrain.core.scale.setScalar(1 + outcomeFlash*0.9);
      activeBrain.mat.opacity = Math.min(1.05, 0.92 + outcomeFlash*0.35);
    } else if(outcome==='idle'){
      SOLVER.core.scale.lerp(new THREE.Vector3(1,1,1),0.05);
      CRITIC.core.scale.lerp(new THREE.Vector3(1,1,1),0.05);
    }

    const deflectTarget = (outcome==='hurt' && streamOn)?1:0;
    deflectAmt += (deflectTarget - deflectAmt)*0.06;
    const streamTarget = streamOn?1:0;
    streamMatA.opacity += (streamTarget*(1-deflectAmt*0.6) - streamMatA.opacity)*0.08;
    streamMatB.opacity += (streamTarget*(1-deflectAmt*0.6) - streamMatB.opacity)*0.08;
    waveMatA.opacity = streamMatA.opacity * 0.35 * (0.6 + Math.sin(t*3.2)*0.4);
    waveMatB.opacity = streamMatB.opacity * 0.35 * (0.6 + Math.sin(t*3.2+1.1)*0.4);

    if(streamMatA.opacity>0.001){
      for(let i=0;i<PCOUNT;i++){
        const phaseA=(t*0.55 + i/PCOUNT)%1;
        const pA=CURVE_A.getPoint(phaseA);
        pPosA[i*3]=pA.x; pPosA[i*3+1]=pA.y + Math.sin(phaseA*40 + i)*0.07; pPosA[i*3+2]=pA.z;
        const phaseB=(1 - (t*0.52 + i/PCOUNT)%1); // opposite direction
        const bend = deflectAmt*1.2;
        const pB=CURVE_B.getPoint(phaseB);
        pB.x += bend * Math.max(0,(phaseB-0.45))*Math.sin(phaseB*26);
        pPosB[i*3]=pB.x; pPosB[i*3+1]=pB.y + Math.sin(phaseB*40 + i)*0.07; pPosB[i*3+2]=pB.z;
      }
      pGeoA.attributes.position.needsUpdate=true;
      pGeoB.attributes.position.needsUpdate=true;
      // waves travel mid-gap
      const midA = CURVE_A.getPoint((t*0.35)%1);
      const midB = CURVE_B.getPoint((t*0.35+0.5)%1);
      waveA.position.copy(midA); waveA.scale.setScalar(0.6 + (t*0.35%1)*1.4);
      waveB.position.copy(midB); waveB.scale.setScalar(0.6 + ((t*0.35+0.5)%1)*1.4);
      waveA.rotation.z = t*0.6; waveB.rotation.z = -t*0.6;
    }

    // camera parallax
    camera.position.x += (mouseX*0.55 - camera.position.x)*0.04;
    camera.position.y += (targetY + mouseY*0.35 - camera.position.y)*0.04;
    camera.lookAt(0,0,0);
    renderer.render(scene,camera);
  }

  if(REDUCED){
    clock.getDelta(); frame();
  } else {
    renderer.setAnimationLoop(frame);
  }
})();
