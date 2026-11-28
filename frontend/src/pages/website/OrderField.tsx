import { SelectField } from '../../components/ui.tsx'
import { IMAGE_ORDERS } from './imageTools.ts'
import type { ImageOrder } from './imageTools.ts'
import { t } from '../../i18n/index.ts'

export function OrderField({
  value,
  onChange,
}: {
  value: ImageOrder
  onChange: (order: ImageOrder) => void
}) {
  return (
    <SelectField
      label={t('Sortieren')}
      value={value}
      onChange={(e) => onChange(e.target.value as ImageOrder)}
    >
      {IMAGE_ORDERS.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </SelectField>
  )
}
