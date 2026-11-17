// Suchfeld für Listen, die als einfache Tabelle im Browser stehen (UX-Audit 16.11. VW-21):
// ab mehr als 20 Zeilen erscheint über der Tabelle ein Suchfeld, darunter bleibt alles wie
// bisher. Für Sortieren, Filter und Seiten ist DataTable da, für sehr lange Listen die
// serverseitige Suche (ListControls).
import { useState } from 'react'
import type { ReactNode } from 'react'
import { t } from '../i18n/index.ts'
import { fold } from './quickSearchEvents.ts'

export const ROW_SEARCH_MIN = 20

/**
 * `shown` sind die Zeilen, deren Suchtext alle eingegebenen Wörter enthält; `field` ist das
 * Suchfeld (oder null bei kurzen Listen) und gehört direkt über die Tabelle.
 */
export function useRowSearch<T>(
  rows: T[],
  text: (row: T) => string,
  label: string,
): { shown: T[]; field: ReactNode } {
  const [term, setTerm] = useState('')
  if (rows.length <= ROW_SEARCH_MIN) return { shown: rows, field: null }
  const words = fold(term).split(/\s+/).filter(Boolean)
  const shown =
    words.length === 0
      ? rows
      : rows.filter((row) => {
          const hay = fold(text(row))
          return words.every((w) => hay.includes(w))
        })
  const field = (
    <div className="row-search">
      <label className="field">
        <span>{t('Suchen')}</span>
        <input
          type="search"
          className="search-input"
          aria-label={t('{label} durchsuchen', { label })}
          value={term}
          onChange={(e) => setTerm(e.target.value)}
        />
      </label>
      <p className="muted small" aria-live="polite">
        {words.length > 0 && t('{n} von {n2} Einträgen', { n: shown.length, n2: rows.length })}
      </p>
    </div>
  )
  return { shown, field }
}
