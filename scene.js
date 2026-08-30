/* ============================================================
   When to Listen — Realistic Brain Aquarium
   - Obsidian black (#000000) background
   - Wireframe aquarium box with data-grid artifacts
   - Two realistic brain meshes (procedural high-poly, pulsing
     amber / cyan glow via custom shaders)
   - Physical conduit pipeline with fiber-optic lattice + core
   - Bidirectional amber/cyan particle streams + pulsing waves
   - 3D UI overlay labels (HTML) + subtle bloom + slow camera drift
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
    window.PeerGPTScene={ setDirection(d){document.body.setAttribute('data-direction',d)}, setStream(on){const el=document.getElementById('scene-fallback'); if(el) el.classList.toggle('stream-on',!!on)}, setOutcome(){}, mode:'css'};
    return;
  }
  const canvas=document.getElementById('scene-canvas');
  const heroWrap=document.getElementById('heroBoxWrap');
  if(!canvas||!heroWrap){ document.body.classList.add('no-webgl'); return; }
  const COLORS={ lq:{r:226/255,g:162/255,b:51/255}, ql:{r:69/255,g:179/255,b:170/255} };
  function heroSize(){ const r=heroWrap.getBoundingClientRect(); return {w:Math.max(r.width,320), h:Math.max(r.height,340)}; }
  let _sz=heroSize();
  const renderer=new THREE.WebGLRenderer({canvas, antialias:true, alpha:true});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,1.8));
  renderer.setSize(_sz.w,_sz.h);
  renderer.setClearColor(0x000000,1);
  const scene=new THREE.Scene();
  scene.background=new THREE.Color(0x000000);
  scene.fog=new THREE.Fog(0x000000, 8, 18);
  const camera=new THREE.PerspectiveCamera(44, _sz.w/_sz.h, 0.1, 80);
  camera.position.set(0, 0.6, 9.5);
  camera.lookAt(0,0,0);
  const WORLD=new THREE.Group(); scene.add(WORLD);
  // subtle starfield
  (function(){
    const n=120; const pos=new Float32Array(n*3); let s=29; function rnd(){ s=(s*16807)%2147483647; return s/2147483647; }
    for(let i=0;i<n;i++){ pos[i*3]=(rnd()*2-1)*20; pos[i*3+1]=(rnd()*2-1)*12; pos[i*3+2]=(rnd()*2-1)*9-3; }
    const g=new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos,3));
    const m=new THREE.PointsMaterial({size:0.045, color:0xffffff, transparent:true, opacity:0.22, depthWrite:false});
    const p=new THREE.Points(g,m); p.name='starfield'; WORLD.add(p);
  })();
  // Wireframe aquarium box with grid artifacts
  const BOX=new THREE.Group(); BOX.position.set(0,0,0); WORLD.add(BOX);
  const boxW=5.4, boxH=3.2, boxD=3.0;
  const boxGeo=new THREE.BoxGeometry(boxW,boxH,boxD);
  const edges=new THREE.EdgesGeometry(boxGeo);
  const lineMat=new THREE.LineBasicMaterial({color:0xE8F0F0, transparent:true, opacity:0.42});
  const boxLines=new THREE.LineSegments(edges, lineMat); BOX.add(boxLines);
  const glowMat=new THREE.LineBasicMaterial({color:0x7FF0E8, transparent:true, opacity:0.08, blending:THREE.AdditiveBlending, depthWrite:false});
  const glowLines=new THREE.LineSegments(edges, glowMat); glowLines.scale.set(1.015,1.015,1.015); BOX.add(glowLines);
  // data-grid artifacts on edges (small ticks)
  (function(){
    const tickGeo=new THREE.BufferGeometry();
    const ticks=[];
    const divisions=6;
    for(let i=1;i<divisions;i++){
      const t=i/divisions;
      // top front edge ticks
      ticks.push(-boxW/2 + t*boxW, boxH/2, boxD/2,  -boxW/2 + t*boxW, boxH/2-0.12, boxD/2);
      ticks.push(-boxW/2 + t*boxW, -boxH/2, boxD/2,  -boxW/2 + t*boxW, -boxH/2+0.12, boxD/2);
    }
    tickGeo.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(ticks),3));
    const tm=new THREE.LineBasicMaterial({color:0xffffff, transparent:true, opacity:0.18});
    BOX.add(new THREE.LineSegments(tickGeo, tm));
  })();
  // --- Realistic brain shader ---
  const vertShader=`
    varying vec3 vNormal;
    varying vec3 vPos;
    uniform float time;
    uniform float pulse;
    void main(){
      vNormal = normalize(normalMatrix * normal);
      vPos = position;
      vec3 pos = position;
      // subtle breathing scale
      pos *= 1.0 + pulse*0.03 * sin(time*0.9 + position.x*2.0);
      // slight gyri displacement (noise-like)
      float n = sin(pos.x*8.0 + time*0.3)*0.02 + sin(pos.y*9.0)*0.015 + sin(pos.z*10.0)*0.015;
      pos += normal * n;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(pos,1.0);
    }
  `;
  const fragShader=`
    varying vec3 vNormal;
    varying vec3 vPos;
    uniform vec3 glowColor;
    uniform float time;
    uniform float pulse;
    uniform float opacity;
    void main(){
      float fresnel = pow(1.0 - abs(dot(vNormal, vec3(0.0,0.0,1.0))), 2.8);
      float core = 0.55 + pulse*0.35 + sin(time*1.2 + vPos.x*3.0)*0.12;
      vec3 col = glowColor * (core + fresnel*1.6);
      // inner translucent
      float alpha = opacity * (0.75 + fresnel*0.9);
      // edge bloom
      col += glowColor * fresnel * 0.8;
      gl_FragColor = vec4(col, alpha);
    }
  `;
  function createBrain(cx, colorHex){
    const g=new THREE.Group(); g.position.set(cx, 0.08, 0);
    BOX.add(g);
    // high-poly brain base
    const baseGeo=new THREE.IcosahedronGeometry(0.92, 4);
    const posAttr=baseGeo.attributes.position;
    const v=new THREE.Vector3();
    // deform to brain-like ellipsoid + folds
    for(let i=0;i<posAttr.count;i++){
      v.fromBufferAttribute(posAttr, i);
      // ellipsoid stretch: frontal bulge, occipital taper
      v.x *= 1.18; v.y *= 0.82; v.z *= 0.88;
      // brain fissure indent on top (longitudinal)
      const fissure = (Math.abs(v.y) < 0.25 && v.x < 0.2) ? -0.08 * Math.cos(v.x*3.0) : 0.0;
      // gyri noise
      const n = Math.sin(v.x*7.5)*0.04 + Math.sin(v.y*8.2)*0.03 + Math.sin(v.z*9.1)*0.03 + Math.cos(v.x*12.0 + v.y*8.0)*0.015;
      const len = v.length();
      v.normalize().multiplyScalar(0.92 + n + fissure);
      // slightly flatten bottom (brain stem)
      if(v.y < -0.45) v.y *= 0.85;
      posAttr.setXYZ(i, v.x, v.y, v.z);
    }
    posAttr.needsUpdate=true; baseGeo.computeVertexNormals();
    const uni = { glowColor:{value:new THREE.Color(colorHex)}, time:{value:0}, pulse:{value:0}, opacity:{value:0.95} };
    const mat=new THREE.ShaderMaterial({
      vertexShader: vertShader,
      fragmentShader: fragShader,
      uniforms: uni,
      transparent:true,
      blending: THREE.AdditiveBlending,
      depthWrite:false,
      side: THREE.DoubleSide
    });
    const mesh=new THREE.Mesh(baseGeo, mat);
    // face each other: left brain rotated to face right, right faces left
    mesh.rotation.y = cx < 0 ? -0.35 : 0.35;
    mesh.rotation.z = cx < 0 ? 0.08 : -0.08;
    g.add(mesh);
    // inner light core (pulsing sphere)
    const coreMat=new THREE.MeshBasicMaterial({color: colorHex, transparent:true, opacity:0.18, blending:THREE.AdditiveBlending, depthWrite:false});
    const core=new THREE.Mesh(new THREE.SphereGeometry(0.38,16,16), coreMat);
    g.add(core);
    // outer wireframe sulci hint
    const wire=new THREE.LineSegments(new THREE.WireframeGeometry(baseGeo), new THREE.LineBasicMaterial({color: colorHex, transparent:true, opacity:0.09}));
    g.add(wire);
    // hemisphere separation line (light)
    return { group:g, mesh, mat, uniforms:uni, core };
  }
  const AMBER=0xE2A233, CYAN=0x3EC0AE;
  const LEFT = createBrain(-1.42, AMBER);
  const RIGHT = createBrain( 1.42, CYAN);
  // --- Physical conduit pipeline ---
  const pipeGroup=new THREE.Group(); BOX.add(pipeGroup);
  // main beam cylinder between brains
  const pipeLen=1.35; // gap
  const pipeGeo=new THREE.CylinderGeometry(0.14,0.14, pipeLen, 20,1,true);
  pipeGeo.rotateZ(Math.PI/2);
  const pipeMat=new THREE.MeshBasicMaterial({color:0xffffff, transparent:true, opacity:0.10, blending:THREE.AdditiveBlending, depthWrite:false, side:THREE.DoubleSide});
  const pipe=new THREE.Mesh(pipeGeo, pipeMat);
  pipe.position.set(0, -0.02, 0.12);
  pipeGroup.add(pipe);
  // pulsing core beam
  const coreBeamGeo=new THREE.CylinderGeometry(0.055,0.055, pipeLen, 16,1,true);
  coreBeamGeo.rotateZ(Math.PI/2);
  const coreBeamMat=new THREE.MeshBasicMaterial({color:0xffffff, transparent:true, opacity:0.55, blending:THREE.AdditiveBlending, depthWrite:false});
  const coreBeam=new THREE.Mesh(coreBeamGeo, coreBeamMat);
  coreBeam.position.copy(pipe.position);
  pipeGroup.add(coreBeam);
  // fiber-optic lattice threads (dense)
  (function(){
    const fiberCount=22;
    const segs=new Float32Array(fiberCount*2*3);
    let idx=0;
    for(let i=0;i<fiberCount;i++){
      const ang=(i/fiberCount)*Math.PI*2;
      const r=0.09 + (i%3)*0.015;
      const y0=Math.cos(ang)*r, z0=Math.sin(ang)*r;
      const y1=Math.cos(ang+0.6)*r*0.95, z1=Math.sin(ang+0.6)*r*0.95;
      // gentle catenary
      segs[idx++]= -pipeLen/2; segs[idx++]= y0; segs[idx++]= z0+0.12;
      segs[idx++]=  pipeLen/2; segs[idx++]= y1; segs[idx++]= z1+0.12;
    }
    const g=new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(segs,3));
    const m=new THREE.LineBasicMaterial({color:0xffffff, transparent:true, opacity:0.22, blending:THREE.AdditiveBlending});
    const lines=new THREE.LineSegments(g,m);
    pipeGroup.add(lines);
  })();
  // glowing end caps (where pipe meets brains)
  const capGeo=new THREE.RingGeometry(0.11,0.16,24); capGeo.rotateY(Math.PI/2);
  const capMatA=new THREE.MeshBasicMaterial({color:AMBER, transparent:true, opacity:0.45, side:THREE.DoubleSide, blending:THREE.AdditiveBlending, depthWrite:false});
  const capMatB=new THREE.MeshBasicMaterial({color:CYAN, transparent:true, opacity:0.45, side:THREE.DoubleSide, blending:THREE.AdditiveBlending, depthWrite:false});
  const capL=new THREE.Mesh(capGeo, capMatA); capL.position.set(-pipeLen/2, -0.02, 0.12); pipeGroup.add(capL);
  const capR=new THREE.Mesh(capGeo, capMatB); capR.position.set( pipeLen/2, -0.02, 0.12); pipeGroup.add(capR);
  // --- Bidirectional particle streams (high-density) ---
  const CURVE_A=new THREE.CatmullRomCurve3([ new THREE.Vector3(-1.02,-0.02,0.12), new THREE.Vector3(-0.35,0.12,0.18), new THREE.Vector3(0.35,0.08,0.14), new THREE.Vector3(1.02,-0.02,0.12) ]);
  const CURVE_B=new THREE.CatmullRomCurve3([ new THREE.Vector3(1.02,-0.02,0.12), new THREE.Vector3(0.35,-0.08,0.18), new THREE.Vector3(-0.35,-0.12,0.14), new THREE.Vector3(-1.02,-0.02,0.12) ]);
  const PCOUNT=72;
  const pPosA=new Float32Array(PCOUNT*3), pPosB=new Float32Array(PCOUNT*3);
  const pGeoA=new THREE.BufferGeometry(); pGeoA.setAttribute('position', new THREE.BufferAttribute(pPosA,3));
  const pGeoB=new THREE.BufferGeometry(); pGeoB.setAttribute('position', new THREE.BufferAttribute(pPosB,3));
  const streamMatA=new THREE.PointsMaterial({size:0.075, transparent:true, opacity:0, color:AMBER, blending:THREE.AdditiveBlending, depthWrite:false});
  const streamMatB=new THREE.PointsMaterial({size:0.075, transparent:true, opacity:0, color:CYAN, blending:THREE.AdditiveBlending, depthWrite:false});
  const streamA=new THREE.Points(pGeoA, streamMatA); const streamB=new THREE.Points(pGeoB, streamMatB);
  BOX.add(streamA); BOX.add(streamB);
  // pulsing waves at core
  const waveGeo=new THREE.RingGeometry(0.10,0.13,24); waveGeo.rotateX(Math.PI/2);
  const waveMat=new THREE.MeshBasicMaterial({color:0xffffff, transparent:true, opacity:0, side:THREE.DoubleSide, blending:THREE.AdditiveBlending, depthWrite:false});
  const wave=new THREE.Mesh(waveGeo, waveMat); wave.position.set(0,-0.02,0.12); BOX.add(wave);
  // --- HTML overlay labels inside hero-stage ---
  (function(){
    const wrap=document.getElementById('heroBoxWrap');
    if(!wrap) return;
    if(wrap.querySelector('.brain-overlay')) return;
    const ov=document.createElement('div');
    ov.className='brain-overlay';
    ov.innerHTML=`
      <span class="brain-label label-llama">LLAMA Solver</span>
      <span class="brain-label label-qwen">QWEN Critic</span>
      <span class="brain-note note-query">Query: Solve problem.</span>
      <span class="brain-note note-critique">Critique: Correction?</span>
      <span class="brain-note note-prerev">Pre-revision signals: accept?</span>
      <span class="brain-note note-correction">Correction: confirm?</span>
    `;
    wrap.appendChild(ov);
  })();
  // ---- State ----
  let direction=document.body.getAttribute('data-direction')||'lq';
  let streamOn=true; // always visible in hero, demo/method will drive but hero keeps it on
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
  // initial stream visible in hero
  streamOn=true;
  // pointer parallax
  let mouseX=0, mouseY=0;
  window.addEventListener('pointermove', e=>{ mouseX=(e.clientX/window.innerWidth-0.5)*2; mouseY=(e.clientY/window.innerHeight-0.5)*2; }, {passive:true});
  function onResize(){ const s=heroSize(); camera.aspect=s.w/s.h; camera.updateProjectionMatrix(); renderer.setSize(s.w,s.h); }
  window.addEventListener('resize', onResize);
  if(typeof ResizeObserver!=='undefined') new ResizeObserver(onResize).observe(heroWrap);
  // responsive scaling
  function responsiveScale(){
    const s=heroSize();
    const isMobile=s.w<560;
    const scale=isMobile?0.62: s.w<880?0.82:1;
    BOX.scale.setScalar(scale);
    camera.position.z = isMobile? 11.2 : 9.5;
  }
  responsiveScale(); window.addEventListener('resize', responsiveScale);
  const clock=new THREE.Clock();
  function frame(){
    const dt=Math.min(clock.getDelta(),0.05); const t=clock.elapsedTime;
    // slow auto drift of whole aquarium
    BOX.rotation.y = Math.sin(t*0.07)*0.12 + mouseX*0.14;
    BOX.rotation.x = Math.sin(t*0.05)*0.04 + mouseY*0.07;
    // brain internal pulse + slow float
    LEFT.uniforms.time.value=t; RIGHT.uniforms.time.value=t+0.6;
    LEFT.uniforms.pulse.value=0.55 + Math.sin(t*1.1)*0.45;
    RIGHT.uniforms.pulse.value=0.55 + Math.sin(t*1.05+1.2)*0.45;
    LEFT.group.position.y = Math.sin(t*0.7)*0.06;
    RIGHT.group.position.y = Math.cos(t*0.68)*0.06;
    LEFT.core.scale.setScalar(1 + Math.sin(t*1.4)*0.08 + outcomeFlash*0.5);
    RIGHT.core.scale.setScalar(1 + Math.cos(t*1.35)*0.08);
    // starfield drift
    const star=WORLD.children.find(c=>c.name==='starfield');
    if(star){ star.rotation.y=t*0.003; }
    // pipeline core pulse (mix amber/cyan)
    const mixPulse = 0.45 + Math.sin(t*2.2)*0.25;
    coreBeamMat.color.setHSL(0.12 + mixPulse*0.04, 0.9, 0.55);
    coreBeamMat.opacity=0.45 + Math.sin(t*3.0)*0.18;
    capL.material.opacity=0.4 + Math.sin(t*2.0)*0.2;
    capR.material.opacity=0.4 + Math.cos(t*2.1)*0.2;
    // outcome flash on active brain
    if(outcomeFlash>0){
      outcomeFlash=Math.max(0, outcomeFlash - dt*1.2);
      const active=(direction==='lq')? LEFT: RIGHT;
      active.uniforms.pulse.value += outcomeFlash*0.9;
      active.core.scale.setScalar(1 + outcomeFlash*0.7);
    }
    const deflectTarget=(outcome==='hurt'&&streamOn)?1:0;
    deflectAmt += (deflectTarget - deflectAmt)*0.07;
    const targetOp = streamOn? (1 - deflectAmt*0.7) : 0;
    streamMatA.opacity += (targetOp - streamMatA.opacity)*0.09;
    streamMatB.opacity += (targetOp - streamMatB.opacity)*0.09;
    wave.material.opacity = targetOp*0.28 * (0.5 + Math.sin(t*4.0)*0.5);
    if(streamMatA.opacity>0.01){
      for(let i=0;i<PCOUNT;i++){
        const phA=(t*0.68 + i/PCOUNT)%1;
        const pA=CURVE_A.getPoint(phA);
        pPosA[i*3]=pA.x + Math.sin(phA*30 + i)*0.02;
        pPosA[i*3+1]=pA.y + Math.sin(phA*28 + i)*0.02;
        pPosA[i*3+2]=pA.z + Math.cos(phA*22 + i)*0.02;
        const phB=(1 - (t*0.66 + i/PCOUNT)%1);
        const pB=CURVE_B.getPoint(phB);
        const bend=deflectAmt*0.9;
        pB.x += bend*Math.max(0,(phB-0.45))*Math.sin(phB*28);
        pPosB[i*3]=pB.x + Math.sin(phB*30 + i)*0.02;
        pPosB[i*3+1]=pB.y + Math.sin(phB*28 + i)*0.02;
        pPosB[i*3+2]=pB.z + Math.cos(phB*22 + i)*0.02;
      }
      pGeoA.attributes.position.needsUpdate=true;
      pGeoB.attributes.position.needsUpdate=true;
      wave.scale.setScalar(0.5 + (t*0.9%1)*1.6);
      wave.rotation.y = t*0.8;
    }
    // pulsing data snippets (HTML) — sequence
    const ov=document.querySelector('.brain-overlay');
    if(ov){
      const seq = Math.floor(t*0.9)%4;
      ov.querySelectorAll('.brain-note').forEach((el,i)=>{
        const active = i===seq;
        el.style.opacity = active? '1' : '0.42';
        el.style.textShadow = active? '0 0 8px currentColor' : 'none';
      });
    }
    camera.position.x += (mouseX*0.45 - camera.position.x)*0.04;
    camera.position.y += (0.6 + mouseY*0.25 - camera.position.y)*0.04;
    camera.lookAt(0,0,0);
    renderer.render(scene,camera);
  }
  if(REDUCED){ clock.getDelta(); frame(); } else renderer.setAnimationLoop(frame);
})();
