// Dokument aus der Ablage an einen Termin knüpfen; gezeigt wird immer die neueste Fassung.
import { useState } from 'react'
import { eventApi } from '../../api/events.ts'
import type { CalendarBase, EventDetail, LinkableDocument } from '../../api/events.ts'
import { errorMessage } from '../forms.ts'
import { Alert } from '../ui.tsx'
import { t } from '../../i18n/index.ts'

export function EventDocumentLink({
  base,
  event,
  disabled,
  onChanged,
}: {
  base: CalendarBase
  event: EventDetail
  disabled: boolean
  onChanged: (event: EventDetail) => void
}) {
  const [choices, setChoices] = useState<LinkableDocument[] | null>(null)
  const [chosen, setChosen] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function open() {
    setBusy(true)
    setError('')
    try {
      setChoices((await eventApi.linkableDocuments(base, event.id)).documents)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function link() {
    setBusy(true)
    setError('')
    try {
      onChanged(await eventApi.linkDocument(base, event.id, Number(chosen)))
      setChoices(null)
      setChosen('')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const selected = choices?.find((d) => String(d.id) === chosen)
  return (
    <div className="stack-sm">
      {error && <Alert kind="error">{error}</Alert>}
      {choices === null ? (
        <div className="button-row">
          <button
            type="button"
            className="button button-ghost"
            disabled={disabled || busy}
            onClick={() => void open()}
          >
            {t('Dokument aus der Ablage verknüpfen')}
          </button>
        </div>
      ) : choices.length === 0 ? (
        <p className="muted small">
          {t('In der Ablage gibt es kein weiteres Dokument, das du hier verknüpfen kannst.')}
        </p>
      ) : (
        <>
          <label className="field">
            <span>{t('Dokument aus der Ablage')}</span>
            <select value={chosen} onChange={(e) => setChosen(e.target.value)} disabled={busy}>
              <option value="">{t('Bitte wählen')}</option>
              {choices.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.title} ({d.folder})
                </option>
              ))}
            </select>
          </label>
          {selected?.narrower && (
            <Alert kind="info">
              {t(
                'Der Ordner „{folder}“ ist enger sichtbar ({visibility}). Am Termin sehen das Dokument alle, die den Termin sehen.',
                { folder: selected.folder, visibility: selected.folder_visibility },
              )}
            </Alert>
          )}
          <div className="button-row">
            <button
              type="button"
              className="button button-primary"
              disabled={busy || disabled || !chosen}
              onClick={() => void link()}
            >
              {t('Verknüpfen')}
            </button>
            <button
              type="button"
              className="button button-ghost"
              disabled={busy}
              onClick={() => {
                setChoices(null)
                setChosen('')
              }}
            >
              {t('Abbrechen')}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
