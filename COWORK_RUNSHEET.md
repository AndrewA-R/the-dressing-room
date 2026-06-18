# The Dressing Room — Cowork run-sheet

Goal: turn one folder into a live website that mirrors the Notion Closet. Three phases —
**assemble → build → deploy.** Re-run build + deploy anytime to push an update.

---

## Before you start (Andrew provides)
- **NOTION_TOKEN** — the internal integration secret (`ntn_…`). Set it as an environment
  variable; never write it into a file or commit it.
- **Finished photos folder** — the exact image files attached in Notion
  (e.g. `…/Fashion Dashboard/Assets/Reshoots`), full resolution.
- **A free GitHub account** (for hosting).
- **Files from this project:** `build_dashboard.py`, `attach_photos.py`,
  `the_dressing_room_site.zip`.
- Once: `pip install requests pillow`

---

## Phase 1 — Assemble the working folder
1. Make a folder `dressing-room/`.
2. Unzip `the_dressing_room_site.zip` into it (gives `manifest.webmanifest`, `icon-*.png`,
   `DEPLOY.md`, and a starter `images/`).
3. Copy `build_dashboard.py` and `attach_photos.py` into it.
4. Replace the contents of `images/` with Andrew's finished photos — the **same files
   attached in Notion, same filenames** (e.g. `IMG_0509-5.jpg`, `sunglasses_rayban_grey.png`).
   This is what makes the site full-res.

---

## Phase 2 — Build from Notion
```
cd dressing-room
export NOTION_TOKEN=ntn_your_secret
python3 build_dashboard.py
```
- Writes `index.html` from the **live Closet**: current items only (anything Andrew deleted
  drops out), brands and edited details included, each item's image referenced by the
  filename attached in Notion (falls back to the Image Details key if a photo isn't attached).
- **Optional** — keep Notion's own gallery filled: if any items still lack an attached photo,
  `python3 attach_photos.py "<finished photos folder>"`. It's idempotent — skips items that
  already have a photo. (Not required for the website; the site reads from `images/`.)

---

## Phase 3 — Deploy (free, no domain)
**GitHub Pages**
1. Create a public repo, e.g. `dressing-room`.
2. Push the whole folder:
   ```
   git init && git add . && git commit -m "The Dressing Room"
   git branch -M main
   git remote add origin https://github.com/USERNAME/dressing-room.git
   git push -u origin main
   ```
3. Repo → Settings → Pages → Deploy from a branch → `main` / root → Save.
4. Live in ~1 min at `https://USERNAME.github.io/dressing-room/`.

**Cloudflare Pages (alt):** pages.cloudflare.com → Create project → Upload assets → drag the
folder in → `https://PROJECT.pages.dev`.

**On the iPad:** open the URL in Safari → Share → **Add to Home Screen**.

---

## The update loop (every time after)
1. Andrew edits Notion / adds items, or logs asks in the tool's **Requests** tab and Claude
   makes styling or look changes.
2. Re-run Phase 2 (`python3 build_dashboard.py`); drop any new photos into `images/`.
3. Commit + push (GitHub) or re-upload (Cloudflare). Refresh the page — hard-refresh once if
   it's cached.

## Secrets
`NOTION_TOKEN` stays an environment variable. The repo contains only the static site
(HTML, images, icons) — no token, no secrets.
