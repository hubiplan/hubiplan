// Gemeinsame Helfer, Typen und Konstanten von ProjectsPage.
import type { ProjectStatus } from '../../api/finance.ts'
import { formatDate } from '../../components/forms.ts'
import { t } from '../../i18n/index.ts'

export const STATUS: { value: ProjectStatus; label: string }[] = [
  {
    value: 'planned',
    get label() {
      return t('geplant')
    },
  },
  {
    value: 'running',
    get label() {
      return t('laufend')
    },
  },
  {
    value: 'done',
    get label() {
      return t('abgeschlossen')
    },
  },
]

export function period(starts: string, ends: string | null): string {
  return ends && ends !== starts
    ? t('{x} bis {x2}', { x: formatDate(starts), x2: formatDate(ends) })
    : formatDate(starts)
}
