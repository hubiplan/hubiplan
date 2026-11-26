// Private Offline-Daten des Standmodus: konto-/zugangsgebunden und zeitlich begrenzt.
import { ApiError, currentAuthGeneration } from './client.ts'

const PREFIX = 'hubiplan.stand.v2.'
const SESSION_MEMBERS_PREFIX = 'hubiplan.stand.members.v2.'
const USER = 'hubiplan.stand.user'
const CHANGE = 'hubiplan:stand-cache'
const MAX_AGE = 12 * 60 * 60 * 1000
let revision = 0
let activeUser: string | null | undefined
const blocked = new Set<string>()
const deadlines = new Map<string, number>()
const memoryPending = new Map<string, number>()

export function rememberStandPending(scope: string, count: number): void {
  if (count) memoryPending.set(scope, count)
  else memoryPending.delete(scope)
}

interface Entry<T> {
  owner: string
  until: number
  data: T
}

function keys(): string[] {
  try {
    return Array.from({ length: localStorage.length }, (_, i) => localStorage.key(i) || '').filter(
      (k) => k.startsWith('hubiplan.stand.') && k !== USER,
    )
  } catch {
    return []
  }
}

export function standUser(): string | null {
  if (activeUser !== undefined) return activeUser
  try {
    return sessionStorage.getItem(USER)
  } catch {
    return null
  }
}

export function suspendStandUser(): void {
  activeUser = null
  try {
    sessionStorage.removeItem(USER)
  } catch {
    /* Speicher gesperrt. */
  }
  deadlines.clear()
  changed()
}

export function removeLegacyStandCache(): number {
  let pending = 0
  for (const key of keys())
    if (!key.startsWith(PREFIX)) {
      try {
        const data = JSON.parse(localStorage.getItem(key) || 'null')
        if (Array.isArray(data?.ops)) pending += data.ops.length
      } catch {
        /* Kein nutzergebundener Offlinezugang. */
      }
      try {
        localStorage.removeItem(key)
      } catch {
        /* Speicher gesperrt. */
      }
    }
  return pending
}

function permitted(scope: string): boolean {
  return scope.startsWith('token.') || (!!standUser() && scope.startsWith(`user.${standUser()}.`))
}

function owner(scope: string): string {
  return scope.startsWith('token.') ? scope : `user.${standUser()}`
}

export function standRevision(): string {
  return `${revision}:${currentAuthGeneration()}`
}

function changed() {
  revision += 1
  window.dispatchEvent(new Event(CHANGE))
}

export function subscribeStandCache(listener: () => void): () => void {
  window.addEventListener(CHANGE, listener)
  return () => window.removeEventListener(CHANGE, listener)
}

function sessionMemberKeys(): string[] {
  try {
    return Array.from({ length: sessionStorage.length }, (_, i) => sessionStorage.key(i) || '').filter(
      (k) => k.startsWith(SESSION_MEMBERS_PREFIX),
    )
  } catch {
    return []
  }
}

export function clearStandCache(): void {
  for (const key of keys()) {
    try {
      localStorage.removeItem(key)
    } catch {
      /* Speicher gesperrt. */
    }
  }
  for (const key of sessionMemberKeys()) {
    try {
      sessionStorage.removeItem(key)
    } catch {
      /* Speicher gesperrt. */
    }
  }
  deadlines.clear()
  blocked.clear()
  memoryPending.clear()
  changed()
}

/** Bei Sitzungsablauf (C-M05): zwischengespeicherte Personen-/Detail-Daten sofort entfernen,
 * nur minimale noch nicht übertragene Eingaben (``ops``) behalten. */
export function scrubStandPiiOnExpiry(): void {
  for (const key of sessionMemberKeys()) {
    try {
      sessionStorage.removeItem(key)
    } catch {
      /* Speicher gesperrt. */
    }
  }
  for (const key of keys()) {
    try {
      if (!key.startsWith(PREFIX)) {
        localStorage.removeItem(key)
        continue
      }
      if (!key.endsWith(':local')) {
        localStorage.removeItem(key)
        continue
      }
      const raw = localStorage.getItem(key)
      if (!raw) continue
      const entry = JSON.parse(raw) as Entry<{ ops?: unknown[]; generation?: number }>
      const ops = Array.isArray(entry?.data?.ops) ? entry.data.ops : []
      if (ops.length === 0) {
        localStorage.removeItem(key)
      } else {
        localStorage.setItem(
          key,
          JSON.stringify({
            ...entry,
            data: {
              starters: [],
              members: [],
              ops,
              recent: [],
              savedAt: null,
              generation: entry.data.generation,
            },
          }),
        )
      }
    } catch {
      try {
        localStorage.removeItem(key)
      } catch {
        /* Speicher gesperrt. */
      }
    }
  }
}

export function bindStandUser(id: number | null): void {
  const next = id === null ? null : String(id)
  const previous = standUser()
  let globalUser: string | null = null
  try {
    globalUser = localStorage.getItem(USER)
  } catch {
    /* Ohne Speicher gibt es keinen dauerhaften Cache. */
  }
  if (globalUser !== next) clearStandCache()
  activeUser = next
  try {
    if (next === null) {
      sessionStorage.removeItem(USER)
      localStorage.removeItem(USER)
    } else {
      sessionStorage.setItem(USER, next)
      localStorage.setItem(USER, next)
    }
  } catch {
    /* Gesperrter Browserspeicher ist kein Offlinezugang. */
  }
  if (previous !== next) changed()
}

export function standCacheAllowed(scope: string): boolean {
  return permitted(scope) && !blocked.has(scope) && (deadlines.get(scope) || 0) > Date.now()
}

export function standCacheExpired(scope: string): boolean {
  return deadlines.has(scope) && (deadlines.get(scope) || 0) <= Date.now()
}

export async function standTokenKey(token: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(token))
  return `token.${Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('')}`
}

export function pendingStandInputs(): number {
  const counts = new Map<string, number>()
  for (const key of keys()) {
    try {
      const parsed = JSON.parse(localStorage.getItem(key) || 'null')
      const data = key.startsWith(PREFIX) ? parsed?.data : parsed
      if (Array.isArray(data?.ops)) counts.set(key, data.ops.length)
    } catch {
      /* Beschädigte Daten sind keine übertragbare Warteschlange. */
    }
  }
  for (const [scope, count] of memoryPending) {
    const key = `${PREFIX}${scope}:local`
    counts.set(key, Math.max(count, counts.get(key) || 0))
  }
  return [...counts.values()].reduce((total, count) => total + count, 0)
}

export function authorizeStandCache(scope: string, expires?: string): void {
  if (!permitted(scope)) return
  const until = expires ? Math.min(Date.now() + MAX_AGE, Date.parse(expires)) : Date.now() + MAX_AGE
  deadlines.set(scope, Number.isFinite(until) ? until : 0)
  blocked.delete(scope)
}

export function revokeStandCache(scope: string): void {
  if (blocked.has(scope)) return
  blocked.add(scope)
  deadlines.delete(scope)
  memoryPending.delete(scope)
  for (const key of keys())
    if (key.startsWith(`${PREFIX}${scope}:`)) {
      try {
        localStorage.removeItem(key)
      } catch {
        /* Speicher gesperrt. */
      }
    }
  try {
    sessionStorage.removeItem(`${SESSION_MEMBERS_PREFIX}${scope}`)
  } catch {
    /* Speicher gesperrt. */
  }
  changed()
}

export function loadStandCache<T>(scope: string, kind: string): T | null {
  if (!permitted(scope) || blocked.has(scope)) return null
  try {
    const raw = localStorage.getItem(`${PREFIX}${scope}:${kind}`)
    if (!raw) return null
    const entry = JSON.parse(raw) as Entry<T>
    if (
      entry.owner !== owner(scope) ||
      !Number.isFinite(entry.until) ||
      entry.until <= Date.now()
    ) {
      deadlines.delete(scope)
      localStorage.removeItem(`${PREFIX}${scope}:${kind}`)
      if (scope.startsWith('token.') && kind === 'local') {
        try {
          sessionStorage.removeItem(`${SESSION_MEMBERS_PREFIX}${scope}`)
        } catch {
          /* Speicher gesperrt. */
        }
      }
      return null
    }
    if (!deadlines.has(scope)) deadlines.set(scope, entry.until)
    if (
      scope.startsWith('token.') &&
      kind === 'local' &&
      entry.data &&
      typeof entry.data === 'object'
    ) {
      try {
        const memRaw = sessionStorage.getItem(`${SESSION_MEMBERS_PREFIX}${scope}`)
        if (memRaw) {
          const memEntry = JSON.parse(memRaw) as Entry<unknown[]>
          if (
            memEntry.owner === owner(scope) &&
            Number.isFinite(memEntry.until) &&
            memEntry.until > Date.now() &&
            Array.isArray(memEntry.data)
          ) {
            return { ...(entry.data as Record<string, unknown>), members: memEntry.data } as T
          }
        }
      } catch {
        /* Ohne Sitzungsspeicher bleibt die Mitgliederliste leer und wird neu geladen. */
      }
    }
    return entry.data
  } catch {
    return null
  }
}

export function saveStandCache<T>(scope: string, kind: string, data: T, at: string): boolean {
  if (at !== standRevision() || !permitted(scope) || blocked.has(scope)) return false
  const until = deadlines.get(scope) || 0
  if (until <= Date.now()) return false
  try {
    let persisted: T = data
    // Standzugang (C-M05): vollständige Mitgliederliste nie dauerhaft in localStorage ablegen;
    // sie bleibt nur im tab-gebundenen sessionStorage.
    if (
      scope.startsWith('token.') &&
      kind === 'local' &&
      data &&
      typeof data === 'object' &&
      'members' in (data as Record<string, unknown>)
    ) {
      const record = data as Record<string, unknown>
      try {
        sessionStorage.setItem(
          `${SESSION_MEMBERS_PREFIX}${scope}`,
          JSON.stringify({ owner: owner(scope), until, data: record.members }),
        )
      } catch {
        /* Ohne sessionStorage bleibt die Liste nur im Arbeitsspeicher. */
      }
      persisted = { ...record, members: [] } as T
    }
    localStorage.setItem(
      `${PREFIX}${scope}:${kind}`,
      JSON.stringify({ owner: owner(scope), until, data: persisted }),
    )
    return true
  } catch {
    /* Kein stiller Ersatz für erfolgreiche Serverspeicherung. */
  }
  return false
}

export function isStandNetworkError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 0
}

export function rejectStandAccess(scope: string, error: unknown, missingScope = true): boolean {
  if (
    error instanceof ApiError &&
    ([401, 403].includes(error.status) || (missingScope && error.status === 404))
  ) {
    revokeStandCache(scope)
    return true
  }
  return false
}
