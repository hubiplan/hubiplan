import { t } from '../../i18n/index.ts'
import './helpers.css'

/** Auswahl der vorausgesetzten Qualifikation (nur mit Modul Qualifikationen und Arten). */
export function QualificationSelect({
  value,
  options,
  onChange,
  label = t('Voraussetzung'),
}: {
  value: string
  options: { id: number; name: string }[]
  onChange: (value: string) => void
  label?: string
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{t('keine')}</option>
        {options.map((k) => (
          <option key={k.id} value={k.id}>
            {k.name}
          </option>
        ))}
      </select>
    </label>
  )
}
