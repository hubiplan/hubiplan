import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client.ts'
import { einvoiceApi } from '../../api/einvoices.ts'
import type { CommercialInput, CommercialInvoice } from '../../api/einvoices.ts'
import { euro } from '../../api/finance.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { useDraftGuard, confirmLeave } from '../../components/leaveGuard.ts'
import { Alert } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { MusicHeader, MusicEmptyState } from './MusicLayout.tsx'
import { CommercialForm } from '../billing/EInvoicesPage.tsx'
import { FeeBatchPanel } from './FeeBatchPanel.tsx'

type Claim = {
  id: number
  assignment: number
  fee: string
  allowance: string
  expenses: string
  attended: boolean
  note: string
  total: string
  status: string
  paid: boolean
  paid_amount?: string
  outstanding?: string
}
type Settlement = {
  fee?: string
  travel?: string
  extras?: string
  note?: string
  agreed?: string
  invoice?: number
  invoice_status?: string
  previous_invoices?: number[]
  invoiced?: string
  revenue?: string
  remuneration?: string
  expenses?: string
  result?: string
  claims: Claim[]
  payments: {
    id: number
    claim: number | null
    booking: number
    number: string
    amount: string
    cancelled: boolean
  }[]
}
type Assignment = { id: number; name: string }

export function SettlementPanel({
  performance,
  title,
  customer,
  assignments,
}: {
  performance: number
  title: string
  customer: number | null
  assignments: Assignment[]
}) {
  const org = useActiveOrg()
  const url = `/api/orgs/${org.id}/music/performances/${performance}/settlement/`
  const load = useLoad(() => api.get<Settlement>(url), [org.id, performance])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [seed, setSeed] = useState<Partial<CommercialInput> | null>(null)
  const [edit, setEdit] = useState<Claim | null>(null)
  const canEdit = org.permissions.includes('finance.edit')
  async function act(data: Record<string, unknown>) {
    setError('')
    setBusy(true)
    try {
      await api.post(url, data)
      await load.reload()
    } catch (err) {
      setError(errorMessage(err))
      throw err
    } finally {
      setBusy(false)
    }
  }
  if (load.error) return <Alert kind="error">{load.error}</Alert>
  const d = load.data
  if (!d) return <p>{t('Lädt …')}</p>
  const invoiceStatuses: Record<string, string> = {
    draft: t('Entwurf'),
    open: t('Offen'),
    paid: t('Bezahlt'),
    cancelled: t('Storniert'),
  }
  return (
    <section className="stack music-page">
      <MusicHeader title={t('Auftrittsabrechnung')} context={title} />
      <Link to={`/musik?vereinbarung=${performance}`}>{t('Angebote und Zusagen')}</Link>
      {error && <Alert kind="error">{error}</Alert>}
      <p>
        {t(
          'Alle Vereinbarungen und Vergütungen sind Bruttobeträge in EUR. Zuordnungen dokumentieren erfolgte Zahlungen und lösen keine Überweisung aus.',
        )}
      </p>
      <dl className="card music-summary">
        {[
          [t('Vereinbart'), d.agreed],
          [t('In Rechnung gestellt'), d.invoiced],
          [t('Tatsächliche Einnahmen'), d.revenue],
          [t('Freigegebene Vergütungen'), d.remuneration],
          [t('Tatsächliche Ausgaben'), d.expenses],
          [t('Ergebnis aus Zahlungen'), d.result],
        ].map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{euro(value || '0')}</dd>
          </div>
        ))}
      </dl>
      {canEdit && (!d.invoice || d.invoice_status === 'draft') && (
        <Amounts
          key={`agreement-${d.agreed}`}
          labels={{ fee: t('Honorar'), travel: t('Fahrtkosten'), extras: t('Weitere Leistungen') }}
          initial={{
            fee: d.fee || '0',
            travel: d.travel || '0',
            extras: d.extras || '0',
            note: d.note || '',
          }}
          onSave={async (values) => {
            await act({ action: 'agreement', ...values })
          }}
        />
      )}
      {d.invoice ? (
        <p>
          <Link to={`/finanzen/rechnungen/leistungen?rechnung=${d.invoice}`}>
            {t('Veranstalterrechnung öffnen')}
          </Link>{' '}
          · {invoiceStatuses[d.invoice_status || ''] || '—'}
        </p>
      ) : (
        canEdit &&
        org.modules.includes('billing') &&
        org.permissions.includes('billing.edit') && (
          <button
            className="button button-primary"
            disabled={busy || !customer || !d.agreed || d.agreed === '0.00'}
            onClick={async () => {
              try {
                const partners = await einvoiceApi.partners(org.id)
                const buyer = partners.find((p) => p.id === customer)?.details
                if (!buyer) throw new Error(t('Bitte einen aktiven Auftraggeber wählen.'))
                setSeed({ subject: title, partner: customer!, buyer })
              } catch (err) {
                setError(errorMessage(err))
              }
            }}
          >
            {t('Veranstalterrechnung erstellen')}
          </button>
        )
      )}
      {seed && (
        <CommercialForm
          seed={seed}
          onClose={() => setSeed(null)}
          onSaved={() => {
            setSeed(null)
            void load.reload()
          }}
          saveDraft={(value, key) =>
            api.post<CommercialInvoice>(
              `/api/orgs/${org.id}/music/performances/${performance}/invoice/`,
              value,
              key,
            )
          }
        />
      )}
      {canEdit && d.invoice_status === 'cancelled' && org.permissions.includes('billing.edit') && (
        <button
          className="button button-ghost"
          disabled={busy}
          onClick={() => void act({ action: 'replace_invoice' }).catch(() => {})}
        >
          {t('Stornierte Rechnung ersetzen')}
        </button>
      )}
      {d.previous_invoices?.map((id) => (
        <Link key={id} to={`/finanzen/rechnungen/leistungen?rechnung=${id}`}>
          {t('Frühere Veranstalterrechnung')} {id}
        </Link>
      ))}
      <h2>{t('Musikervergütungen')}</h2>
      <Link to="/musik?auszahlungen=1">{t('Sammelauszahlungen')}</Link>
      {canEdit && (
        <FeeBatchPanel
          url={url}
          assignments={assignments.filter((a) => !d.claims.some((c) => c.assignment === a.id))}
          onSaved={load.reload}
        />
      )}
      {canEdit && (
        <Amounts
          key={edit?.id || 'new'}
          labels={{ fee: t('Gage'), allowance: t('Pauschale'), expenses: t('Auslagen') }}
          initial={{
            fee: edit?.fee || '0',
            allowance: edit?.allowance || '0',
            expenses: edit?.expenses || '0',
            note: edit?.note || '',
            attended: edit?.attended || false,
            assignment: edit?.assignment || assignments[0]?.id || '',
          }}
          choices={assignments}
          onSave={async (values) => {
            await act({ action: 'claim', ...values })
            setEdit(null)
          }}
        />
      )}
      {!d.claims.length && <MusicEmptyState />}
      {d.claims.map((c) => (
        <article className="card stack music-record" key={c.id}>
          <strong>{assignments.find((a) => a.id === c.assignment)?.name}</strong>
          <p>
            {euro(c.fee)} {t('Gage')} + {euro(c.allowance)} {t('Pauschale')} + {euro(c.expenses)}{' '}
            {t('Auslagen')} = {euro(c.total)}
          </p>
          <p>
            {c.status === 'draft'
              ? t('Entwurf')
              : c.status === 'void'
                ? t('Aufgehoben')
                : c.paid
                  ? t('Ausgezahlt')
                  : Number(c.paid_amount || 0) > 0
                    ? t('Teilweise ausgezahlt')
                    : t('Freigegeben')}
          </p>
          <p>{c.note}</p>
          {c.paid_amount !== undefined && (
            <p>
              {t('Ausgezahlt')}: {euro(c.paid_amount)} · {t('Offener Vergütungsbetrag')}:{' '}
              {euro(c.outstanding || '0')}
            </p>
          )}
          {canEdit && (
            <div className="actions">
              {c.status === 'draft' && (
                <>
                  <button
                    className="button button-ghost"
                    onClick={async () => {
                      if (await confirmLeave()) setEdit(c)
                    }}
                  >
                    {t('Bearbeiten')}
                  </button>
                  <button
                    className="button button-primary"
                    disabled={busy}
                    onClick={() => void act({ action: 'approve', claim: c.id }).catch(() => {})}
                  >
                    {t('Vergütung freigeben')}
                  </button>
                </>
              )}
              {!c.paid && Number(c.paid_amount || 0) === 0 && (
                <button
                  className="button button-ghost"
                  disabled={busy}
                  onClick={() =>
                    void act({
                      action: c.status === 'void' ? 'reopen' : 'void',
                      claim: c.id,
                    }).catch(() => {})
                  }
                >
                  {c.status === 'void' ? t('Erneut bearbeiten') : t('Freigabe aufheben')}
                </button>
              )}
            </div>
          )}
          {canEdit && c.status === 'approved' && !c.paid && (
            <PaymentLink onSave={(booking) => act({ action: 'payment', claim: c.id, booking })} />
          )}
        </article>
      ))}
      <h2>{t('Weitere Auftrittsausgaben')}</h2>
      {canEdit && <PaymentLink onSave={(booking) => act({ action: 'payment', booking })} />}
      <p>
        {t(
          'Kassenbuchungen mit Belegen zuerst in der Kasse erfassen. Eine Vergütung kann mehreren Teilzahlungen zugeordnet werden; jede Buchung zählt vollständig. Stornos erfolgen in der Kasse.',
        )}
      </p>
      <Link to="/finanzen/kassenbuch">{t('Zum Kassenbuch')}</Link>
      {d.payments.map((p) => (
        <p key={p.id}>
          <Link to={`/finanzen/kassenbuch?buchung=${p.booking}`}>{p.number}</Link> ·{' '}
          {euro(p.amount)} · {p.cancelled ? t('Storniert') : t('Zugeordnet')}
        </p>
      ))}
    </section>
  )
}

function PaymentLink({ onSave }: { onSave: (booking: number) => Promise<unknown> }) {
  const org = useActiveOrg()
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const load = useLoad(
    () =>
      api.get<{
        results: { id: number; number: string; text: string; amount: string }[]
        next: string | null
      }>(
        `/api/orgs/${org.id}/finance/bookings/?art=expense&suche=${encodeURIComponent(search)}&page=${page}`,
      ),
    [org.id, search, page],
  )
  const [booking, setBooking] = useState('')
  const [busy, setBusy] = useState(false)
  return (
    <form
      className="stack"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        try {
          await onSave(Number(booking))
        } catch {
        } finally {
          setBusy(false)
        }
      }}
    >
      <label>
        {t('Ausgabe suchen')}
        <input
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setPage(1)
          }}
        />
      </label>
      {load.error && <Alert kind="error">{load.error}</Alert>}
      <label>
        {t('Erfolgte Auszahlung')}
        <select required value={booking} onChange={(e) => setBooking(e.target.value)}>
          <option value="">{t('Bitte wählen')}</option>
          {load.data?.results.map((b) => (
            <option key={b.id} value={b.id}>
              {b.number} · {b.text} · {euro(b.amount)}
            </option>
          ))}
        </select>
      </label>
      <div className="actions">
        <button
          type="button"
          className="button button-ghost"
          disabled={page === 1}
          onClick={() => setPage(page - 1)}
        >
          {t('Zurück')}
        </button>
        <button
          type="button"
          className="button button-ghost"
          disabled={!load.data?.next}
          onClick={() => setPage(page + 1)}
        >
          {t('Weiter')}
        </button>
        <button className="button button-primary" disabled={busy || !booking}>
          {t('Auszahlung zuordnen')}
        </button>
      </div>
    </form>
  )
}

function Amounts({
  labels,
  initial,
  choices,
  onSave,
}: {
  labels: Record<string, string>
  initial: Record<string, string | number | boolean>
  choices?: Assignment[]
  onSave: (values: Record<string, unknown>) => Promise<void>
}) {
  const [values, setValues] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [clean, setClean] = useState(JSON.stringify(initial))
  useDraftGuard(JSON.stringify(values) !== clean)
  return (
    <form
      className="card stack"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        try {
          await onSave(values)
          setClean(JSON.stringify(values))
        } catch (err) {
          setError(errorMessage(err))
        } finally {
          setBusy(false)
        }
      }}
    >
      {error && <Alert kind="error">{error}</Alert>}
      {choices && (
        <label>
          {t('Musiker')}
          <select
            required
            value={String(values.assignment)}
            onChange={(e) => setValues({ ...values, assignment: Number(e.target.value) })}
          >
            {choices.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <div className="music-form-fields">
        {Object.entries(labels).map(([key, label]) => (
          <label key={key}>
            {label}
            <input
              required
              type="number"
              min="0"
              max="9999999999.99"
              step="0.01"
              value={String(values[key])}
              onChange={(e) => setValues({ ...values, [key]: e.target.value })}
            />
          </label>
        ))}
      </div>
      {choices && (
        <label>
          <input
            type="checkbox"
            checked={Boolean(values.attended)}
            onChange={(e) => setValues({ ...values, attended: e.target.checked })}
          />
          {t('Teilnahme bestätigt')}
        </label>
      )}
      <label>
        {t('Abrechnungsvermerk')}
        <textarea
          maxLength={2000}
          value={String(values.note)}
          onChange={(e) => setValues({ ...values, note: e.target.value })}
        />
      </label>
      <button className="button button-primary" disabled={busy}>
        {t('Speichern')}
      </button>
    </form>
  )
}
