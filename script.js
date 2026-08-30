// ============ Direction toggle ============
// The whole page's accent color is a CSS custom property swapped on <body>.
// It also re-colors the 3D scene's critique stream through PeerGPTScene.
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

// ============ Sticky nav active state ============
(function(){
  const toc = document.getElementById('toc');
  if (!toc) return;
  const links = Array.prototype.slice.call(toc.querySelectorAll('a'));
  if ('IntersectionObserver' in window) {
    const targets = links.map(a => document.querySelector(a.getAttribute('href'))).filter(Boolean);
    const spy = new IntersectionObserver((entries) => {
      entries.forEach(en => {
        if (en.isIntersecting) {
          links.forEach(l => l.classList.toggle('on', l.getAttribute('href') === '#' + en.target.id));
        }
      });
    }, { rootMargin: '-45% 0px -50% 0px', threshold: 0 });
    targets.forEach(t => spy.observe(t));
  }
})();

// ============ Drive the 3D scene from scroll position ============
(function(){
  if (!window.PeerGPTScene) return;
  const method = document.getElementById('method');
  const results = document.getElementById('results');
  if (!('IntersectionObserver' in window)) return;

  // Show the critique stream while the Method section is in view.
  new IntersectionObserver((entries) => {
    entries.forEach(en => {
      if (en.isIntersecting) window.PeerGPTScene.setStream(true);
      else window.PeerGPTScene.setStream(false);
    });
  }, { rootMargin: '-20% 0px -35% 0px' }).observe(method);

  // When the Results section is in view, reflect the selected outcome
  // (HELPED => stream lands + solver brightens; HURT => stream deflects).
  const outBtns = document.querySelectorAll('.out-btn');
  let activeOutcome = 'helped';
  const hint = document.getElementById('outcomeHint');

  outBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      activeOutcome = btn.getAttribute('data-outcome');
      outBtns.forEach(b => b.classList.toggle('active', b === btn));
      window.PeerGPTScene.setOutcome(activeOutcome);
      if (hint) {
        hint.textContent = activeOutcome === 'helped'
          ? 'The critique lands and the Solver cluster brightens — it accepted the critique.'
          : 'The critique stream deflects and fades before reaching the Solver — it rejected the critique.';
      }
    });
  });

  new IntersectionObserver((entries) => {
    entries.forEach(en => {
      if (en.isIntersecting) window.PeerGPTScene.setOutcome(activeOutcome);
      else if (!results.contains(document.activeElement) && en.boundingClientRect.top > 0) {
        window.PeerGPTScene.setOutcome('idle');
      }
    });
  }, { rootMargin: '0px 0px -40% 0px' }).observe(results);
})();

// ============ Demo case stepper ============
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
