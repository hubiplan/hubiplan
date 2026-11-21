// Texte zu Sammelbestellungen: Stand, Preis und Grenzen eines Artikels.
import { amount } from '../../api/orders.ts'
import type { CampaignState, OrderArticle } from '../../api/orders.ts'
import { t } from '../../i18n/index.ts'
import { formatEuro } from '../../i18n/format.ts'

export function stateLabel(state: CampaignState) {
  if (state === 'open') return t('läuft')
  if (state === 'closed') return t('beendet')
  return t('Entwurf')
}

/** Preis eines Artikels als Text („25,00 €“), leer ohne Preis */
export function priceText(article: OrderArticle) {
  const n = amount(article.price)
  return n === null ? '' : formatEuro(n)
}

/** Grenzen eines Artikels in einem Satz */
export function limitText(article: OrderArticle) {
  const parts: string[] = []
  if (article.max_per_member)
    parts.push(t('höchstens {n} je Mitglied', { n: article.max_per_member }))
  if (article.max_total) {
    parts.push(
      article.left !== undefined
        ? t('noch {n} von {m} verfügbar', { n: article.left, m: article.max_total })
        : t('insgesamt {n}', { n: article.max_total }),
    )
  }
  return parts.join(' · ')
}
