// Pfad der aktuellen Seite aus der Menüstruktur (Seitenkopf S-05): Modul, Unterpunkt der
// Seitenleiste und die von der Seite angemeldeten Unterpunkte (Reiter). Layout berechnet ihn
// einmal; Seitentitel, h1 und Pfadzeile im Seitenkopf lesen dieselbe Quelle.
import { createContext, useContext } from 'react'
import { buildNavTree } from './subnav.ts'
import type { NavNode, SubNavItem } from './subnav.ts'
import { t } from '../i18n/index.ts'

export interface TrailItem {
  to: string
  label: string
}

export interface NavTrailValue {
  /** Vom Modul bis zur aktuellen Seite; leer außerhalb der Bereiche */
  trail: TrailItem[]
  /** Name der gewählten Einheit, nur wenn die Person mehrere Einheiten wählen kann */
  unit: string | null
}

export const NavTrailContext = createContext<NavTrailValue>({ trail: [], unit: null })

export function useNavTrail(): NavTrailValue {
  return useContext(NavTrailContext)
}

const covers = (parent: string, path: string) => path === parent || path.startsWith(`${parent}/`)

/**
 * Kette vom Modul bis zum tiefsten Menüpunkt, der zum Pfad passt. Ein Unterpunkt mit dem
 * Pfad seines Elternpunkts (z. B. „Übersicht“) gehört zum Elternpunkt selbst.
 */
export function navTrail(
  pathname: string,
  mod: { path: string; label: string; link?: string } | null,
  fixed: SubNavItem[],
  registered: SubNavItem[][],
): TrailItem[] {
  if (!mod) return []
  const path = pathname.replace(/(.)\/$/, '$1')
  const trail: TrailItem[] = [{ to: mod.link ?? mod.path, label: mod.label }]
  let nodes: NavNode[] = buildNavTree(mod.path, fixed, registered)
  let parent = mod.path
  for (;;) {
    const from = parent
    const next = nodes
      .filter((n) => n.to !== from && covers(n.to, path))
      .sort((a, b) => b.to.length - a.to.length)[0]
    if (!next) break
    trail.push({ to: next.to, label: next.label })
    parent = next.to
    nodes = next.children
  }
  // Dritte Ebene, die der Baum nicht einhängt: tiefster angemeldeter Unterpunkt (W-02)
  const deep = registered
    .flat()
    .filter((c) => c.to.length > parent.length && covers(c.to, path))
    .sort((a, b) => b.to.length - a.to.length)[0]
  if (deep) trail.push({ to: deep.to, label: deep.label })
  // Gleich benannte Glieder hintereinander (Unterpunkt heißt wie der Bereich) nur einmal
  return trail.filter((item, i) => i === 0 || item.label !== trail[i - 1].label)
}

/** Seitentitel aus dem Pfad: tiefste Ebene zuerst („Mahnungen · Rechnungen · Finanzen“). */
export function trailTitle(trail: TrailItem[], title?: string | null): string | null {
  const parts = [...(title ? [title] : []), ...trail.map((i) => i.label).reverse()]
  if (parts.length === 0) return null
  return parts.reduce((all, label) => t('{label} · {modLabel}', { label: all, modLabel: label }))
}
