// Kassenbuch: eine Buchung auf mehrere Kategorien aufteilen (Splitbuchung).
import { useState } from 'react'
import type { FormEvent } from 'react'
import { euro, financeApi, parseAmount } from '../../api/finance.ts'
import type { Booking, Category, Project } from '../../api/finance.ts'
import { errorMessage } from '../../components/forms.ts'
import { Alert } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

interface Row {
  category: string
  amount: string
  project: string
  text: string
}

function cents(value: string): number {
  const n = Number(parseAmount(value))
  return Number.isFinite(n) ? Math.round(n * 100) : 0
}

export function SplitEditor({
  orgId,
  booking,
  categories,
  projects,
  onDone,
  onCancel,
}: {
  orgId: number
  booking: Booking
  categories: Category[]
  projects: Project[]
  onDone: (lead: Booking) => void
  onCancel: () => void
}) {
  const [rows, setRows] = useState<Row[]>([
    {
      category: String(booking.category ?? ''),
      amount: booking.amount.replace('.', ','),
      project: String(booking.project ?? ''),
      text: '',
    },
    { category: '', amount: '', project: '', text: '' },
  ])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const total = cents(booking.amount)
  const rest = total - rows.reduce((sum, r) => sum + cents(r.amount), 0)

  function update(i: number, patch: Partial<Row>) {
    setRows((all) => all.map((r, k) => (k === i ? { ...r, ...patch } : r)))
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const result = await financeApi.splitBooking(
        orgId,
        booking.id,
        rows.map((r) => ({
          category: Number(r.category),
          amount: parseAmount(r.amount),
          project: r.project ? Number(r.project) : null,
          text: r.text,
        })),
      )
      onDone(result[0])
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="subcard" onSubmit={submit} aria-label={t('Buchung aufteilen')}>
      <h3>{t('Buchung aufteilen')}</h3>
      <p className="muted small">
        {t(
          'Ein Zahlungsvorgang, mehrere Kategorien: Jeder Teil wird eine eigene Buchung. Datum, Konto und Empfänger bzw. Zahler bleiben gleich; Belege und Kontoumsatz bleiben beim ersten Teil.',
        )}
      </p>
      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th>{t('Kategorie')}</th>
              <th className="num">{t('Betrag')}</th>
              {projects.length > 0 && <th>{t('Veranstaltung')}</th>}
              <th>{t('Buchungstext (optional)')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td>
                  <select
                    aria-label={t('Kategorie von Teil {n}', { n: i + 1 })}
                    value={r.category}
                    required
                    onChange={(e) => update(i, { category: e.target.value })}
                  >
                    <option value="">{t('bitte wählen')}</option>
                    {categories.map((c) => (
                      <option key={c.id} value={String(c.id)}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="num">
                  <input
                    aria-label={t('Betrag von Teil {n}', { n: i + 1 })}
                    inputMode="decimal"
                    value={r.amount}
                    required
                    size={9}
                    onChange={(e) => update(i, { amount: e.target.value })}
                  />
                </td>
                {projects.length > 0 && (
                  <td>
                    <select
                      aria-label={t('Veranstaltung von Teil {n}', { n: i + 1 })}
                      value={r.project}
                      onChange={(e) => update(i, { project: e.target.value })}
                    >
                      <option value="">–</option>
                      {projects.map((p) => (
                        <option key={p.id} value={String(p.id)}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                  </td>
                )}
                <td>
                  <input
                    aria-label={t('Buchungstext von Teil {n}', { n: i + 1 })}
                    value={r.text}
                    maxLength={200}
                    onChange={(e) => update(i, { text: e.target.value })}
                  />
                </td>
                <td>
                  {rows.length > 2 && (
                    <button
                      type="button"
                      className="button button-ghost"
                      onClick={() => setRows((all) => all.filter((_, k) => k !== i))}
                    >
                      {t('Entfernen')}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p
        className={rest === 0 ? 'muted small' : 'small'}
        data-testid="split-rest"
        aria-live="polite"
      >
        {rest === 0
          ? t('Die Teile ergeben genau den Betrag der Buchung.')
          : t('Noch zu verteilen: {x}', { x: euro((rest / 100).toFixed(2)) })}
      </p>
      {error && <Alert kind="error">{error}</Alert>}
      <div className="button-row">
        <button type="submit" className="button button-primary" disabled={busy || rest !== 0}>
          {t('Aufteilen')}
        </button>
        {rows.length < 20 && (
          <button
            type="button"
            className="button button-ghost"
            onClick={() =>
              setRows((all) => [
                ...all,
                {
                  category: '',
                  amount: rest > 0 ? (rest / 100).toFixed(2).replace('.', ',') : '',
                  project: '',
                  text: '',
                },
              ])
            }
          >
            {t('Teil hinzufügen')}
          </button>
        )}
        <button type="button" className="button button-ghost" onClick={onCancel}>
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}
