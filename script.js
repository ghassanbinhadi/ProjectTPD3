// ============================================================
// When to Listen — single-page behavior
// - smooth scroll nav + active section tracking (top nav + rail)
// - direction toggle (drives CSS accent + 3D scene)
// - outcome toggle (drives 3D scene HELPED/HURT)
// - scroll-driven 3D stream (Method -> show, Results -> outcome)
// - bar fill animation on view
// - demo case stepper (6 HELPED examples)
// ============================================================

(function(){
  const body=document.body;

  // ============ Smooth scroll nav ============
  document.querySelectorAll('[data-scroll-to]').forEach(a=>{
    a.addEventListener('click', function(e){
      e.preventDefault();
      const id=a.getAttribute('data-scroll-to');
      const el=document.getElementById(id);
      if(el) el.scrollIntoView({ behavior:'smooth', block:'start' });
      history.replaceState(null,'','#'+id);
    });
  });

  // ============ Active section tracking ============
  const sections=['hero','background','method','results','demo','policy','team'];
  const railDots=document.querySelectorAll('.rail-dot');
  const navLinks=document.querySelectorAll('.topnav__links a');
  const observer=new IntersectionObserver((entries)=>{
    entries.forEach(entry=>{
      if(entry.isIntersecting){
        const id=entry.target.id;
        railDots.forEach(d=> d.classList.toggle('active', d.getAttribute('data-scroll-to')===id));
        navLinks.forEach(l=> l.classList.toggle('active', l.getAttribute('data-scroll-to')===id));
        driveBySection(id);
      }
    });
  }, { rootMargin:'-45% 0px -45% 0px', threshold:0 });
  sections.forEach(id=>{
    const el=document.getElementById(id);
    if(el) observer.observe(el);
  });

  // ============ Drive 3D scene from scroll section ============
  let activeOutcome='helped';
  const outcomeHint=document.getElementById('outcomeHint');
  function driveBySection(id){
    if(!window.PeerGPTScene) return;
    // Method: stream on, Results: stream + outcome, else idle (but keep direction)
    if(id==='method'){
      window.PeerGPTScene.setStream(true);
      window.PeerGPTScene.setOutcome('idle');
    } else if(id==='results'){
      window.PeerGPTScene.setStream(true);
      window.PeerGPTScene.setOutcome(activeOutcome);
    } else if(id==='hero'){
      window.PeerGPTScene.setStream(false);
      window.PeerGPTScene.setOutcome('idle');
    } else {
      // demo/policy/team etc — keep stream faintly visible? hide to reduce clutter on scroll
      window.PeerGPTScene.setStream(false);
      window.PeerGPTScene.setOutcome('idle');
    }
  }
  // If scene not yet ready when observer fires, retry after load
  window.addEventListener('load', ()=>{ const h=location.hash.replace('#','')||'hero'; driveBySection(h); });

  // ============ Direction toggle ============
  (function(){
    const btns=document.querySelectorAll('.dir-btn');
    btns.forEach(btn=>{
      btn.addEventListener('click', ()=>{
        const dir=btn.getAttribute('data-dir');
        body.setAttribute('data-direction', dir);
        btns.forEach(b=> b.classList.toggle('active', b===btn));
        if(window.PeerGPTScene) window.PeerGPTScene.setDirection(dir);
      });
    });
  })();

  // ============ Outcome toggle ============
  (function(){
    const btns=document.querySelectorAll('.out-btn');
    btns.forEach(btn=>{
      btn.addEventListener('click', ()=>{
        activeOutcome=btn.getAttribute('data-outcome');
        btns.forEach(b=> b.classList.toggle('active', b===btn));
        // only drive scene if currently on results; otherwise hint still updates
        const onResults = document.querySelector('.rail-dot[data-scroll-to="results"].active');
        if(window.PeerGPTScene && onResults) window.PeerGPTScene.setOutcome(activeOutcome);
        else if(window.PeerGPTScene) window.PeerGPTScene.setOutcome(activeOutcome);
        if(outcomeHint){
          outcomeHint.textContent = activeOutcome==='helped'
            ? 'The critique lands and the Solver cluster brightens — it accepted the critique.'
            : 'The critique stream deflects and fades before reaching the Solver — it rejected the critique.';
        }
      });
    });
  })();

  // ============ Bar fills on view ============
  (function(){
    const fills=document.querySelectorAll('.bar-fill[data-w]');
    const barObs=new IntersectionObserver((entries)=>{
      entries.forEach(e=>{
        if(e.isIntersecting){
          const w=e.target.getAttribute('data-w');
          // small delay for staggered feel
          requestAnimationFrame(()=>{ e.target.style.width=w; });
          barObs.unobserve(e.target);
        }
      });
    }, { threshold:0.2 });
    fills.forEach(f=> barObs.observe(f));
  })();

  // ============ Demo — master-detail (6 questions beside full trace) ============
  (function(){
    const CASES={
      shells:{
        dir:'lq', title:'Martha shells', qlabel:'Llama solves → Qwen critiques',
        question:'Martha has been collecting shells since she turned 5 years old, every month she collects one shell. By her 10th birthday, how many shells will Martha have collected?',
        steps:[
          { eyebrow:'Question', tag:null, body:'Martha collects one shell per month from age 5 to her 10th birthday. How many shells by then?' },
          { eyebrow:'Solver — Llama', tag:{text:'Answer: 6', cls:'tag-neutral'}, body:'Llama answers 6 — counting years (10 − 5 + 1) rather than months, missing the per-month rate.' },
          { eyebrow:'Critic verdict — Qwen', tag:{text:'INCORRECT', cls:'tag-wrong'}, body:'Qwen: "the other model likely did not account for the fact that Martha collects one shell each month for 60 months."' },
          { eyebrow:'Critic’s proposed answer', tag:{text:'Proposed: 60', cls:'tag-neutral'}, body:'Qwen computes 5 years × 12 months = 60 shells and proposes 60.' },
          { eyebrow:'Solver revision', tag:{text:'Revised: 60', cls:'tag-right'}, body:'Llama revises to 60 shells.' },
          { eyebrow:'Outcome', tag:{text:'HELPED — gold 60', cls:'tag-right'}, body:'Revision correct. Real poster example; counts toward the 29.1% HELPED rate for Llama→Qwen.' }
        ]
      },
      train:{
        dir:'lq', title:'Train speed', qlabel:'Llama solves → Qwen critiques',
        question:'A train travels 60 miles in 1.5 hours. If it continues at the same speed, how many miles will it travel in 4 hours?',
        steps:[
          { eyebrow:'Question', tag:null, body:'A train covers 60 miles in 1.5 hours. At the same speed, how far in 4 hours?' },
          { eyebrow:'Solver — Llama', tag:{text:'Answer: 240', cls:'tag-neutral'}, body:'Llama multiplies 60 × 4 = 240, using total distance instead of first finding speed per hour.' },
          { eyebrow:'Critic verdict — Qwen', tag:{text:'INCORRECT', cls:'tag-wrong'}, body:'Qwen: "the solver multiplied the total distance by 4 instead of first finding the speed per hour."' },
          { eyebrow:'Critic’s proposed answer', tag:{text:'Proposed: 160', cls:'tag-neutral'}, body:'Qwen finds 40 mph (60 / 1.5) and proposes 160 miles (40 × 4).' },
          { eyebrow:'Solver revision', tag:{text:'Revised: 160', cls:'tag-right'}, body:'Llama revises to 160 miles.' },
          { eyebrow:'Outcome', tag:{text:'HELPED — gold 160', cls:'tag-right'}, body:'Representative example (illustrative).' }
        ]
      },
      flour:{
        dir:'lq', title:'Flour for cookies', qlabel:'Llama solves → Qwen critiques',
        question:'A recipe calls for 2 cups of flour to make 12 cookies. How many cups of flour are needed to make 30 cookies?',
        steps:[
          { eyebrow:'Question', tag:null, body:'2 cups make 12 cookies. How many cups for 30 cookies?' },
          { eyebrow:'Solver — Llama', tag:{text:'Answer: 4', cls:'tag-neutral'}, body:'Llama scales by 2× (12→24) giving 4 cups, instead of the correct 2.5× (12→30).' },
          { eyebrow:'Critic verdict — Qwen', tag:{text:'INCORRECT', cls:'tag-wrong'}, body:'Qwen: "the solver used a 2x scaling factor instead of the correct 2.5x scaling factor for 30 cookies."' },
          { eyebrow:'Critic’s proposed answer', tag:{text:'Proposed: 5', cls:'tag-neutral'}, body:'Qwen proposes 5 cups (2 × 2.5).' },
          { eyebrow:'Solver revision', tag:{text:'Revised: 5', cls:'tag-right'}, body:'Llama revises to 5 cups.' },
          { eyebrow:'Outcome', tag:{text:'HELPED — gold 5', cls:'tag-right'}, body:'Representative example (illustrative).' }
        ]
      },
      ali:{
        dir:'ql', title:'Ali saves & spends', qlabel:'Qwen solves → Llama critiques',
        question:'Ali saves $8 every week. After 6 weeks, he spends $20 on a toy. How much money does he have left?',
        steps:[
          { eyebrow:'Question', tag:null, body:'Ali saves $8/week for 6 weeks, then spends $20. How much left?' },
          { eyebrow:'Solver — Qwen', tag:{text:'Answer: 48', cls:'tag-neutral'}, body:'Qwen computes 8 × 6 = 48 but forgets to subtract the $20 spent.' },
          { eyebrow:'Critic verdict — Llama', tag:{text:'INCORRECT', cls:'tag-wrong'}, body:'Llama: "the solver calculated total savings but forgot to subtract the $20 spent on the toy."' },
          { eyebrow:'Critic’s proposed answer', tag:{text:'Proposed: 28', cls:'tag-neutral'}, body:'Llama proposes 28 (48 − 20).' },
          { eyebrow:'Solver revision', tag:{text:'Revised: 28', cls:'tag-right'}, body:'Qwen revises to 28.' },
          { eyebrow:'Outcome', tag:{text:'HELPED — gold 28', cls:'tag-right'}, body:'Representative example (illustrative).' }
        ]
      },
      garden:{
        dir:'ql', title:'Tomato plants', qlabel:'Qwen solves → Llama critiques',
        question:'A garden has 8 rows of tomato plants with 15 plants in each row. If 12 plants die, how many tomato plants remain?',
        steps:[
          { eyebrow:'Question', tag:null, body:'8 rows × 15 plants, 12 die. How many remain?' },
          { eyebrow:'Solver — Qwen', tag:{text:'Answer: 120', cls:'tag-neutral'}, body:'Qwen finds 8 × 15 = 120 total but does not subtract the 12 that died.' },
          { eyebrow:'Critic verdict — Llama', tag:{text:'INCORRECT', cls:'tag-wrong'}, body:'Llama: "the solver found the total planted but didn\'t subtract the 12 plants that died."' },
          { eyebrow:'Critic’s proposed answer', tag:{text:'Proposed: 108', cls:'tag-neutral'}, body:'Llama proposes 108 (120 − 12).' },
          { eyebrow:'Solver revision', tag:{text:'Revised: 108', cls:'tag-right'}, body:'Qwen revises to 108.' },
          { eyebrow:'Outcome', tag:{text:'HELPED — gold 108', cls:'tag-right'}, body:'Representative example (illustrative).' }
        ]
      },
      sara:{
        dir:'ql', title:'Sara reading', qlabel:'Qwen solves → Llama critiques',
        question:'Sara reads 24 pages per day. Her book has 312 pages. If she has already read 96 pages, how many more days will it take her to finish?',
        steps:[
          { eyebrow:'Question', tag:null, body:'Sara reads 24 pages/day; book is 312 pages; she has read 96. How many more days?' },
          { eyebrow:'Solver — Qwen', tag:{text:'Answer: 13', cls:'tag-neutral'}, body:'Qwen divides 312 / 24 = 13, using the full length without subtracting the 96 already read.' },
          { eyebrow:'Critic verdict — Llama', tag:{text:'INCORRECT', cls:'tag-wrong'}, body:'Llama: "the solver divided the full book length by the daily pace without subtracting the 96 pages already read."' },
          { eyebrow:'Critic’s proposed answer', tag:{text:'Proposed: 9', cls:'tag-neutral'}, body:'Llama proposes 9 days ((312 − 96) / 24).' },
          { eyebrow:'Solver revision', tag:{text:'Revised: 9', cls:'tag-right'}, body:'Qwen revises to 9 days.' },
          { eyebrow:'Outcome', tag:{text:'HELPED — gold 9', cls:'tag-right'}, body:'Representative example (illustrative).' }
        ]
      }
    };
    const ORDER=['shells','train','flour','ali','garden','sara'];
    const listEl=document.getElementById('demoList');
    const detailEl=document.getElementById('demoDetail');
    if(!listEl || !detailEl) return;

    function renderDetail(key){
      const c=CASES[key];
      // sync direction
      body.setAttribute('data-direction', c.dir);
      document.querySelectorAll('.dir-btn').forEach(b=> b.classList.toggle('active', b.getAttribute('data-dir')===c.dir));
      if(window.PeerGPTScene) window.PeerGPTScene.setDirection(c.dir);
      // highlight active card
      listEl.querySelectorAll('.demo-qcard').forEach(el=> el.classList.toggle('active', el.dataset.key===key));
      // build detail: full trace like spec Case 1
      let html = `<span class="detail-eyebrow">${c.title} · ${c.qlabel}</span>`;
      html += `<p class="detail-question">${c.question}</p><div class="detail-grid">`;
      c.steps.forEach(s=>{
        const isQuestion = s.eyebrow==='Question';
        const cls = s.tag ? s.tag.cls : '';
        const tag = s.tag ? `<span class="detail-tag ${cls}">${s.tag.text}</span>` : '';
        const rowCls = s.eyebrow==='Outcome' ? 'detail-row highlight' : 'detail-row';
        html += `<div class="${rowCls}"><span class="detail-label">${s.eyebrow}${tag}</span><span class="detail-body">${s.body}</span></div>`;
      });
      html += `</div>`;
      detailEl.innerHTML=html;
    }

    // build list of 6
    ORDER.forEach(k=>{
      const c=CASES[k];
      const btn=document.createElement('button');
      btn.className='demo-qcard';
      btn.dataset.key=k;
      btn.innerHTML=`<span class="q-title">${c.title}</span><span class="q-meta">${c.qlabel}</span><span class="q-preview">${c.question.slice(0,72)}…</span>`;
      btn.addEventListener('click', ()=> renderDetail(k));
      listEl.appendChild(btn);
    });
    renderDetail(ORDER[0]);
    window.__demo={ CASES, renderDetail };
  })();
})();
