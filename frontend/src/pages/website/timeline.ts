// Zeitleiste der Chronik: Prüfen, Sortieren und Beschriften der Einträge.
import type { TimelineEntry } from '../../api/website.ts'
import { t } from '../../i18n/index.ts'

export const MAX_TIMELINE = 300
export const MAX_TITLE = 120
export const MAX_TEXT = 400
const MIN_YEAR = 1000
const MAX_YEAR = 2999

export const EMPTY: TimelineEntry = {
  kind: 'event',
  year: null,
  until: null,
  title: '',
  text: '',
  image: null,
}

/** „1939–1948“ oder „1920“ */
export function periodLabel(e: Pick<TimelineEntry, 'year' | 'until'>): string {
  return e.until && e.until !== e.year ? `${e.year}–${e.until}` : String(e.year ?? '')
}

/** Nach Jahr sortiert, Kapitel vor den Ereignissen ihres Jahres; sonst bleibt die
 * Reihenfolge gleicher Jahre (wie auf der Webseite) */
export function sortTimeline(entries: TimelineEntry[]): TimelineEntry[] {
  return entries
    .map((e, i) => ({ e, i }))
    .sort(
      (a, b) =>
        (a.e.year ?? 0) - (b.e.year ?? 0) ||
        Number(a.e.kind !== 'chapter') - Number(b.e.kind !== 'chapter') ||
        a.i - b.i,
    )
    .map(({ e }) => e)
}

/** Fehler je Feld, wie der Server sie prüft */
export function entryErrors(e: TimelineEntry): Partial<Record<keyof TimelineEntry, string>> {
  const errors: Partial<Record<keyof TimelineEntry, string>> = {}
  if (e.year === null || e.year < MIN_YEAR || e.year > MAX_YEAR)
    errors.year = t('Bitte ein Jahr zwischen 1000 und 2999 angeben.')
  if (e.until !== null) {
    if (e.until < MIN_YEAR || e.until > MAX_YEAR) errors.until = t('Das Jahr „bis“ ist ungültig.')
    else if (e.year !== null && e.until < e.year)
      errors.until = t('Das Jahr „bis“ liegt vor dem Jahr.')
  }
  if (!e.title.trim()) errors.title = t('Bitte eine Überschrift angeben.')
  else if (e.title.length > MAX_TITLE)
    errors.title = t('Die Überschrift darf höchstens {n} Zeichen haben.', { n: MAX_TITLE })
  if (e.text.length > MAX_TEXT)
    errors.text = t('Der Text darf höchstens {n} Zeichen haben.', { n: MAX_TEXT })
  return errors
}

export function yearValue(text: string): number | null {
  const n = Number(text.trim())
  return text.trim() && Number.isInteger(n) ? n : null
}
