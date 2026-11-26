// Hilfe: Ort eines Eintrags im Menü (konzepte/hilfe-neustruktur.md, HN1).
//
// Die Hilfe ist so gegliedert wie das Menü: Bereich › Menüpunkt. Der Ort folgt aus der
// ersten Route des Eintrags (oder dem Feld „menue“), damit Hilfe und Menü nie auseinanderlaufen.
import { t } from '../i18n/index.ts'
import { modules } from '../modules.tsx'
import type { AreaId } from '../modules.tsx'
import { areaOf, arrangedAreas } from '../menuLayout.ts'
import type { MenuLayout } from '../menuLayout.ts'
import type { OrgSummary } from '../api/orgs.ts'
import type { HelpEntry } from './content.ts'
import { financeGroups, financeSections } from '../pages/finanzen/access.ts'
import type { FinanceAccess } from '../pages/finanzen/access.ts'

// Bereiche der Einheit (Menü frei anordnen): Standard oder eigene Kennungen
export type HelpGroup = AreaId | 'konto' | 'plattform' | (string & {})

/** Bereiche in der Reihenfolge der Bereichsleiste; Mein Konto und Plattform am Ende. */
export const HELP_GROUPS: readonly HelpGroup[] = [
  'start',
  'mitglieder',
  'untereinheiten',
  'planung',
  'kommunikation',
  'webseite',
  'vereinsleben',
  'finanzen',
  'verein',
  'konto',
  'plattform',
]

export interface MenuPlace {
  group: HelpGroup
  /** Menüpunkt: id des Moduls oder „konto“ */
  item: string
  /** Position in der Seitenleiste (zum Sortieren) */
  index: number
}

const ACCOUNT_ROUTES = ['/mein-konto', '/briefvorlage']

/** Ort eines Eintrags im Menü; null, wenn seine Route zu keinem Menüpunkt gehört. */
export function placeOf(
  entry: Pick<HelpEntry, 'routes' | 'menu'>,
  layout: MenuLayout | null = null,
): MenuPlace | null {
  const route = entry.menu ?? entry.routes[0]
  if (!route) return null
  const top = route === '/' ? '/' : `/${route.split('/')[1]}`
  if (ACCOUNT_ROUTES.includes(top)) return { group: 'konto', item: 'konto', index: modules.length }
  const index = modules.findIndex((m) => m.path === top || m.also?.includes(top))
  if (index < 0) return null
  const m = modules[index]
  if (m.id === 'plattform') return { group: 'plattform', item: m.id, index }
  return { group: areaOf(layout, m), item: m.id, index }
}

/** Gruppen der Hilfe in Leistenreihenfolge der Einheit; Mein Konto und Plattform am Ende. */
export function helpGroups(layout: MenuLayout | null = null): HelpGroup[] {
  return layout ? [...layout.areas.map((a) => a.id), 'konto', 'plattform'] : [...HELP_GROUPS]
}

export function groupLabel(group: HelpGroup, layout: MenuLayout | null = null): string {
  if (group === 'konto') return t('Mein Konto')
  if (group === 'plattform') return t('Plattform')
  return arrangedAreas(layout).find((a) => a.id === group)?.label ?? group
}

/** Name des Menüpunkts, wie die Seitenleiste ihn für die Einheit zeigt (z. B. „Züge“). */
export function itemLabel(item: string, org: OrgSummary | null): string {
  if (item === 'konto') return t('Mein Konto')
  const m = modules.find((x) => x.id === item)
  if (!m) return item
  return m.labelFor?.(org, { dept: null, portal: null }) ?? m.label
}

// Alle Einträge von Finanzen, wie sie mit allen Modulen und Rechten erscheinen
const FINANCE_ALL: FinanceAccess = {
  finance: true,
  financeEdit: true,
  billing: true,
  billingEdit: true,
  feeRuns: true,
  sepa: true,
  received: true,
  receivedLabel: '',
  donations: true,
  cashCounts: true,
  reserves: true,
  tax: true,
  payouts: true,
  expenses: true,
  expensesEdit: true,
  expensesPay: true,
}

/**
 * Teil innerhalb eines Menüpunkts: bei Finanzen die Arbeitsgruppe der Seitenleiste
 * (Konzept S-01), sonst keiner. Ordnet nach der ersten Route des Eintrags.
 */
export function partOf(entry: Pick<HelpEntry, 'routes'>, item: string): string | null {
  if (item !== 'finanzen') return null
  const route = (entry.routes[0] ?? '').split(/[?#]/)[0]
  const items = financeSections(FINANCE_ALL)
  const page = items.find((i) => i.group?.to === route)
  if (page?.group) return page.group.label
  const hit = items
    .filter((i) => route === i.to || route.startsWith(`${i.to}/`))
    .sort((x, y) => y.to.length - x.to.length)[0]
  return hit?.group?.label ?? null
}

/** Reihenfolge der Teile wie in der Seitenleiste (Teil ohne Gruppe zuerst). */
export function partRank(part: string | null): number {
  if (part === null) return -1
  return Object.values(financeGroups()).findIndex((g) => g.label === part)
}

/** Seitenhilfe der Hauptseite des Menüpunkts zuerst, dann nach „reihe“, dann nach Titel. */
function byOrder(item: string) {
  const path = modules.find((m) => m.id === item)?.path
  const main = (e: HelpEntry) => (e.kind === 'page' && e.routes[0] === path ? 0 : 1)
  return (a: HelpEntry, b: HelpEntry) =>
    main(a) - main(b) || (a.order ?? 1000) - (b.order ?? 1000) || a.title.localeCompare(b.title)
}

export interface HelpItem {
  item: string
  entries: HelpEntry[]
}
export interface HelpSection {
  group: HelpGroup
  items: HelpItem[]
}

/** Einträge nach Gruppe und Menüpunkt, in der Reihenfolge der Seitenleiste. */
export function byMenu(entries: HelpEntry[], layout: MenuLayout | null = null): HelpSection[] {
  const placed = entries
    .map((e) => ({ e, p: placeOf(e, layout) }))
    .filter((x): x is { e: HelpEntry; p: MenuPlace } => !!x.p)
  return helpGroups(layout)
    .map((group) => {
      const inGroup = placed.filter((x) => x.p.group === group)
      const itemIds = [
        ...new Set(inGroup.sort((a, b) => a.p.index - b.p.index).map((x) => x.p.item)),
      ]
      return {
        group,
        items: itemIds.map((item) => ({
          item,
          entries: inGroup
            .filter((x) => x.p.item === item)
            .map((x) => x.e)
            .sort(byOrder(item)),
        })),
      }
    })
    .filter((s) => s.items.length > 0)
}

/**
 * Platzhalter `{bereich:<Menüpunkt>}` im Hilfetext: Name des Bereichs, in dem der Menüpunkt bei
 * der Einheit steht (Menü frei anordnen). Ohne Anordnung der vorgegebene Bereich.
 */
export function fillAreas(
  text: string,
  layout: MenuLayout | null = null,
  transform?: (value: string) => string,
): string {
  return text.replace(/\{bereich:([a-z-]+)\}/g, (all, id: string) => {
    const m = modules.find((x) => x.id === id)
    if (!m) return all
    const label = groupLabel(areaOf(layout, m), layout)
    return transform ? transform(label) : label
  })
}
