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

  // ---- Scene ----
  const canvas = document.getElementById('scene-canvas');
  if (!canvas) { document.body.classList.add('no-webgl'); return; }

  const COLORS = {
    lq: { r:226/255, g:162/255, b:51/255 },
    ql: { r:69/255,  g:179/255, b:170/255 }
  };

  const renderer = new THREE.WebGLRenderer({ canvas:canvas, antialias:true, alpha:true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio||1, 1.8));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setClearColor(0x000000, 0);

  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x000000, 10, 26);

  const camera = new THREE.PerspectiveCamera(46, window.innerWidth/window.innerHeight, 0.1, 80);
  camera.position.set(0, 0.45, 9.2);
  camera.lookAt(0, 0, 0);

  // Root group that will be offset to the right so the box bleeds off edge
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

  // ============ Wireframe box — dominates right side, bleeds off ============
  const BOX = new THREE.Group();
  // Position box to the right so it bleeds off viewport (hero split 40/60)
  BOX.position.set(2.6, -0.15, 0);
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

  // ============ Two clusters inside box ============
  const nodeMats = [];
  function glowSpriteTexture(){
    const c=document.createElement('canvas'); c.width=64; c.height=64;
    const g=c.getContext('2d');
    const grd=g.createRadialGradient(32,32,0,32,32,32);
    grd.addColorStop(0,'rgba(255,255,255,0.9)');
    grd.addColorStop(0.2,'rgba(255,255,255,0.35)');
    grd.addColorStop(0.45,'rgba(255,255,255,0.08)');
    grd.addColorStop(1,'rgba(255,255,255,0)');
    g.fillStyle=grd; g.fillRect(0,0,64,64);
    const tex=new THREE.CanvasTexture(c);
    return tex;
  }
  const glowTex = glowSpriteTexture();

  function buildCluster(cx, count, radius, tint){
    const g=new THREE.Group();
    g.position.set(cx,0,0);
    BOX.add(g);
    const positions=[];
    let s = cx<0? 7:13;
    function rnd(){ s=(s*16807)%2147483647; return s/2147483647; }
    const baseColor = new THREE.Color(tint);
    for(let i=0;i<count;i++){
      const theta=Math.acos(rnd()*2-1);
      const phi=rnd()*Math.PI*2;
      const r=radius*(0.55+rnd()*0.45);
      const x=r*Math.sin(theta)*Math.cos(phi);
      const y=r*Math.sin(theta)*Math.sin(phi)*0.85;
      const z=r*Math.cos(theta)*0.7;
      const mat=new THREE.MeshBasicMaterial({ color:baseColor, transparent:true, opacity:0.78 });
      const sph=new THREE.Mesh(new THREE.SphereGeometry(0.055 + 0.04*rnd(), 10,10), mat);
      sph.position.set(x,y,z);
      g.add(sph);
      // glow halo sprite behind each node
      const spr=new THREE.Sprite(new THREE.SpriteMaterial({ map:glowTex, color:baseColor, transparent:true, opacity:0.22, blending:THREE.AdditiveBlending, depthWrite:false }));
      spr.scale.set(0.32,0.32,1);
      spr.position.copy(sph.position);
      g.add(spr);
      positions.push({ mesh:sph, sprite:spr, mat:mat, base:mat.opacity, pos:sph.position });
      nodeMats.push(mat);
    }
    // intra-cluster edges
    const segs=[];
    for(let i=0;i<positions.length;i++){
      for(let j=i+1;j<positions.length;j++){
        const d=positions[i].pos.distanceTo(positions[j].pos);
        if(d<radius*1.05){
          segs.push(positions[i].pos.x,positions[i].pos.y,positions[i].pos.z,
                    positions[j].pos.x,positions[j].pos.y,positions[j].pos.z);
        }
      }
    }
    const geo=new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(segs,3));
    const seg=new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color:0xffffff, transparent:true, opacity:0.18 }));
    g.add(seg);
    // subtle core
    const core=new THREE.Mesh(
      new THREE.SphereGeometry(radius*0.22,16,16),
      new THREE.MeshBasicMaterial({ color:baseColor, transparent:true, opacity:0.08, blending:THREE.AdditiveBlending })
    );
    g.add(core);
    return { group:g, nodes:positions, core:core, seg:seg };
  }

  const SOLVER = buildCluster(-1.15, 10, 0.95, 0xECE8DC);
  const CRITIC = buildCluster( 1.15, 10, 0.95, 0xECE8DC);

  // ============ Critique stream (Critic -> Solver) inside box ============
  // Curve in BOX local space: from CRITIC cluster to SOLVER cluster with arc
  const CURVE = new THREE.CatmullRomCurve3([
    new THREE.Vector3( 1.15, 0.12, 0.18),
    new THREE.Vector3( 0.35, 0.95, 0.42),
    new THREE.Vector3(-0.45, 0.65,-0.18),
    new THREE.Vector3(-1.15, 0.10, 0.10)
  ]);
  const PCOUNT=48;
  const pPos=new Float32Array(PCOUNT*3);
  const pGeo=new THREE.BufferGeometry();
  pGeo.setAttribute('position', new THREE.BufferAttribute(pPos,3));
  const streamMat=new THREE.PointsMaterial({
    size:0.13, transparent:true, opacity:0,
    color:new THREE.Color(COLORS.lq.r, COLORS.lq.g, COLORS.lq.b),
    depthWrite:false, blending:THREE.AdditiveBlending
  });
  const streamPoints=new THREE.Points(pGeo, streamMat);
  BOX.add(streamPoints);

  // ---- State ----
  let direction = document.body.getAttribute('data-direction')||'lq';
  let streamOn=false;
  let outcome='idle';
  let outcomeFlash=0;
  let deflectAmt=0;

  function applyColor(){
    const c=new THREE.Color(COLORS[direction].r, COLORS[direction].g, COLORS[direction].b);
    streamMat.color.copy(c);
    canvas.dataset.streamColor='#'+c.getHexString();
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
    camera.aspect=window.innerWidth/window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });

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

    // node pulse + subtle vertical rain
    [SOLVER,CRITIC].forEach(function(cl){
      for(let i=0;i<cl.nodes.length;i++){
        const n=cl.nodes[i];
        const s=Math.sin(t*1.2 + i*1.7);
        n.pos.y += Math.cos(t*0.9 + i)*0.00035;
        const targetOp = n.base + s*0.16;
        n.mat.opacity += (targetOp - n.mat.opacity)*0.06;
        if(n.sprite) n.sprite.material.opacity = 0.18 + s*0.06;
      }
    });

    // outcome brighten
    if(outcomeFlash>0){
      outcomeFlash=Math.max(0, outcomeFlash - dt*1.35);
      SOLVER.nodes.forEach(function(n){ n.mat.opacity=Math.min(1.15, n.base + outcomeFlash*0.6); });
      SOLVER.core.scale.setScalar(1 + outcomeFlash*1.05);
      if(SOLVER.seg) SOLVER.seg.material.opacity = 0.18 + outcomeFlash*0.35;
    } else if(outcome==='idle'){
      SOLVER.core.scale.lerp(new THREE.Vector3(1,1,1),0.05);
      if(SOLVER.seg) SOLVER.seg.material.opacity += (0.18 - SOLVER.seg.material.opacity)*0.05;
    }

    const deflectTarget = (outcome==='hurt' && streamOn)?1:0;
    deflectAmt += (deflectTarget - deflectAmt)*0.06;
    const streamTarget = streamOn?1:0;
    streamMat.opacity += (streamTarget*(1-deflectAmt) - streamMat.opacity)*0.08;

    if(streamMat.opacity>0.001){
      for(let i=0;i<PCOUNT;i++){
        const phase=(t*0.55 + i/PCOUNT)%1;
        const bend = deflectAmt*1.4;
        const p=CURVE.getPoint(phase);
        p.x += bend * Math.max(0,(phase-0.48)) * Math.sin(phase*30);
        pPos[i*3]=p.x; pPos[i*3+1]=p.y + Math.sin(phase*60 + i)*0.10; pPos[i*3+2]=p.z;
      }
      pGeo.attributes.position.needsUpdate=true;
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
