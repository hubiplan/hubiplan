// Gemeinsame Angaben für Rollen aller Einheiten (Liste und Maske: RoleEditor.tsx)
import type { CatalogModule } from '../api/orgs.ts'
import { t } from '../i18n/index.ts'

export interface RoleValues {
  name: string
  description: string
  is_board: boolean
  represents: boolean
  on_letterhead: boolean
  contact_email: string
  on_website: boolean
  in_chronicle: boolean
  permissions: string[]
}

export type RoleField = Exclude<keyof RoleValues, 'name' | 'permissions'>

/** Rolle, wie sie in Liste und Maske erscheint */
export interface RoleLike extends Partial<RoleValues> {
  id: number
  name: string
  permissions: string[]
  /** Inhaber: Anzahl oder Namen */
  holders: number | string[]
}

const FULL: RoleField[] = [
  'description',
  'is_board',
  'represents',
  'on_letterhead',
  'contact_email',
  'on_website',
  'in_chronicle',
]
/** Angaben, die Rollen einer Untereinheit (Zuordnung über die Mitgliederakte) haben */
export const UNIT_ROLE_FIELDS: RoleField[] = ['on_letterhead', 'contact_email', 'on_website']
export const ALL_ROLE_FIELDS = FULL

export type Level = 'none' | 'view' | 'edit'

/** Stufe einer Rolle in einem Bereich */
export function levelOf(codes: string[], area: CatalogModule): Level {
  const levels = area.levels ?? []
  if (levels.some((l) => l.level === 'edit' && codes.includes(l.code))) return 'edit'
  if (levels.some((l) => l.level === 'view' && codes.includes(l.code))) return 'view'
  return 'none'
}

/** Stufe setzen: Bearbeiten schließt Lesen ein; ohne Lesen fallen abhängige Zusatzrechte weg */
export function withLevel(
  codes: string[],
  area: CatalogModule,
  level: Level,
  catalog: CatalogModule[],
): string[] {
  const own = (area.levels ?? []).map((l) => l.code)
  let next = codes.filter((c) => !own.includes(c))
  const view = area.levels?.find((l) => l.level === 'view')?.code
  const edit = area.levels?.find((l) => l.level === 'edit')?.code
  if (level === 'view' && view) next.push(view)
  if (level === 'edit') {
    if (view) next.push(view)
    if (edit) next.push(edit)
  }
  if (level === 'none' && view) {
    const extras = catalog.filter((m) => m.kind === 'extras').flatMap((m) => m.permissions)
    next = next.filter((c) => !extras.some((e) => e.code === c && e.needs === view))
  }
  return next
}

export function permissionLabels(codes: string[], catalog: CatalogModule[]): string {
  if (codes.length === 0) return t('keine')
  const labels = catalog.flatMap((m) => m.permissions).filter((p) => codes.includes(p.code))
  return labels.map((p) => p.label).join(', ')
}

export interface PermissionArea {
  label: string
  /** höchste Stufe des Bereichs (bzw. alle Rechte des Bereichs) */
  full: boolean
  /** Stufe als Text („lesen“, „bearbeiten“) oder die einzelnen Rechte */
  permissions: string[]
}

/** Rechte nach Bereichen des Katalogs zusammengefasst (für die kurze Übersicht) */
export function permissionAreas(codes: string[], catalog: CatalogModule[]): PermissionArea[] {
  return catalog
    .map((m) => {
      if (m.kind === 'area') {
        const level = levelOf(codes, m)
        const top = m.levels?.[m.levels.length - 1]?.level
        return {
          label: m.label,
          full: level === top,
          permissions: level === 'none' ? [] : [level === 'edit' ? t('bearbeiten') : t('lesen')],
        }
      }
      const held = m.permissions.filter((p) => codes.includes(p.code))
      return {
        label: m.label,
        full: m.kind === 'extras' || held.length === m.permissions.length,
        permissions: held.map((p) => p.label),
      }
    })
    .filter((a) => a.permissions.length > 0)
}
