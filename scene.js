/* ============================================================
   When to Listen — Bespoke 3D Neuro-Communication Canvas
   - Obsidian black (#000000) background, subtle fog
   - Ultra-fine wireframe aquarium (opacity 0.15) + starfield
   - Two anatomically-real procedural brains (dual-hemisphere,
     gyri/sulci convolutions, tapered cerebellum/stem) driven by
     a custom Fresnel/rim shader with pulsing internal core
     (left amber #FFAA00 / right cyan #00F2FE) at ~0.8 Hz
   - Arched rainbow neural conduit: CatmullRomCurve3 upper +
     lower arches, braided central nexus, gating-gate hub
   - High-density fiber-optic particle streams (amber L->R via
     upper arch, cyan R->L via lower arch), additive blending
   - Glassmorphism HUD labels aligned to the arcs
   - Slow ambient camera drift + dampened mouse parallax
   - Fully responsive hero-only canvas
   ============================================================ */
(function(){
  'use strict';
  if(window.PeerGPTScene) return;

  const REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const MOBILE = window.innerWidth < 680 || window.matchMedia('(pointer: coarse)').matches;
  const LOWPOWER = typeof navigator.hardwareConcurrency==='number' && navigator.hardwareConcurrency>0 && navigator.hardwareConcurrency<=3;
  let webglOK=false;
  if(typeof THREE!=='undefined'){
    try{ const c=document.createElement('canvas'); webglOK=!!(c.getContext && (c.getContext('webgl2')||c.getContext('webgl'))); }catch(e){webglOK=false;}
  }
  const useCss = !webglOK || LOWPOWER || MOBILE || REDUCED;
  if(useCss || !webglOK){
    document.body.classList.add('no-webgl');
    window.PeerGPTScene={
      setDirection(d){document.body.setAttribute('data-direction',d)},
      setStream(on){const el=document.getElementById('scene-fallback'); if(el) el.classList.toggle('stream-on',!!on)},
      setOutcome(){}, mode:'css'
    };
    return;
  }

  const canvas=document.getElementById('scene-canvas');
  const heroWrap=document.getElementById('heroBoxWrap');
  if(!canvas||!heroWrap){ document.body.classList.add('no-webgl'); return; }

  // Direction accent colors
  const COLORS={ lq:{r:226/255,g:162/255,b:51/255}, ql:{r:69/255,g:179/255,b:170/255} };

  /* ---------------- helpers ---------------- */
  let _seed=1337;
  function rnd(){ _seed=(_seed*16807)%2147483647; return (_seed/2147483647)*2-1; }
  function smoothstep(a,b,x){ const t=Math.min(1,Math.max(0,(x-a)/(b-a))); return t*t*(3-2*t); }

  /* ---------------- renderer / scene / camera ---------------- */
  function heroSize(){ const r=heroWrap.getBoundingClientRect(); return {w:Math.max(r.width,320), h:Math.max(r.height,340)}; }
  let _sz=heroSize();
  const renderer=new THREE.WebGLRenderer({canvas, antialias:true, alpha:true});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,1.8));
  renderer.setSize(_sz.w,_sz.h);
  renderer.setClearColor(0x000000,1);
  const scene=new THREE.Scene();
  scene.background=new THREE.Color(0x000000);
  scene.fog=new THREE.Fog(0x000000, 10, 20);
  const camera=new THREE.PerspectiveCamera(44, _sz.w/_sz.h, 0.1, 90);
  camera.position.set(0, 0.9, 12);
  camera.lookAt(0,0,0);
  const WORLD=new THREE.Group(); scene.add(WORLD);

  // subtle starfield
  (function(){
    const n=140; const pos=new Float32Array(n*3); _seed=999;
    for(let i=0;i<n;i++){ pos[i*3]=rnd()*24; pos[i*3+1]=rnd()*14; pos[i*3+2]=rnd()*12-4; }
    const g=new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos,3));
    const m=new THREE.PointsMaterial({size:0.04, color:0xffffff, transparent:true, opacity:0.18, depthWrite:false});
    const p=new THREE.Points(g,m); p.name='starfield'; WORLD.add(p);
  })();

  // ---- Aquarium wireframe (ultra-fine, opacity 0.15) ----
  const BOX=new THREE.Group(); WORLD.add(BOX);
  const boxW=6.4, boxH=3.8, boxD=3.4;
  const boxGeo=new THREE.BoxGeometry(boxW,boxH,boxD);
  const edges=new THREE.EdgesGeometry(boxGeo);
  const lineMat=new THREE.LineBasicMaterial({color:0xE8F0F0, transparent:true, opacity:0.15});
  const boxLines=new THREE.LineSegments(edges, lineMat); BOX.add(boxLines);
  const glowMat=new THREE.LineBasicMaterial({color:0x7FF0E8, transparent:true, opacity:0.05, blending:THREE.AdditiveBlending, depthWrite:false});
  const glowLines=new THREE.LineSegments(edges, glowMat); glowLines.scale.set(1.02,1.02,1.02); BOX.add(glowLines);
  // faint data-grid ticks along front top/bottom edges
  (function(){
    const tickGeo=new THREE.BufferGeometry();
    const ticks=[]; const divisions=8;
    for(let i=1;i<divisions;i++){
      const t=i/divisions;
      ticks.push(-boxW/2+t*boxW, boxH/2, boxD/2, -boxW/2+t*boxW, boxH/2-0.10, boxD/2);
      ticks.push(-boxW/2+t*boxW, -boxH/2, boxD/2, -boxW/2+t*boxW, -boxH/2+0.10, boxD/2);
    }
    tickGeo.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(ticks),3));
    const tm=new THREE.LineBasicMaterial({color:0xffffff, transparent:true, opacity:0.1});
    BOX.add(new THREE.LineSegments(tickGeo, tm));
  })();

  /* ============================================================
     ANATOMICAL BRAIN — dual-hemisphere + gyri/sulci + cerebellum
     ============================================================ */
  function makeBrainGeo(){
    const g=new THREE.IcosahedronGeometry(1.0, 5);
    const pos=g.attributes.position; const v=new THREE.Vector3(); const n=new THREE.Vector3();
    function noise3(x,y,z){
      let a=0, f=1.0, amp=1.0, tot=0;
      for(let o=0;o<4;o++){
        a += Math.sin(x*f*2.7 + Math.sin(y*f*3.1+1.3) + z*f*1.7)*amp
           + Math.sin(y*f*5.3 + z*f*2.3 + Math.sin(x*f*4.1))*amp*0.5;
        tot+=amp*1.5; f*=2.1; amp*=0.5;
      }
      return a/tot;
    }
    for(let i=0;i<pos.count;i++){
      v.fromBufferAttribute(pos,i);
      n.copy(v).normalize();
      const nx=n.x, ny=n.y, nz=n.z;
      const front=smoothstep(-0.15,0.75,nz);   // +z frontal
      const back=smoothstep(-0.75,0.15,-nz);   // -z occipital
      let R=1.0;
      R*=1.0+0.16*front*Math.max(0,nz);        // frontal bulge
      R*=1.0-0.14*back;                         // occipital taper
      R*=1.0-0.20*Math.abs(nx);                 // bitemporal narrowing
      R*=1.0+0.10*Math.abs(ny);                 // slight vertical stretch
      // dual-hemisphere separation along median sagittal plane
      const hemi=smoothstep(-0.10,0.16,Math.abs(nx));
      R*=0.30+0.72*hemi;                        // deep central sulcus gap
      // gyri / sulci convolutions
      const folds=noise3(nx*4.2+0.5, ny*4.2+0.5, nz*4.2+0.5);
      R*=1.0+0.075*folds*(0.4+0.6*hemi);
      R*=1.0+0.03*noise3(nx*9.0, ny*9.0, nz*9.0);
      // cerebellum: bulge low / posterior
      const cereb=smoothstep(-0.35,0.1,-ny)*smoothstep(0.15,0.75,-nz);
      R*=1.0+0.10*cereb;
      // brain-stem taper straight down
      const stem=smoothstep(-0.55,-0.05,ny);
      const stemMag=0.30*stem*smoothstep(0.2,0.8,1.0-Math.abs(nx))*smoothstep(0.3,0.8,1.0-Math.abs(nz));
      const finalR=R*0.78;
      const sx=n.x*finalR;
      const sy=n.y*finalR - stemMag*Math.abs(nz)*0.6;
      const sz=n.z*finalR;
      pos.setXYZ(i, sx, sy, sz);
    }
    g.computeVertexNormals();
    return g;
  }

  // Fresnel rim-lighting subsurface shader
  const vertShader=`
    varying vec3 vNormal;
    varying vec3 vWorldPos;
    uniform float time;
    uniform float pulse;
    void main(){
      vNormal = normalize(normalMatrix * normal);
      vec3 pos = position;
      pos *= 1.0 + pulse*0.05 * sin(time*0.8 + position.y*2.0);
      vec4 wp = modelMatrix * vec4(pos,1.0);
      vWorldPos = wp.xyz;
      gl_Position = projectionMatrix * viewMatrix * wp;
    }
  `;
  const fragShader=`
    varying vec3 vNormal;
    varying vec3 vWorldPos;
    uniform vec3 glowColor;
    uniform float time;
    uniform float pulse;
    uniform float opacity;
    void main(){
      vec3 N = normalize(vNormal);
      vec3 V = normalize(cameraPosition - vWorldPos);
      float rim = pow(1.0 - max(dot(N, V), 0.0), 2.4);
      float pulseA = 0.6 + pulse*0.4 + sin(time*1.6 + vWorldPos.y*3.0)*0.18;
      vec3 col = glowColor * (0.35 + pulseA*0.6);
      col += glowColor * rim * 1.9;
      float alpha = opacity * (0.35 + rim*1.1);
      gl_FragColor = vec4(col, alpha);
    }
  `;
  function createBrain(cx, colorHex){
    const group=new THREE.Group(); group.position.set(cx, 0.1, 0); BOX.add(group);
    const geo=makeBrainGeo();
    const uni={ glowColor:{value:new THREE.Color(colorHex)}, time:{value:0}, pulse:{value:0.5}, opacity:{value:0.95} };
    const mat=new THREE.ShaderMaterial({
      vertexShader:vertShader, fragmentShader:fragShader, uniforms:uni,
      transparent:true, blending:THREE.AdditiveBlending, depthWrite:false, side:THREE.DoubleSide
    });
    const mesh=new THREE.Mesh(geo, mat);
    mesh.rotation.y = cx<0 ? -0.5 : 0.5;
    mesh.rotation.z = cx<0 ? 0.1 : -0.1;
    group.add(mesh);
    // internal pulsing light core
    const coreMat=new THREE.MeshBasicMaterial({color:colorHex, transparent:true, opacity:0.16, blending:THREE.AdditiveBlending, depthWrite:false});
    const core=new THREE.Mesh(new THREE.SphereGeometry(0.34,24,24), coreMat);
    core.position.y=0.1; group.add(core);
    // sparse glowing synaptic points on surface
    const attr=geo.attributes.position;
    const ptsGeo=new THREE.BufferGeometry();
    const arr=new Float32Array(attr.count*3);
    for(let i=0;i<attr.count;i++){ arr[i*3]=attr.getX(i); arr[i*3+1]=attr.getY(i); arr[i*3+2]=attr.getZ(i); }
    ptsGeo.setAttribute('position', new THREE.BufferAttribute(arr,3));
    const ptsMat=new THREE.PointsMaterial({size:0.02, color:colorHex, transparent:true, opacity:0.5, blending:THREE.AdditiveBlending, depthWrite:false});
    const pts=new THREE.Points(ptsGeo, ptsMat);
    mesh.add(pts);
    return { group, mesh, mat, uniforms:uni, core };
  }
  const AMBER=0xFFAA00, CYAN=0x00F2FE;
  const LEFT=createBrain(-1.55, AMBER);
  const RIGHT=createBrain( 1.55, CYAN);

  /* ============================================================
     ARCHED RAINBOW NEURAL CONDUIT
     ============================================================ */
  const pipeGroup=new THREE.Group(); BOX.add(pipeGroup);
  const BX=1.55, GAP=0.3, ARC=0.95, DIP=-0.85;
  // Upper arch: L -> R through frontal lobes
  const CURVE_UP=new THREE.CatmullRomCurve3([
    new THREE.Vector3(-BX+GAP, 0.25, 0.1),
    new THREE.Vector3(-BX*0.42, 0.85, 0.35),
    new THREE.Vector3(0.0, ARC, 0.45),
    new THREE.Vector3(BX*0.42, 0.85, 0.35),
    new THREE.Vector3(BX-GAP, 0.25, 0.1)
  ], false, 'catmullrom', 0.5);
  // Lower arch: R -> L (symmetric dip)
  const CURVE_DN=new THREE.CatmullRomCurve3([
    new THREE.Vector3(BX-GAP, -0.15, 0.1),
    new THREE.Vector3(BX*0.42, -0.72, 0.35),
    new THREE.Vector3(0.0, DIP, 0.45),
    new THREE.Vector3(-BX*0.42, -0.72, 0.35),
    new THREE.Vector3(-BX+GAP, -0.15, 0.1)
  ], false, 'catmullrom', 0.5);
  // visible conduit strands (dense fiber-optic lattice along both arches)
  function conduitStrands(curve, count, color, opacity, radius){
    const pts=curve.getPoints(40);
    const segs=new Float32Array((pts.length-1)*2*3);
    let idx=0;
    for(let s=0;s<count;s++){
      const a=(s/count)*Math.PI*2;
      const r=radius;
      const prev=new THREE.Vector3();
      for(let i=0;i<pts.length-1;i++){
        const p=pts[i], q=pts[i+1];
        const d=new THREE.Vector3().subVectors(q,p).normalize();
        // perpendicular offset basis
        const u=new THREE.Vector3(Math.sin(a), Math.cos(a), 0);
        const perp=u.clone().applyAxisAngle(d, 0);
        const o1=perp.clone().multiplyScalar(r*(1-(i/(pts.length-1))*0.4));
        const o2=perp.clone().multiplyScalar(r*(1-((i+1)/(pts.length-1))*0.4));
        segs[idx++]=p.x+o1.x; segs[idx++]=p.y+o1.y; segs[idx++]=p.z+o1.z;
        segs[idx++]=q.x+o2.x; segs[idx++]=q.y+o2.y; segs[idx++]=q.z+o2.z;
      }
    }
    const gg=new THREE.BufferGeometry(); gg.setAttribute('position', new THREE.BufferAttribute(segs,3));
    const m=new THREE.LineBasicMaterial({color, transparent:true, opacity, blending:THREE.AdditiveBlending});
    const lines=new THREE.LineSegments(gg,m);
    pipeGroup.add(lines);
    return {mat:m};
  }
  const strandUp=conduitStrands(CURVE_UP, 14, AMBER, 0.35, 0.11);
  const strandDn=conduitStrands(CURVE_DN, 14, CYAN, 0.35, 0.11);
  // glowing heart-line cores of each conduit
  function heartLine(curve, color, opacity){
    const pts=curve.getPoints(48);
    const g=new THREE.BufferGeometry().setFromPoints(pts);
    const m=new THREE.LineBasicMaterial({color, transparent:true, opacity, blending:THREE.AdditiveBlending});
    pipeGroup.add(new THREE.Line(g,m));
    return {mat:m};
  }
  const coreUp=heartLine(CURVE_UP, AMBER, 0.6);
  const coreDn=heartLine(CURVE_DN, CYAN, 0.6);

  // ---- Braided central nexus (vortex where paths converge) ----
  const nexus=new THREE.Group(); pipeGroup.add(nexus);
  const NEXUS_N=260, NEXUS_R=0.4;
  const npGeo=new THREE.BufferGeometry(); const np=new Float32Array(NEXUS_N*3);
  npGeo.setAttribute('position', new THREE.BufferAttribute(np,3));
  const npMat=new THREE.PointsMaterial({size:0.05, color:0xffffff, transparent:true, opacity:0, blending:THREE.AdditiveBlending, depthWrite:false});
  const nexusPts=new THREE.Points(npGeo, npMat); nexus.add(nexusPts);
  // braid ring structure
  const ringGeo=new THREE.TorusGeometry(0.3, 0.012, 8, 48);
  const ringMat=new THREE.MeshBasicMaterial({color:0xffffff, transparent:true, opacity:0.5, blending:THREE.AdditiveBlending, depthWrite:false});
  const ring=new THREE.Mesh(ringGeo, ringMat);
  ring.rotation.x=Math.PI/2; ring.position.y=0.1; nexus.add(ring);
  const ring2=new THREE.Mesh(new THREE.TorusGeometry(0.2,0.009,8,40), ringMat);
  ring2.rotation.x=Math.PI/2; ring2.rotation.z=Math.PI/3; ring2.position.y=0.1; nexus.add(ring2);

  // ---- Glowing particle streams along the arches ----
  const PCOUNT=110;
  const pGeoA=new THREE.BufferGeometry(); const pPosA=new Float32Array(PCOUNT*3);
  pGeoA.setAttribute('position', new THREE.BufferAttribute(pPosA,3));
  const pGeoB=new THREE.BufferGeometry(); const pPosB=new Float32Array(PCOUNT*3);
  pGeoB.setAttribute('position', new THREE.BufferAttribute(pPosB,3));
  const pSizeA=new Float32Array(PCOUNT), pSizeB=new Float32Array(PCOUNT);
  for(let i=0;i<PCOUNT;i++){ pSizeA[i]=0.03+rnd()*0.05; pSizeB[i]=0.03+rnd()*0.05; }
  pGeoA.setAttribute('size', new THREE.BufferAttribute(pSizeA,1));
  pGeoB.setAttribute('size', new THREE.BufferAttribute(pSizeB,1));
  function streamMat(){
    return new THREE.PointsMaterial({
      color:0xffffff, size:0.06, transparent:true, opacity:0,
      blending:THREE.AdditiveBlending, depthWrite:false,
      sizeAttenuation:true
    });
  }
  const streamMatA=streamMat(); const streamMatB=streamMat();
  streamMatA.color.setHex(AMBER); streamMatB.color.setHex(CYAN);
  const streamA=new THREE.Points(pGeoA, streamMatA); pipeGroup.add(streamA);
  const streamB=new THREE.Points(pGeoB, streamMatB); pipeGroup.add(streamB);

  // ---- HTML HUD overlay aligned to arcs ----
  (function(){
    const wrap=document.getElementById('heroBoxWrap');
    if(!wrap) return;
    if(wrap.querySelector('.brain-overlay')) return;
    const ov=document.createElement('div');
    ov.className='brain-overlay';
    ov.innerHTML=`
      <span class="brain-label label-llama">Llama Solver</span>
      <span class="brain-label label-qwen">Qwen Critic</span>
      <span class="brain-note note-query">Query: Solve problem &rarr;</span>
      <span class="brain-note note-critique">&larr; Critique: Evaluation</span>
      <span class="brain-note note-gate">Decision Gate (Accept / Reject)</span>
      <span class="brain-note note-prerev">Pre-revision Signals</span>
      <span class="brain-note note-correct">Correction Confirmed</span>
    `;
    wrap.appendChild(ov);
  })();

  /* ---- State & API ---- */
  let direction=document.body.getAttribute('data-direction')||'lq';
  let streamOn=true;
  let outcome='idle', outcomeFlash=0, deflectAmt=0;
  function applyColor(){
    const c=new THREE.Color(COLORS[direction].r, COLORS[direction].g, COLORS[direction].b);
    canvas.dataset.streamColor='#'+c.getHexString();
  }
  const api={
    mode:'webgl',
    setDirection(d){ if(COLORS[d]){ direction=d; applyColor(); }},
    setStream(on){ streamOn=!!on; const fb=document.getElementById('scene-fallback'); if(fb) fb.classList.toggle('stream-on',!!on); if(!on) deflectAmt=0; },
    setOutcome(o){ if(o!=='helped'&&o!=='hurt'&&o!=='idle') return; if(o!==outcome){ outcome=o; outcomeFlash=o==='idle'?0:1; deflectAmt=o==='hurt'?1:0; } }
  };
  window.PeerGPTScene=api; applyColor();

  // pointer parallax (dampened)
  let mouseX=0, mouseY=0;
  window.addEventListener('pointermove', e=>{
    mouseX=(e.clientX/window.innerWidth-0.5)*2;
    mouseY=(e.clientY/window.innerHeight-0.5)*2;
  }, {passive:true});

  function onResize(){ const s=heroSize(); camera.aspect=s.w/s.h; camera.updateProjectionMatrix(); renderer.setSize(s.w,s.h); }
  window.addEventListener('resize', onResize);
  if(typeof ResizeObserver!=='undefined') new ResizeObserver(onResize).observe(heroWrap);
  function responsiveScale(){
    const s=heroSize();
    const isMobile=s.w<560;
    const scale=isMobile?0.6: s.w<880?0.8:1;
    BOX.scale.setScalar(scale);
    camera.position.z = isMobile? 13.5 : 12;
  }
  responsiveScale(); window.addEventListener('resize', responsiveScale);

  const clock=new THREE.Clock();
  function frame(){
    const dt=Math.min(clock.getDelta(),0.05); const t=clock.elapsedTime;
    // slow auto drift + dampened parallax
    BOX.rotation.y = Math.sin(t*0.07)*0.14 + mouseX*0.16;
    BOX.rotation.x = Math.sin(t*0.05)*0.05 + mouseY*0.08;
    // brain pulse at ~0.8 Hz and slow float
    const pulseA=0.55 + Math.sin(t*0.8)*0.45;
    const pulseB=0.55 + Math.sin(t*0.78+1.2)*0.45;
    LEFT.uniforms.time.value=t; RIGHT.uniforms.time.value=t+0.6;
    LEFT.uniforms.pulse.value=pulseA; RIGHT.uniforms.pulse.value=pulseB;
    LEFT.group.position.y=0.1+Math.sin(t*0.6)*0.06;
    RIGHT.group.position.y=0.1+Math.cos(t*0.58)*0.06;
    LEFT.core.scale.setScalar(1+Math.sin(t*1.3)*0.09+outcomeFlash*0.5);
    RIGHT.core.scale.setScalar(1+Math.cos(t*1.25)*0.09);
    // starfield
    const star=WORLD.children.find(c=>c.name==='starfield');
    if(star) star.rotation.y=t*0.003;
    // conduit heart-lines pulse
    coreUp.mat.opacity=0.4+Math.sin(t*2.0)*0.2;
    coreDn.mat.opacity=0.4+Math.cos(t*2.1)*0.2;
    strandUp.mat.opacity=0.2+Math.sin(t*2.2)*0.12;
    strandDn.mat.opacity=0.2+Math.cos(t*2.3)*0.12;
    // outcome flash on active brain
    if(outcomeFlash>0){
      outcomeFlash=Math.max(0, outcomeFlash-dt*1.2);
      const active=(direction==='lq')?LEFT:RIGHT;
      active.uniforms.pulse.value+=outcomeFlash*0.9;
      active.core.scale.setScalar(1+outcomeFlash*0.7);
    }
    // deflect for hurt outcome (diverge lower stream)
    const deflectTarget=(outcome==='hurt'&&streamOn)?1:0;
    deflectAmt+=(deflectTarget-deflectAmt)*0.07;
    const targetOp=streamOn?(1-deflectAmt*0.6):0;
    streamMatA.opacity+=(targetOp-streamMatA.opacity)*0.09;
    streamMatB.opacity+=(targetOp-streamMatB.opacity)*0.09;
    // nexus pulse + braid rotation
    npMat.opacity=targetOp*0.85;
    nexus.rotation.z=t*0.5;
    ring.scale.setScalar(1+Math.sin(t*2.0)*0.08);
    ring2.rotation.y=t*0.4;
    // populate nexus braid points
    for(let i=0;i<NEXUS_N;i++){
      const ph=i/NEXUS_N;
      const a=ph*Math.PI*2*3+t*1.2;      // triple helixes
      const a2=ph*Math.PI*2*3-t*1.2;
      const rn=NEXUS_R*(0.4+0.35*Math.sin(ph*Math.PI));  // braid waist
      const x1=Math.cos(a)*Math.sin(ph*Math.PI);
      const z1=Math.sin(a)*Math.sin(ph*Math.PI);
      const x2=Math.cos(a2)*Math.sin(ph*Math.PI);
      const z2=Math.sin(a2)*Math.sin(ph*Math.PI);
      if(i%3===0){ np[i*3]=x1*rn; np[i*3+1]=ph*0.5-0.25; np[i*3+2]=z1*rn; }
      else if(i%3===1){ np[i*3]=x2*rn; np[i*3+1]=ph*0.5-0.25; np[i*3+2]=z2*rn; }
      else { np[i*3]=(x1+x2)*0.5*rn*0.6; np[i*3+1]=ph*0.5-0.25; np[i*3+2]=(z1+z2)*0.5*rn; }
    }
    npGeo.attributes.position.needsUpdate=true;
    // populate particle streams along arches
    if(streamMatA.opacity>0.01){
      for(let i=0;i<PCOUNT;i++){
        // AMBER: L->R along upper arch
        const phA=(t*0.5+i/PCOUNT)%1;
        const pA=CURVE_UP.getPoint(phA);
        const wob=0.02*Math.sin(phA*24+i*1.3);
        pPosA[i*3]=pA.x+wob; pPosA[i*3+1]=pA.y+0.02*Math.sin(phA*20+i); pPosA[i*3+2]=pA.z;
        // CYAN: R->L along lower arch
        const phB=(1-(t*0.5+i/PCOUNT)%1);
        const pB=CURVE_DN.getPoint(phB);
        const bend=deflectAmt*0.9;
        pPosB[i*3]=pB.x+bend*Math.max(0,(phB-0.45))*Math.sin(phB*26);
        pPosB[i*3+1]=pB.y+0.02*Math.sin(phB*20+i); pPosB[i*3+2]=pB.z;
      }
      pGeoA.attributes.position.needsUpdate=true;
      pGeoB.attributes.position.needsUpdate=true;
    }
    // HUD note pulse sequence
    const ov=document.querySelector('.brain-overlay');
    if(ov){
      const seq=Math.floor(t*0.9)%5;  // cycle through 5 dynamic notes (excl. static labels)
      ov.querySelectorAll('.brain-note').forEach((el,i)=>{
        const noteIdx=[0,1,2,3,4]; // query, critique, gate, prerev, correct
        const active = (i===seq) || (i<2);  // keep query/critique static-prominent
        el.classList.toggle('note-active', active && i>=2 ? active : (i<2));
        el.style.opacity = (i>=2)? (i===seq?'1':'0.4') : '0.85';
        el.style.textShadow = (i>=2 && i===seq)? '0 0 8px currentColor' : (i<2?'0 0 6px currentColor':'none');
      });
    }
    // camera parallax dampening
    camera.position.x+=(mouseX*0.5-camera.position.x)*0.04;
    camera.position.y+=(0.9+mouseY*0.3-camera.position.y)*0.04;
    camera.lookAt(0,0.1,0);
    renderer.render(scene,camera);
  }
  if(REDUCED){ clock.getDelta(); frame(); } else renderer.setAnimationLoop(frame);
})();
