// Stand der Zahlung einer Anmeldung als Marke (Verwaltung, Einlass).
import type { PaidState } from '../../api/registrations.ts'
import { t } from '../../i18n/index.ts'

const PAID: Record<PaidState, () => string> = {
  free: () => t('kostenlos'),
  open: () => t('offen'),
  partly: () => t('teilweise bezahlt'),
  paid: () => t('bezahlt'),
  cancelled: () => t('abgemeldet'),
  waiting: () => t('Warteliste'),
}

export function PaidBadge({ state }: { state: PaidState }) {
  const cls = state === 'paid' ? 'badge badge-yes' : state === 'open' ? 'badge badge-open' : 'badge'
  return <span className={cls}>{PAID[state]()}</span>
}
