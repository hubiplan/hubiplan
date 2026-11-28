import { useState } from 'react'
import { euro, financeApi } from '../../api/finance.ts'
import { todayIso } from '../../api/members.ts'
import { PERM } from '../../api/orgs.ts'
import { peeringApi } from '../../api/peering.ts'
import type { Coupling, CouplingInvoice } from '../../api/peering.ts'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import { Alert } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

export function InvoiceList({ coupling, onChange }: { coupling: Coupling; onChange: () => void }) {
  const [open, setOpen] = useState<number | null>(null)
  const incoming = coupling.direction === 'parent'
  return (
    <div>
      <h4>{incoming ? t('Eingangsrechnungen') : t('Rechnungen an diese Einheit')}</h4>
      <table className="table">
        <thead>
          <tr>
            <th>{t('Nummer')}</th>
            <th>{t('Betreff')}</th>
            <th>{t('fällig')}</th>
            <th className="num">{t('Betrag')}</th>
            <th>{t('Stand')}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {coupling.invoices.map((inv) => (
            <tr key={inv.id}>
              <td>{inv.number}</td>
              <td>{inv.subject}</td>
              <td>{inv.due_date ? formatDate(inv.due_date) : '–'}</td>
              <td className="num">{euro(inv.total)}</td>
              <td>
                <InvoiceState inv={inv} />
              </td>
              <td>
                {inv.download_url && (
                  <a href={inv.download_url} target="_blank" rel="noreferrer">
                    PDF
                  </a>
                )}
                {incoming && inv.status === 'open' && !inv.paid_reported_on && (
                  <>
                    {inv.download_url && ' · '}
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => setOpen(open === inv.id ? null : inv.id)}
                    >
                      {t('bezahlt melden')}
                    </button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {open !== null && (
        <ReportPaid
          coupling={coupling}
          inv={coupling.invoices.find((i) => i.id === open)!}
          onDone={() => {
            setOpen(null)
            onChange()
          }}
        />
      )}
    </div>
  )
}

function InvoiceState({ inv }: { inv: CouplingInvoice }) {
  if (inv.status === 'cancelled') return <>{t('storniert')}</>
  const parts: string[] = []
  if (inv.settled) parts.push('ausgeglichen')
  else if (inv.paid && Number(inv.paid) > 0) parts.push(t('{x} eingegangen', { x: euro(inv.paid) }))
  else parts.push('offen')
  if (inv.paid_reported_on)
    parts.push(t('als bezahlt gemeldet am {x}', { x: formatDate(inv.paid_reported_on) }))
  return <>{parts.join(' · ')}</>
}

function ReportPaid({
  coupling,
  inv,
  onDone,
}: {
  coupling: Coupling
  inv: CouplingInvoice
  onDone: () => void
}) {
  const org = useActiveOrg()
  const canBook = org.permissions.includes(PERM.financeEdit)
  const [date, setDate] = useState(todayIso)
  const [book, setBook] = useState(canBook)
  const [account, setAccount] = useState('')
  const [category, setCategory] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const { data: accounts } = useLoad(
    () => (canBook ? financeApi.accounts(org.id) : Promise.resolve([])),
    [org.id, canBook],
  )
  const { data: categories } = useLoad(
    () => (canBook ? financeApi.categories(org.id) : Promise.resolve([])),
    [org.id, canBook],
  )

  async function submit() {
    setErr(null)
    setBusy(true)
    try {
      await peeringApi.reportPaid(org.id, coupling.id, inv.id, {
        date,
        ...(book && account ? { account: Number(account), category: Number(category) } : {}),
      })
      onDone()
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card">
      <h4>
        {t('Rechnung {number} über {x} als bezahlt melden', {
          number: inv.number,
          x: euro(inv.total),
        })}
      </h4>
      {inv.bank.iban && (
        <p className="muted small">
          {t('Zahlung an {holder}, IBAN', { holder: inv.bank.holder })} {inv.bank.iban}
          {inv.bank.bank_name && ` (${inv.bank.bank_name})`}
          {t(', Verwendungszweck {number}.', { number: inv.number })}
        </p>
      )}
      <label className="field">
        <span>{t('bezahlt am')}</span>
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      </label>
      {canBook && (
        <>
          <label className="checkbox">
            <input type="checkbox" checked={book} onChange={(e) => setBook(e.target.checked)} />{' '}
            {t('Ausgabe in der eigenen Kasse buchen (mit der Rechnung als Beleg)')}
          </label>
          {book && (
            <>
              <label className="field">
                <span>{t('Konto')}</span>
                <select value={account} onChange={(e) => setAccount(e.target.value)}>
                  <option value="">{t('bitte wählen')}</option>
                  {(accounts ?? [])
                    .filter((a) => a.is_active)
                    .map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name}
                      </option>
                    ))}
                </select>
              </label>
              <label className="field">
                <span>{t('Kategorie')}</span>
                <select value={category} onChange={(e) => setCategory(e.target.value)}>
                  <option value="">{t('bitte wählen')}</option>
                  {(categories ?? [])
                    .filter((c) => c.is_active && c.kind !== 'income')
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                </select>
              </label>
            </>
          )}
        </>
      )}
      <p className="muted small">
        {t(
          'Die Meldung geht an {name}. Als ausgeglichen gilt die Rechnung erst, wenn das Geld dort eingegangen ist.',
          { name: coupling.remote.name },
        )}
      </p>
      {err && <Alert kind="error">{err}</Alert>}
      <div className="button-row">
        <button
          type="button"
          className="button button-primary"
          disabled={busy || (book && canBook && (!account || !category))}
          onClick={() => void submit()}
        >
          {t('Melden')}
        </button>
      </div>
    </div>
  )
}
