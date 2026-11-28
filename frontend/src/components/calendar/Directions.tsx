import { useState } from 'react'
import { Field } from '../ui.tsx'
import { pointFromLink } from '../mapLink.ts'
import { t } from '../../i18n/index.ts'
import { type Values } from './eventFormHelpers.ts'

/** Anfahrt: Hinweise und auf Wunsch ein genauer Punkt (eingeklappt, wenn leer). */
export function Directions({
  v,
  errors,
  set,
}: {
  v: Values
  errors: Partial<Record<string, string>>
  set: <K extends keyof Values>(key: K, value: Values[K]) => void
}) {
  const [link, setLink] = useState('')
  const [linkError, setLinkError] = useState('')
  const filled = !!(v.directions || v.latitude || v.longitude)
  function take(text: string) {
    setLink(text)
    if (!text.trim()) return setLinkError('')
    const point = pointFromLink(text)
    if (!point) return setLinkError(t('In diesem Link steht kein Punkt.'))
    setLinkError('')
    set('latitude', String(point.latitude))
    set('longitude', String(point.longitude))
    setLink('')
  }
  return (
    <details className="subcard stack-sm" open={filled}>
      <summary>{t('Anfahrt')}</summary>
      <label className="field">
        <span>{t('Anfahrt und Hinweise (optional)')}</span>
        <textarea
          rows={2}
          value={v.directions}
          maxLength={1000}
          placeholder={t('z. B. Parken am Sportplatz, Eingang über den Hof')}
          onChange={(e) => set('directions', e.target.value)}
        />
      </label>
      <p className="muted small">
        {t(
          'Ohne genauen Punkt führen die Kartenlinks zur Anschrift. Einen Punkt brauchst du nur, wenn die Anschrift nicht reicht, etwa für eine Wiese oder einen Platz im Freien.',
        )}
      </p>
      <div className="grid-3">
        <Field
          label={t('Breite')}
          inputMode="decimal"
          value={v.latitude}
          error={errors.latitude}
          onChange={(e) => set('latitude', e.target.value)}
        />
        <Field
          label={t('Länge')}
          inputMode="decimal"
          value={v.longitude}
          error={errors.longitude}
          onChange={(e) => set('longitude', e.target.value)}
        />
        <Field
          label={t('Punkt aus Kartenlink übernehmen')}
          placeholder={t('Link aus OpenStreetMap oder Google Maps')}
          value={link}
          error={linkError}
          onChange={(e) => take(e.target.value)}
        />
      </div>
    </details>
  )
}
