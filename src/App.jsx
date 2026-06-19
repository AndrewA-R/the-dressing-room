import React, { useEffect, useMemo, useState, useCallback } from 'react'

const OCCASIONS = ['Day out', 'Dinner', 'Travel', 'Beach', 'Work', 'Evening']
const RATINGS = ['Top', 'Solid', 'Maybe']
const FORMALITIES = ['Beach', 'Casual', 'Smart', 'Dressy']
const TABS = ['Closet', 'Looks', 'Capsules', 'Shop']

async function api(path, body) {
  const res = await fetch(path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined)
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`)
  return data
}

export default function App() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [tab, setTab] = useState('Closet')
  const [toast, setToast] = useState(null)

  const load = useCallback(async () => {
    try {
      setError(null)
      const d = await api('/api/data')
      setData(d)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const flash = useCallback((msg) => {
    setToast(msg)
    setTimeout(() => setToast(null), 2600)
  }, [])

  const closetById = useMemo(() => {
    const m = new Map()
    ;(data?.closet || []).forEach((p) => m.set(p.id, p))
    return m
  }, [data])

  const capsuleById = useMemo(() => {
    const m = new Map()
    ;(data?.capsules || []).forEach((c) => m.set(c.id, c))
    return m
  }, [data])

  if (loading) return <Shell tab={tab} setTab={setTab}><div className="state">Opening the wardrobe…</div></Shell>
  if (error) return <Shell tab={tab} setTab={setTab}><div className="state error"><p>The wardrobe didn’t load.</p><code>{error}</code><button className="btn" onClick={load}>Try again</button></div></Shell>

  return (
    <Shell tab={tab} setTab={setTab}>
      {tab === 'Closet' && <Closet data={data} capsules={data.capsules} onChanged={load} flash={flash} />}
      {tab === 'Looks' && <Looks data={data} closetById={closetById} capsuleById={capsuleById} onChanged={load} flash={flash} />}
      {tab === 'Capsules' && <Capsules data={data} closetById={closetById} flash={flash} />}
      {tab === 'Shop' && <Shop data={data} capsuleById={capsuleById} />}
      {toast && <div className="toast">{toast}</div>}
    </Shell>
  )
}

function Shell({ tab, setTab, children }) {
  return (
    <div className="app">
      <header className="masthead">
        <div className="wordmark">The Dressing&nbsp;Room</div>
        <nav className="nav">
          {TABS.map((t) => (
            <button key={t} className={`navlink ${tab === t ? 'on' : ''}`} onClick={() => setTab(t)}>{t}</button>
          ))}
        </nav>
      </header>
      <main className="main">{children}</main>
    </div>
  )
}

/* ---------------- Closet ---------------- */
function Closet({ data, capsules, onChanged, flash }) {
  const [cat, setCat] = useState('All')
  const [open, setOpen] = useState(null)
  const cats = useMemo(() => ['All', ...Array.from(new Set(data.closet.map((p) => p.category).filter(Boolean)))], [data])
  const items = data.closet.filter((p) => cat === 'All' || p.category === cat)

  return (
    <section>
      <SectionHead eyebrow="Everything you own" title="The Closet" count={`${data.closet.length} pieces`} />
      <Filters>
        {cats.map((c) => <Chip key={c} on={cat === c} onClick={() => setCat(c)}>{c}</Chip>)}
      </Filters>
      <div className="grid">
        {items.map((p) => (
          <button key={p.id} className="card" onClick={() => setOpen(p)}>
            <Frame src={p.photo} alt={p.name} />
            <div className="card-meta">
              <span className="card-title">{p.name}</span>
              <span className="card-sub">{[p.brand, p.category].filter(Boolean).join(' · ')}</span>
            </div>
          </button>
        ))}
      </div>
      {open && <PiecePanel piece={open} capsules={capsules} onClose={() => setOpen(null)} onChanged={onChanged} flash={flash} />}
    </section>
  )
}

function PiecePanel({ piece, capsules, onClose, onChanged, flash }) {
  const [occasion, setOccasion] = useState('Dinner')
  const [capsuleId, setCapsuleId] = useState('')
  const [busy, setBusy] = useState(false)

  async function build() {
    setBusy(true)
    try {
      const out = await api('/api/generate', { pieceId: piece.id, occasion, capsuleId: capsuleId || undefined })
      flash(`Built “${out.name}” — added to Looks.`)
      onChanged()
      onClose()
    } catch (e) {
      flash(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Panel onClose={onClose}>
      <Frame src={piece.photo} alt={piece.name} big />
      <h2 className="panel-title">{piece.name}</h2>
      <p className="panel-sub">{[piece.brand, piece.product].filter(Boolean).join(' · ')}</p>
      <dl className="specs">
        {piece.category && <Spec k="Category" v={piece.category} />}
        {piece.colors?.length > 0 && <Spec k="Colour" v={piece.colors.join(', ')} />}
        {piece.material && <Spec k="Material" v={piece.material} />}
        {piece.fit && <Spec k="Fit" v={piece.fit} />}
        {piece.formality && <Spec k="Formality" v={piece.formality} />}
        {piece.status && <Spec k="Status" v={piece.status} />}
      </dl>

      <div className="build">
        <div className="build-head">Build a look around this</div>
        <label className="field">
          <span>for</span>
          <select value={occasion} onChange={(e) => setOccasion(e.target.value)}>
            {OCCASIONS.map((o) => <option key={o}>{o}</option>)}
          </select>
        </label>
        <label className="field">
          <span>into</span>
          <select value={capsuleId} onChange={(e) => setCapsuleId(e.target.value)}>
            <option value="">No capsule</option>
            {capsules.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <button className="btn primary" disabled={busy} onClick={build}>{busy ? 'Styling…' : 'Build the look'}</button>
      </div>
      {piece.notionUrl && <a className="notion-link" href={piece.notionUrl} target="_blank" rel="noreferrer">Open in Notion ↗</a>}
    </Panel>
  )
}

/* ---------------- Looks ---------------- */
function Looks({ data, closetById, capsuleById, onChanged, flash }) {
  const [fCap, setFCap] = useState('All')
  const [fForm, setFForm] = useState('All')
  const [fRate, setFRate] = useState('All')
  const [open, setOpen] = useState(null)

  const looks = data.looks.filter((l) => {
    if (fCap !== 'All' && !l.capsuleIds.includes(fCap)) return false
    if (fForm !== 'All' && l.formality !== fForm) return false
    if (fRate !== 'All' && l.rating !== fRate) return false
    return true
  })

  async function act(look, action, extra) {
    try {
      await api('/api/look', { action, lookId: look.id, ...extra })
      if (action === 'rate') flash(extra.rating ? `Rated ${extra.rating}.` : 'Rating cleared.')
      if (action === 'delete') flash('Look archived.')
      if (action === 'duplicate') flash('Duplicated into capsule.')
      onChanged()
      if (action === 'delete') setOpen(null)
    } catch (e) { flash(e.message) }
  }

  return (
    <section>
      <SectionHead eyebrow="Every look, every capsule" title="The Looks" count={`${data.looks.length} looks`} />
      <Filters>
        <Select value={fCap} onChange={setFCap} label="Capsule" options={[['All', 'All capsules'], ...data.capsules.map((c) => [c.id, c.name])]} />
        <Select value={fForm} onChange={setFForm} label="Formality" options={[['All', 'All formality'], ...FORMALITIES.map((f) => [f, f])]} />
        <Select value={fRate} onChange={setFRate} label="Rating" options={[['All', 'All ratings'], ...RATINGS.map((x) => [x, x])]} />
      </Filters>
      {looks.length === 0 ? (
        <div className="state">No looks match that filter. Loosen it, or build one from a piece in the Closet.</div>
      ) : (
        <div className="grid">
          {looks.map((l) => (
            <article key={l.id} className="card look">
              <button className="card-open" onClick={() => setOpen(l)}>
                <Frame src={l.photo} alt={l.name} />
                <div className="card-meta">
                  <span className="card-title">{l.name}</span>
                  <span className="card-sub">{[l.capsuleIds.map((id) => capsuleById.get(id)?.name).filter(Boolean).join(', '), l.formality].filter(Boolean).join(' · ')}</span>
                </div>
              </button>
              <div className="rate-row">
                {RATINGS.map((rt) => (
                  <button key={rt} className={`pill ${l.rating === rt ? 'on' : ''}`} onClick={() => act(l, 'rate', { rating: l.rating === rt ? null : rt })}>{rt}</button>
                ))}
              </div>
            </article>
          ))}
        </div>
      )}
      {open && <LookPanel look={open} closetById={closetById} capsules={data.capsules} onClose={() => setOpen(null)} onAct={act} />}
    </section>
  )
}

function LookPanel({ look, closetById, capsules, onClose, onAct }) {
  const [dupTo, setDupTo] = useState('')
  const pieces = look.itemIds.map((id) => closetById.get(id)).filter(Boolean)
  return (
    <Panel onClose={onClose}>
      <Frame src={look.photo} alt={look.name} big />
      <h2 className="panel-title">{look.name}</h2>
      <p className="panel-sub">{[look.formality, look.occasion?.join(', ')].filter(Boolean).join(' · ')}</p>
      {look.notes && <p className="notes">{look.notes}</p>}

      <div className="rate-row wide">
        {RATINGS.map((rt) => (
          <button key={rt} className={`pill ${look.rating === rt ? 'on' : ''}`} onClick={() => onAct(look, 'rate', { rating: look.rating === rt ? null : rt })}>{rt}</button>
        ))}
      </div>

      <div className="pieces-head">The pieces</div>
      <div className="mini-grid">
        {pieces.map((p) => (
          <div key={p.id} className="mini">
            <Frame src={p.photo} alt={p.name} />
            <span className="mini-name">{p.name}</span>
          </div>
        ))}
      </div>

      <div className="build">
        <div className="build-head">Duplicate into another capsule</div>
        <label className="field">
          <span>to</span>
          <select value={dupTo} onChange={(e) => setDupTo(e.target.value)}>
            <option value="">Choose a capsule</option>
            {capsules.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <button className="btn" disabled={!dupTo} onClick={() => onAct(look, 'duplicate', { capsuleId: dupTo })}>Duplicate</button>
      </div>

      <button className="btn danger" onClick={() => { if (confirm('Archive this look? It moves to your Notion trash and can be restored there.')) onAct(look, 'delete') }}>Delete look</button>
      {look.notionUrl && <a className="notion-link" href={look.notionUrl} target="_blank" rel="noreferrer">Open in Notion ↗</a>}
    </Panel>
  )
}

/* ---------------- Capsules ---------------- */
function Capsules({ data, closetById, flash }) {
  const [open, setOpen] = useState(null)
  return (
    <section>
      <SectionHead eyebrow="Trips, seasons, purposes" title="The Capsules" count={`${data.capsules.length}`} />
      <div className="cap-list">
        {data.capsules.map((c) => (
          <button key={c.id} className="cap-row" onClick={() => setOpen(c)}>
            <div className="cap-row-main">
              <span className="cap-name">{c.name}</span>
              <span className="cap-sub">{[c.type, fmtDates(c.dates)].filter(Boolean).join(' · ')}</span>
            </div>
            <span className="cap-count">{c.looksCount ?? c.outfitIds.length} looks</span>
          </button>
        ))}
      </div>
      {open && <CapsuleDetail capsule={open} data={data} closetById={closetById} onClose={() => setOpen(null)} />}
    </section>
  )
}

function CapsuleDetail({ capsule, data, closetById, onClose }) {
  const looks = data.looks.filter((l) => l.capsuleIds.includes(capsule.id))
  const recs = data.recs.filter((rc) => rc.capsuleIds.includes(capsule.id))
  return (
    <Panel onClose={onClose} wide>
      <div className="cap-head">
        <span className="eyebrow">{[capsule.type, fmtDates(capsule.dates)].filter(Boolean).join(' · ')}</span>
        <h2 className="panel-title big">{capsule.name}</h2>
      </div>

      {capsule.brief?.length > 0 && (
        <div className="brief">
          {capsule.brief.map((b, i) => <BriefBlock key={i} b={b} />)}
        </div>
      )}

      <div className="pieces-head">The looks · {looks.length}</div>
      {looks.length === 0 ? <p className="muted">No looks in this capsule yet.</p> : (
        <div className="grid">
          {looks.map((l) => (
            <div key={l.id} className="card">
              <Frame src={l.photo} alt={l.name} />
              <div className="card-meta">
                <span className="card-title">{l.name}</span>
                <span className="card-sub">{[l.formality, l.rating].filter(Boolean).join(' · ')}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="pieces-head">Buy to fill gaps · {recs.length}</div>
      {recs.length === 0 ? <p className="muted">Nothing proposed yet for this capsule.</p> : (
        <div className="grid">
          {recs.map((rc) => <RecCard key={rc.id} rec={rc} />)}
        </div>
      )}

      {capsule.notionUrl && <a className="notion-link" href={capsule.notionUrl} target="_blank" rel="noreferrer">Open full brief in Notion ↗</a>}
    </Panel>
  )
}

function BriefBlock({ b }) {
  if (b.kind === 'heading') return <h3 className="brief-h">{b.text}</h3>
  if (b.kind === 'quote') return <blockquote className="brief-q">{b.text}</blockquote>
  if (b.kind === 'bullet') return <div className="brief-li">— {b.text}</div>
  if (b.kind === 'todo') return <div className="brief-li">{b.checked ? '✓' : '○'} {b.text}</div>
  return <p className="brief-p">{b.text}</p>
}

/* ---------------- Shop (Recommendations) ---------------- */
function Shop({ data, capsuleById }) {
  const recs = data.recs.filter((r) => r.status !== 'Dismissed')
  return (
    <section>
      <SectionHead eyebrow="Vetted buys to fill gaps" title="The Shop" count={`${recs.length}`} />
      {recs.length === 0 ? (
        <div className="state">No recommendations yet. They’ll appear here as they’re validated.</div>
      ) : (
        <div className="grid">
          {recs.map((rc) => <RecCard key={rc.id} rec={rc} capsuleName={rc.capsuleIds.map((id) => capsuleById.get(id)?.name).filter(Boolean).join(', ')} />)}
        </div>
      )}
    </section>
  )
}

function RecCard({ rec, capsuleName }) {
  return (
    <article className="card rec">
      <Frame src={rec.photo} alt={rec.name} />
      <div className="card-meta">
        <span className="card-title">{rec.name}</span>
        <span className="card-sub">{[rec.brand, rec.price != null ? `$${rec.price}` : null].filter(Boolean).join(' · ')}</span>
        {rec.status && <span className={`status ${rec.status?.toLowerCase()}`}>{rec.status}</span>}
        {rec.rationale && <span className="rec-why">{rec.rationale}</span>}
        {capsuleName && <span className="card-sub muted">{capsuleName}</span>}
        {rec.link && <a className="shop-link" href={rec.link} target="_blank" rel="noreferrer">View ↗</a>}
      </div>
    </article>
  )
}

/* ---------------- shared bits ---------------- */
function SectionHead({ eyebrow, title, count }) {
  return (
    <div className="sec-head">
      <span className="eyebrow">{eyebrow}</span>
      <h1 className="sec-title">{title}</h1>
      {count && <span className="sec-count">{count}</span>}
    </div>
  )
}
function Filters({ children }) { return <div className="filters">{children}</div> }
function Chip({ on, onClick, children }) { return <button className={`chip ${on ? 'on' : ''}`} onClick={onClick}>{children}</button> }
function Select({ value, onChange, label, options }) {
  return (
    <select className="sel" value={value} onChange={(e) => onChange(e.target.value)} aria-label={label}>
      {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </select>
  )
}
function Spec({ k, v }) { return (<><dt>{k}</dt><dd>{v}</dd></>) }
function Frame({ src, alt, big }) {
  return (
    <div className={`frame ${big ? 'big' : ''}`}>
      {src ? <img src={src} alt={alt} loading="lazy" /> : <div className="frame-empty">No photo</div>}
    </div>
  )
}
function Panel({ children, onClose, wide }) {
  return (
    <div className="overlay" onClick={onClose}>
      <div className={`panel ${wide ? 'wide' : ''}`} onClick={(e) => e.stopPropagation()}>
        <button className="panel-close" onClick={onClose} aria-label="Close">×</button>
        {children}
      </div>
    </div>
  )
}
function fmtDates(d) {
  if (!d?.start) return ''
  const opt = { month: 'short', day: 'numeric' }
  const s = new Date(d.start).toLocaleDateString('en-US', opt)
  if (!d.end) return s
  return `${s} – ${new Date(d.end).toLocaleDateString('en-US', opt)}`
}
