// Bilder der Webseite (Ralf 01.11.): Übersicht als Kacheln mit Suche und Filtern,
// Fenster „Bild bearbeiten“ (Ausschnitt neu wählen, Angaben, Zuordnung zu einer
// Untereinheit, ersetzen, kopieren, löschen) und ein Auswahl-Dialog für Texte, der
// auf Seiten einer Untereinheit zuerst deren Bilder zeigt.
// Diese Datei: gemeinsame Helfer, Typen und Konstanten des Bereichs.
import type { WebsiteImage } from '../../api/website.ts'
import { needsAlt } from './imageTools.ts'

export interface Unit {
  id: number
  name: string
}

export const ACCEPT = 'image/jpeg,image/png,image/webp'
export const PAGE_SIZE = 40
export type Scope = 'all' | 'general' | number
export type State = 'all' | 'unused' | 'no_alt'

export function matches(i: WebsiteImage, q: string, scope: Scope, state: State): boolean {
  if (scope === 'general' && i.department) return false
  if (typeof scope === 'number' && i.department !== scope) return false
  if (state === 'unused' && i.used !== false) return false
  if (state === 'no_alt' && !needsAlt(i)) return false
  if (q) {
    const hay = [i.caption, i.alt_text, i.credit ?? '', i.department_name ?? '']
      .join(' ')
      .toLowerCase()
    if (
      !q
        .toLowerCase()
        .split(/\s+/)
        .every((w) => hay.includes(w))
    )
      return false
  }
  return true
}
