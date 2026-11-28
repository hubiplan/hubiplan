import type { Price } from '../../api/registrations.ts'
import { euro } from '../../api/finance.ts'
import { formatDay } from './time.ts'
import { t } from '../../i18n/index.ts'
import { priceName } from './registrationHelpers.ts'

/** „29,00 € (Early Bird bis 31.03.2027, noch 5 Plätze) · danach 35,00 €“ */
function priceText(p: Price): string {
  if (!p.current) return t('nicht mehr buchbar')
  const extra: string[] = []
  if (p.current.name) extra.push(p.current.name)
  if (p.current.until_date)
    extra.push(t('bis {date}', { date: formatDay(p.current.until_date, false) }))
  if (p.current.remaining !== null)
    extra.push(t('noch {n} zu diesem Preis', { n: p.current.remaining }))
  let text = euro(p.current.amount)
  if (extra.length) text += ` (${extra.join(', ')})`
  if (p.next) text += t(' · danach {amount}', { amount: euro(p.next.amount) })
  return text
}

function conditions(p: Price): string {
  const parts: string[] = []
  if (p.applies === 'members') parts.push(t('nur Mitglieder'))
  if (p.applies === 'guests') parts.push(t('nur Gäste'))
  if (p.age_from !== null && p.age_to !== null)
    parts.push(t('{a} bis {b} Jahre', { a: p.age_from, b: p.age_to }))
  else if (p.age_from !== null) parts.push(t('ab {a} Jahren', { a: p.age_from }))
  else if (p.age_to !== null) parts.push(t('bis {b} Jahre', { b: p.age_to }))
  return parts.join(', ')
}

export function PriceList({ prices }: { prices: Price[] }) {
  return (
    <ul className="plain-list">
      {prices.map((p) => (
        <li key={p.id}>
          <strong>{priceName(p)}</strong>
          {conditions(p) && <span className="muted small"> ({conditions(p)})</span>}: {priceText(p)}
          {p.free !== null && (
            <span className="muted small"> · {t('{n} Plätze frei', { n: p.free })}</span>
          )}
        </li>
      ))}
    </ul>
  )
}
