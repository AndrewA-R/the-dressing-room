#!/usr/bin/env python3
"""
build_dashboard.py  —  The Dressing Room

Reads the Wardrobe OS Notion databases (Closet, Outfits, Capsules) and generates
a static, photographic, rateable wardrobe dashboard for GitHub Pages.

Source of truth is Notion. This script:
  - pulls every Closet item, Outfit (look), and Capsule via the Notion REST API
  - downloads each piece photo LOCALLY so Notion's signed URLs can't expire
    between hourly rebuilds (the thing that silently breaks a naive build)
  - groups looks by capsule, then by formality (Beach / Casual / Smart / Dressy)
  - renders each look photographically: the piece thumbnails, the slot list,
    a styling note, and the "wear with" accessories
  - adds the in-tool feedback loop: Top / Solid / Maybe / Cut + a note per look,
    saved in the browser, with an Export button that produces text to paste back
  - builds a categorized, checkbox packing list per capsule

Stdlib only — no pip install, so nothing to break in CI.

Environment:
  NOTION_TOKEN   Notion internal integration token (set as a GitHub Actions secret).
                 The integration must be shared with the Closet, Outfits, and
                 Capsules databases.

Output (default ./dist, override with OUTPUT_DIR env or argv[1]):
  dist/index.html
  dist/images/...          downloaded piece photos

The GitHub Pages deploy must publish whatever OUTPUT_DIR resolves to.
"""

import os
import sys
import json
import html
import time
import pathlib
import mimetypes
import urllib.request
import urllib.error

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "").strip()
NOTION_VERSION = "2022-06-28"
API = "https://api.notion.com/v1"

# Wardrobe OS database IDs
DB_CLOSET = "17624a68-9429-4359-a39d-9e6fadd600ff"
DB_OUTFITS = "bd8d2b67-dba3-4149-ad8c-35b38b5c53a8"
DB_CAPSULES = "92ce74f2-cb18-4116-bf8f-fd7cab490a98"

OUT_DIR = pathlib.Path(
    (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("OUTPUT_DIR", "dist")).strip()
)
IMG_DIR = OUT_DIR / "images"

# Category -> layout slot
TOP_CATS = {"Shirt", "Polo", "Knitwear", "Tee", "Outerwear", "Swim"}
BOTTOM_CATS = {"Trousers", "Shorts", "Tailoring"}
SHOE_CATS = {"Footwear"}
ACC_CATS = {"Accessory"}

# Formality order + display labels (matches the original dashboard)
FORMALITY_ORDER = ["Beach", "Casual", "Smart", "Dressy"]
FORMALITY_LABEL = {
    "Beach": "Beach \u00b7 Pool",
    "Casual": "Casual",
    "Smart": "Smart Casual",
    "Dressy": "Laid-Back Dressy",
}

# --------------------------------------------------------------------------- #
# Notion API
# --------------------------------------------------------------------------- #


def _api_post(path, body):
    req = urllib.request.Request(
        API + path,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": "Bearer " + NOTION_TOKEN,
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        raise SystemExit(
            "Notion API error on POST %s (%s):\n%s" % (path, e.code, detail)
        )


def notion_query(db_id):
    """Return every page in a database, following pagination."""
    out, payload = [], {"page_size": 100}
    while True:
        data = _api_post("/databases/%s/query" % db_id, payload)
        out.extend(data.get("results", []))
        if data.get("has_more"):
            payload["start_cursor"] = data["next_cursor"]
        else:
            return out


# ---- property extractors -------------------------------------------------- #


def p_title(props, name):
    return "".join(t.get("plain_text", "") for t in props.get(name, {}).get("title", [])).strip()


def p_text(props, name):
    return "".join(
        t.get("plain_text", "") for t in props.get(name, {}).get("rich_text", [])
    ).strip()


def p_select(props, name):
    s = props.get(name, {}).get("select")
    return s["name"] if s else None


def p_multi(props, name):
    return [o["name"] for o in props.get(name, {}).get("multi_select", [])]


def p_relation(props, name):
    return [r["id"] for r in props.get(name, {}).get("relation", [])]


def p_file_url(props, name):
    for f in props.get(name, {}).get("files", []):
        if f.get("type") == "file":
            return f["file"]["url"]
        if f.get("type") == "external":
            return f["external"]["url"]
    return None


# --------------------------------------------------------------------------- #
# Image download (keeps photos from expiring)
# --------------------------------------------------------------------------- #


def download_image(url, stem):
    """Download to OUT_DIR/images/<stem>.<ext>; return a path relative to index.html.
    Falls back to the original URL if the download fails."""
    if not url:
        return None
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    # extension from the URL path, ignoring the query signature
    path_part = url.split("?", 1)[0]
    ext = os.path.splitext(path_part)[1].lower().lstrip(".")
    if ext not in ("jpg", "jpeg", "png", "webp", "gif", "avif"):
        ext = ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
            if not ext:
                ctype = r.headers.get("Content-Type", "")
                guess = mimetypes.guess_extension((ctype or "").split(";")[0].strip())
                ext = (guess or ".jpg").lstrip(".")
        fname = "%s.%s" % (stem, ext)
        (IMG_DIR / fname).write_bytes(data)
        return "images/" + fname
    except Exception as e:  # noqa: BLE001 - want to keep building
        sys.stderr.write("  ! image download failed (%s): %s\n" % (url[:60], e))
        return url


# --------------------------------------------------------------------------- #
# Load data
# --------------------------------------------------------------------------- #


def slot_of(cat):
    if cat in TOP_CATS:
        return "top"
    if cat in BOTTOM_CATS:
        return "bottom"
    if cat in SHOE_CATS:
        return "shoes"
    if cat in ACC_CATS:
        return "acc"
    return "acc"


def load():
    print("Loading Closet...")
    closet = {}
    for pg in notion_query(DB_CLOSET):
        pid = pg["id"]
        props = pg["properties"]
        url = p_file_url(props, "Photo")
        closet[pid] = {
            "name": p_title(props, "Item"),
            "category": p_select(props, "Category"),
            "brand": p_text(props, "Brand"),
            "img": download_image(url, "closet_" + pid.replace("-", "")[:14]),
        }
    print("  %d items" % len(closet))

    print("Loading Capsules...")
    capsules = {}
    for pg in notion_query(DB_CAPSULES):
        pid = pg["id"]
        props = pg["properties"]
        date = props.get("Dates", {}).get("date") or {}
        capsules[pid] = {
            "name": p_title(props, "Capsule"),
            "notes": p_text(props, "Notes"),
            "type": p_select(props, "Type"),
            "start": date.get("start"),
        }
    print("  %d capsules" % len(capsules))

    print("Loading Outfits...")
    outfits = []
    for pg in notion_query(DB_OUTFITS):
        props = pg["properties"]
        caps = p_relation(props, "Capsule")
        outfits.append(
            {
                "id": pg["id"],
                "name": p_title(props, "Look"),
                "formality": p_select(props, "Formality"),
                "capsule": caps[0] if caps else None,
                "items": p_relation(props, "Items"),
                "notes": p_text(props, "Notes"),
                "rating": p_select(props, "Rating"),
                "occasion": p_multi(props, "Occasion"),
            }
        )
    print("  %d looks" % len(outfits))
    return closet, capsules, outfits


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #

CSS = r"""
:root{
  --bg:#faf8f3; --ink:#2b2723; --muted:#8c8377; --line:#e7e0d4;
  --panel:#efe9df; --tile:#fbfaf6; --card:#fffdf9;
  --top:#5c7a52; --solid:#b08328; --maybe:#9a948b; --cut:#a8493c;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",Helvetica,Arial,sans-serif;
  line-height:1.45;-webkit-font-smoothing:antialiased}
.serif{font-family:"Hoefler Text","Iowan Old Style",Garamond,Georgia,"Times New Roman",serif}
.wrap{max-width:880px;margin:0 auto;padding:0 20px 96px}
header.top{padding:48px 0 8px}
.eyebrow{font-size:12px;letter-spacing:.22em;text-transform:uppercase;color:var(--muted)}
h1{font-size:54px;line-height:1;margin:10px 0 6px;font-weight:500}
.sub{color:var(--muted);font-size:16px;margin:0}
.stats{display:flex;gap:36px;margin:26px 0 8px}
.stat .n{font-size:30px;font-weight:600;line-height:1}
.stat .l{font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);margin-top:4px}

.filters{position:sticky;top:0;z-index:5;background:var(--bg);
  border-bottom:1px solid var(--line);padding:14px 0;margin-bottom:8px}
.frow{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:4px 0}
.frow .lbl{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted);margin-right:6px}
.chip{border:1px solid var(--line);background:#fff;border-radius:999px;
  padding:6px 13px;font-size:13px;cursor:pointer;color:var(--ink)}
.chip.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.export{margin-left:auto;border:1px solid var(--ink);background:#fff;border-radius:999px;
  padding:6px 14px;font-size:13px;cursor:pointer}

.capsule{margin-top:40px}
.capsule h2{font-size:30px;font-weight:500;margin:0 0 2px}
.capsule .cmeta{color:var(--muted);font-size:14px;margin:0 0 14px}
.group-label{font-size:11px;letter-spacing:.2em;text-transform:uppercase;
  color:var(--muted);margin:26px 0 12px;border-top:1px solid var(--line);padding-top:14px}

.look{background:var(--card);border:1px solid var(--line);border-radius:16px;
  overflow:hidden;margin:16px 0}
.look.cut{opacity:.5}
.strip{display:flex;gap:2px;background:var(--panel);padding:14px}
.tile{flex:1;min-width:0;aspect-ratio:1/1;background:var(--tile);border-radius:8px;
  display:flex;align-items:center;justify-content:center;overflow:hidden}
.tile img{width:100%;height:100%;object-fit:contain;mix-blend-mode:multiply}
.tile.empty{color:var(--muted);font-size:11px}
.body{padding:16px 18px 18px}
.lhead{display:flex;justify-content:space-between;align-items:baseline;gap:12px}
.lnum{font-size:12px;color:var(--muted)}
.ltag{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}
.lname{font-size:24px;font-weight:500;margin:2px 0 12px}
.slots{font-size:14px;border-top:1px solid var(--line);padding-top:12px}
.slot{display:flex;gap:10px;margin:3px 0}
.slot .k{width:62px;color:var(--muted);font-size:11px;letter-spacing:.12em;text-transform:uppercase;padding-top:2px}
.note{font-style:italic;color:#6f675b;font-size:14px;border-top:1px solid var(--line);
  margin-top:12px;padding-top:12px}
.wear{border-top:1px solid var(--line);margin-top:12px;padding-top:12px}
.wear .wl{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin-bottom:8px}
.acc{display:flex;align-items:center;gap:10px;margin:6px 0;font-size:14px}
.acc .athumb{width:44px;height:44px;border-radius:6px;background:var(--tile);
  display:flex;align-items:center;justify-content:center;overflow:hidden;flex:0 0 auto}
.acc .athumb img{width:100%;height:100%;object-fit:contain;mix-blend-mode:multiply}

.rate{display:flex;align-items:center;gap:8px;flex-wrap:wrap;
  border-top:1px solid var(--line);margin-top:14px;padding-top:14px}
.rbtn{border:1px solid var(--line);background:#fff;border-radius:999px;
  padding:6px 14px;font-size:13px;cursor:pointer;color:var(--ink)}
.rbtn[data-r=top].on{background:var(--top);border-color:var(--top);color:#fff}
.rbtn[data-r=solid].on{background:var(--solid);border-color:var(--solid);color:#fff}
.rbtn[data-r=maybe].on{background:var(--maybe);border-color:var(--maybe);color:#fff}
.rbtn[data-r=cut].on{background:var(--cut);border-color:var(--cut);color:#fff}
.ninput{flex:1;min-width:160px;border:1px solid var(--line);border-radius:10px;
  padding:7px 11px;font-size:13px;font-family:inherit;background:#fff}

.pack{background:var(--card);border:1px solid var(--line);border-radius:16px;
  padding:18px;margin-top:18px}
.pack h3{font-size:16px;margin:0 0 10px;font-weight:600}
.pack .cat{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted);margin:14px 0 6px}
.pitem{display:flex;align-items:center;gap:10px;font-size:14px;margin:4px 0}
.pitem input{width:17px;height:17px;accent-color:var(--top)}
.pitem.done label{color:var(--muted);text-decoration:line-through}

.empty-state{color:var(--muted);text-align:center;padding:60px 0}
footer{color:var(--muted);font-size:12px;text-align:center;margin-top:48px}
@media(max-width:560px){h1{font-size:40px}.lname{font-size:21px}.strip{flex-wrap:wrap}.tile{flex-basis:30%}}

.modal{position:fixed;inset:0;background:rgba(20,18,15,.45);display:none;
  align-items:center;justify-content:center;z-index:20;padding:20px}
.modal.show{display:flex}
.modal .box{background:#fff;border-radius:16px;max-width:560px;width:100%;padding:22px}
.modal h3{margin:0 0 6px}
.modal p{color:var(--muted);font-size:13px;margin:0 0 12px}
.modal textarea{width:100%;height:240px;border:1px solid var(--line);border-radius:10px;
  padding:12px;font-family:ui-monospace,Menlo,monospace;font-size:12px}
.modal .actions{display:flex;gap:8px;justify-content:flex-end;margin-top:12px}
.modal button{border:1px solid var(--ink);background:#fff;border-radius:999px;padding:7px 16px;cursor:pointer;font-size:13px}
.modal button.primary{background:var(--ink);color:#fff}
"""

JS = r"""
const LS = window.localStorage;
const rkey = id => "dr:rating:" + id;
const nkey = id => "dr:note:" + id;
const pkey = (cap,it) => "dr:pack:" + cap + ":" + it;

function effRating(card){
  const id = card.dataset.look;
  return LS.getItem(rkey(id)) || card.dataset.rating || "";
}
function paintLook(card){
  const id = card.dataset.look;
  const r = LS.getItem(rkey(id)) || "";
  card.querySelectorAll(".rbtn").forEach(b => b.classList.toggle("on", b.dataset.r === r));
  card.classList.toggle("cut", r === "cut");
  const n = card.querySelector(".ninput");
  if (n) n.value = LS.getItem(nkey(id)) || "";
}
function setRating(card, r){
  const id = card.dataset.look;
  const cur = LS.getItem(rkey(id)) || "";
  if (cur === r) LS.removeItem(rkey(id)); else LS.setItem(rkey(id), r);
  paintLook(card); applyFilters();
}

let fFormality = "all", fRating = "all";
function applyFilters(){
  document.querySelectorAll(".look").forEach(card => {
    const okF = fFormality === "all" || card.dataset.formality === fFormality;
    const eff = effRating(card);
    let okR = true;
    if (fRating === "all") okR = true;
    else if (fRating === "unrated") okR = !eff;
    else okR = eff === fRating;
    card.style.display = (okF && okR) ? "" : "none";
  });
  document.querySelectorAll(".capsule").forEach(sec => {
    const any = [...sec.querySelectorAll(".look")].some(c => c.style.display !== "none");
    sec.querySelectorAll(".group-label").forEach(g => {
      let n = g.nextElementSibling, vis = false;
      while (n && !n.classList.contains("group-label") && !n.classList.contains("pack")){
        if (n.classList.contains("look") && n.style.display !== "none") vis = true;
        n = n.nextElementSibling;
      }
      g.style.display = vis ? "" : "none";
    });
  });
}

function exportFeedback(){
  const buckets = {top:[], solid:[], maybe:[], cut:[]};
  const notes = [];
  document.querySelectorAll(".look").forEach(card => {
    const id = card.dataset.look;
    const name = card.dataset.name;
    const r = LS.getItem(rkey(id));
    if (r && buckets[r]) buckets[r].push(name + "  [" + id + "]");
    const n = LS.getItem(nkey(id));
    if (n) notes.push("- " + name + ": " + n + "  [" + id + "]");
  });
  let out = "DRESSING ROOM — FEEDBACK\n\n";
  const lab = {top:"TOP", solid:"SOLID", maybe:"MAYBE", cut:"CUT"};
  for (const k of ["top","solid","maybe","cut"]){
    out += lab[k] + " (" + buckets[k].length + ")\n";
    out += (buckets[k].length ? buckets[k].map(x => "  " + x).join("\n") : "  \u2014") + "\n\n";
  }
  out += "NOTES\n" + (notes.length ? notes.join("\n") : "  \u2014") + "\n";
  const ta = document.getElementById("exportText");
  ta.value = out;
  document.getElementById("exportModal").classList.add("show");
  ta.select();
}
function copyExport(){
  const ta = document.getElementById("exportText");
  ta.select(); document.execCommand("copy");
  const b = document.getElementById("copyBtn"); b.textContent = "Copied";
  setTimeout(() => b.textContent = "Copy", 1400);
}

function paintPack(){
  document.querySelectorAll(".pitem input").forEach(cb => {
    const on = LS.getItem(pkey(cb.dataset.cap, cb.dataset.it)) === "1";
    cb.checked = on; cb.closest(".pitem").classList.toggle("done", on);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".look").forEach(paintLook);
  document.querySelectorAll(".rbtn").forEach(b =>
    b.addEventListener("click", () => setRating(b.closest(".look"), b.dataset.r)));
  document.querySelectorAll(".ninput").forEach(n =>
    n.addEventListener("input", () => {
      const id = n.closest(".look").dataset.look;
      if (n.value.trim()) LS.setItem(nkey(id), n.value); else LS.removeItem(nkey(id));
    }));
  document.querySelectorAll("[data-ff]").forEach(c =>
    c.addEventListener("click", () => {
      fFormality = c.dataset.ff;
      document.querySelectorAll("[data-ff]").forEach(x => x.classList.toggle("on", x === c));
      applyFilters();
    }));
  document.querySelectorAll("[data-fr]").forEach(c =>
    c.addEventListener("click", () => {
      fRating = c.dataset.fr;
      document.querySelectorAll("[data-fr]").forEach(x => x.classList.toggle("on", x === c));
      applyFilters();
    }));
  document.querySelectorAll(".pitem input").forEach(cb =>
    cb.addEventListener("change", () => {
      if (cb.checked) LS.setItem(pkey(cb.dataset.cap, cb.dataset.it), "1");
      else LS.removeItem(pkey(cb.dataset.cap, cb.dataset.it));
      cb.closest(".pitem").classList.toggle("done", cb.checked);
    }));
  document.getElementById("exportBtn").addEventListener("click", exportFeedback);
  document.getElementById("copyBtn").addEventListener("click", copyExport);
  document.getElementById("closeBtn").addEventListener("click",
    () => document.getElementById("exportModal").classList.remove("show"));
  paintPack(); applyFilters();
});
"""


def esc(s):
    return html.escape(s or "")


def tile(item):
    if item and item.get("img"):
        return '<div class="tile"><img src="%s" alt="%s" loading="lazy"></div>' % (
            esc(item["img"]),
            esc(item["name"]),
        )
    return '<div class="tile empty">%s</div>' % esc(item["name"] if item else "")


def render_look(o, closet, num):
    tops, bottoms, shoes, accs = [], [], [], []
    for iid in o["items"]:
        it = closet.get(iid)
        if not it:
            continue
        s = slot_of(it["category"])
        {"top": tops, "bottom": bottoms, "shoes": shoes, "acc": accs}[s].append(it)

    strip = (tops + bottoms + shoes)[:6] or [None, None, None]
    thumbs = "".join(tile(it) for it in strip)

    slot_rows = []
    for label, group in (("Top", tops), ("Bottom", bottoms), ("Shoes", shoes)):
        if group:
            slot_rows.append(
                '<div class="slot"><div class="k">%s</div><div>%s</div></div>'
                % (label, esc(" + ".join(i["name"] for i in group)))
            )
    slots_html = "".join(slot_rows)

    note_html = '<div class="note">%s</div>' % esc(o["notes"]) if o["notes"] else ""

    wear_html = ""
    if accs:
        rows = "".join(
            '<div class="acc"><div class="athumb">%s</div><div>%s</div></div>'
            % (
                ('<img src="%s" alt="">' % esc(a["img"])) if a.get("img") else "",
                esc(a["name"]),
            )
            for a in accs
        )
        wear_html = '<div class="wear"><div class="wl">Wear with</div>%s</div>' % rows

    tag = FORMALITY_LABEL.get(o["formality"], o["formality"] or "")

    return """
<div class="look" data-look="%s" data-name="%s" data-formality="%s" data-rating="%s">
  <div class="strip">%s</div>
  <div class="body">
    <div class="lhead"><span class="lnum">Look %02d</span><span class="ltag">%s</span></div>
    <div class="lname serif">%s</div>
    <div class="slots">%s</div>
    %s%s
    <div class="rate">
      <button class="rbtn" data-r="top">Top</button>
      <button class="rbtn" data-r="solid">Solid</button>
      <button class="rbtn" data-r="maybe">Maybe</button>
      <button class="rbtn" data-r="cut">Cut</button>
      <input class="ninput" placeholder="note\u2026">
    </div>
  </div>
</div>""" % (
        esc(o["id"]),
        esc(o["name"]),
        esc(o["formality"] or ""),
        esc((o["rating"] or "").lower()),
        thumbs,
        num,
        esc(tag),
        esc(o["name"]),
        slots_html,
        note_html,
        wear_html,
    )


def render_pack(cap_id, cap, looks, closet):
    # union of all items used across this capsule's looks, grouped by category
    seen, by_cat = set(), {}
    cat_order = [
        "Shirt", "Polo", "Knitwear", "Tee", "Outerwear",
        "Tailoring", "Trousers", "Shorts", "Footwear", "Swim", "Accessory",
    ]
    for o in looks:
        for iid in o["items"]:
            if iid in seen:
                continue
            it = closet.get(iid)
            if not it:
                continue
            seen.add(iid)
            by_cat.setdefault(it["category"] or "Other", []).append((iid, it))
    if not seen:
        return ""
    blocks = []
    for cat in cat_order + [c for c in by_cat if c not in cat_order]:
        items = by_cat.get(cat)
        if not items:
            continue
        rows = "".join(
            '<div class="pitem"><input type="checkbox" data-cap="%s" data-it="%s" id="p_%s"><label for="p_%s">%s</label></div>'
            % (esc(cap_id), esc(iid), esc(iid), esc(iid), esc(it["name"]))
            for iid, it in sorted(items, key=lambda x: x[1]["name"].lower())
        )
        blocks.append('<div class="cat">%s</div>%s' % (esc(cat), rows))
    return '<div class="pack"><h3>Packing list \u00b7 %s</h3>%s</div>' % (
        esc(cap["name"]),
        "".join(blocks),
    )


def build_html(closet, capsules, outfits):
    # group outfits by capsule
    by_cap = {}
    for o in outfits:
        by_cap.setdefault(o["capsule"], []).append(o)

    total = len(outfits)
    rated = sum(1 for o in outfits if o["rating"])

    parts = []
    cap_ids = [c for c in by_cap if c is not None]
    cap_ids.sort(key=lambda c: (capsules.get(c, {}).get("start") or "", capsules.get(c, {}).get("name") or ""))
    if None in by_cap:
        cap_ids.append(None)

    if not outfits:
        parts.append('<div class="empty-state">No looks yet. Add looks in Notion and they\u2019ll appear here on the next rebuild.</div>')

    for cap_id in cap_ids:
        looks = by_cap[cap_id]
        cap = capsules.get(cap_id, {"name": "Unsorted", "notes": "", "start": None})
        meta_bits = []
        if cap.get("start"):
            meta_bits.append(esc(cap["start"]))
        if cap.get("notes"):
            meta_bits.append(esc(cap["notes"]))
        cmeta = " \u00b7 ".join(meta_bits)
        sec = ['<section class="capsule">',
               '<h2 class="serif">%s</h2>' % esc(cap["name"])]
        if cmeta:
            sec.append('<p class="cmeta">%s</p>' % cmeta)

        n = 0
        for f in FORMALITY_ORDER:
            flooks = [o for o in looks if o["formality"] == f]
            if not flooks:
                continue
            sec.append('<div class="group-label">%s</div>' % esc(FORMALITY_LABEL[f]))
            for o in flooks:
                n += 1
                sec.append(render_look(o, closet, n))
        # looks with no/other formality
        rest = [o for o in looks if o["formality"] not in FORMALITY_ORDER]
        if rest:
            sec.append('<div class="group-label">Other</div>')
            for o in rest:
                n += 1
                sec.append(render_look(o, closet, n))

        sec.append(render_pack(cap_id, cap, looks, closet))
        sec.append("</section>")
        parts.append("".join(sec))

    formality_chips = '<button class="chip on" data-ff="all">All</button>' + "".join(
        '<button class="chip" data-ff="%s">%s</button>' % (f, esc(FORMALITY_LABEL[f]))
        for f in FORMALITY_ORDER
    )
    rating_chips = "".join(
        '<button class="chip%s" data-fr="%s">%s</button>'
        % (" on" if v == "all" else "", v, lbl)
        for v, lbl in [
            ("all", "All"), ("unrated", "Unrated"),
            ("top", "Top"), ("solid", "Solid"), ("maybe", "Maybe"), ("cut", "Cut"),
        ]
    )

    return """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Dressing Room</title>
<style>%s</style>
</head><body>
<div class="wrap">
  <header class="top">
    <div class="eyebrow">Wardrobe OS</div>
    <h1 class="serif">The Dressing Room</h1>
    <p class="sub">Looks built in Notion. Rate, note, and cut here \u2014 the next rebuild reflects it.</p>
    <div class="stats">
      <div class="stat"><div class="n">%d</div><div class="l">Looks</div></div>
      <div class="stat"><div class="n">%d</div><div class="l">Capsules</div></div>
      <div class="stat"><div class="n">%d</div><div class="l">Rated</div></div>
    </div>
  </header>

  <div class="filters">
    <div class="frow"><span class="lbl">Vibe</span>%s
      <button class="export" id="exportBtn">Export feedback</button></div>
    <div class="frow"><span class="lbl">Rating</span>%s</div>
  </div>

  %s

  <footer>Generated from Notion \u00b7 The Dressing Room</footer>
</div>

<div class="modal" id="exportModal"><div class="box">
  <h3 class="serif">Export feedback</h3>
  <p>Copy this and paste it back in chat. I\u2019ll apply your ratings in Notion and cut what you cut.</p>
  <textarea id="exportText" readonly></textarea>
  <div class="actions">
    <button id="closeBtn">Close</button>
    <button class="primary" id="copyBtn">Copy</button>
  </div>
</div></div>

<script>%s</script>
</body></html>""" % (
        CSS,
        total,
        len([c for c in by_cap if c is not None]),
        rated,
        formality_chips,
        rating_chips,
        "\n".join(parts),
        JS,
    )


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def main():
    if not NOTION_TOKEN:
        raise SystemExit(
            "NOTION_TOKEN is not set. In CI, set it as a secret and pass it to the step:\n"
            "  env:\n    NOTION_TOKEN: ${{ secrets.NOTION_TOKEN }}"
        )
    t0 = time.time()
    closet, capsules, outfits = load()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    html_out = build_html(closet, capsules, outfits)
    (OUT_DIR / "index.html").write_text(html_out, encoding="utf-8")
    print(
        "Wrote %s  (%d looks, %d items, %d capsules)  in %.1fs"
        % (OUT_DIR / "index.html", len(outfits), len(closet), len(capsules), time.time() - t0)
    )


if __name__ == "__main__":
    main()
