#!/usr/bin/env python3
"""
attach_photos.py
Resize Andrew's finished wardrobe images under Notion's 5MB free-plan cap and
attach each to its Closet page via the Notion file-upload API.

Matching:
  - Files named IMG_####(.jpg/png/...) match the Closet page whose Notes contain
    that exact IMG_#### key (set during cataloging).
  - The 28 Italy product-shot slugs match by the SLUG_TO_TITLE map below.
  - Anything unmatched is listed at the end and skipped (handle manually later).

Idempotent: pages that already have a Photo are skipped, so re-runs are safe.

Requirements:  pip install requests pillow
Auth:          export NOTION_TOKEN=ntn_xxx   (internal integration secret)
Run:           python3 attach_photos.py "/path/to/Assets/Reshoots"
"""

import os, sys, re, time, glob
from io import BytesIO
import requests
from PIL import Image, ImageOps

# ---- config -------------------------------------------------------------
API              = "https://api.notion.com/v1"
VER              = "2025-09-03"          # current data-source-era version
DATA_SOURCE_ID   = "79f58a2a-2767-48b4-9eba-0cef6140ac15"   # Closet data source
DB_ID            = "17624a6894294359a39d9e6fadd600ff"       # Closet database (fallback)
PHOTO_PROP       = "Photo"
CARD             = (242, 238, 231)       # cream card behind any transparency
MAX_EDGE         = 1800                  # longest edge px
TARGET_BYTES     = 4_700_000             # stay safely under the 5 MB cap
TOKEN            = os.environ.get("NOTION_TOKEN")

# Italy product-shot slugs -> exact Closet Item title (the 43 preserved entries)
SLUG_TO_TITLE = {
    "bylt_dc_black":          "Black BYLT Tee",
    "bylt_tee_bone":          "Bone BYLT Tee",
    "bylt_henley_navy":       "Navy BYLT Henley",
    "bylt_henley_bone":       "Bone BYLT Henley",
    "new_onia_stripe":        "Onia Navy Stripe SS",
    "real_reiss_stripe":      "Reiss Pink Stripe Linen LS",
    "bearbottom_stone":       "Bear Bottom Stone",
    "bearbottom_navy":        "Bear Bottom Navy",
    "bearbottom_mauve":       "Bear Bottom Deep Mauve",
    "real_sand_pants":        "Sand 5-Pocket Pants",
    "new_ae_trekker":         "AE Pull-On Trekker Tan",
    "real_pink_pants":        "Pink/Mauve 5-Pocket",
    "maamgic_blackyellow":    "Maamgic Black/Yellow",
    "maamgic_bluegrey":       "Maamgic Blue/Grey",
    "maamgic_navyred":        "Maamgic Navy/Red",
    "belt_tan_leather":       "CT Tan Leather Belt",
    "belt_woven_tobacco":     "Nisolo Woven Tobacco Belt",
    "belt_olive_dring":       "Olive D-Ring Belt",
    "belt_stripe":            "J.Crew Stripe Canvas Belt",
    "sunglasses_honey_green": "Quince Brixton Honey/Green",
    "sunglasses_lespecs_tort":"Le Specs Bandwagon Tort",
    "sunglasses_rayban_grey": "Ray-Ban RB4387",
}
# Known orphans (no Closet row yet) — reported, not attached:
#   BYLTBLENDHENLEYDCLSNAVY, bearbottom_sanddune, dungaree_pant,
#   henley_ls_black*, henley_ls_white*, maamgic_greenorange

H_AUTH = {"Authorization": f"Bearer {TOKEN}", "Notion-Version": VER}
H_JSON = {**H_AUTH, "Content-Type": "application/json"}
IMG_RE = re.compile(r"IMG_\d+(?:-\d+)?")


def req(method, url, **kw):
    """Request wrapper with simple 429 backoff."""
    for attempt in range(6):
        r = requests.request(method, url, **kw)
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After", 2)))
            continue
        return r
    return r


def all_pages():
    pages, cursor = [], None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        r = req("POST", f"{API}/data_sources/{DATA_SOURCE_ID}/query", headers=H_JSON, json=body)
        if r.status_code >= 400:  # fallback for older API behavior
            h = {**H_AUTH, "Content-Type": "application/json", "Notion-Version": "2022-06-28"}
            r = req("POST", f"{API}/databases/{DB_ID}/query", headers=h, json=body)
        r.raise_for_status()
        j = r.json()
        pages += j["results"]
        cursor = j.get("next_cursor")
        if not j.get("has_more"):
            return pages


def ptext(page, name):
    v = page["properties"].get(name, {})
    arr = v.get("title") or v.get("rich_text") or []
    return "".join(t.get("plain_text", "") for t in arr)


def has_photo(page):
    return bool(page["properties"].get(PHOTO_PROP, {}).get("files"))


def encode_under(im, target):
    for q in (90, 82, 74, 66, 58, 50, 42):
        buf = BytesIO(); im.save(buf, "JPEG", quality=q, optimize=True)
        if buf.tell() <= target:
            return buf.getvalue()
    while max(im.size) > 700:
        im = im.resize((int(im.width * 0.85), int(im.height * 0.85)))
        buf = BytesIO(); im.save(buf, "JPEG", quality=70, optimize=True)
        if buf.tell() <= target:
            return buf.getvalue()
    return buf.getvalue()


def prep(path):
    im = ImageOps.exif_transpose(Image.open(path))
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, CARD); bg.paste(im, mask=im.split()[-1]); im = bg
    else:
        im = im.convert("RGB")
    if max(im.size) > MAX_EDGE:
        im.thumbnail((MAX_EDGE, MAX_EDGE))
    return encode_under(im, TARGET_BYTES)


def upload_and_attach(page_id, data, filename):
    c = req("POST", f"{API}/file_uploads", headers=H_JSON,
            json={"filename": filename, "content_type": "image/jpeg"})
    c.raise_for_status(); up = c.json()
    s = req("POST", up["upload_url"], headers=H_AUTH,
            files={"file": (filename, data, "image/jpeg")})
    s.raise_for_status()
    body = {"properties": {PHOTO_PROP: {"files": [
        {"type": "file_upload", "file_upload": {"id": up["id"]}, "name": filename}]}}}
    a = req("PATCH", f"{API}/pages/{page_id}", headers=H_JSON, json=body)
    a.raise_for_status()


def main():
    if not TOKEN:
        sys.exit("Set NOTION_TOKEN env var (internal integration secret).")
    if len(sys.argv) < 2:
        sys.exit('Usage: python3 attach_photos.py "/path/to/finished/folder"')
    folder = sys.argv[1]

    print("Fetching Closet pages...")
    pages = all_pages()
    by_img, by_title = {}, {}
    for p in pages:
        m = IMG_RE.search(ptext(p, "Notes"))
        if m:
            by_img[m.group(0)] = p
        by_title[ptext(p, "Item")] = p
    print(f"  {len(pages)} pages | {len(by_img)} IMG keys indexed")

    files = sorted(f for ext in ("png", "jpg", "jpeg", "webp", "tif", "tiff")
                   for f in glob.glob(os.path.join(folder, f"*.{ext}")))
    done, skipped, unmatched, failed = 0, [], [], []

    for path in files:
        stem = os.path.splitext(os.path.basename(path))[0]
        if stem.startswith("IMG_"):
            key = IMG_RE.match(stem)
            page = by_img.get(key.group(0)) if key else None
        else:
            page = by_title.get(SLUG_TO_TITLE.get(stem, "\0"))
        if not page:
            unmatched.append(stem); continue
        if has_photo(page):
            skipped.append(stem); continue
        try:
            upload_and_attach(page["id"], prep(path), f"{stem}.jpg")
            done += 1
            print(f"  attached {stem}  ->  {ptext(page,'Item')}")
            time.sleep(0.35)  # stay under ~3 req/s
        except Exception as e:
            failed.append((stem, str(e)[:120]))
            print(f"  FAILED   {stem}: {e}")

    print(f"\nAttached: {done} | already had photo: {len(skipped)} | "
          f"unmatched: {len(unmatched)} | failed: {len(failed)}")
    if unmatched:
        print("Unmatched (no Closet row / add manually):\n  " + ", ".join(unmatched))
    if failed:
        print("Failed:\n  " + "\n  ".join(f"{s}: {e}" for s, e in failed))


if __name__ == "__main__":
    main()
