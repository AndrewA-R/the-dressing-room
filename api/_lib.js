// Shared Notion helpers. Files prefixed with "_" are not exposed as routes by Vercel.
// Notion REST API, version 2022-06-28 (stable, queries by database_id).

export const NOTION_VERSION = '2022-06-28'
export const NOTION = 'https://api.notion.com/v1'

export const DB = {
  closet: '17624a68-9429-4359-a39d-9e6fadd600ff',
  outfits: 'bd8d2b67-dba3-4149-ad8c-35b38b5c53a8',
  capsules: '92ce74f2-cb18-4116-bf8f-fd7cab490a98',
  recs: '2b7a811906554b578fdc6d87f00e871f',
}

function token() {
  const t = process.env.NOTION_TOKEN
  if (!t) throw new Error('NOTION_TOKEN is not set in the environment.')
  return t
}

async function notionFetch(path, options = {}) {
  const res = await fetch(`${NOTION}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token()}`,
      'Notion-Version': NOTION_VERSION,
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`Notion ${res.status} on ${path}: ${body.slice(0, 500)}`)
  }
  return res.json()
}

// Query an entire database, following pagination.
export async function queryAll(databaseId, body = {}) {
  const results = []
  let cursor = undefined
  do {
    const page = await notionFetch(`/databases/${databaseId}/query`, {
      method: 'POST',
      body: JSON.stringify({ ...body, start_cursor: cursor, page_size: 100 }),
    })
    results.push(...page.results)
    cursor = page.has_more ? page.next_cursor : undefined
  } while (cursor)
  return results
}

export async function getPage(pageId) {
  return notionFetch(`/pages/${pageId}`)
}

export async function updatePage(pageId, body) {
  return notionFetch(`/pages/${pageId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export async function createPage(body) {
  return notionFetch(`/pages`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

// Fetch a page's child blocks (used for the capsule brief body).
export async function getBlocks(pageId) {
  const out = []
  let cursor = undefined
  do {
    const page = await notionFetch(
      `/blocks/${pageId}/children?page_size=100${cursor ? `&start_cursor=${cursor}` : ''}`
    )
    out.push(...page.results)
    cursor = page.has_more ? page.next_cursor : undefined
  } while (cursor)
  return out
}

// ---- property readers (2022-06-28 shapes) ----
const richText = (p) => (p?.rich_text || []).map((t) => t.plain_text).join('') || ''
const title = (p) => (p?.title || []).map((t) => t.plain_text).join('') || ''
const select = (p) => p?.select?.name || null
const multi = (p) => (p?.multi_select || []).map((o) => o.name)
const number = (p) => (typeof p?.number === 'number' ? p.number : null)
const url = (p) => p?.url || null
const checkbox = (p) => !!p?.checkbox
const relIds = (p) => (p?.relation || []).map((r) => r.id)
const fileUrl = (p) => {
  const f = (p?.files || [])[0]
  if (!f) return null
  return f.type === 'external' ? f.external?.url : f.file?.url
}
const dateRange = (p) => (p?.date ? { start: p.date.start, end: p.date.end } : null)
const rollupNumber = (p) =>
  p?.rollup?.type === 'number' && typeof p.rollup.number === 'number' ? p.rollup.number : null

export const read = { richText, title, select, multi, number, url, checkbox, relIds, fileUrl, dateRange, rollupNumber }

// Render a flat brief from a capsule's blocks.
export function renderBrief(blocks) {
  const text = (b) => (b[b.type]?.rich_text || []).map((t) => t.plain_text).join('')
  const out = []
  for (const b of blocks) {
    switch (b.type) {
      case 'heading_1':
      case 'heading_2':
      case 'heading_3':
        out.push({ kind: 'heading', text: text(b) })
        break
      case 'paragraph': {
        const t = text(b)
        if (t.trim()) out.push({ kind: 'para', text: t })
        break
      }
      case 'quote':
        out.push({ kind: 'quote', text: text(b) })
        break
      case 'bulleted_list_item':
      case 'numbered_list_item':
        out.push({ kind: 'bullet', text: text(b) })
        break
      case 'to_do':
        out.push({ kind: 'todo', text: text(b), checked: !!b.to_do?.checked })
        break
      default:
        break
    }
  }
  return out
}

export function sendError(res, err) {
  // eslint-disable-next-line no-console
  console.error(err)
  res.status(500).json({ error: err.message || String(err) })
}
