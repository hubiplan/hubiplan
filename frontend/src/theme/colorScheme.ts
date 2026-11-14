// Dunkelmodus der Web-App (UX-Audit 08.11. X-02; Stufe D2 mit Design „Frisch“ D8).
//
// Dunkel gibt es auf allen Seiten, auch in der Verwaltung, aber nur auf eigenen Wunsch: Vorgabe
// ist „Hell“ (Ralf 14.11.). Die Wahl „Hell / Dunkel / Wie Gerät“ steht im Konto (gilt auf allen
// Geräten); der Browser merkt sie sich zusätzlich, damit die Anmeldeseite schon vor dem Laden
// des Kontos passt.
import { setThemeScheme } from './theme.ts'
import type { Scheme } from './theme.ts'

export type ColorSchemeChoice = 'auto' | 'light' | 'dark'

const KEY = 'hubiplan.darstellung'
const CHOICES: readonly ColorSchemeChoice[] = ['auto', 'light', 'dark']
/** Ohne eigene Wahl bleibt HUBIplan hell */
const DEFAULT_CHOICE: ColorSchemeChoice = 'light'

/** Seiten, die immer hell bleiben (eigene, feste Farbwelt). Zurzeit keine. */
const LIGHT_PATHS: RegExp[] = []

export function darkAllowed(pathname: string): boolean {
  return !LIGHT_PATHS.some((re) => re.test(pathname))
}

let choice: ColorSchemeChoice = readStored()
let pathname = typeof location === 'undefined' ? '/' : location.pathname
const listeners = new Set<() => void>()

function readStored(): ColorSchemeChoice {
  try {
    const v = localStorage.getItem(KEY)
    return CHOICES.includes(v as ColorSchemeChoice) ? (v as ColorSchemeChoice) : DEFAULT_CHOICE
  } catch {
    return DEFAULT_CHOICE
  }
}

function deviceDark(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches
  )
}

/** Wirksame Darstellung für eine Wahl auf einer Seite. */
export function resolveScheme(
  pick: ColorSchemeChoice,
  path: string,
  systemDark: boolean = deviceDark(),
): Scheme {
  if (!darkAllowed(path)) return 'light'
  if (pick === 'dark') return 'dark'
  if (pick === 'light') return 'light'
  return systemDark ? 'dark' : 'light'
}

function apply() {
  const scheme = resolveScheme(choice, pathname)
  const root = document.documentElement
  if (scheme === 'dark') root.dataset.theme = 'dark'
  else delete root.dataset.theme
  setThemeScheme(scheme)
}

export function colorSchemeChoice(): ColorSchemeChoice {
  return choice
}

/** Wahl aus dem Konto übernehmen (beim Anmelden und nach dem Ändern). */
export function setColorSchemeChoice(next: ColorSchemeChoice) {
  choice = CHOICES.includes(next) ? next : DEFAULT_CHOICE
  try {
    if (choice === DEFAULT_CHOICE) localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, choice)
  } catch {
    // Ohne Speicher gilt die Wahl bis zum Neuladen
  }
  apply()
  for (const l of listeners) l()
}

/** Seite gewechselt: Seiten mit fester heller Farbwelt bleiben hell. */
export function setColorSchemePath(next: string) {
  if (next === pathname) return
  pathname = next
  apply()
}

export function onColorSchemeChange(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** Einmal beim Start: Geräteeinstellung beobachten und sofort anwenden. */
export function initColorScheme() {
  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener?.('change', apply)
  }
  apply()
}
