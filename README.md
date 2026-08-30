# PeerGPT project site

Static, dependency-free-ish one-page site (plain HTML/CSS/JS + Three.js from CDN,
no build step) for the poster *"When Should an LLM Listen to Another LLM?
Predicting Beneficial Critique Acceptance in Multi-LLM Collaboration."*

## Files

- `index.html` — all page content (hero, background, method pipeline, results,
  demo stepper, decision policy, future work, team/acknowledgements/links)
- `style.css` — design system (restrained ink/paper research palette, two-tone
  direction accents, tabular mono numbers, responsive, reduced-motion support)
- `script.js` — direction toggle, sticky-nav active state, scroll-driven 3D
  scene wiring, outcome toggle, demo-case stepper
- `scene.js` — the WebGL (Three.js) hero: two neural node-clusters
  (Solver / Critic) with a critique particle stream, mobile/low-power and
  `prefers-reduced-motion` fallbacks
- `README.md` — this file

Three.js is loaded from the jsDelivr CDN; if it fails to load, has no WebGL, or
runs on a low-power/mobile device, the page automatically falls back to a
CSS-only version of the same scene (`body.no-webgl`).

## Deploy on GitHub Pages

The repo is already initialized and configured with a remote. To publish:

1. Make sure the branch you deploy from is `main`:
   ```bash
   git branch -M main
   git push -u origin main
   ```
2. On GitHub: go to the repo → **Settings → Pages**.
3. Under **Build and deployment → Source**, choose **Deploy from a branch**.
4. Branch: `main`, folder: `/ (root)` → **Save**.
5. Wait ~1 minute — your site will be live at
   `https://<your-username>.github.io/<repo-name>/`.

If you deploy from a different branch or prefer `/docs`, adjust steps 2–4
accordingly. The static files live at the repo root, so no build step is needed.

## Things to swap in before you publish

- **Teammate LinkedIn links** — the four team cards currently show
  `[LINKEDIN URL]` as visible placeholder text (they are not wired to real
  URLs yet). Replace each with the real `https://linkedin.com/in/...` href and
  update the visible label. `src`-side note: the mentor card is intentionally
  not linked (Dr. Eman Alnabati — include only if she wishes).
- **Project poster (PDF)** — the footer "Project poster (PDF)" link is a
  placeholder. Add the file (e.g. `assets/poster.pdf`) and point
  `#posterLink` at it.
- The **GitHub** link already points at this repo
  (`https://github.com/ghassanbinhadi/ProjectTPD3`); update it if the repo URL
  changes.

## Customizing further

- Colors and fonts live in `style.css` under `:root` and
  `body[data-direction="ql"]` (the two direction accents swap there).
- The pipeline diagram is inline SVG in `index.html`.
- The demo-case stepper's content lives in the `steps` array at the top of
  `script.js`.
- The 3D scene behavior (stream timing, direction colors, outcome effects) is
  in `scene.js`.
