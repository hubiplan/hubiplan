// Ortsfeld mit Auswahl aus den gespeicherten Orten (Einstellungen › Orte).
// Freie Eingabe bleibt möglich; ein neuer Ort lässt sich gleich speichern.
import { useId, useState } from 'react'
import { placeApi } from '../api/places.ts'
import type { Place } from '../api/places.ts'
import { findPlace, usePlaces } from './places.ts'
import { Field } from './ui.tsx'
import { errorMessage } from './forms.ts'
import { t } from '../i18n/index.ts'

export function PlaceField({
  label,
  value,
  onChange,
  onPick,
  address = '',
  error,
  placeholder,
  maxLength = 200,
  required,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  /** Gespeicherter Ort gewählt: Anschrift usw. übernehmen */
  onPick?: (place: Place) => void
  /** Anschrift aus dem Formular, die beim Speichern als neuer Ort mitgeht */
  address?: string
  error?: string
  placeholder?: string
  maxLength?: number
  required?: boolean
}) {
  const listId = useId()
  const { places, canEdit, base, add } = usePlaces()
  const [saving, setSaving] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const known = findPlace(places, value)
  const change = (next: string) => {
    setNote(null)
    onChange(next)
    const hit = findPlace(places, next)
    if (hit && onPick) onPick(hit)
  }
  const save = async () => {
    if (!base) return
    setSaving(true)
    try {
      const place = await placeApi.create(base, { name: value.trim(), address: address.trim() })
      add(place)
      setNote(t('Ort „{name}“ gespeichert.', { name: place.name }))
    } catch (err) {
      setNote(errorMessage(err))
    } finally {
      setSaving(false)
    }
  }
  return (
    <div className="place-field">
      <Field
        label={label}
        value={value}
        maxLength={maxLength}
        placeholder={placeholder}
        error={error}
        required={required}
        list={places.length ? listId : undefined}
        autoComplete="off"
        hint={places.length ? t('Gespeicherten Ort wählen oder frei eingeben.') : undefined}
        onChange={(e) => change(e.target.value)}
      />
      {places.length > 0 && (
        <datalist id={listId}>
          {places.map((p) => (
            <option key={p.id} value={p.name}>
              {[p.address, p.owner].filter(Boolean).join(' · ')}
            </option>
          ))}
        </datalist>
      )}
      {base && canEdit && value.trim() && !known && (
        <button type="button" className="link-button place-save" disabled={saving} onClick={save}>
          {t('Als Ort speichern')}
        </button>
      )}
      {note && (
        <small className="muted" role="status">
          {note}
        </small>
      )}
    </div>
  )
}
