import { formatDate } from '../../components/forms.ts'
import { t } from '../../i18n/index.ts'

/** „bis 31.12.2027“ oder „unbefristet“ */
export function untilText(validUntil: string | null): string {
  return validUntil ? t('bis {date}', { date: formatDate(validUntil) }) : t('unbefristet')
}
