// Vergleich von Zellwerten für DataTable und useRowSort: Zahlen numerisch, Texte nach deutscher
// Sortierung mit Zahlen im Text („Zug 2“ vor „Zug 10“), leere Werte immer ans Ende.
export type CellValue = string | number | boolean | null | undefined

const collator = new Intl.Collator('de', { numeric: true, sensitivity: 'base' })

export function compareCells(a: CellValue, b: CellValue): number {
  const emptyA = a === null || a === undefined || a === ''
  const emptyB = b === null || b === undefined || b === ''
  if (emptyA || emptyB) return emptyA === emptyB ? 0 : emptyA ? 1 : -1
  if (typeof a === 'number' && typeof b === 'number') return a - b
  if (typeof a === 'boolean' && typeof b === 'boolean') return Number(b) - Number(a)
  return collator.compare(String(a), String(b))
}
