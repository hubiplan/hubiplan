import { SelectField } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

/** Auswahl der Frist „wie lange aktuell“ (Ralf 14.11.2026); muss zu DAYS_CHOICES passen */
const DAYS_CHOICES = [3, 7, 14, 30, 60, 90, 180, 365]

export function DaysField({
  value,
  hint,
  onChange,
}: {
  value: number | null | undefined
  hint: string
  onChange: (days: number | null) => void
}) {
  return (
    <SelectField
      label={t('Wie lange zeigen')}
      value={value ?? ''}
      hint={hint}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
    >
      <option value="">{t('Immer')}</option>
      {DAYS_CHOICES.map((n) => (
        <option key={n} value={n}>
          {t('{x} Tage danach', { x: n })}
        </option>
      ))}
    </SelectField>
  )
}
