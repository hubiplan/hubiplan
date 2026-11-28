// Gemeinsame Helfer, Typen und Konstanten von MeetingsPage.
import type { Meeting, MeetingStatus } from '../../api/meetings.ts'
import { locale, t } from '../../i18n/index.ts'
import './meetings.css'

export const ZONE = 'Europe/Berlin'

/**
 * Autospeichern in der Versammlung: Angaben, Tagesordnung und Protokoll speichern einzeln,
 * jede Antwort bringt eine neue Fassung (`version`). Die Formulare holen sich darum die
 * jeweils neueste Versammlung hier ab und melden ihre Antwort zurück, ohne dass die
 * anderen Formulare neu aufgebaut werden (Eingaben und Fokus bleiben erhalten).
 */
export type Sync = {
  current: () => Meeting
  stored: (meeting: Meeting) => void
}

export function statusLabel(status: MeetingStatus) {
  return {
    draft: t('in Vorbereitung'),
    invited: t('eingeladen'),
    held: t('durchgeführt'),
    minutes: t('Protokoll in Arbeit'),
    done: t('Protokoll freigegeben'),
    cancelled: t('abgesagt'),
  }[status]
}

export function when(m: Meeting) {
  return new Date(m.starts_at).toLocaleString(locale(), {
    timeZone: ZONE,
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

/** Wert für ein datetime-local-Feld in der Zeitzone des Browsers */
export function local(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}
