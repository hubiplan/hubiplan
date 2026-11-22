// Anordnung des Menüs je Einheit (konzepte/menue-frei-anordnen.md).
//
// Die Standardanordnung steht in modules.tsx (AREAS und das Feld `area` je Menüpunkt). Eine
// Einheit kann davon abweichen: andere Reihenfolge der Hauptmenüpunkte, eigene Bereiche mit
// eigenem Namen, ein Menüpunkt als eigener Hauptmenüpunkt oder in einem anderen Bereich.
// Gespeichert werden nur die Abweichungen (backend/organizations/menu_layout.py, gleiche Regeln).
// Die Anordnung bestimmt nur den Ort; was jemand sieht, entscheiden Module und Rechte.
import type { ReactNode } from 'react'
import { AREAS, modules } from './modules.tsx'
import type { AppModule } from './modules.tsx'
import { lang, t } from './i18n/index.ts'

export interface MenuLayoutArea {
  id: string
  label?: string
  label_en?: string
  /** Kennung eines Bereichs oder Menüpunkts, dessen Zeichen der Bereich trägt */
  icon?: string
}

export interface MenuLayout {
  v: 1
  areas: MenuLayoutArea[]
  /** Nur Abweichungen: Menüpunkt → Bereich */
  items: Record<string, string>
}

export const MAX_AREAS = 12
export const MIN_AREAS = 2
export const MAX_LABEL = 24
/** Menüpunkte, die nicht verschoben werden */
export const FIXED_ITEMS = new Set(['start', 'plattform'])

export type AreaKind = 'standard' | 'item' | 'custom'

export interface ArrangedArea {
  id: string
  label: string
  icon: ReactNode
  kind: AreaKind
  /** Die Einheit hat dem Bereich selbst einen Namen gegeben */
  named: boolean
}

const STANDARD_IDS = AREAS.map((a) => a.id as string)
const MODULE_IDS = modules.map((m) => m.id)
const isCustom = (id: string) => /^b[1-9][0-9]?$/.test(id)

export function kindOf(id: string): AreaKind {
  if (STANDARD_IDS.includes(id)) return 'standard'
  if (isCustom(id)) return 'custom'
  return 'item'
}

/** Zeichen zu einer Kennung (Bereich oder Menüpunkt) */
export function iconOf(key: string | undefined): ReactNode {
  if (!key) return null
  return AREAS.find((a) => a.id === key)?.icon ?? modules.find((m) => m.id === key)?.icon ?? null
}

/** Name eines Bereichs in der aktuellen Sprache */
export function areaLabel(area: MenuLayoutArea): string {
  const own = lang() === 'en' ? area.label_en || area.label : area.label
  if (own) return own
  const std = AREAS.find((a) => a.id === area.id)
  if (std) return std.label
  const m = modules.find((x) => x.id === area.id)
  return m ? m.label : t('Neuer Bereich')
}

/** Bereiche der Einheit in Leistenreihenfolge */
export function arrangedAreas(layout: MenuLayout | null | undefined): ArrangedArea[] {
  const list: MenuLayoutArea[] = layout ? layout.areas : STANDARD_IDS.map((id) => ({ id }))
  return list.map((a) => ({
    id: a.id,
    label: areaLabel(a),
    icon: iconOf(a.icon) ?? iconOf(a.id) ?? iconOf('verein'),
    kind: kindOf(a.id),
    named: !!a.label,
  }))
}

/** Bereich eines Menüpunkts (gleiche Regeln wie menu_layout.area_of im Backend) */
export function areaOf(layout: MenuLayout | null | undefined, m: Pick<AppModule, 'id' | 'area'>) {
  const fallback: string = m.area
  if (!layout) return fallback
  const ids = layout.areas.map((a) => a.id)
  if (m.id === 'plattform') return ids.includes(fallback) ? fallback : ids[ids.length - 1]
  const chosen = layout.items?.[m.id]
  if (chosen && ids.includes(chosen)) return chosen
  if (ids.includes(m.id)) return m.id
  if (ids.includes(fallback)) return fallback
  return ids.length > 1 ? ids[1] : ids[0]
}

/** Anordnung als vollständige Liste (für den Editor): Bereiche mit ihren Menüpunkten */
export interface Arrangement {
  areas: MenuLayoutArea[]
  /** Bereich → Menüpunkte in Standardreihenfolge */
  items: Record<string, string[]>
}

export function toArrangement(layout: MenuLayout | null | undefined): Arrangement {
  const areas = layout ? layout.areas.map((a) => ({ ...a })) : STANDARD_IDS.map((id) => ({ id }))
  const items: Record<string, string[]> = Object.fromEntries(areas.map((a) => [a.id, []]))
  for (const m of modules) {
    const area = areaOf(layout ? { ...layout, areas } : null, m)
    ;(items[area] ??= []).push(m.id)
  }
  return { areas, items }
}

/** Speicherbare Anordnung aus der vollständigen Liste: nur Abweichungen; null = Standard */
export function fromArrangement(arr: Arrangement): MenuLayout | null {
  const layout: MenuLayout = { v: 1, areas: arr.areas.map((a) => ({ ...a })), items: {} }
  for (const [area, list] of Object.entries(arr.items)) {
    for (const id of list) {
      if (id === 'plattform') continue
      const m = modules.find((x) => x.id === id)
      if (!m) continue
      if (areaOf({ ...layout, items: {} }, m) !== area) layout.items[id] = area
    }
  }
  const standard =
    layout.areas.map((a) => a.id).join() === STANDARD_IDS.join() &&
    layout.areas.every((a) => Object.keys(a).length === 1) &&
    Object.keys(layout.items).length === 0
  return standard ? null : layout
}

/** Nächste freie Kennung für einen eigenen Bereich */
export function nextCustomId(areas: MenuLayoutArea[]): string {
  for (let i = 1; i < 100; i++) if (!areas.some((a) => a.id === `b${i}`)) return `b${i}`
  return 'b99'
}

/** Zeichen, die ein eigener Bereich tragen kann */
export const ICON_KEYS: string[] = [
  ...STANDARD_IDS,
  ...MODULE_IDS.filter((id) => id !== 'plattform'),
]
