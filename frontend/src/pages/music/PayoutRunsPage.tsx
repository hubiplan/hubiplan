import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, newRequestKey, requestBlob, saveBlob } from '../../api/client.ts'
import { todayIso } from '../../api/members.ts'
import { euro } from '../../api/finance.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { useDraftGuard } from '../../components/leaveGuard.ts'
import { Alert, Field } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { MusicHeader, MusicEmptyState } from './MusicLayout.tsx'

type Payee = { holder: string; iban: string; bic: string }
type Run = {
  id: number
  reference: string
  execution_date: string
  total: string
  cancelled: boolean
  exported: boolean
  completed: boolean
  items: (Payee & {
    claim: number
    title: string
    performance: number
    amount: string
    settled: boolean
  })[]
}
type Choices = {
  runs: Run[]
  banks: { id: number; name: string }[]
  claims: { id: number; name: string; title: string; amount: string }[]
}

export function PayoutRunsPage() {
  const org = useActiveOrg()
  const allowed =
    org.modules.includes('finance') &&
    org.permissions.includes('finance.view') &&
    org.permissions.includes('events.view')
  return allowed ? (
    <PayoutRuns />
  ) : (
    <Alert kind="error">{t('Dafür fehlt dir die Berechtigung.')}</Alert>
  )
}

function PayoutRuns() {
  const org = useActiveOrg()
  const url = `/api/orgs/${org.id}/music/payout-runs/`
  const load = useLoad(() => api.get<Choices>(url), [org.id])
  const [rows, setRows] = useState<Record<number, Payee>>({})
  const [bank, setBank] = useState('')
  const [date, setDate] = useState(todayIso)
  const [key, setKey] = useState(newRequestKey)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useDraftGuard(Object.keys(rows).length > 0)
  const canEdit = org.permissions.includes('finance.edit')
  async function act(work: () => Promise<unknown>) {
    setBusy(true)
    setError('')
    try {
      await work()
      await load.reload()
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  const change = (next: Record<number, Payee>) => {
    setRows(next)
    setKey(newRequestKey())
  }
  return (
    <section className="stack music-page">
      <MusicHeader
        title={t('Sammelauszahlungen')}
        description={t(
          'Freigegebene Restbeträge prüfen, als SEPA-Datei exportieren und mit tatsächlichen Ausgaben abgleichen.',
        )}
      />
      <Alert kind="info">
        {t(
          'Den Bankexport vor der Freigabe bei der Bank prüfen. Ein Export löst keine Überweisung aus und markiert keine Vergütung als bezahlt. Jede Überweisung braucht später eine eigene Ausgabenbuchung.',
        )}
      </Alert>
      {(error || load.error) && <Alert kind="error">{error || load.error}</Alert>}
      {canEdit && (
        <form
          className="card stack"
          onSubmit={(e) => {
            e.preventDefault()
            void act(async () => {
              await api.post(
                url,
                {
                  bank_account: Number(bank),
                  execution_date: date,
                  items: Object.entries(rows).map(([claim, payee]) => ({
                    claim: Number(claim),
                    ...payee,
                  })),
                },
                key,
              )
              setRows({})
              setKey(newRequestKey())
            })
          }}
        >
          <h2>{t('Zahlungslauf vorbereiten')}</h2>
          <label>
            {t('Bankkonto')}
            <select
              required
              disabled={busy}
              value={bank}
              onChange={(e) => {
                setBank(e.target.value)
                setKey(newRequestKey())
              }}
            >
              <option value="">{t('Bitte wählen')}</option>
              {load.data?.banks.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          </label>
          <Field
            type="date"
            required
            min={todayIso()}
            label={t('Ausführungstag')}
            disabled={busy}
            value={date}
            onChange={(e) => {
              setDate(e.target.value)
              setKey(newRequestKey())
            }}
          />
          {load.data?.claims.length === 0 && (
            <MusicEmptyState>
              {t('Keine freigegebenen offenen Vergütungen verfügbar.')}
            </MusicEmptyState>
          )}
          {load.data?.claims.map((c) => (
            <fieldset className="stack" key={c.id} disabled={busy}>
              <legend>
                <label>
                  <input
                    type="checkbox"
                    checked={c.id in rows}
                    onChange={(e) => {
                      const next = { ...rows }
                      if (e.target.checked) next[c.id] = { holder: c.name, iban: '', bic: '' }
                      else delete next[c.id]
                      change(next)
                    }}
                  />{' '}
                  {c.name} · {c.title} · {euro(c.amount)}
                </label>
              </legend>
              {rows[c.id] && (
                <div className="music-form-fields">
                  {(['holder', 'iban', 'bic'] as const).map((field) => (
                    <Field
                      key={field}
                      label={
                        field === 'holder'
                          ? t('Kontoinhaber')
                          : field === 'iban'
                            ? t('IBAN')
                            : t('BIC')
                      }
                      required={field !== 'bic'}
                      maxLength={field === 'holder' ? 70 : field === 'iban' ? 50 : 11}
                      value={rows[c.id][field]}
                      onChange={(e) =>
                        change({ ...rows, [c.id]: { ...rows[c.id], [field]: e.target.value } })
                      }
                    />
                  ))}
                </div>
              )}
            </fieldset>
          ))}
          <button className="button button-primary" disabled={busy || !Object.keys(rows).length}>
            {t('Zahlungslauf zur Prüfung speichern')}
          </button>
        </form>
      )}
      <h2>{t('Zahlungsläufe')}</h2>
      {load.data?.runs.map((run) => (
        <article className="card stack" key={run.id}>
          <h3>
            {run.execution_date} · {euro(run.total)}
          </h3>
          <p className="muted">{run.reference}</p>
          <p>
            {run.cancelled
              ? t('Aufgehoben')
              : run.completed
                ? t('Mit Buchungen abgeglichen')
                : run.exported
                  ? t('Bankdatei exportiert')
                  : t('Zur Prüfung')}
          </p>
          {run.items.map((item) => (
            <div className="music-record" key={item.claim}>
              <strong>
                {item.holder} · {euro(item.amount)}
              </strong>
              <p>
                {item.iban} · {item.bic}
              </p>
              <Link to={`/musik?abrechnung=${item.performance}`}>
                {item.title} · {item.settled ? t('Bezahlt') : t('Buchung zuordnen')}
              </Link>
            </div>
          ))}
          {canEdit && !run.cancelled && !run.completed && (
            <div className="music-actions">
              <button
                className="button button-primary"
                disabled={busy || run.items.some((i) => i.settled)}
                onClick={() =>
                  void act(async () => {
                    const blob = await requestBlob('POST', `${url}${run.id}/`, { action: 'export' })
                    saveBlob(blob, `music-payout-${run.reference}.xml`)
                  })
                }
              >
                {t('SEPA-Datei herunterladen')}
              </button>
              <button
                className="button button-ghost"
                disabled={busy}
                onClick={async () => {
                  if (
                    await confirmDialog(
                      t(
                        'Zahlungslauf aufheben? Bereits bei der Bank eingereichte Überweisungen müssen dort gesondert gestoppt werden. Bereits zugeordnete Buchungen bleiben erhalten.',
                      ),
                    )
                  )
                    void act(() => api.post(`${url}${run.id}/`, { action: 'cancel' }))
                }}
              >
                {t('Zahlungslauf aufheben')}
              </button>
            </div>
          )}
        </article>
      ))}
    </section>
  )
}
