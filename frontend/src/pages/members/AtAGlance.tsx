import { Link } from 'react-router-dom'
import type { MemberDetail } from '../../api/members.ts'
import { materialApi } from '../../api/materials.ts'
import type { OrgSummary } from '../../api/orgs.ts'
import { formatDateTime, formatMemberDate, jubileeWhen, useLoad } from '../../components/forms.ts'
import { formatEuro } from '../../i18n/format.ts'
import { t, tn } from '../../i18n/index.ts'

/**
 * „Auf einen Blick“ (Konzept S-03, A3): bis zu vier Kacheln, nur mit Inhalt und nur, wenn
 * der Zielreiter sichtbar ist. Rechnungen und Konto prüft der Server (``summary``).
 */
export function AtAGlance({
  org,
  member,
  tabs,
}: {
  org: OrgSummary
  member: MemberDetail
  /** sichtbare Reiter der Akte */
  tabs: string[]
}) {
  const invoices = tabs.includes('beitraege') ? member.summary?.invoices : null
  const account = tabs.includes('rollen') ? member.summary?.account : null
  const club = member.duration.club
  const first = member.periods.length
    ? member.periods.map((p) => p.entry_date).sort()[0]
    : undefined
  return (
    <section className="tiles tiles-figures member-glance" aria-labelledby="blick-titel">
      <h2 id="blick-titel" className="sr-only">
        {t('Auf einen Blick')}
      </h2>
      {first && (
        <Link className="card tile tile-link" to="?bereich=mitgliedschaft">
          <h3>{t('Mitglied seit')}</h3>
          <p className="amount-big">{formatMemberDate(first, org.date_precision)}</p>
          <p className="small muted">
            {tn('{n} Jahr', '{n} Jahre', club.years)}
            {club.next &&
              t(' · nächstes Jubiläum: {years} Jahre {x}', {
                years: club.next.years,
                x: jubileeWhen(club.next.date, club.precision),
              })}
          </p>
        </Link>
      )}
      {invoices && (
        <Link
          className={`card tile tile-link${invoices.overdue > 0 ? ' tile-alert' : ''}`}
          to="?bereich=beitraege"
        >
          <h3>{t('Beiträge')}</h3>
          <p className={`amount-big${invoices.overdue > 0 ? ' amount-out' : ''}`}>
            {formatEuro(Number(invoices.open_amount))}
          </p>
          <p className="small muted">
            {invoices.open === 0
              ? t('Keine offenen Rechnungen')
              : invoices.open === 1
                ? t('1 Rechnung offen')
                : t('{n} Rechnungen offen', { n: invoices.open })}
            {invoices.overdue > 0 && t(' · davon {n} überfällig', { n: invoices.overdue })}
          </p>
        </Link>
      )}
      {account && (
        <Link className="card tile tile-link" to="?bereich=rollen">
          <h3>{t('Konto')}</h3>
          {account.has_access ? (
            <>
              <p>
                {[
                  t('Mitgliederbereich'),
                  account.app && t('App verbunden'),
                  account.mfa && t('Zwei-Faktor an'),
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </p>
              <p className="small muted">
                {account.last_login
                  ? t('Zuletzt angemeldet: {x}', { x: formatDateTime(account.last_login) })
                  : t('Noch nie angemeldet')}
              </p>
            </>
          ) : (
            <p className="small muted">{t('Kein Zugang zum Mitgliederbereich')}</p>
          )}
        </Link>
      )}
      {tabs.includes('mitgliedschaft') && <MaterialTile org={org} memberId={member.id} />}
    </section>
  )
}

/** Zahl der ausgegebenen Teile; dieselbe Abfrage und Rechteprüfung wie der Abschnitt. */
function MaterialTile({ org, memberId }: { org: OrgSummary; memberId: number }) {
  const enabled = org.modules.includes('material') && org.permissions.includes('material.view')
  const { data } = useLoad(
    () =>
      enabled
        ? materialApi.list(`/api/orgs/${org.id}/materials/`, `member=${memberId}`)
        : Promise.resolve(null),
    [org.id, memberId, enabled],
  )
  const count = data?.items.length ?? 0
  if (!count) return null
  return (
    <Link className="card tile tile-link" to="?bereich=mitgliedschaft">
      <h3>{t('Material')}</h3>
      <p className="amount-big">{count}</p>
      <p className="small muted">{count === 1 ? t('Teil ausgegeben') : t('Teile ausgegeben')}</p>
    </Link>
  )
}
