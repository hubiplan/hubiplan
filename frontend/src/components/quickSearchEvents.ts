// Terminsuche der Schnellsuche (UX-Audit 16.11. VW-59), getrennt von der Komponente.
import type { Occurrence } from '../api/events.ts'
import { berlin, today } from './calendar/time.ts'

const MAX_EVENTS = 6

export function fold(text: string): string {
  return text.toLocaleLowerCase('de').normalize('NFD').replace(/[̀-ͯ]/g, '')
}

/**
 * Termine, deren Titel alle Suchwörter enthält; je Serie nur die nächste Ausgabe, kommende
 * zuerst (UX-Audit 16.11. VW-59).
 */
export function matchEvents(items: Occurrence[], term: string, from = today()): Occurrence[] {
  const words = fold(term).split(/\s+/).filter(Boolean)
  if (words.length === 0) return []
  const upcoming: Occurrence[] = []
  const past: Occurrence[] = []
  const seen = new Set<number>()
  const sorted = [...items].sort((a, b) => a.starts_at.localeCompare(b.starts_at))
  const fits = (o: Occurrence) => {
    const title = fold(o.title)
    return words.every((w) => title.includes(w))
  }
  for (const o of sorted) {
    if (berlin(o.starts_at).date < from || seen.has(o.event_id) || !fits(o)) continue
    seen.add(o.event_id)
    upcoming.push(o)
  }
  for (const o of sorted.reverse()) {
    if (berlin(o.starts_at).date >= from || seen.has(o.event_id) || !fits(o)) continue
    seen.add(o.event_id)
    past.push(o)
  }
  return [...upcoming, ...past].slice(0, MAX_EVENTS)
}
