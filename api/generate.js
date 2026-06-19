import { DB, queryAll, createPage, read, sendError } from './_lib.js'

const r = read

const HOUSE_STYLE = `You are Andrew's in-house stylist. His taste:
- George Clooney sprezzatura: cloth and texture over color; soft, unstructured tailoring; slim-to-tailored fits only.
- Palette: cream (not white), marigold, tan, olive, tobacco, ecru, navy. Marigold is the single warm pop — one pop per look, never two.
- Real natural fibers. In heat, linen and cotton.
- Hard avoids: streetwear, preppy/catalog looks, conspicuous logos, hype pieces, wide silhouettes.
- He is breaking a white-sneaker rut — prefer loafers, Sabahs, suede, or leather sandals over white sneakers.
A good look is 3 to 6 pieces: a top, a bottom, footwear, and optional layer/accessory, coherent in palette and formality.`

const FORMALITY = ['Beach', 'Casual', 'Smart', 'Dressy']

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    res.status(405).json({ error: 'Use POST.' })
    return
  }
  try {
    const key = process.env.ANTHROPIC_API_KEY
    if (!key) throw new Error('ANTHROPIC_API_KEY is not set — add it in Vercel and redeploy.')

    const { pieceId, occasion, capsuleId } = req.body || {}
    if (!pieceId) throw new Error('pieceId is required.')
    if (!occasion) throw new Error('occasion is required.')

    // Build the inventory Claude chooses from (wearable, in-rotation pieces).
    const closet = await queryAll(DB.closet)
    const inventory = closet
      .map((p) => {
        const x = p.properties
        const status = r.select(x['Status'])
        if (status === 'Sold/Gone' || status === 'Archived' || status === 'Donating') return null
        return {
          id: p.id,
          name: r.title(x['Item']),
          category: r.select(x['Category']),
          colors: r.multi(x['Color']),
          formality: r.select(x['Formality']),
        }
      })
      .filter(Boolean)

    const piece = inventory.find((i) => i.id === pieceId) || { id: pieceId, name: 'the selected piece' }

    const prompt = `${HOUSE_STYLE}

Here is Andrew's available wardrobe as JSON (id, name, category, colors, formality):
${JSON.stringify(inventory)}

Build one cohesive look that is anchored on this piece:
${JSON.stringify(piece)}

The occasion is: "${occasion}".

Choose 3 to 6 items from the wardrobe by id (you MUST include the anchor piece's id). Respond with ONLY a JSON object, no prose, no markdown fences:
{"look_name": "<short evocative name, 2-5 words>", "item_ids": ["<id>", ...], "formality": "<one of ${FORMALITY.join('/')}>", "rationale": "<one sentence>"}`

    const aiRes = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'x-api-key': key,
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-6',
        max_tokens: 1024,
        system: 'You return only valid JSON. No commentary, no code fences.',
        messages: [{ role: 'user', content: prompt }],
      }),
    })
    if (!aiRes.ok) {
      const t = await aiRes.text()
      throw new Error(`Anthropic ${aiRes.status}: ${t.slice(0, 400)}`)
    }
    const aiData = await aiRes.json()
    const text = (aiData.content || [])
      .filter((b) => b.type === 'text')
      .map((b) => b.text)
      .join('')
      .trim()

    let parsed
    try {
      parsed = JSON.parse(text.replace(/^```json\s*|\s*```$/g, '').trim())
    } catch (e) {
      throw new Error(`Could not parse the stylist response: ${text.slice(0, 300)}`)
    }

    const validIds = new Set(inventory.map((i) => i.id))
    let itemIds = (parsed.item_ids || []).filter((id) => validIds.has(id))
    if (!itemIds.includes(pieceId)) itemIds = [pieceId, ...itemIds]
    const formality = FORMALITY.includes(parsed.formality) ? parsed.formality : null

    const props = {
      Look: { title: [{ text: { content: parsed.look_name || 'New look' } }] },
      Items: { relation: itemIds.map((id) => ({ id })) },
      Occasion: { multi_select: [{ name: occasion }] },
      Status: { select: { name: 'Idea' } },
    }
    if (formality) props.Formality = { select: { name: formality } }
    if (capsuleId) props.Capsule = { relation: [{ id: capsuleId }] }
    if (parsed.rationale) props.Notes = { rich_text: [{ text: { content: String(parsed.rationale) } }] }

    const created = await createPage({ parent: { database_id: DB.outfits }, properties: props })

    res.status(200).json({
      ok: true,
      id: created.id,
      name: parsed.look_name,
      itemIds,
      formality,
      rationale: parsed.rationale || '',
    })
  } catch (err) {
    sendError(res, err)
  }
}
