#!/usr/bin/env python3
"""
build_dashboard.py  —  Wardrobe OS front-end generator.

Reads the live Notion Wardrobe OS (Closet, Outfits, Capsules, Recommendations,
Inspiration) and writes a single self-contained `wardrobe.html` you open locally.
Item images load from a sibling `images/` folder, matched by the IMG_####/slug key.

  pip install requests
  export NOTION_TOKEN=ntn_xxx
  python3 build_dashboard.py                # full build from Notion -> wardrobe.html
  python3 build_dashboard.py --preview DIR  # demo build from local thumbnails in DIR

Put your finished photos in an `images/` folder next to wardrobe.html (filenames
= the key in each item's Notes, e.g. IMG_0523.jpg, bylt_henley_navy.jpg).
"""
import os, sys, re, json, base64, glob, time
try:
    import requests
except ImportError:
    requests = None

API   = "https://api.notion.com/v1"
VER   = "2025-09-03"
TOKEN = os.environ.get("NOTION_TOKEN")

SRC = {  # data_source_id, database_id (fallback)
    "closet":  ("79f58a2a-2767-48b4-9eba-0cef6140ac15", "17624a6894294359a39d9e6fadd600ff"),
    "outfits": ("5af185ef-9fac-4f98-80fc-7d00955de606", "bd8d2b67dba34149ad8c35b38b5c53a8"),
    "capsules":("fb3a25cd-ae3c-4ebf-8a82-a6175443b24d", "92ce74f2cb184116bf8ffd7cab490a98"),
    "recs":    ("4901c849-db7d-4ecd-b24d-5eef73ce0bee", "2b7a811906554b578fdc6d87f00e871f"),
    "insp":    ("584f6fb8-4c1e-4c5c-9a86-cf98e969eae6", "5a65f884477a4efca8b879a8f009f8e0"),
}

# preserved Italy items -> their product-shot slug filename (no extension)
TITLE_TO_SLUG = {
    "Black BYLT Tee": "bylt_dc_black", "Bone BYLT Tee": "bylt_tee_bone",
    "Navy BYLT Henley": "bylt_henley_navy", "Bone BYLT Henley": "bylt_henley_bone",
    "Onia Navy Stripe SS": "new_onia_stripe", "Reiss Pink Stripe Linen LS": "real_reiss_stripe",
    "Bear Bottom Stone": "bearbottom_stone", "Bear Bottom Navy": "bearbottom_navy",
    "Bear Bottom Deep Mauve": "bearbottom_mauve", "Sand 5-Pocket Pants": "real_sand_pants",
    "AE Pull-On Trekker Tan": "new_ae_trekker", "Pink/Mauve 5-Pocket": "real_pink_pants",
    "Maamgic Black/Yellow": "maamgic_blackyellow", "Maamgic Blue/Grey": "maamgic_bluegrey",
    "Maamgic Navy/Red": "maamgic_navyred", "CT Tan Leather Belt": "belt_tan_leather",
    "Nisolo Woven Tobacco Belt": "belt_woven_tobacco", "Olive D-Ring Belt": "belt_olive_dring",
    "J.Crew Stripe Canvas Belt": "belt_stripe", "Quince Brixton Honey/Green": "sunglasses_honey_green",
    "Le Specs Bandwagon Tort": "sunglasses_lespecs_tort", "Ray-Ban RB4387": "sunglasses_rayban_grey",
}
IMG_RE = re.compile(r"IMG_\d+(?:-\d+)?")

# ---------- Notion helpers ----------
def H():  return {"Authorization": f"Bearer {TOKEN}", "Notion-Version": VER, "Content-Type": "application/json"}
def title(p): return "".join(t.get("plain_text","") for t in p.get("title", [])) if p else ""
def rich(p):  return "".join(t.get("plain_text","") for t in p.get("rich_text", [])) if p else ""
def sel(p):   return (p.get("select") or {}).get("name","") if p else ""
def msel(p):  return [o["name"] for o in p.get("multi_select", [])] if p else []
def relids(p):return [r["id"] for r in p.get("relation", [])] if p else []

def query(name):
    ds, db = SRC[name]
    out, cur = [], None
    while True:
        body = {"page_size": 100}
        if cur: body["start_cursor"] = cur
        r = requests.post(f"{API}/data_sources/{ds}/query", headers=H(), json=body)
        if r.status_code >= 400:
            h = {**H(), "Notion-Version": "2022-06-28"}
            r = requests.post(f"{API}/databases/{db}/query", headers=h, json=body)
        r.raise_for_status(); j = r.json()
        out += j["results"]; cur = j.get("next_cursor")
        if not j.get("has_more"): break
        time.sleep(0.2)
    return out

def img_key(item_title, notes):
    m = IMG_RE.search(notes or "")
    if m: return m.group(0)
    return TITLE_TO_SLUG.get(item_title, "")

def load_from_notion():
    closet_raw = query("closet")
    id2name = {p["id"]: title(p["properties"].get("Item", {})) for p in closet_raw}
    def photo_name(P):
        files = (P.get("Photo", {}) or {}).get("files", [])
        return files[0].get("name", "") if files else ""
    items = []
    for p in closet_raw:
        P = p["properties"]; nm = title(P.get("Item", {}))
        fn = photo_name(P); details = rich(P.get("Image Details", {}))
        key = os.path.splitext(fn)[0] if fn else img_key(nm, details)
        items.append({
            "id": p["id"], "name": nm, "brand": rich(P.get("Brand", {})),
            "cat": sel(P.get("Category", {})), "status": sel(P.get("Status", {})),
            "form": sel(P.get("Formality", {})), "fit": sel(P.get("Fit", {})),
            "colors": msel(P.get("Color", {})), "material": rich(P.get("Material", {})),
            "season": msel(P.get("Season", {})), "vibe": msel(P.get("Vibe", {})),
            "product": rich(P.get("Product", {})),
            "notes": "", "key": key, "img": fn,
        })
    items.sort(key=lambda x: (x["cat"], x["name"]))
    def safe(name, fn):
        try: return fn(query(name))
        except Exception as e: print(f"  ({name} skipped: {e})"); return []
    looks = safe("outfits", lambda raw: [{
        "name": title(p["properties"].get("Look", {})),
        "items": [id2name.get(i,"") for i in relids(p["properties"].get("Items", {}))],
        "occasion": msel(p["properties"].get("Occasion", {})),
        "form": sel(p["properties"].get("Formality", {})),
        "rating": sel(p["properties"].get("Rating", {})),
        "status": sel(p["properties"].get("Status", {})),
        "notes": rich(p["properties"].get("Notes", {})),
    } for p in raw])
    capsules = safe("capsules", lambda raw: [{
        "name": title(p["properties"].get("Capsule", {})),
        "type": sel(p["properties"].get("Type", {})),
        "items": [id2name.get(i,"") for i in relids(p["properties"].get("Items", {}))],
        "notes": rich(p["properties"].get("Notes", {})),
    } for p in raw])
    recs = safe("recs", lambda raw: [{
        "name": title(p["properties"].get("Item", {})),
        "brand": rich(p["properties"].get("Brand", {})),
        "price": (p["properties"].get("Price", {}) or {}).get("number"),
        "link": (p["properties"].get("Link", {}) or {}).get("url"),
        "rationale": rich(p["properties"].get("Rationale", {})),
        "status": sel(p["properties"].get("Status", {})),
        "priority": sel(p["properties"].get("Priority", {})),
    } for p in raw])
    return items, looks, capsules, recs

# ---------- HTML ----------
CSS = """
:root{
  --paper:#E9E3D7; --card:#F2EEE7; --ink:#211D17; --ink-soft:#6A6253;
  --line:#D4CCBC; --olive:#5E6646; --navy:#2A3550; --tobacco:#8A6F4E;
  --marigold:#C08A1E; --rust:#A8542E;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);
  font-family:Inter,system-ui,-apple-system,sans-serif;font-size:15px;line-height:1.5}
.mono{font-family:"Spline Sans Mono",ui-monospace,Menlo,monospace}
.serif{font-family:Fraunces,Georgia,serif}
a{color:inherit}
header.top{position:sticky;top:0;z-index:30;background:rgba(233,227,215,.92);
  backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
.bar{max-width:1320px;margin:0 auto;padding:14px 22px;display:flex;align-items:baseline;gap:18px;flex-wrap:wrap}
.brandmark{font-family:Fraunces,serif;font-weight:600;font-size:23px;letter-spacing:.2px}
.brandmark em{font-style:italic;color:var(--olive)}
.eyebrow{font-family:"Spline Sans Mono",monospace;font-size:10.5px;letter-spacing:.22em;
  text-transform:uppercase;color:var(--ink-soft)}
nav.tabs{margin-left:auto;display:flex;gap:2px}
nav.tabs button{font-family:"Spline Sans Mono",monospace;font-size:11px;letter-spacing:.12em;
  text-transform:uppercase;background:none;border:0;color:var(--ink-soft);padding:8px 11px;
  cursor:pointer;border-bottom:2px solid transparent}
nav.tabs button[aria-selected=true]{color:var(--ink);border-bottom-color:var(--marigold)}
nav.tabs button:focus-visible{outline:2px solid var(--navy);outline-offset:2px}
.wrap{max-width:1320px;margin:0 auto;padding:22px}

/* filter spec bar */
.spec{display:flex;gap:10px;flex-wrap:wrap;align-items:center;
  padding:12px 14px;background:var(--card);border:1px solid var(--line);border-radius:3px;margin-bottom:6px}
.spec input[type=search]{flex:1 1 200px;min-width:160px;border:1px solid var(--line);background:#fff;
  padding:8px 10px;border-radius:2px;font:inherit}
.spec select{font-family:"Spline Sans Mono",monospace;font-size:11px;letter-spacing:.06em;
  text-transform:uppercase;border:1px solid var(--line);background:#fff;padding:7px 8px;border-radius:2px;cursor:pointer}
.spec .count{font-family:"Spline Sans Mono",monospace;font-size:11px;color:var(--ink-soft);letter-spacing:.08em;margin-left:auto}
.spec .clear{border:0;background:none;color:var(--ink-soft);cursor:pointer;font:inherit;text-decoration:underline}

/* grid */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(206px,1fr));gap:16px;margin-top:18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:3px;overflow:hidden;
  cursor:pointer;transition:transform .14s ease,box-shadow .14s ease;display:flex;flex-direction:column}
.card:hover{transform:translateY(-3px);box-shadow:0 10px 26px -16px rgba(33,29,23,.5)}
.card:focus-visible{outline:2px solid var(--navy);outline-offset:2px}
.thumb{position:relative;aspect-ratio:1/1;background:var(--card);display:flex;align-items:center;justify-content:center;padding:14px}
.thumb img{max-width:100%;max-height:100%;object-fit:contain}
.thumb .ph{font-family:"Spline Sans Mono",monospace;font-size:10px;color:var(--ink-soft);text-align:center;padding:0 10px;letter-spacing:.05em}
.idx{position:absolute;top:8px;left:9px;font-family:"Spline Sans Mono",monospace;font-size:9.5px;
  color:var(--ink-soft);letter-spacing:.06em}
.star{position:absolute;top:6px;right:8px;font-size:13px;color:var(--marigold);letter-spacing:-1px}
.meta{padding:11px 12px 13px;border-top:1px solid var(--line)}
.meta .nm{font-family:Fraunces,serif;font-size:14.5px;line-height:1.25}
.meta .br{font-family:"Spline Sans Mono",monospace;font-size:10px;text-transform:uppercase;
  letter-spacing:.1em;color:var(--ink-soft);margin-top:3px;min-height:12px}
.chips{display:flex;gap:5px;flex-wrap:wrap;margin-top:9px;align-items:center}
.chip{font-family:"Spline Sans Mono",monospace;font-size:9.5px;text-transform:uppercase;letter-spacing:.07em;
  padding:2px 6px;border:1px solid var(--line);border-radius:2px;color:var(--ink-soft)}
.sw{width:12px;height:12px;border-radius:50%;border:1px solid rgba(0,0,0,.18);display:inline-block}
.statusdot{margin-left:auto;font-family:"Spline Sans Mono",monospace;font-size:9px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--ink-soft)}

/* drawer */
.scrim{position:fixed;inset:0;background:rgba(33,29,23,.34);opacity:0;pointer-events:none;transition:opacity .2s;z-index:40}
.scrim.on{opacity:1;pointer-events:auto}
.drawer{position:fixed;top:0;right:0;height:100%;width:min(430px,92vw);background:var(--paper);
  border-left:1px solid var(--line);transform:translateX(100%);transition:transform .24s ease;z-index:50;
  overflow:auto;padding:24px}
.drawer.on{transform:none}
.drawer .x{position:absolute;top:16px;right:18px;border:0;background:none;font-size:22px;cursor:pointer;color:var(--ink-soft)}
.drawer .dimg{background:var(--card);border:1px solid var(--line);border-radius:3px;aspect-ratio:1/1;
  display:flex;align-items:center;justify-content:center;padding:22px;margin-bottom:18px}
.drawer .dimg img{max-width:100%;max-height:100%;object-fit:contain}
.drawer h2{font-family:Fraunces,serif;font-weight:600;font-size:24px;line-height:1.15;margin:0 0 2px}
.drawer .dbrand{font-family:"Spline Sans Mono",monospace;font-size:11px;text-transform:uppercase;letter-spacing:.12em;color:var(--ink-soft);margin-bottom:18px}
.spec-row{display:grid;grid-template-columns:88px 1fr;gap:8px;padding:9px 0;border-top:1px solid var(--line);font-size:13.5px}
.spec-row .k{font-family:"Spline Sans Mono",monospace;font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:var(--ink-soft);padding-top:2px}
.rate{display:flex;gap:6px;margin:6px 0 2px}
.rate button{border:1px solid var(--line);background:#fff;font-family:"Spline Sans Mono",monospace;font-size:10px;
  letter-spacing:.08em;text-transform:uppercase;padding:6px 10px;border-radius:2px;cursor:pointer}
.rate button[aria-pressed=true]{background:var(--ink);color:var(--paper);border-color:var(--ink)}
.note{width:100%;border:1px solid var(--line);background:#fff;border-radius:2px;padding:9px;font:inherit;margin-top:8px;resize:vertical;min-height:64px}

/* simple tab panels */
.panel{display:none} .panel.on{display:block}
.empty{text-align:center;padding:70px 20px;color:var(--ink-soft)}
.empty h3{font-family:Fraunces,serif;color:var(--ink);font-size:21px;margin:0 0 8px}
.list{display:flex;flex-direction:column;gap:12px;margin-top:18px}
.row{background:var(--card);border:1px solid var(--line);border-radius:3px;padding:14px 16px}
.row .rt{font-family:Fraunces,serif;font-size:17px}
.row .rs{font-family:"Spline Sans Mono",monospace;font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:var(--ink-soft);margin-top:3px}
.reqbtn{font-family:"Spline Sans Mono",monospace;font-size:11px;letter-spacing:.08em;text-transform:uppercase;
  border:1px solid var(--ink);background:var(--ink);color:var(--paper);padding:10px 14px;border-radius:2px;cursor:pointer}
.reqbtn.alt{background:#fff;color:var(--ink)}
.reqbtn:focus-visible,.reqx:focus-visible{outline:2px solid var(--navy);outline-offset:2px}
.reqx{border:0;background:none;font-size:20px;line-height:1;color:var(--ink-soft);cursor:pointer;padding:0 4px}
@media (max-width:640px){ .bar{padding:12px 14px} nav.tabs{width:100%;margin-left:0;overflow-x:auto} .wrap{padding:14px} }
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""

APP_JS = r"""
const COLORS={Cream:'#EBE4D4',White:'#FBFAF7',Navy:'#2A3550',Blue:'#5B7A99',Olive:'#5E6646',
  Tan:'#B79B72',Brown:'#6E4E34',Grey:'#928D82',Black:'#211F1C',Pink:'#C9A6A0',
  Marigold:'#C08A1E',Rust:'#A8542E'};
const ITEMS=DATA.items;
function srcFor(it){ if(MODE==='base64'){return IMG[it.key]||'';} return it.img?('images/'+it.img):(it.key?('images/'+it.key+'.jpg'):''); }
function ann(id){ try{return JSON.parse(localStorage.getItem('wd:'+id))||{}}catch(e){return{}} }
function setAnn(id,a){ localStorage.setItem('wd:'+id,JSON.stringify(a)); }

function swatch(c){ if(c==='Stripe') return '<span class="sw" style="background:repeating-linear-gradient(45deg,#2A3550 0 3px,#EBE4D4 3px 6px)" title="Stripe"></span>';
  return '<span class="sw" style="background:'+(COLORS[c]||'#ccc')+'" title="'+c+'"></span>'; }

function cardHTML(it,i){
  const s=srcFor(it); const a=ann(it.id);
  const img=s?('<img loading="lazy" src="'+s+'" alt="'+it.name+'" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'block\'">'+
              '<span class="ph" style="display:none">'+(it.key||it.name)+'<br>(drop image in /images)</span>')
            :('<span class="ph">'+(it.key||'no key')+'</span>');
  const sw=(it.colors||[]).map(swatch).join('');
  return '<button class="card" data-i="'+i+'">'+
    '<div class="thumb"><span class="idx">'+String(i+1).padStart(3,'0')+'</span>'+
      (a.rating?'<span class="star" title="'+a.rating+'">'+(a.rating==='Top'?'★★':a.rating==='Solid'?'★':'☆')+'</span>':'')+
      img+'</div>'+
    '<div class="meta"><div class="nm">'+it.name+'</div>'+
      '<div class="br">'+(it.brand||'—')+'</div>'+
      '<div class="chips">'+(it.cat?'<span class="chip">'+it.cat+'</span>':'')+sw+
        '<span class="statusdot">'+(it.status||'')+'</span></div>'+
    '</div></button>';
}

let view=[];
function applyFilters(){
  const q=(F.q.value||'').toLowerCase();
  const get=id=>F[id].value;
  view=ITEMS.filter(it=>{
    if(q && !(it.name+' '+it.brand+' '+it.material+' '+it.notes).toLowerCase().includes(q)) return false;
    if(get('cat') && it.cat!==get('cat')) return false;
    if(get('status') && it.status!==get('status')) return false;
    if(get('form') && it.form!==get('form')) return false;
    if(get('color') && !(it.colors||[]).includes(get('color'))) return false;
    if(get('season') && !(it.season||[]).includes(get('season'))) return false;
    if(get('vibe') && !(it.vibe||[]).includes(get('vibe'))) return false;
    return true;
  });
  const sort=F.sort.value;
  if(sort==='name') view.sort((a,b)=>a.name.localeCompare(b.name));
  else if(sort==='cat') view.sort((a,b)=>(a.cat||'').localeCompare(b.cat||'')||a.name.localeCompare(b.name));
  document.getElementById('grid').innerHTML=view.map(cardHTML).join('');
  document.getElementById('count').textContent=view.length+' / '+ITEMS.length+' pieces';
}

function opt(arr){ return ['<option value="">All</option>'].concat([...new Set(arr)].filter(Boolean).sort()
  .map(v=>'<option>'+v+'</option>')).join(''); }
const F={};
function initFilters(){
  ['q','cat','color','form','season','vibe','status','sort'].forEach(id=>F[id]=document.getElementById('f-'+id));
  F.cat.innerHTML=opt(ITEMS.map(i=>i.cat));
  F.color.innerHTML=opt(ITEMS.flatMap(i=>i.colors||[]));
  F.form.innerHTML=opt(ITEMS.map(i=>i.form));
  F.season.innerHTML=opt(ITEMS.flatMap(i=>i.season||[]));
  F.vibe.innerHTML=opt(ITEMS.flatMap(i=>i.vibe||[]));
  F.status.innerHTML=opt(ITEMS.map(i=>i.status));
  Object.values(F).forEach(el=>el.addEventListener('input',applyFilters));
  document.getElementById('f-clear').onclick=()=>{Object.values(F).forEach(el=>{if(el.tagName==='SELECT')el.value='';else el.value='';});applyFilters();};
}

function openDrawer(it){
  const s=srcFor(it); const a=ann(it.id);
  const row=(k,v)=> v&&v.length? '<div class="spec-row"><div class="k">'+k+'</div><div>'+(Array.isArray(v)?v.join(', '):v)+'</div></div>':'';
  document.getElementById('dbody').innerHTML=
    '<div class="dimg">'+(s?'<img src="'+s+'" alt="'+it.name+'" onerror="this.replaceWith(document.createTextNode(\''+(it.key||'')+'\'))">':(it.key||'no image key'))+'</div>'+
    '<h2 class="serif">'+it.name+'</h2><div class="dbrand">'+(it.brand||'—')+'</div>'+
    row('Category',it.cat)+row('Colour',it.colors)+row('Material',it.material)+row('Fit',it.fit)+
    row('Formality',it.form)+row('Season',it.season)+row('Vibe',it.vibe)+row('Status',it.status)+row('Product',it.product)+
    '<div class="spec-row"><div class="k">My take</div><div>'+
      '<div class="rate">'+['Top','Solid','Maybe'].map(r=>'<button data-r="'+r+'" aria-pressed="'+(a.rating===r)+'">'+r+'</button>').join('')+'</div>'+
      '<textarea class="note" placeholder="Personal note (saved on this device)">'+(a.note||'')+'</textarea>'+
    '</div></div>';
  document.querySelectorAll('.rate button').forEach(b=>b.onclick=()=>{
    const cur=ann(it.id); cur.rating=(cur.rating===b.dataset.r?'':b.dataset.r); setAnn(it.id,cur);
    document.querySelectorAll('.rate button').forEach(x=>x.setAttribute('aria-pressed', x.dataset.r===cur.rating));
    applyFilters();
  });
  document.querySelector('.note').oninput=e=>{const cur=ann(it.id);cur.note=e.target.value;setAnn(it.id,cur);};
  document.getElementById('scrim').classList.add('on');
  document.getElementById('drawer').classList.add('on');
}
function closeDrawer(){document.getElementById('scrim').classList.remove('on');document.getElementById('drawer').classList.remove('on');}

function renderRows(elId, rows, fmt, emptyTitle, emptyMsg){
  const el=document.getElementById(elId);
  if(!rows.length){ el.innerHTML='<div class="empty"><h3>'+emptyTitle+'</h3><p>'+emptyMsg+'</p></div>'; return; }
  el.innerHTML='<div class="list">'+rows.map(fmt).join('')+'</div>';
}

function tab(name){
  document.querySelectorAll('nav.tabs button').forEach(b=>b.setAttribute('aria-selected', b.dataset.t===name));
  document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('on', p.id==='panel-'+name));
}

document.addEventListener('DOMContentLoaded',()=>{
  initFilters(); applyFilters();
  document.getElementById('grid').addEventListener('click',e=>{const c=e.target.closest('.card');if(c)openDrawer(view[+c.dataset.i]);});
  document.getElementById('scrim').onclick=closeDrawer;
  document.getElementById('dclose').onclick=closeDrawer;
  document.addEventListener('keydown',e=>{if(e.key==='Escape')closeDrawer();});
  document.querySelectorAll('nav.tabs button').forEach(b=>b.onclick=()=>tab(b.dataset.t));

  renderRows('panel-looks', DATA.looks, l=>'<div class="row"><div class="rt serif">'+l.name+'</div>'+
    '<div class="rs">'+[l.form,(l.occasion||[]).join(' · '),l.status].filter(Boolean).join('  ·  ')+'</div>'+
    (l.items&&l.items.length?'<div style="margin-top:8px;font-size:13.5px">'+l.items.join(' · ')+'</div>':'')+'</div>',
    'No looks yet','Outfits live in Notion. Tell Claude “build looks from my closet” and they’ll appear here on the next build.');
  renderRows('panel-capsules', DATA.capsules, c=>'<div class="row"><div class="rt serif">'+c.name+'</div>'+
    '<div class="rs">'+(c.type||'')+'</div>'+(c.items&&c.items.length?'<div style="margin-top:8px;font-size:13.5px">'+c.items.join(' · ')+'</div>':'')+'</div>',
    'No capsules yet','Create a trip, event, seasonal, or vibe capsule in Notion and it shows up here.');
  renderRows('panel-want', DATA.recs, r=>'<div class="row"><div class="rt serif">'+r.name+(r.price?' — $'+r.price:'')+'</div>'+
    '<div class="rs">'+[r.brand,r.status,r.priority].filter(Boolean).join('  ·  ')+'</div>'+
    (r.rationale?'<div style="margin-top:8px;font-size:13.5px">'+r.rationale+'</div>':'')+
    (r.link?'<div style="margin-top:8px"><a class="mono" style="font-size:11px" href="'+r.link+'" target="_blank">View →</a></div>':'')+'</div>',
    'Nothing on the want list','Validated buys from Claude land here — confirmed link + price, the gap each one fills.');
  renderRequests();
  document.getElementById('req-add').onclick=addReq;
  document.getElementById('req-copy').onclick=copyReqs;
  document.getElementById('req-text').addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.metaKey||e.ctrlKey))addReq();});
});
function reqAll(){try{return JSON.parse(localStorage.getItem('dr:requests'))||[]}catch(e){return[]}}
function reqSave(a){localStorage.setItem('dr:requests',JSON.stringify(a));}
function renderRequests(){
  const a=reqAll(); const el=document.getElementById('req-list');
  document.getElementById('req-count').textContent=a.length?(a.length+' open'):'';
  if(!a.length){el.innerHTML='<div class="empty"><h3>No requests yet</h3><p>Jot any change — a styling tweak, a new look, a catalog fix. It saves here; tap “Copy for Claude” and paste it into chat to push an update.</p></div>';return;}
  el.innerHTML='<div class="list">'+a.map((r,i)=>'<div class="row"><div style="display:flex;gap:10px;align-items:flex-start"><div style="flex:1">'+r.t.replace(/&/g,'&amp;').replace(/</g,'&lt;')+'<div class="rs">'+new Date(r.ts).toLocaleDateString()+'</div></div><button class="reqx" data-i="'+i+'" aria-label="Delete request">×</button></div></div>').join('')+'</div>';
  el.querySelectorAll('.reqx').forEach(b=>b.onclick=()=>{const x=reqAll();x.splice(+b.dataset.i,1);reqSave(x);renderRequests();});
}
function addReq(){const t=document.getElementById('req-text');const v=t.value.trim();if(!v)return;const a=reqAll();a.unshift({t:v,ts:Date.now()});reqSave(a);t.value='';renderRequests();}
function copyReqs(){const a=reqAll();if(!a.length)return;const txt='The Dressing Room — requests:\n'+a.map((r,i)=>(i+1)+'. '+r.t).join('\n');
  navigator.clipboard.writeText(txt).then(()=>{const b=document.getElementById('req-copy');const o=b.textContent;b.textContent='Copied ✓';setTimeout(()=>b.textContent=o,1400);});}
"""

def shell(items, looks, capsules, recs, mode, imgmap):
    data = {"items": items, "looks": looks, "capsules": capsules, "recs": recs}
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>The Dressing Room</title>
<meta name="theme-color" content="#E9E3D7">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="The Dressing Room">
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="icon-180.png">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,600;1,9..144,400&family=Inter:wght@400;500&family=Spline+Sans+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>
<header class="top"><div class="bar">
  <div><div class="brandmark">The Dressing Room</div><div class="eyebrow">A+R atelier inventory</div></div>
  <nav class="tabs" role="tablist">
    <button data-t="closet" aria-selected="true">Closet</button>
    <button data-t="looks" aria-selected="false">Looks</button>
    <button data-t="capsules" aria-selected="false">Capsules</button>
    <button data-t="want" aria-selected="false">Want / Find</button>
    <button data-t="requests" aria-selected="false">Requests</button>
  </nav>
</div></header>
<div class="wrap">
  <section id="panel-closet" class="panel on">
    <div class="spec">
      <input id="f-q" type="search" placeholder="Search name, brand, material, notes…" aria-label="Search">
      <select id="f-cat" aria-label="Category"></select>
      <select id="f-color" aria-label="Colour"></select>
      <select id="f-form" aria-label="Formality"></select>
      <select id="f-season" aria-label="Season"></select>
      <select id="f-vibe" aria-label="Vibe"></select>
      <select id="f-status" aria-label="Status"></select>
      <select id="f-sort" aria-label="Sort"><option value="">By index</option><option value="name">By name</option><option value="cat">By category</option></select>
      <button id="f-clear" class="clear">Clear</button>
      <span id="count" class="count"></span>
    </div>
    <div id="grid" class="grid"></div>
  </section>
  <section id="panel-looks" class="panel"></section>
  <section id="panel-capsules" class="panel"></section>
  <section id="panel-want" class="panel"></section>
  <section id="panel-requests" class="panel">
    <div class="spec" style="gap:10px">
      <textarea id="req-text" placeholder="Describe a change — “build 5 Lisbon dinner looks”, “make the cards larger”, “0556 is black not grey”…" style="flex:1 1 260px;border:1px solid var(--line);background:#fff;padding:9px 10px;border-radius:2px;font:inherit;min-height:46px;resize:vertical"></textarea>
      <button id="req-add" class="reqbtn">Add</button>
      <button id="req-copy" class="reqbtn alt">Copy for Claude</button>
      <span id="req-count" class="count"></span>
    </div>
    <div id="req-list"></div>
  </section>
</div>
<div id="scrim" class="scrim"></div>
<aside id="drawer" class="drawer" role="dialog" aria-modal="true">
  <button id="dclose" class="x" aria-label="Close">×</button><div id="dbody"></div>
</aside>
<script>const MODE={json.dumps(mode)};const IMG={json.dumps(imgmap)};const DATA={json.dumps(data)};</script>
<script>{APP_JS}</script>
</body></html>"""

# ---------- preview ----------
PREVIEW = [
    ("IMG_0522","Navy Breton Stripe SS Tee","","Tee","Casual","Slim",["Navy","Stripe"],"","Riviera"),
    ("IMG_0523","Tan Slub SS Tee","","Tee","Casual","Slim",["Tan"],"","Riviera"),
    ("bylt_henley_navy","Navy BYLT Henley","BYLT","Tee","Casual","Slim",["Navy"],"","Riviera"),
    ("IMG_0540","Tan Linen Shorts","","Shorts","Casual","Slim",["Tan"],"Linen","Riviera"),
    ("IMG_0509-5","Rust 5-Pocket Trousers","","Trousers","Casual","Slim",["Rust"],"","Riviera"),
    ("IMG_0515","Olive Trousers","","Trousers","Casual","Slim",["Olive"],"","Soft tailoring"),
    ("IMG_0548","Marigold Sweater","","Knitwear","Casual","Slim",["Marigold"],"","Riviera"),
    ("IMG_0605","Navy Soft Blazer","","Tailoring","Smart","Tailored",["Navy"],"","Soft tailoring"),
    ("IMG_0619","Cognac Leather Boots","","Footwear","Smart","",["Brown"],"Leather","Heritage"),
    ("IMG_0638","White On Cloud Sneakers","On","Footwear","Casual","",["White"],"","Sporty"),
    ("belt_woven_tobacco","Nisolo Woven Tobacco Belt","Nisolo","Accessory","Casual","",["Brown"],"Woven leather","Riviera"),
    ("IMG_0633","Watch — Cream Dial, Steel Bracelet","","Accessory","Dressy","",["Cream","Grey"],"","Heritage"),
]
def build_preview(thumbs):
    items, imgmap = [], {}
    for k,nm,br,cat,form,fit,cols,mat,vibe in PREVIEW:
        items.append({"id":k,"name":nm,"brand":br,"cat":cat,"status":"Regular rotation","form":form,
            "fit":fit,"colors":cols,"material":mat,"season":["SS"],"vibe":[vibe] if vibe else [],"notes":k,"key":k})
        fp=os.path.join(thumbs,k+".jpg")
        if os.path.exists(fp):
            imgmap[k]="data:image/jpeg;base64,"+base64.b64encode(open(fp,"rb").read()).decode()
    looks=[]; capsules=[]
    recs=[{"name":"Bather — Sage Linen Camp Shirt","brand":"Bather","price":150,"link":"https://bather.com",
           "rationale":"Camp collar in a quiet sage linen — riviera, not loud. Confirm stock at purchase.","status":"Watching","priority":"Med"}]
    html=shell(items,looks,capsules,recs,"base64",imgmap)
    open("/home/claude/wardrobe_preview.html","w").write(html)
    print(f"preview written: {len(items)} items, {len(imgmap)} images embedded")

def main():
    if "--preview" in sys.argv:
        build_preview(sys.argv[sys.argv.index("--preview")+1]); return
    if not requests: sys.exit("pip install requests")
    if not TOKEN: sys.exit("Set NOTION_TOKEN.")
    print("Querying Notion…")
    items, looks, capsules, recs = load_from_notion()
    html=shell(items,looks,capsules,recs,"path",{})
    open("index.html","w").write(html)
    print(f"index.html written — {len(items)} items, {len(looks)} looks, {len(capsules)} capsules, {len(recs)} recs.")
    print("Drop your finished photos in an images/ folder beside it, using the exact filenames attached in Notion (e.g. IMG_0509-5.jpg, sunglasses_rayban_grey.png).")

if __name__=="__main__":
    main()
