// Sortieren für Listen, die als einfache Tabelle im Browser stehen (UX-Audit 16.11. VW-21):
// dieselben Spaltenköpfe wie DataTable (Knopf, ▲/▼, aria-sort), ohne die Tabelle umzubauen.
// Zusammen mit useRowSearch: erst suchen, dann sortieren.
import { useState } from 'react'
import type { ReactNode, ThHTMLAttributes } from 'react'
import { compareCells, type CellValue } from './sorting.ts'

export type RowSortState = { key: string; dir: 'asc' | 'desc' }

/**
 * `values` nennt je sortierbarer Spalte den Wert einer Zeile (Zahl, Datum als ISO-Text, Text).
 * `rows` kommen sortiert zurück; `head(key, label)` ist der fertige Spaltenkopf. Ohne Klick
 * bleibt die Reihenfolge des Servers, außer `initial` sagt etwas anderes.
 */
export function useRowSort<T>(
  rows: T[],
  values: Record<string, (row: T) => CellValue>,
  initial: RowSortState | null = null,
): {
  rows: T[]
  sort: RowSortState | null
  head: (key: string, label: ReactNode, props?: ThHTMLAttributes<HTMLTableCellElement>) => ReactNode
} {
  const [sort, setSort] = useState<RowSortState | null>(initial)
  const value = sort ? values[sort.key] : undefined
  const sorted =
    sort && value
      ? [...rows].sort((a, b) => {
          const r = compareCells(value(a), value(b))
          return sort.dir === 'asc' ? r : -r
        })
      : rows
  function head(key: string, label: ReactNode, props?: ThHTMLAttributes<HTMLTableCellElement>) {
    const active = sort?.key === key
    return (
      <th
        scope="col"
        {...props}
        aria-sort={active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : undefined}
      >
        <button
          type="button"
          className={`th-sort${active ? ' th-sort-active' : ''}`}
          onClick={() =>
            setSort((s) =>
              s?.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'asc' },
            )
          }
        >
          {label}
          <span className="sort-mark" aria-hidden="true">
            {active ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ' ↕'}
          </span>
        </button>
      </th>
    )
  }
  return { rows: sorted, sort, head }
}
