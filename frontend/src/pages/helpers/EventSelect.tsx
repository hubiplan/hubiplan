import { helperApi } from '../../api/helpers.ts'
import { useLoad } from '../../components/forms.ts'
import { t } from '../../i18n/index.ts'
import './helpers.css'
import { dayText } from './helpersHelpers.ts'

export function EventSelect({
  base,
  value,
  onChange,
}: {
  base: string
  value: number | null
  onChange: (id: number | null) => void
}) {
  const events = useLoad(() => helperApi.events(base), [base])
  return (
    <label className="field">
      <span>{t('Termin (optional)')}</span>
      <select
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
      >
        <option value="">{t('ohne Termin')}</option>
        {(events.data ?? []).map((e) => (
          <option key={e.id} value={e.id}>
            {dayText(e.starts_at)} · {e.title}
          </option>
        ))}
      </select>
    </label>
  )
}
