import { Link } from 'react-router-dom'
import { bookingApi } from '../../api/bookings.ts'
import type { OrgSummary } from '../../api/orgs.ts'
import { useLoad } from '../../components/forms.ts'
import { t } from '../../i18n/index.ts'
import { span, statusLabel } from './format.ts'

/** Belegungen, die für dieses Mitglied gebucht sind (Mitgliedsakte, Reiter Mitgliedschaft). */
export function MemberBookings({ org, memberId }: { org: OrgSummary; memberId: number }) {
  const enabled =
    org.modules.includes('bookings') &&
    (org.modules.includes('material') || org.modules.includes('infrastructure')) &&
    ['bookings.edit', 'material.edit', 'infrastructure.edit'].some((p) =>
      org.permissions.includes(p),
    )
  const base = `/api/orgs/${org.id}/bookings/`
  const { data } = useLoad(
    () => (enabled ? bookingApi.forMember(base, memberId) : Promise.resolve(null)),
    [base, memberId, enabled],
  )
  if (!data?.bookings.length) return null
  return (
    <section className="card card-wide">
      <h2>{t('Belegungen')}</h2>
      <ul className="plain-list">
        {data.bookings.map((b) => (
          <li key={b.id}>
            <strong>{b.item_title}</strong> · {b.title}
            <br />
            <span className="small muted">
              {span(b)} · {statusLabel(b.status)}
              {b.repeat !== 'none' ? ` · ${t('Serie')}` : ''}
            </span>
          </li>
        ))}
      </ul>
      <Link to="/belegung">{t('Belegung öffnen')}</Link>
    </section>
  )
}
