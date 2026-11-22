// Blättern zwischen Einträgen einer Liste direkt in der Akte (Web-Oberfläche W12): die Liste
// merkt sich die Reihenfolge ihrer angezeigten Seite, die Akte zeigt „‹ Vorheriges · 2 von 50 ·
// Nächstes ›“. Nur für diese Sitzung im Browser.
import { Link } from 'react-router-dom'
import { t } from '../../i18n/index.ts'
import { order } from './recordOrder.ts'

export function RecordPager({
  list,
  current,
  path,
  label,
}: {
  list: string
  current: number
  /** Adresse eines Eintrags, z. B. (id) => `/mitglieder/${id}` */
  path: (id: number) => string
  /** z. B. „Mitglied“ für die Beschriftung der Pfeile */
  label: { prev: string; next: string }
}) {
  const ids = order(list)
  const i = ids.indexOf(current)
  if (i < 0 || ids.length < 2) return null
  const prev = ids[i - 1]
  const next = ids[i + 1]
  return (
    <nav className="record-pager" aria-label={t('Blättern')}>
      {prev !== undefined ? (
        <Link to={path(prev)} rel="prev">
          <span aria-hidden="true">‹ </span>
          {label.prev}
        </Link>
      ) : (
        <span className="muted" aria-hidden="true">
          ‹ {label.prev}
        </span>
      )}
      <span className="muted small">{t('{n} von {total}', { n: i + 1, total: ids.length })}</span>
      {next !== undefined ? (
        <Link to={path(next)} rel="next">
          {label.next}
          <span aria-hidden="true"> ›</span>
        </Link>
      ) : (
        <span className="muted" aria-hidden="true">
          {label.next} ›
        </span>
      )}
    </nav>
  )
}
