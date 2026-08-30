// ============================================================
// PeerGPT — Corvus pagination-app behavior
// 1. Click-to-continue loader (% -> 100% -> CLICK TO CONTINUE)
// 2. Sound button toggle (global)
// 3. Numbered pagination switcher (001-007, swap panels in place)
// 4. Direction toggle drives CSS accent + 3D scene
// 5. Outcome toggle drives 3D scene
// 6. Demo case stepper
// ============================================================

// ============ 1. Click-to-continue loader ============
(function(){
  const loader  = document.getElementById('loader');
  const counter = document.getElementById('loaderCounter');
  const cta     = document.getElementById('loaderCta');
  if (!loader || !counter || !cta) return;

  let pct = 0;
  let started = false;
  const tick = setInterval(function(){
    pct += 1 + Math.floor(Math.random() * 3);
    if (pct >= 100) { pct = 100; clearInterval(tick); }
    counter.textContent = pct + '%';
    if (pct === 100 && !started) {
      started = true;
      cta.classList.add('show');
      cta.classList.remove('hidden');
    }
  }, 28);

  function enter(){
    loader.classList.add('done');
    document.querySelectorAll('.panel').forEach(function(p){
      if (p.dataset.panel === '1') p.classList.add('active');
    });
  }
  cta.addEventListener('click', enter);
  cta.addEventListener('keydown', function(e){ if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); enter(); } });
})();

// ============ 2. Sound button toggle ============
(function(){
  const btn = document.getElementById('soundBtn');
  if (!btn) return;
  btn.addEventListener('click', function(){
    const active = btn.classList.toggle('sound-button--active');
    btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    // Corvus mutes/unmutes a global ambient track. No audio asset ships with
    // PeerGPT, so this toggles the visual active state (faithful interaction).
  });
})();

// ============ 3. Numbered pagination switcher ============
(function(){
  const dots = Array.prototype.slice.call(document.querySelectorAll('.pagination__number'));
  const panels = Array.prototype.slice.call(document.querySelectorAll('.panel'));
  const footLinks = Array.prototype.slice.call(document.querySelectorAll('[data-panel-goto]'));
  const logo = document.querySelector('.header__logo');
  let current = 1;

  function activate(n){
    current = n;
    dots.forEach(d => {
      const seq = parseInt(d.dataset.panel, 10);
      d.classList.toggle('active', seq === n);
      d.classList.toggle('prev', seq < n);
    });
    panels.forEach(p => {
      p.classList.toggle('active', parseInt(p.dataset.panel, 10) === n);
    });
    if (window.PeerGPTScene) driveScene(n);
  }

  dots.forEach(d => {
    const click = () => activate(parseInt(d.dataset.panel, 10));
    d.addEventListener('click', click);
    d.addEventListener('keydown', function(e){
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); click(); }
    });
  });

  (footLinks.concat(logo ? [logo] : [])).forEach(a => {
    a.addEventListener('click', function(e){
      e.preventDefault();
      activate(parseInt(a.dataset.panelGoto, 10) || 1);
    });
  });

  activate(1);
})();

// ============ Drive the 3D scene from the active panel ============
// Corvus is a fixed-viewport app (no page scroll), so the scene is driven
// by which panel is open instead of by scroll position.
let activeOutcome = 'helped';
const outcomeHint = document.getElementById('outcomeHint');

function driveScene(n){
  if (!window.PeerGPTScene) return;
  // Method panel (3) shows the critique stream.
  window.PeerGPTScene.setStream(n === 3);
  // Results panel (4) reflects the outcome; elsewhere it idles.
  if (n === 4) window.PeerGPTScene.setOutcome(activeOutcome);
  else window.PeerGPTScene.setOutcome('idle');
}

// ============ 4. Direction toggle ============
(function(){
  const body = document.body;
  const btns = document.querySelectorAll('.dir-btn');
  btns.forEach(btn => {
    btn.addEventListener('click', () => {
      const dir = btn.getAttribute('data-dir');
      body.setAttribute('data-direction', dir);
      btns.forEach(b => b.classList.toggle('active', b === btn));
      if (window.PeerGPTScene) window.PeerGPTScene.setDirection(dir);
    });
  });
})();

// ============ 5. Outcome toggle ============
(function(){
  const outBtns = document.querySelectorAll('.out-btn');
  outBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      activeOutcome = btn.getAttribute('data-outcome');
      outBtns.forEach(b => b.classList.toggle('active', b === btn));
      if (window.PeerGPTScene) window.PeerGPTScene.setOutcome(activeOutcome);
      if (outcomeHint) {
        outcomeHint.textContent = activeOutcome === 'helped'
          ? 'The critique lands and the Solver cluster brightens — it accepted the critique.'
          : 'The critique stream deflects and fades before reaching the Solver — it rejected the critique.';
      }
    });
  });
})();

// ============ 6. Demo case stepper ============
(function(){
  const steps = [
    {
      eyebrow: 'Question',
      tag: null,
      body: 'Martha has been collecting shells since she turned 5 years old, every month she collects one shell. By her 10th birthday, how many shells will Martha have collected?'
    },
    {
      eyebrow: 'Solver — Llama',
      tag: { text: 'Answer: 6', cls: 'tag-neutral' },
      body: 'Llama solves independently and answers 6.'
    },
    {
      eyebrow: 'Critic verdict — Qwen',
      tag: { text: 'INCORRECT', cls: 'tag-wrong' },
      body: 'Qwen solves the same problem independently, compares the two answers, and flags Llama\u2019s as incorrect: the other model likely did not account for the fact that Martha collects one shell each month for 60 months.'
    },
    {
      eyebrow: 'Critic\u2019s proposed answer',
      tag: { text: 'Proposed: 60', cls: 'tag-neutral' },
      body: 'Qwen proposes 60 as the corrected answer.'
    },
    {
      eyebrow: 'Solver revision',
      tag: { text: 'Revised: 60', cls: 'tag-right' },
      body: 'Given the critique, Llama revises its answer from 6 to 60.'
    },
    {
      eyebrow: 'Outcome',
      tag: { text: 'HELPED — matches gold answer (60)', cls: 'tag-right' },
      body: 'The revision was correct. This case counts toward the 29.1% HELPED rate for the Llama-solver \u2192 Qwen-critic direction.'
    }
  ];

  const track = document.getElementById('demoTrack');
  const progress = document.getElementById('demoProgress');
  const prevBtn = document.getElementById('demoPrev');
  const nextBtn = document.getElementById('demoNext');
  if (!track) return;

  let idx = 0;

  steps.forEach(s => {
    const el = document.createElement('div');
    el.className = 'demo-step';
    const tagHtml = s.tag ? `<span class="step-tag ${s.tag.cls}">${s.tag.text}</span>` : '';
    el.innerHTML = `<span class="step-eyebrow">${s.eyebrow}</span>${tagHtml}<p class="step-body">${s.body}</p>`;
    track.appendChild(el);
  });

  function render(){
    track.style.transform = `translateX(-${idx * 100}%)`;
    track.style.transition = 'transform .35s ease';
    progress.textContent = `${idx + 1} / ${steps.length}`;
    prevBtn.disabled = idx === 0;
    nextBtn.disabled = idx === steps.length - 1;
  }

  prevBtn.addEventListener('click', () => { if (idx > 0) { idx--; render(); } });
  nextBtn.addEventListener('click', () => { if (idx < steps.length - 1) { idx++; render(); } });

  render();
})();
