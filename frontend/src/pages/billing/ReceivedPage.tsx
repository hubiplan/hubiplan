// Verein: Rechnungen des Dachverbands an den Verein.
import { useRowSort } from '../../components/RowSort.tsx'
import { useRowSearch } from '../../components/RowSearch.tsx'
import { billingApi } from '../../api/billing.ts'
import { euro } from '../../api/finance.ts'
import { formatDate, useLoad } from '../../components/forms.ts'
import { Alert, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { useTerms } from '../../org/terms.ts'
import { StatusBadge } from './InvoicesPage.tsx'
import { t } from '../../i18n/index.ts'

export function ReceivedPage() {
  const org = useActiveOrg()
  const terms = useTerms()
  const { data, error } = useLoad(() => billingApi.received(org.id), [org.id])
  const search = useRowSearch(
    data?.invoices ?? [],
    (inv) => `${inv.number} ${inv.subject}`,
    t('Rechnungen'),
  )
  const sorting = useRowSort(search.shown, {
    number: (inv) => inv.number,
    subject: (inv) => inv.subject,
    due: (inv) => inv.due_date,
    status: (inv) => inv.status,
    total: (inv) => Number(inv.total),
    open: (inv) => Number(inv.outstanding),
  })
  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading />
  if (!data.federation)
    return (
      <div className="card empty-state">
        <p>
          {terms.e_Nom} {t('gehört zu keiner übergeordneten Einheit.')}
        </p>
      </div>
    )
  return (
    <div className="card card-wide">
      <h2>
        {t('Rechnungen von')} {data.federation}
      </h2>
      {data.invoices.length === 0 ? (
        <p className="muted">{t('Noch keine Rechnungen.')}</p>
      ) : (
        <div className="table-scroll">
          {search.field}
          <table className="table">
            <thead>
              <tr>
                {sorting.head('number', t('Nummer'))}
                {sorting.head('subject', t('Betreff'))}
                {sorting.head('due', t('fällig'))}
                {sorting.head('status', t('Status'))}
                {sorting.head('total', t('Betrag'), { className: 'num' })}
                {sorting.head('open', t('offen'), { className: 'num' })}
                <th />
              </tr>
            </thead>
            <tbody>
              {sorting.rows.map((inv) => (
                <tr key={inv.id}>
                  <td>{inv.number}</td>
                  <td>
                    {inv.subject}
                    <div className="muted small">
                      {inv.lines
                        .map((l) => t('{text} {detail}', { text: l.text, detail: l.detail }).trim())
                        .join(' · ')}
                      {inv.dunnings.length > 0 &&
                        t(' · {name} vom {x}', {
                          name: inv.dunnings[inv.dunnings.length - 1].name,
                          x: formatDate(inv.dunnings[inv.dunnings.length - 1].date),
                        })}
                    </div>
                  </td>
                  <td>{formatDate(inv.due_date)}</td>
                  <td>
                    <StatusBadge row={inv} />
                  </td>
                  <td className="num">{euro(inv.total)}</td>
                  <td className="num">{Number(inv.outstanding) ? euro(inv.outstanding) : '–'}</td>
                  <td className="actions">
                    <a
                      className="link-button"
                      href={billingApi.receivedPdfUrl(org.id, inv.id)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      PDF
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="muted small">
        {t('Die Zahlung an {dv_akk} buchst du wie jede Ausgabe in der Kasse.', {
          dv_akk: terms.dv_akk,
        })}
      </p>
    </div>
  )
}
