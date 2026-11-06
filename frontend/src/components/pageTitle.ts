// Seitentitel im Browser-Tab (WCAG 2.4.2, UI-Audit NUI-09).
//
// Layout setzt den Titel aus dem gewählten Bereich. Seiten ohne eigenen Bereich
// (z. B. „Seite nicht gefunden“) melden ihren Titel über usePageTitle; der gilt
// dann vorrangig, solange die Seite zu sehen ist.
import { useEffect, useSyncExternalStore } from 'react'
import { instanceName } from '../theme/platform.ts'

let override: string | null = null
const listeners = new Set<() => void>()

function setOverride(value: string | null) {
  override = value
  for (const l of listeners) l()
}

export function useTitleOverride(): string | null {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l)
      return () => listeners.delete(l)
    },
    () => override,
  )
}

/** Titel einer Seite ohne eigenen Bereich; ohne Token oder Personendaten. null: keiner. */
export function usePageTitle(title: string | null) {
  useEffect(() => {
    if (title === null) return
    setOverride(title)
    return () => setOverride(null)
  }, [title])
}

/** Titel aus Teilen, am Ende der Name der Instanz (Vorgabe „HUBIplan“, White Label). */
export function formatTitle(...parts: (string | null | undefined)[]): string {
  const name = instanceName()
  return [...parts.filter((p) => p !== name), name].filter(Boolean).join(' · ')
}
