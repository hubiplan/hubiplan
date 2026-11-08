// Hilfe: Ort eines Eintrags im Menü (konzepte/hilfe-neustruktur.md, HN1).
//
// Die Hilfe ist so gegliedert wie die Seitenleiste: Gruppe › Menüpunkt. Der Ort folgt aus der
// ersten Route des Eintrags (oder dem Feld „menue“), damit Hilfe und Menü nie auseinanderlaufen.
import { t } from '../i18n/index.ts'
import { GROUP_LABELS, modules } from '../modules.tsx'
import type { AppModule } from '../modules.tsx'
import type { OrgSummary } from '../api/orgs.ts'
import type { HelpEntry } from './content.ts'

export type HelpGroup = AppModule['group'] | 'konto' | 'plattform'

/** Gruppen in der Reihenfolge der Seitenleiste; Mein Konto und Plattform am Ende. */
export const HELP_GROUPS: readonly HelpGroup[] = [
  'alltag',
  'planen',
  'verein',
  'organisation',
  'verwaltung',
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
export function placeOf(entry: Pick<HelpEntry, 'routes' | 'menu'>): MenuPlace | null {
  const route = entry.menu ?? entry.routes[0]
  if (!route) return null
  const top = route === '/' ? '/' : `/${route.split('/')[1]}`
  if (ACCOUNT_ROUTES.includes(top)) return { group: 'konto', item: 'konto', index: modules.length }
  const index = modules.findIndex((m) => m.path === top || m.also?.includes(top))
  if (index < 0) return null
  const m = modules[index]
  if (m.id === 'plattform') return { group: 'plattform', item: m.id, index }
  return { group: m.group, item: m.id, index }
}

export function groupLabel(group: HelpGroup): string {
  if (group === 'konto') return t('Mein Konto')
  if (group === 'plattform') return t('Plattform')
  return GROUP_LABELS[group]
}

/** Name des Menüpunkts, wie die Seitenleiste ihn für die Einheit zeigt (z. B. „Züge“). */
export function itemLabel(item: string, org: OrgSummary | null): string {
  if (item === 'konto') return t('Mein Konto')
  const m = modules.find((x) => x.id === item)
  if (!m) return item
  return m.labelFor?.(org, { dept: null, portal: null }) ?? m.label
}

/** Teil innerhalb eines Menüpunkts (nur Finanzen: Beiträge oder Kasse, wie im Menü). */
export function partOf(entry: Pick<HelpEntry, 'module'>, item: string): string | null {
  if (item !== 'finanzen') return null
  return entry.module === 'billing' ? t('Beiträge und Rechnungen') : t('Kasse und Abschluss')
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
export function byMenu(entries: HelpEntry[]): HelpSection[] {
  const placed = entries
    .map((e) => ({ e, p: placeOf(e) }))
    .filter((x): x is { e: HelpEntry; p: MenuPlace } => !!x.p)
  return HELP_GROUPS.map((group) => {
    const inGroup = placed.filter((x) => x.p.group === group)
    const itemIds = [...new Set(inGroup.sort((a, b) => a.p.index - b.p.index).map((x) => x.p.item))]
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
  }).filter((s) => s.items.length > 0)
}
