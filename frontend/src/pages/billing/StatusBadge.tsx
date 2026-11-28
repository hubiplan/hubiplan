import type { InvoiceRow } from '../../api/billing.ts'
import { t } from '../../i18n/index.ts'

export function StatusBadge({
  row,
}: {
  row: Pick<InvoiceRow, 'status' | 'status_label' | 'overdue'>
}) {
  const cls = row.overdue ? 'overdue' : row.status
  return (
    <span className={`status status-${cls}`}>
      {row.overdue ? t('überfällig') : row.status_label}
    </span>
  )
}
