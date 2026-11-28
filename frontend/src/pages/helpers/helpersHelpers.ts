// Gemeinsame Helfer, Typen und Konstanten von HelpersPage.
import type { PlanStatus } from '../../api/helpers.ts'
import { locale, t } from '../../i18n/index.ts'
import './helpers.css'

export const ZONE = 'Europe/Berlin'

export function statusLabel(status: PlanStatus) {
  if (status === 'published') return t('veröffentlicht')
  if (status === 'closed') return t('abgeschlossen')
  return t('in Vorbereitung')
}

export function dayText(value: string) {
  return new Date(value).toLocaleDateString(locale(), {
    timeZone: ZONE,
    weekday: 'short',
    day: '2-digit',
    month: '2-digit',
  })
}

export function timeText(value: string) {
  return new Date(value).toLocaleTimeString(locale(), {
    timeZone: ZONE,
    hour: '2-digit',
    minute: '2-digit',
  })
}
