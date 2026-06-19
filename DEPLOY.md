# The Dressing Room — app (deploy via Cowork)

This replaces the old static GitHub Pages site. It's a Vite + React front end with three
Vercel serverless functions that read and write Andrew's Notion live. There is no more
hourly rebuild — the app reflects Notion in real time.

## What to do
1. Put the contents of this folder into the GitHub repo connected to Andrew's Vercel project
   (replace the previous static-site files — `build_dashboard.py`, `index.html`, `images/`,
   the old `rebuild.yml` are all obsolete and can be removed).
2. Confirm these env vars exist in the Vercel project (Settings → Environment Variables),
   for Production:
   - `NOTION_TOKEN` — the existing `ntn_…` integration secret.
   - `ANTHROPIC_API_KEY` — for the "Build a look" generate feature.
3. Vercel auto-detects Vite. No build config needed: build command `vite build`, output `dist`,
   functions in `/api` run on the Node runtime automatically.
4. Deploy. Send Andrew the live URL.

## Notes
- The Notion integration must have access to all five databases (Closet, Outfits, Capsules,
  Recommendations, Inspiration) — it already does from the previous setup.
- Photos are served from Notion's own (short-lived) signed URLs; because the app fetches live
  on each load, they stay fresh. No local image folder needed.
- `delete` archives a look to Notion's trash (recoverable) — it is never a hard delete.

## Local check (optional)
```
npm install
npm run build      # confirms the front end compiles
```
