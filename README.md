# When to Listen — project site

Static one-page research site (plain HTML/CSS/JS + Three.js from CDN, no build step) for the poster **"When Should an LLM Listen to Another LLM? Predicting Beneficial Critique Acceptance in Multi-LLM Collaboration."** — site wordmark is **When to Listen**.

## Files

- `index.html` — hero (split text + 3D box), background/objectives, method, results charts, demo stepper (6 HELPED cases), decision policy, future work, team/acknowledgements/links
- `style.css` — Corvus-inspired system: pure-black, white/grey, two-tone accent (amber Llama→Qwen / cyan Qwen→Llama), League Spartan + Satoshi + Roboto Mono, corner brackets, progress rail, pill, bottom nav, responsive, reduced-motion
- `script.js` — sticky nav + scroll-driven 3D wiring (direction/outcome), direction toggle, bar-fill on view, demo stepper
- `scene.js` — WebGL hero: glowing wireframe box with two neural clusters (Solver/Critic) + particle critique stream, starfield + topology lines, mouse parallax, scroll-triggered HELPED/HURT, bloom via additive glow, mobile/low-power fallbacks
- `README.md` — this file

Three.js is loaded from jsDelivr CDN. If it fails, has no WebGL, or runs on low-power/mobile, the page falls back to a CSS-only scene (`body.no-webgl`). `prefers-reduced-motion: reduce` renders a single static frame.

## Deploy on GitHub Pages

Static files live at repo root — no build step.

1. Make sure the latest build is pushed (site branch is `Project-Page-clean`, kept separate from `main` which holds the earlier research code):
   ```bash
   git push -u origin Project-Page-clean
   ```
2. On GitHub: repo → **Settings → Pages**.
3. Under **Build and deployment → Source**, choose **Deploy from a branch**.
4. Branch: `Project-Page-clean`, folder: `/ (root)` → **Save**.
5. Wait ~1 minute — live at `https://<username>.github.io/<repo-name>/`.

To publish from `main` instead, change the branch in step 4.

## Things to swap in before publishing

- **Teammate LinkedIn links** — four team cards show `[LINKEDIN URL]` as visible placeholder text (not wired to real URLs yet). Replace each `href="#"` with the real `https://linkedin.com/in/...` and update the label. Mentor (Dr. Eman Alnabati) is intentionally not linked — include only if she wishes.
- **Poster PDF** — footer "Project poster (PDF)" link is a placeholder. Add the file (e.g. `assets/poster.pdf`) and point `#posterLink` at it.
- **GitHub link** already points at `https://github.com/ghassanbinhadi/ProjectTPD3`; update if the repo URL changes.

## Customizing

- Colors/fonts in `style.css` `:root` and `body[data-direction="ql"]` (accents swap there). Numbers use tabular Roboto Mono.
- Hero split (35-40% text / 55-60% box) and chrome (corners, rail, pill, bottom nav) in `style.css` `.page--hero` and chrome blocks.
- 3D box/starfield/topology/stream colors in `scene.js` `COLORS` and `buildCluster`.
- Demo cases in `script.js` `CASES` (Case 1 is real poster example — Martha shells 60; cases 2–6 are illustrative placeholders in spec style — replace with real notebook output before publishing if desired).
