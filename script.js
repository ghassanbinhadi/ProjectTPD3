// ============ Direction toggle ============
// The whole page's accent color is a CSS custom property swapped on <body>.
// This is the site's signature interaction: pick a direction once, and every
// downstream chart/diagram/hero reads it back through the same color.
(function(){
  const body = document.body;
  const btns = document.querySelectorAll('.dir-btn');
  btns.forEach(btn => {
    btn.addEventListener('click', () => {
      const dir = btn.getAttribute('data-dir');
      body.setAttribute('data-direction', dir);
      btns.forEach(b => b.classList.toggle('active', b === btn));
    });
  });
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
