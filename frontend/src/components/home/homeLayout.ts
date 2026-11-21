// Startseite selbst zusammenstellen (S-04): Welche Blöcke in welcher Reihenfolge und Breite
// erscheinen, wählt jede Person je Arbeitsbereich. Ohne eigene Anordnung gilt der Standard der
// Rolle; Blöcke, die erst später dazukommen, erscheinen an ihrer Standardstelle.
import type { ReactNode } from 'react'
import type { HomeLayout } from '../../api/homeActions.ts'
import { PERM } from '../../api/orgs.ts'
import type { OrgSummary } from '../../api/orgs.ts'

export const BLOCK = {
  tasks: 'zu-erledigen',
  deptTodos: 'aufgaben',
  actions: 'schnellaktionen',
  upcoming: 'termine',
  jubilees: 'jubilaeen',
  birthdays: 'geburtstage',
  notices: 'hinweise',
  // Mitgliederbereich
  nextEvent: 'naechster-termin',
  memberArea: 'mein-bereich',
} as const

/** Raster der Startseite: 12 Spalten, Zeilen zu je ROW_REM */
export const GRID_COLUMNS = 12
export const MIN_COLUMNS = 3
/** Höhe einer Rasterzeile in rem; fein genug, dass Blöcke in Lücken nachrutschen */
export const ROW_REM = 0.5
export const MIN_ROWS = 6
export const MAX_ROWS = 300

/** Auswahl bei Kacheln, die von selbst nur bei Anlass erscheinen */
export type BlockChoice = 'auto' | 'on' | 'off'

export interface HomeBlock {
  key: string
  label: string
  /** Standard: über die ganze Breite */
  wide?: boolean
  /** Kachel bei Anlass (backend/hometiles): ohne eigene Wahl nur sichtbar, wenn `urgent` */
  optional?: boolean
  /** Es gibt gerade einen Anlass */
  urgent?: boolean
  render: () => ReactNode
}

export interface PlacedBlock extends HomeBlock {
  shown: boolean
  /** Nur bei `optional`: bei Anlass, immer, nie */
  choice: BlockChoice
  /** Breite in Spalten (von 12) */
  cols: number
  /** Höhe in Rasterzeilen; null = so hoch wie der Inhalt */
  rows: number | null
}

export const clampCols = (n: number) => Math.max(MIN_COLUMNS, Math.min(GRID_COLUMNS, Math.round(n)))
export const clampRows = (n: number) => Math.max(MIN_ROWS, Math.min(MAX_ROWS, Math.round(n)))

/**
 * Ordnet die verfügbaren Blöcke (in Standardreihenfolge) nach der eigenen Anordnung. Fremde
 * Schlüssel fallen weg, neue Blöcke kommen hinter ihren Standard-Vorgänger.
 */
export function placeBlocks(blocks: HomeBlock[], layout?: HomeLayout | null): PlacedBlock[] {
  const byKey = new Map(blocks.map((b) => [b.key, b]))
  const known = new Set(layout?.order ?? [])
  const order = (layout?.order ?? []).filter((k) => byKey.has(k))
  blocks.forEach((b, i) => {
    if (order.includes(b.key)) return
    const before = blocks
      .slice(0, i)
      .map((x) => x.key)
      .filter((k) => order.includes(k))
      .at(-1)
    order.splice(before === undefined ? 0 : order.indexOf(before) + 1, 0, b.key)
  })
  const hidden = new Set(layout?.hidden ?? [])
  const always = new Set(layout?.shown ?? [])
  const wide = new Set(layout?.wide ?? [])
  const sizes = layout?.sizes ?? {}
  return order.map((key) => {
    const b = byKey.get(key) as HomeBlock
    const size = sizes[key]
    // Breite aus „wide“ nur, wenn der Block beim Speichern schon dabei war (ältere Fassung)
    const isWide = layout && known.has(key) ? wide.has(key) : !!b.wide
    const choice: BlockChoice = always.has(key) ? 'on' : hidden.has(key) ? 'off' : 'auto'
    return {
      ...b,
      choice,
      shown: b.optional ? choice === 'on' || (choice === 'auto' && !!b.urgent) : !hidden.has(key),
      cols: size ? clampCols(size.w) : isWide ? GRID_COLUMNS : GRID_COLUMNS / 2,
      rows: size?.h ? clampRows(size.h) : null,
    }
  })
}

/**
 * Stand zum Speichern: alle Blöcke in Reihenfolge, ausgeblendete, breite und Größen. Kacheln bei
 * Anlass stehen nur mit eigener Wahl in `shown` (immer) bzw. `hidden` (nie).
 */
export function layoutOf(placed: PlacedBlock[]): HomeLayout {
  return {
    order: placed.map((b) => b.key),
    hidden: placed
      .filter((b) => (b.optional ? b.choice === 'off' : !b.shown))
      .map((b) => b.key),
    shown: placed.filter((b) => b.optional && b.choice === 'on').map((b) => b.key),
    wide: placed.filter((b) => b.cols === GRID_COLUMNS).map((b) => b.key),
    sizes: Object.fromEntries(placed.map((b) => [b.key, { w: b.cols, h: b.rows }])),
  }
}

/** Breite als Bruch für Menschen: 6 → „½“, 5 → „5/12“ */
export function widthLabel(cols: number): string {
  const named: Record<number, string> = { 3: '¼', 4: '⅓', 6: '½', 8: '⅔', 9: '¾' }
  return named[cols] ?? `${cols}/12`
}

function showsPeople(org: OrgSummary): boolean {
  return (
    org.type === 'club' &&
    org.modules.includes('members') &&
    org.permissions.includes(PERM.membersView)
  )
}

/** Kann die Einheit eine Jubiläen-Karte haben? (Für die Auswahl der Blöcke) */
export const hasJubilees = (org: OrgSummary) => showsPeople(org) && org.modules.includes('awards')
/** Kann die Einheit eine Geburtstags-Karte haben? */
export const hasBirthdays = showsPeople
