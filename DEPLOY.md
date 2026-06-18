# The Dressing Room — deploy (free, no domain)

This whole folder *is* the site. Pick one host below — both are free and give a URL
that works on the iPad (Safari → Share → **Add to Home Screen** installs it like an app).

## Option A — GitHub Pages
1. Free account at github.com.
2. New repository, e.g. `dressing-room`, Public.
3. Add file → Upload files → drag in everything here (index.html, manifest.webmanifest,
   the icon-*.png files, and the images/ folder). Commit.
4. Settings → Pages → Source: Deploy from a branch → `main` / root → Save.
5. URL appears in ~1 min: https://USERNAME.github.io/dressing-room/

## Option B — Cloudflare Pages
pages.cloudflare.com → Create project → Upload assets → drag this folder in →
get a https://PROJECT.pages.dev URL.

## On the iPad
Open the URL in Safari → Share → Add to Home Screen. Launches full-screen, hanger icon.

## Updating (no downloads for you)
When I improve styling or your catalog, I hand you a new `index.html` (and any changed
images). Overwrite the file(s) in the repo and refresh the page. Requests you log in the
**Requests** tab → tap *Copy for Claude* → paste into chat, and I push the update.

## Full resolution
images/ ships with 600px working photos so it looks right immediately. For full-res,
drop your finished-folder JPEGs into images/ using the same filenames
(IMG_0523.jpg, bylt_henley_navy.jpg, …) and re-upload.

## Let Cowork do it
Cowork can create the repo, push this folder, enable Pages, and push every future
update — point it here and at your GitHub login.
