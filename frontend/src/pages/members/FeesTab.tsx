// Mitgliederakte › Beiträge: Rechnungen, offene Beträge, Mandat und Rechnungsanschrift an
// einer Stelle (Menüprüfung 2, N-08).
import { Link } from 'react-router-dom'
import { billingApi, sepaApi } from '../../api/billing.ts'
import { euro } from '../../api/finance.ts'
import type { MemberDetail } from '../../api/members.ts'
import { PERM } from '../../api/orgs.ts'
import type { OrgSummary } from '../../api/orgs.ts'
import { formatDate, useLoad } from '../../components/forms.ts'
import { LoadError } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { BillingAddressSection } from './BillingAddressSection.tsx'

export function FeesTab({
  org,
  member,
  canEdit,
  onSaved,
}: {
  org: OrgSummary
  member: MemberDetail
  canEdit: boolean
  onSaved: (m: MemberDetail) => void
}) {
  const view = org.permissions.includes(PERM.billingView)
  return (
    <div className="stack">
      {view && <MemberInvoices orgId={org.id} memberId={member.id} />}
      {view && org.sepa_enabled && <MemberMandates orgId={org.id} memberId={member.id} />}
      <BillingAddressSection
        key={`rechnung-${member.id}`}
        orgId={org.id}
        member={member}
        canEdit={canEdit && !member.managed_by}
        onSaved={onSaved}
      />
    </div>
  )
}

function MemberInvoices({ orgId, memberId }: { orgId: number; memberId: number }) {
  const { data, error, reload } = useLoad(
    () => billingApi.invoices(orgId, { mitglied: memberId }),
    [orgId, memberId],
  )
  if (error) return <LoadError message={error} onRetry={() => void reload()} />
  const rows = data?.results ?? []
  const open = rows.reduce((sum, r) => sum + Number(r.outstanding || 0), 0)
  return (
    <section className="card stack">
      <h2>{t('Rechnungen')}</h2>
      {!data ? (
        <p className="muted">{t('Lädt …')}</p>
      ) : rows.length === 0 ? (
        <p className="muted">{t('Für dieses Mitglied gibt es keine Rechnungen.')}</p>
      ) : (
        <>
          <p>
            {open > 0 ? t('Offen: {amount}', { amount: euro(open) }) : t('Keine offenen Beträge.')}
          </p>
          <table className="table">
            <thead>
              <tr>
                <th>{t('Nummer')}</th>
                <th>{t('Datum')}</th>
                <th>{t('Betreff')}</th>
                <th className="num">{t('Betrag')}</th>
                <th className="num">{t('Offen')}</th>
                <th>{t('Stand')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link to={`/finanzen/rechnungen?rechnung=${r.id}`}>{r.number || '–'}</Link>
                  </td>
                  <td>{formatDate(r.date)}</td>
                  <td>{r.subject}</td>
                  <td className="num">{euro(r.total)}</td>
                  <td className="num">{euro(r.outstanding)}</td>
                  <td>
                    {r.status_label}
                    {r.overdue && ` · ${t('überfällig')}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.count > rows.length && (
            <p className="muted small">
              {t('Die neuesten {shown} von {count} Rechnungen.', {
                shown: rows.length,
                count: data.count,
              })}
            </p>
          )}
        </>
      )}
    </section>
  )
}

function MemberMandates({ orgId, memberId }: { orgId: number; memberId: number }) {
  const { data, error } = useLoad(
    () => sepaApi.mandates(orgId, { mitglied: memberId }),
    [orgId, memberId],
  )
  if (error) return null
  const rows = data?.results ?? []
  return (
    <section className="card stack">
      <h2>{t('SEPA-Mandate')}</h2>
      {data && rows.length === 0 && <p className="muted">{t('Kein SEPA-Mandat hinterlegt.')}</p>}
      {rows.map((m) => (
        <p key={m.id}>
          <strong>{m.reference}</strong> · {m.iban_masked} · {m.status_label}
          {m.expired && ` · ${t('abgelaufen')}`}
          <br />
          <span className="muted small">
            {t('unterschrieben am {date}', { date: formatDate(m.signed_on) })}
          </span>
        </p>
      ))}
      <p>
        <Link to="/finanzen/lastschrift/mandate">{t('Zu den SEPA-Mandaten')}</Link>
      </p>
    </section>
  )
}
