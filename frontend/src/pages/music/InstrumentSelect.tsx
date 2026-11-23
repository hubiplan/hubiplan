import { useState } from 'react'
import { api } from '../../api/client.ts'
import { t } from '../../i18n/index.ts'
import './music.css'

/** Eintrag der Instrumentenliste der Einheit (Einstellungen › Musik › Instrumente) */
export type Instrument = {
  id: number
  name: string
  group: string
  position: number
  active: boolean
  used: number
}

export const instrumentGroups: [string, string][] = [
  ['wood', t('Holz')],
  ['brass', t('Blech')],
  ['percussion', t('Schlagwerk')],
  ['corps', t('Spielleute')],
  ['other', t('Weitere')],
]

/** Liste laden; fehlt sie (ältere Stände), bleibt die Seite benutzbar. */
export function loadInstruments(orgId: number | string) {
  return api
    .get<Instrument[]>(`/api/orgs/${orgId}/music/instruments/`)
    .catch(() => [] as Instrument[])
}

const NEW = '\u0000neu'

/**
 * Instrument aus der Liste wählen statt tippen (konzepte/instrumente.md). „Neues Instrument …“
 * öffnet ein Textfeld; HUBIplan nimmt den Namen beim Speichern in die Liste auf.
 */
export function InstrumentSelect({
  instruments,
  value,
  onChange,
  required = true,
  disabled,
  label,
}: {
  instruments: Instrument[]
  value: string
  onChange: (value: string) => void
  required?: boolean
  disabled?: boolean
  /** Beschriftung für Bildschirmleser, wenn kein umgebendes label */
  label?: string
}) {
  const active = instruments.filter((i) => i.active)
  const known = active.some((i) => i.name === value)
  // Ohne Liste (ältere Stände) oder bei unbekanntem Namen gleich das Textfeld
  const [adding, setAdding] = useState(
    () => instruments.length === 0 || (!!value && !instruments.some((i) => i.name === value)),
  )
  if (adding)
    return (
      <span className="music-instrument-new">
        <input
          required={required}
          maxLength={100}
          value={value}
          disabled={disabled}
          aria-label={label}
          placeholder={t('Name des Instruments')}
          onChange={(e) => onChange(e.target.value)}
        />
        {instruments.length > 0 && (
          <button
            type="button"
            className="button button-ghost"
            disabled={disabled}
            onClick={() => {
              setAdding(false)
              onChange('')
            }}
          >
            {t('Aus der Liste wählen')}
          </button>
        )}
      </span>
    )
  return (
    <select
      required={required}
      value={value}
      disabled={disabled}
      aria-label={label}
      onChange={(e) => {
        if (e.target.value === NEW) {
          setAdding(true)
          onChange('')
        } else onChange(e.target.value)
      }}
    >
      <option value="" disabled={required}>
        {required ? t('Bitte wählen') : '—'}
      </option>
      {/* Ausgeblendetes Instrument bleibt an bestehenden Einträgen wählbar */}
      {value && !known && <option value={value}>{value}</option>}
      {instrumentGroups.map(([group, groupLabel]) => {
        const items = active.filter((i) => i.group === group)
        return items.length ? (
          <optgroup key={group} label={groupLabel}>
            {items.map((i) => (
              <option key={i.id} value={i.name}>
                {i.name}
              </option>
            ))}
          </optgroup>
        ) : null
      })}
      <option value={NEW}>{t('Neues Instrument …')}</option>
    </select>
  )
}
