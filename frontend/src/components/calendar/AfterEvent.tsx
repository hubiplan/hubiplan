// Nach der Veranstaltung (Anmeldung A6, Konzept 3.11): Qualifikation für alle Teilnehmenden
// eintragen. Teilgenommen heißt beim Einlass abgehakt; ohne Einlass gelten alle Angemeldeten.
import { useState } from 'react'
import type { CalendarBase } from '../../api/events.ts'
import { registrationApi } from '../../api/registrations.ts'
import type { QualificationResult } from '../../api/registrations.ts'
import { errorMessage } from '../forms.ts'
import { Alert, Field, SelectField } from '../ui.tsx'
import { t } from '../../i18n/index.ts'

export function QualificationPanel({
  base,
  eventId,
  kinds,
  lastDay,
}: {
  base: CalendarBase
  eventId: number
  kinds: { id: number; name: string }[]
  lastDay: string
}) {
  const [kind, setKind] = useState(kinds[0]?.id ?? 0)
  const [day, setDay] = useState(lastDay)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<QualificationResult | null>(null)

  async function save() {
    setBusy(true)
    setError(null)
    try {
      setResult(await registrationApi.addQualification(base, eventId, { kind, acquired_on: day }))
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack">
      <p className="muted small">
        {t(
          'Trägt die Qualifikation bei allen teilnehmenden Mitgliedern ein. Teilgenommen hat, wer beim Einlass abgehakt ist; ohne Einlass alle Angemeldeten. Gäste ohne Mitgliedschaft werden übersprungen.',
        )}
      </p>
      <SelectField
        label={t('Qualifikation')}
        value={kind}
        onChange={(e) => setKind(Number(e.target.value))}
      >
        {kinds.map((k) => (
          <option key={k.id} value={k.id}>
            {k.name}
          </option>
        ))}
      </SelectField>
      <Field
        label={t('erworben am')}
        type="date"
        value={day}
        onChange={(e) => setDay(e.target.value)}
      />
      {error && <Alert kind="error">{error}</Alert>}
      {result && (
        <Alert kind="success">
          {t('{n} Nachweise eingetragen.', { n: result.created })}
          {result.existing > 0 && ` ${t('{n} hatten ihn schon.', { n: result.existing })}`}
          {result.guests > 0 && ` ${t('{n} Gäste übersprungen.', { n: result.guests })}`}
        </Alert>
      )}
      <div className="button-row">
        <button type="button" className="button" disabled={busy || !kind} onClick={save}>
          {t('Eintragen')}
        </button>
      </div>
    </div>
  )
}
