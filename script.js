// ============================================================
// When to Listen — Corvus pagination-app behavior
// 1. Sound button toggle (global)
// 2. Numbered pagination switcher (001-007, swap panels in place)
// 3. Direction toggle drives CSS accent + 3D scene
// 4. Outcome toggle drives 3D scene
// 5. Demo case stepper (real GSM8K HELPED cases + case selector)
// ============================================================

// ============ 1. Sound button toggle ============
(function(){
  const btn = document.getElementById('soundBtn');
  if (!btn) return;
  btn.addEventListener('click', function(){
    const active = btn.classList.toggle('sound-button--active');
    btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    // Corvus mutes/unmutes a global ambient track. No audio asset ships with
    // this project, so this toggles the visual active state (faithful interaction).
  });
})();

// ============ 2. Numbered pagination switcher ============
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
    if (window.PeerGPTModels) window.PeerGPTModels.setActive(n === 3);
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
let activeOutcome = 'helped';
const outcomeHint = document.getElementById('outcomeHint');

function driveScene(n){
  if (!window.PeerGPTScene) return;
  window.PeerGPTScene.setStream(n === 3);
  if (n === 4) window.PeerGPTScene.setOutcome(activeOutcome);
  else window.PeerGPTScene.setOutcome('idle');
}

// ============ 3. Direction toggle ============
(function(){
  const body = document.body;
  const btns = document.querySelectorAll('.dir-btn');
  btns.forEach(btn => {
    btn.addEventListener('click', () => {
      const dir = btn.getAttribute('data-dir');
      body.setAttribute('data-direction', dir);
      btns.forEach(b => b.classList.toggle('active', b === btn));
      if (window.PeerGPTScene) window.PeerGPTScene.setDirection(dir);
      if (window.PeerGPTModels) window.PeerGPTModels.setDirection(dir);
    });
  });
})();

// ============ 4. Outcome toggle ============
(function(){
  const outBtns = document.querySelectorAll('.out-btn');
  outBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      activeOutcome = btn.getAttribute('data-outcome');
      outBtns.forEach(b => b.classList.toggle('active', b === btn));
      if (window.PeerGPTScene) window.PeerGPTScene.setOutcome(activeOutcome);
      if (window.PeerGPTModels) window.PeerGPTModels.setOutcome(activeOutcome);
      if (outcomeHint) {
        outcomeHint.textContent = activeOutcome === 'helped'
          ? 'The critique lands and the Solver cluster brightens — it accepted the critique.'
          : 'The critique stream deflects and fades before reaching the Solver — it rejected the critique.';
      }
    });
  });
})();

// ============ 5. Demo case stepper ============
// Real GSM8K disagreement cases from the dataset. Three $directions.
(function(){
  // ---- Case library (question, then a sequence of steps) ----
  const CASES = {
    // Llama-solver -> Qwen-critic
    buoys: {
      dir: 'lq',
      title: 'Buoy distance',
      qlabel: 'Llama solves → Qwen critiques',
      question: 'A swimmer dives into the sea from a beach. She swims straight out. The first buoy is some distance out; the second buoy is the same distance farther out, and so on. When the swimmer reaches the third buoy, she has swum 72 meters. How far from the beach is the fourth buoy?',
      steps: [
        { eyebrow: 'Question', tag: null, body: 'A swimmer reaches the third buoy after swimming 72 meters from the beach. Buoys are spaced at a consistent interval. How far is the fourth buoy from the beach?' },
        { eyebrow: 'Solver — Llama', tag: { text: 'Answer: 72', cls: 'tag-neutral' }, body: 'Llama divides the 72 meters by the 2 intervals before the third buoy (36 m each) and then multiplies by the same 2 intervals — concluding the fourth buoy is also 72 m away. It reused the earlier interval incorrectly.' },
        { eyebrow: 'Critic verdict — Qwen', tag: { text: 'INCORRECT', cls: 'tag-wrong' }, body: 'Qwen critiques: "The other model likely did not account for the consistent interval between buoys, leading them to an incorrect total distance." With 72 m over 2 equal gaps, each gap is 36 m, so the fourth buoy sits 3 intervals out: 72 + 36 = 108 m.' },
        { eyebrow: 'Critic\u2019s proposed answer', tag: { text: 'Proposed: 96', cls: 'tag-neutral' }, body: 'Qwen (which solves on its own first) arrives at 96 m and proposes it as the corrected answer.' },
        { eyebrow: 'Solver revision', tag: { text: 'Revised: 96', cls: 'tag-right' }, body: 'Re-reading the consistent-interval reading, Llama revises its answer from 72 to 96.' },
        { eyebrow: 'Outcome', tag: { text: 'HELPED — matches gold answer (96)', cls: 'tag-right' }, body: 'The revision was correct. Counts toward the 29.1% HELPED rate for the Llama-solver → Qwen-critic direction.' }
      ]
    },
    percy: {
      dir: 'lq',
      title: 'Percy\u2019s weekly swim hours',
      qlabel: 'Llama solves → Qwen critiques',
      question: 'Percy swims 1 hour each before and after school for all 5 school days, and 3 hours total across the weekend days. If he keeps this up for 4 weeks, how many hours does he swim in total?',
      steps: [
        { eyebrow: 'Question', tag: null, body: 'Percy swims 1 hour before school and 1 hour after school each of the 5 weekdays, plus 3 hours at the weekend. How many hours in 4 weeks?' },
        { eyebrow: 'Solver — Llama', tag: { text: 'Answer: 64', cls: 'tag-neutral' }, body: 'Llama counts 10 weekday hours (5 + 5) plus 6 weekend hours (3 + 3) = 16 h/week, then 16 × 4 = 64 h. It over-counts the weekend as 6 h instead of 3 h.' },
        { eyebrow: 'Critic verdict — Qwen', tag: { text: 'INCORRECT', cls: 'tag-wrong' }, body: 'Qwen: "did not account for the fact that Percy swims 10 hours per week during the weekdays … the correct calculation should be 10 hours per week (5 days × 2 h/day) plus 3 hours on the weekend, which totals 13 hours per week."' },
        { eyebrow: 'Critic\u2019s proposed answer', tag: { text: 'Proposed: 52', cls: 'tag-neutral' }, body: 'Qwen computes 13 h/week × 4 weeks = 52 h and proposes 52.' },
        { eyebrow: 'Solver revision', tag: { text: 'Revised: 52', cls: 'tag-right' }, body: 'Llama accepts the corrected weekend total and revises: 13 × 4 = 52 h.' },
        { eyebrow: 'Outcome', tag: { text: 'HELPED — matches gold answer (52)', cls: 'tag-right' }, body: 'The revision was correct. Counts toward the 29.1% HELPED rate for the Llama-solver → Qwen-critic direction.' }
      ]
    },
    pool: {
      dir: 'lq',
      title: 'Pool drain vs. hose net rate',
      qlabel: 'Llama solves → Qwen critiques',
      question: 'A hose can fill a 120-liter pool in 6 hours, while a drain can empty it in 4 hours. If both are running at the same time starting from a full pool, how much water is left after 3 hours?',
      steps: [
        { eyebrow: 'Question', tag: null, body: 'A full 120-liter pool is being drained (empties in 4 h) while a hose fills it (fills in 6 h) at the same time. How much water remains after 3 hours?' },
        { eyebrow: 'Solver — Llama', tag: { text: 'Answer: 0', cls: 'tag-neutral' }, body: 'Llama computes the net rate as 20 − 30 = −10 L/h (hose 20, drain 30) and concludes the pool empties to 0, stopping early. It forgets to apply the net change to the 120 L starting level.' },
        { eyebrow: 'Critic verdict — Qwen', tag: { text: 'INCORRECT', cls: 'tag-wrong' }, body: 'Qwen: "did not account for the net rate of change in the water level correctly." Net change over 3 hours is −10 × 3 = −30 L; starting at 120 L leaves 90 L.' },
        { eyebrow: 'Critic\u2019s proposed answer', tag: { text: 'Proposed: 90', cls: 'tag-neutral' }, body: 'Qwen proposes 90 L as the corrected answer.' },
        { eyebrow: 'Solver revision', tag: { text: 'Revised: 90', cls: 'tag-right' }, body: 'Llama revises: 120 L − 30 L = 90 L remaining.' },
        { eyebrow: 'Outcome', tag: { text: 'HELPED — matches gold answer (90)', cls: 'tag-right' }, body: 'The revision was correct. Counts toward the 29.1% HELPED rate for the Llama-solver → Qwen-critic direction.' }
      ]
    },
    // Qwen-solver -> Llama-critic
    tabitha: {
      dir: 'ql',
      title: 'Tabitha\u2019s hair colors',
      qlabel: 'Qwen solves → Llama critiques',
      question: 'Tabitha dyed her hair a new color each year. She got her second hair color at age 15. In three years she will have 8 different hair colors. How old is Tabitha now?',
      steps: [
        { eyebrow: 'Question', tag: null, body: 'Tabitha adds one new hair color each year; she had her second hair color at age 15. In three years she will have 8 colors. How old is she now?' },
        { eyebrow: 'Solver — Qwen', tag: { text: 'Answer: 19', cls: 'tag-neutral' }, body: 'Qwen reasons she currently has 8 − 3 = 5 colors and, placing her first color at age 14, concludes her current age is 14 + 5 = 19. It mis-places the 8-colors-in-3-years relationship.' },
        { eyebrow: 'Critic verdict — Llama', tag: { text: 'INCORRECT', cls: 'tag-wrong' }, body: 'Llama critiques: "incorrectly assumes she started with 1 color at age 15, when the problem states she started with her second hair color at age 15."' },
        { eyebrow: 'Critic\u2019s proposed answer', tag: { text: 'Proposed: 6', cls: 'tag-wrong' }, body: 'Llama\u2019s own independent solve lands on the wildly wrong 6 — its proposed correction is itself incorrect.' },
        { eyebrow: 'Solver revision', tag: { text: 'Revised: 18', cls: 'tag-right' }, body: 'Qwen does NOT blindly copy the critic\u2019s 6. It uses only the critique\u2019s insight (second color at 15 ⇒ first at 14) to re-derive its age — landing independently on 18.' },
        { eyebrow: 'Outcome', tag: { text: 'HELPED — matches gold answer (18)', cls: 'tag-right' }, body: 'The critique was worth hearing even though its proposed number was wrong — the solver reasoned its own way to the correct answer. Counts toward the 11.2% HELPED rate for the Qwen-solver → Llama-critic direction.' }
      ]
    },
    bedroom: {
      dir: 'ql',
      title: 'Bedroom set discount + gift card',
      qlabel: 'Qwen solves → Llama critiques',
      question: 'Perry buys a $2000 bedroom set at 15% off. He pays $200 with gift cards, then gets an additional 10% off the remaining amount with a store credit card. How much does he pay?',
      steps: [
        { eyebrow: 'Question', tag: null, body: 'A $2000 set is discounted 15%, then $200 of gift cards are used, then a further 10% store-credit discount applies. How much does Perry pay?' },
        { eyebrow: 'Solver — Qwen', tag: { text: 'Answer: 1350', cls: 'tag-neutral' }, body: 'Qwen computes 15% off → $1700, subtracts $200 gift cards → $1500, then takes 10% off → $1350. It applied the 10% after the gift cards instead of before.' },
        { eyebrow: 'Critic verdict — Llama', tag: { text: 'INCORRECT', cls: 'tag-wrong' }, body: 'Llama: "likely forgot to subtract the gift card amount from the final discounted price before applying it." The 10% should come off the $1700 discounted price first, then the $200 gift card.' },
        { eyebrow: 'Critic\u2019s proposed answer', tag: { text: 'Proposed: 1330', cls: 'tag-neutral' }, body: 'Llama computes 10% off $1700 → $1530, then subtracts $200 → $1330.' },
        { eyebrow: 'Solver revision', tag: { text: 'Revised: 1330', cls: 'tag-right' }, body: 'Qwen revises to the correct order: $1700 − 10% = $1530, then − $200 = $1330.' },
        { eyebrow: 'Outcome', tag: { text: 'HELPED — matches gold answer (1330)', cls: 'tag-right' }, body: 'The revision was correct. Counts toward the 11.2% HELPED rate for the Qwen-solver → Llama-critic direction.' }
      ]
    },
    legs: {
      dir: 'ql',
      title: 'Counting furniture legs',
      qlabel: 'Qwen solves → Llama critiques',
      question: 'A room has 4 tables with 4 legs each, 1 sofa with 4 legs, 2 chairs with 4 legs, 3 tables with 3 legs each, 1 table with 1 leg, and 1 rocking chair with 2 legs. How many legs are in the room?',
      steps: [
        { eyebrow: 'Question', tag: null, body: 'Count the legs of a room of mixed furniture: 4 four-legged tables, a 4-legged sofa, 2 four-legged chairs, 3 three-legged tables, a one-legged table, and a two-legged rocking chair.' },
        { eyebrow: 'Solver — Qwen', tag: { text: 'Answer: 30', cls: 'tag-neutral' }, body: 'Qwen sums 16 + 4 + 8 + 9 + 1 + 2 = 40 on paper — but reports 30, an arithmetic slip when adding the groups.' },
        { eyebrow: 'Critic verdict — Llama', tag: { text: 'INCORRECT', cls: 'tag-wrong' }, body: 'Llama: "made an error in calculating the total number of legs of the 3 tables with 3 legs each". It reconstructs the correct group totals.' },
        { eyebrow: 'Critic\u2019s proposed answer', tag: { text: 'Proposed: 40', cls: 'tag-neutral' }, body: 'Llama recomputes the full sum as 40 and proposes it.' },
        { eyebrow: 'Solver revision', tag: { text: 'Revised: 40', cls: 'tag-right' }, body: 'Qwen re-adds the groups and revises its answer from 30 to 40.' },
        { eyebrow: 'Outcome', tag: { text: 'HELPED — matches gold answer (40)', cls: 'tag-right' }, body: 'The revision was correct. Counts toward the 11.2% HELPED rate for the Qwen-solver → Llama-critic direction.' }
      ]
    }
  };

  const ORDER = ['buoys', 'percy', 'pool', 'tabitha', 'bedroom', 'legs'];

  const track = document.getElementById('demoTrack');
  const progress = document.getElementById('demoProgress');
  const prevBtn = document.getElementById('demoPrev');
  const nextBtn = document.getElementById('demoNext');
  const select = document.getElementById('caseSelect');
  const questionEl = document.getElementById('demoQuestion');
  if (!track) return;

  function renderQuestion(c){
    if (questionEl) {
      questionEl.innerHTML = '<span class="dq-eyebrow">' + c.title + ' · ' + c.qlabel + '</span><p class="dq-body">' + c.question + '</p>';
    }
  }

  function renderSteps(c){
    track.innerHTML = '';
    c.steps.forEach(s => {
      const el = document.createElement('div');
      el.className = 'demo-step';
      const tagHtml = s.tag ? `<span class="step-tag ${s.tag.cls}">${s.tag.text}</span>` : '';
      el.innerHTML = `<span class="step-eyebrow">${s.eyebrow}</span>${tagHtml}<p class="step-body">${s.body}</p>`;
      track.appendChild(el);
    });
  }

  let currentIdx = 0;
  let currentKey = ORDER[0];
  let current = CASES[currentKey];

  function loadCase(key){
    currentKey = key;
    current = CASES[key];
    currentIdx = 0;
    renderQuestion(current);
    renderSteps(current);
    render();
    if (window.PeerGPTScene) window.PeerGPTScene.setDirection(current.dir);
    if (window.PeerGPTModels) window.PeerGPTModels.setDirection(current.dir);
  }

  function render(){
    track.style.transform = `translateX(-${currentIdx * 100}%)`;
    track.style.transition = 'transform .35s ease';
    progress.textContent = `${currentIdx + 1} / ${current.steps.length}`;
    prevBtn.disabled = currentIdx === 0;
    nextBtn.disabled = currentIdx === current.steps.length - 1;
  }

  if (select) {
    select.addEventListener('change', () => loadCase(select.value));
    ORDER.forEach(k => {
      const opt = document.createElement('option');
      opt.value = k;
      opt.textContent = (CASES[k].dir === 'ql' ? 'Qwen→Llama · ' : 'Llama→Qwen · ') + CASES[k].title;
      select.appendChild(opt);
    });
    select.value = ORDER[0];
  }

  prevBtn.addEventListener('click', () => { if (currentIdx > 0) { currentIdx--; render(); } });
  nextBtn.addEventListener('click', () => { if (currentIdx < current.steps.length - 1) { currentIdx++; render(); } });

  loadCase(ORDER[0]);
})();
