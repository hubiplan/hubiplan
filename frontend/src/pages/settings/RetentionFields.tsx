import { SelectField } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

// Frist je Art der abgelegten Dateien; leer heißt Voreinstellung, 0 dauerhaft
const RETENTION: { key: string; label: () => string; standard: () => string }[] = [
  {
    key: 'records',
    label: () => t('Beschlüsse und Grundlagen'),
    standard: () => t('dauerhaft'),
  },
  {
    key: 'finance',
    label: () => t('Kassen- und Steuerunterlagen'),
    standard: () => t('10 Jahre nach Jahresende'),
  },
  {
    key: 'statistics',
    label: () => t('Planung und Statistik ohne Personen'),
    standard: () => t('dauerhaft'),
  },
  {
    key: 'reports',
    label: () => t('Meldungen an Verbände'),
    standard: () => t('6 Jahre nach Jahresende'),
  },
  { key: 'personal', label: () => t('Personenbezogene Listen'), standard: () => t('3 Monate') },
  { key: 'other', label: () => t('Sonstiges'), standard: () => t('2 Jahre') },
]

export function RetentionFields({
  value,
  onChange,
}: {
  value: Record<string, number>
  onChange: (v: Record<string, number>) => void
}) {
  return (
    <details className="small">
      <summary>{t('Fristen je Art anpassen')}</summary>
      {RETENTION.map((r) => (
        <SelectField
          key={r.key}
          label={r.label()}
          value={value[r.key] === undefined ? '' : String(value[r.key])}
          onChange={(e) => {
            const next = { ...value }
            if (e.target.value === '') delete next[r.key]
            else next[r.key] = Number(e.target.value)
            onChange(next)
          }}
        >
          <option value="">{t('Voreinstellung: {x}', { x: r.standard() })}</option>
          <option value="0">{t('dauerhaft')}</option>
          {[2, 3, 5, 6, 10].map((y) => (
            <option key={y} value={String(y)}>
              {t('{years} Jahre', { years: y })}
            </option>
          ))}
        </SelectField>
      ))}
    </details>
  )
}
