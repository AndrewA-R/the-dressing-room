import { DB, getPage, updatePage, createPage, read, sendError } from './_lib.js'

const r = read

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    res.status(405).json({ error: 'Use POST.' })
    return
  }
  try {
    const { action, lookId } = req.body || {}
    if (!lookId) throw new Error('lookId is required.')

    if (action === 'rate') {
      // rating: "Top" | "Solid" | "Maybe" | null (to clear)
      const { rating } = req.body
      await updatePage(lookId, {
        properties: { Rating: { select: rating ? { name: rating } : null } },
      })
      res.status(200).json({ ok: true })
      return
    }

    if (action === 'delete') {
      // Soft delete: archive to Notion trash (recoverable), never a hard delete.
      await updatePage(lookId, { archived: true })
      res.status(200).json({ ok: true })
      return
    }

    if (action === 'duplicate') {
      // Copy the look into another capsule. Pieces, formality, and occasion carry over;
      // the photo does not (Notion-hosted files can't be re-referenced via the API).
      const { capsuleId } = req.body
      if (!capsuleId) throw new Error('capsuleId is required to duplicate.')
      const src = await getPage(lookId)
      const x = src.properties
      const props = {
        Look: { title: [{ text: { content: `${r.title(x['Look']) || 'Look'} (copy)` } }] },
        Items: { relation: r.relIds(x['Items']).map((id) => ({ id })) },
        Capsule: { relation: [{ id: capsuleId }] },
        Status: { select: { name: 'Idea' } },
      }
      const formality = r.select(x['Formality'])
      if (formality) props.Formality = { select: { name: formality } }
      const occasion = r.multi(x['Occasion'])
      if (occasion.length) props.Occasion = { multi_select: occasion.map((name) => ({ name })) }

      const created = await createPage({ parent: { database_id: DB.outfits }, properties: props })
      res.status(200).json({ ok: true, id: created.id })
      return
    }

    throw new Error(`Unknown action: ${action}`)
  } catch (err) {
    sendError(res, err)
  }
}
