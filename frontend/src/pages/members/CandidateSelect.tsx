import { t } from '../../i18n/index.ts'

export function CandidateSelect({
  label,
  candidates,
  value,
  onChange,
}: {
  label: string
  candidates: { id: number; name: string; birth_year: number | null }[]
  value: number | null
  onChange: (id: number | null) => void
}) {
  if (candidates.length === 0)
    return <div className="muted small">{t('kein passendes Mitglied')}</div>
  return (
    <select
      aria-label={label}
      value={value === null ? '' : String(value)}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
    >
      <option value="">{t('nur Name (kein Mitglied)')}</option>
      {candidates.map((c) => (
        <option key={c.id} value={c.id}>
          {c.name}
          {c.birth_year ? t(' (geb. {x0})', { x0: c.birth_year }) : ''}
        </option>
      ))}
    </select>
  )
}
