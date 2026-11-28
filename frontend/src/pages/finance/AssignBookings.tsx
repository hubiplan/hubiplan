import { useState } from 'react'
import { euro, financeApi } from '../../api/finance.ts'
import type { Booking, ProjectEvaluation } from '../../api/finance.ts'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import { Alert, Field, LoadError, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

function shiftDays(date: string, days: number): string {
  const d = new Date(`${date}T12:00:00`)
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}

/** Vorhandene Buchungen ohne Veranstaltung rund um den Zeitraum zuordnen. */
export function AssignBookings({
  project,
  onDone,
}: {
  project: ProjectEvaluation
  onDone: () => void
}) {
  const org = useActiveOrg()
  const [open, setOpen] = useState(false)
  const [von, setVon] = useState(shiftDays(project.starts_on, -30))
  const [bis, setBis] = useState(shiftDays(project.ends_on ?? project.starts_on, 30))
  const [suche, setSuche] = useState('')
  // Sammeln über Filter hinweg bleibt möglich, die Auswahl ist aber immer sichtbar
  // (UI-Audit NAF-05)
  const [picked, setPicked] = useState<Map<number, Booking>>(new Map())
  const [error, setError] = useState<string | null>(null)
  const candidates = useLoad(
    () =>
      open
        ? financeApi.bookings(org.id, {
            veranstaltung: '-',
            von,
            bis,
            suche,
            page_size: 200,
          })
        : Promise.resolve(null),
    [org.id, open, von, bis, suche],
  )

  if (!open)
    return (
      <div className="button-row">
        <button type="button" className="button button-ghost" onClick={() => setOpen(true)}>
          {t('Vorhandene Buchungen zuordnen')}
        </button>
      </div>
    )

  const rows = (candidates.data?.results ?? []).filter((b: Booking) => b.kind !== 'transfer')
  const visible = new Set(rows.map((b) => b.id))
  const outside = [...picked.keys()].filter((id) => !visible.has(id)).length
  function toggle(b: Booking) {
    setPicked((prev) => {
      const next = new Map(prev)
      if (next.has(b.id)) next.delete(b.id)
      else next.set(b.id, b)
      return next
    })
  }
  function cancel() {
    setPicked(new Map())
    setError(null)
    setOpen(false)
  }
  async function assign() {
    try {
      await financeApi.assignBookings(org.id, project.id, [...picked.keys()])
      setPicked(new Map())
      setOpen(false)
      onDone()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <div className="subcard">
      <h3>{t('Buchungen ohne Veranstaltung')}</h3>
      <div className="filters">
        <Field label={t('von')} type="date" value={von} onChange={(e) => setVon(e.target.value)} />
        <Field label={t('bis')} type="date" value={bis} onChange={(e) => setBis(e.target.value)} />
        <Field
          label={t('Suche')}
          type="search"
          value={suche}
          placeholder={t('Text, Beleg, Betrag')}
          onChange={(e) => setSuche(e.target.value)}
        />
      </div>
      {candidates.error && (
        <LoadError message={candidates.error} onRetry={() => void candidates.reload()} />
      )}
      {candidates.data && candidates.data.count > candidates.data.results.length && (
        <Alert kind="info">
          {t(
            'Gezeigt werden die ersten {n} von {count}  Buchungen. Bitte Zeitraum oder Suche eingrenzen.',
            { n: candidates.data.results.length, count: candidates.data.count },
          )}
        </Alert>
      )}
      {!candidates.data ? (
        !candidates.error && <Loading />
      ) : rows.length === 0 ? (
        <p className="muted small">{t('Keine passenden Buchungen in diesem Zeitraum.')}</p>
      ) : (
        <div className="table-scroll">
          <table className="table">
            <tbody>
              {rows.map((b) => (
                <tr key={b.id}>
                  <td>
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        checked={picked.has(b.id)}
                        onChange={() => toggle(b)}
                        aria-label={t('Buchung {display_number} zuordnen', {
                          display_number: b.display_number,
                        })}
                      />
                      <span>{b.display_number}</span>
                    </label>
                  </td>
                  <td>{formatDate(b.date)}</td>
                  <td>{b.text}</td>
                  <td>{b.category_name}</td>
                  <td className={`num ${b.kind === 'expense' ? 'amount-out' : 'amount-in'}`}>
                    {euro(b.kind === 'expense' ? -Number(b.amount) : Number(b.amount))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {picked.size > 0 && (
        <div className="subcard stack-sm" aria-live="polite">
          <p className="small">
            <strong>
              {picked.size} {t('ausgewählt')}
            </strong>
            {outside > 0 && t(', davon {outside} außerhalb des Filters', { outside })}
          </p>
          <ul className="plain-list small">
            {[...picked.values()].map((b) => (
              <li key={b.id}>
                {b.display_number} · {formatDate(b.date)} · {b.text} ·{' '}
                {euro(b.kind === 'expense' ? -Number(b.amount) : Number(b.amount))}{' '}
                <button type="button" className="link-button" onClick={() => toggle(b)}>
                  {t('entfernen')}
                </button>
              </li>
            ))}
          </ul>
          <button type="button" className="link-button" onClick={() => setPicked(new Map())}>
            {t('Auswahl leeren')}
          </button>
        </div>
      )}
      {error && <Alert kind="error">{error}</Alert>}
      <div className="button-row">
        <button
          type="button"
          className="button button-primary"
          disabled={picked.size === 0}
          onClick={() => void assign()}
        >
          {picked.size === 1
            ? t('1 Buchung zuordnen')
            : t('{size} Buchungen zuordnen', { size: picked.size })}
        </button>
        <button type="button" className="button button-ghost" onClick={cancel}>
          {t('Abbrechen')}
        </button>
      </div>
    </div>
  )
}
