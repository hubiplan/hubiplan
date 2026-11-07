// Modulverzeichnis (access/modules.py): einzige Quelle für Namen, Gruppen und Voraussetzungen
import { api } from './client.ts'

export interface ModuleInfo {
  id: string
  label: string
  description: string
  default: boolean
  requires: string[]
  requires_any: string[]
  org_types: string[]
}

export interface ModuleGroup {
  id: string
  label: string
  modules: ModuleInfo[]
}

/** Modul einer Einheit unter Einstellungen › Module */
export interface OrgModule {
  id: string
  label: string
  description: string
  requires: string[]
  requires_any: string[]
  released: boolean
  enabled: boolean
  needed_by: string[]
}

export interface OrgModules {
  groups: { id: string; label: string; modules: OrgModule[] }[]
  changes?: { on: string[]; off: string[] }
}

export const moduleApi = {
  directory: () => api.get<ModuleGroup[]>('/api/modules/'),
  ofOrg: (org: number) => api.get<OrgModules>(`/api/orgs/${org}/modules/`),
  setOrg: (org: number, enabled: string[], dryRun = false) =>
    api.patch<OrgModules>(`/api/orgs/${org}/modules/`, { enabled, dry_run: dryRun }),
}

/** Alle Module der Gruppen in einer Liste */
export function flatModules(groups: ModuleGroup[] | null | undefined): ModuleInfo[] {
  return (groups ?? []).flatMap((g) => g.modules)
}

/** Module samt allem, was sie voraussetzen (wie im Backend) */
export function withRequirements(ids: string[], all: ModuleInfo[]): string[] {
  const byId = new Map(all.map((m) => [m.id, m]))
  const result = new Set(ids.filter((id) => byId.has(id)))
  let changed = true
  while (changed) {
    changed = false
    for (const id of [...result]) {
      const m = byId.get(id)!
      for (const need of m.requires) {
        if (!result.has(need)) {
          result.add(need)
          changed = true
        }
      }
      if (m.requires_any.length && !m.requires_any.some((x) => result.has(x))) {
        result.add(m.requires_any[0])
        changed = true
      }
    }
  }
  return [...result]
}

/** Ohne Module, deren Voraussetzung fehlt (wie im Backend) */
export function withoutDependents(ids: string[], all: ModuleInfo[]): string[] {
  const byId = new Map(all.map((m) => [m.id, m]))
  const result = new Set(ids.filter((id) => byId.has(id)))
  let changed = true
  while (changed) {
    changed = false
    for (const id of [...result]) {
      const m = byId.get(id)!
      const missing =
        m.requires.some((x) => !result.has(x)) ||
        (m.requires_any.length > 0 && !m.requires_any.some((x) => result.has(x)))
      if (missing) {
        result.delete(id)
        changed = true
      }
    }
  }
  return [...result]
}

/** Namen der Module, die ein Modul voraussetzt, für Hinweise */
export function requirementText(m: ModuleInfo, all: ModuleInfo[]): string {
  const name = (id: string) => all.find((x) => x.id === id)?.label ?? id
  const parts = m.requires.map(name)
  if (m.requires_any.length) parts.push(m.requires_any.map(name).join(' / '))
  return parts.join(', ')
}
