import { DB, queryAll, getBlocks, renderBrief, read, sendError } from './_lib.js'

const r = read

export default async function handler(req, res) {
  try {
    const [closetRaw, looksRaw, capsulesRaw, recsRaw] = await Promise.all([
      queryAll(DB.closet),
      queryAll(DB.outfits),
      queryAll(DB.capsules),
      queryAll(DB.recs),
    ])

    const closet = closetRaw.map((p) => {
      const x = p.properties
      return {
        id: p.id,
        name: r.title(x['Item']),
        brand: r.richText(x['Brand']),
        product: r.richText(x['Product']),
        category: r.select(x['Category']),
        colors: r.multi(x['Color']),
        fit: r.select(x['Fit']),
        formality: r.select(x['Formality']),
        material: r.richText(x['Material']),
        season: r.multi(x['Season']),
        status: r.select(x['Status']),
        vibe: r.multi(x['Vibe']),
        photo: r.fileUrl(x['Photo']),
        notionUrl: p.url,
      }
    })

    const looks = looksRaw.map((p) => {
      const x = p.properties
      return {
        id: p.id,
        name: r.title(x['Look']),
        capsuleIds: r.relIds(x['Capsule']),
        itemIds: r.relIds(x['Items']),
        formality: r.select(x['Formality']),
        occasion: r.multi(x['Occasion']),
        rating: r.select(x['Rating']),
        status: r.select(x['Status']),
        notes: r.richText(x['Notes']),
        photo: r.fileUrl(x['Photo']),
        notionUrl: p.url,
      }
    })

    const recs = recsRaw.map((p) => {
      const x = p.properties
      return {
        id: p.id,
        name: r.title(x['Item']),
        brand: r.richText(x['Brand']),
        category: r.select(x['Category']),
        link: r.url(x['Link']),
        price: r.number(x['Price']),
        priority: r.select(x['Priority']),
        status: r.select(x['Status']),
        photo: r.fileUrl(x['Photo']),
        rationale: r.richText(x['Rationale']),
        fillsGap: r.richText(x['Fills gap']),
        validated: r.checkbox(x['Validated']),
        capsuleIds: r.relIds(x['Capsule']),
        notionUrl: p.url,
      }
    })

    // Capsules + their brief bodies (low volume, so fetch blocks per capsule).
    const capsules = await Promise.all(
      capsulesRaw.map(async (p) => {
        const x = p.properties
        let brief = []
        try {
          brief = renderBrief(await getBlocks(p.id))
        } catch (e) {
          brief = []
        }
        return {
          id: p.id,
          name: r.title(x['Capsule']),
          type: r.select(x['Type']),
          dates: r.dateRange(x['Dates']),
          notes: r.richText(x['Notes']),
          looksCount: r.rollupNumber(x['Looks']),
          outfitIds: r.relIds(x['Outfits']),
          recIds: r.relIds(x['Recommendations']),
          brief,
          notionUrl: p.url,
        }
      })
    )

    res.setHeader('Cache-Control', 'no-store')
    res.status(200).json({ closet, looks, capsules, recs })
  } catch (err) {
    sendError(res, err)
  }
}
