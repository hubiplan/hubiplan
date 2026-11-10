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
} as const

export interface HomeBlock {
  key: string
  label: string
  /** Standard: über die ganze Breite */
  wide?: boolean
  render: () => ReactNode
}

export interface PlacedBlock extends HomeBlock {
  shown: boolean
  wide: boolean
}

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
  const wide = new Set(layout?.wide ?? [])
  return order.map((key) => {
    const b = byKey.get(key) as HomeBlock
    return {
      ...b,
      shown: !hidden.has(key),
      // Breite nur übernehmen, wenn der Block beim Speichern schon dabei war
      wide: layout && known.has(key) ? wide.has(key) : !!b.wide,
    }
  })
}

/** Stand zum Speichern: alle Blöcke in Reihenfolge, ausgeblendete und breite. */
export function layoutOf(placed: PlacedBlock[]): HomeLayout {
  return {
    order: placed.map((b) => b.key),
    hidden: placed.filter((b) => !b.shown).map((b) => b.key),
    wide: placed.filter((b) => b.wide).map((b) => b.key),
  }
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
