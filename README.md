# PeerGPT project site

Static, dependency-free site (plain HTML/CSS/JS — no build step) for the poster
*"When Should an LLM Listen to Another LLM? Predicting Beneficial Critique
Acceptance in Multi-LLM Collaboration."*

## Files
- `index.html` — all page content
- `style.css` — design system (colors, type, layout)
- `script.js` — the direction toggle + demo-case stepper

## Deploy on GitHub Pages

1. Create a new repo on GitHub (e.g. `peergpt-site`), or use an existing one.
2. From this folder, push it as the repo root:
   ```bash
   cd site
   git init
   git add .
   git commit -m "Initial project site"
   git branch -M main
   git remote add origin https://github.com/<your-username>/<repo-name>.git
   git push -u origin main
   ```
3. On GitHub: go to the repo → **Settings → Pages**.
4. Under **Build and deployment → Source**, choose **Deploy from a branch**.
5. Branch: `main`, folder: `/ (root)` → **Save**.
6. Wait ~1 minute — your site will be live at
   `https://<your-username>.github.io/<repo-name>/`.

## Things to swap in before you publish
- The GitHub link in the top bar and footer currently points to a placeholder
  (`https://github.com/`) — replace with your actual repo URL.
- The "Project poster (PDF)" link in the footer is a placeholder `#` — add the
  poster PDF to the repo (e.g. `assets/poster.pdf`) and point the link at it.
- All numbers (directional benefit, correction effectiveness, false alarms,
  ablation, decision policy) are pulled directly from the poster. If any of
  these get updated after the frozen test-set run finishes, update them in
  `index.html` under the relevant `<section>`.

## Customizing further
- Colors, fonts, and spacing all live in `style.css` under the `:root` and
  `body[data-direction="ql"]` blocks at the top.
- The pipeline diagram is inline SVG in `index.html` — easy to tweak node
  positions/labels directly.
- The demo-case stepper's content lives in the `steps` array at the top of
  `script.js` — add more demo cases (e.g. a HURT / false-alarm case) by adding
  another array and a second stepper instance.
