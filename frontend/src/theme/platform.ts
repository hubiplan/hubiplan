// Erscheinungsbild der Instanz (White Label, konzepte/white-label.md W1).
//
// Wer HUBIplan selbst betreibt, gibt der Plattform-Einheit einen Namen, Farben und ein
// Logo. Die gelten überall, wo keine Einheit feststeht: Anmeldeseite, öffentliche Seiten,
// Konto ohne Einheit, Seitentitel. Mit gewählter Einheit gewinnt wie bisher die Einheit.
import { useSyncExternalStore } from 'react'
import { api } from '../api/client.ts'
import { applyPlatformTheme } from './theme.ts'
import type { ThemeColors } from './theme.ts'

/** Name der Software; bleibt in Lizenz, Versionen und Hilfe. */
export const PRODUCT_NAME = 'HUBIplan'

export interface PlatformInfo {
  name: string
  short_name: string
  logo_url: string | null
  /** null: die Instanz nutzt die Standardfarben */
  theme: ThemeColors | null
}

const DEFAULT: PlatformInfo = { name: PRODUCT_NAME, short_name: '', logo_url: null, theme: null }

let current: PlatformInfo = DEFAULT
const listeners = new Set<() => void>()

export function setPlatform(info: PlatformInfo) {
  current = { ...DEFAULT, ...info, name: info.name?.trim() || PRODUCT_NAME }
  applyPlatformTheme(current.theme)
  for (const l of listeners) l()
}

/**
 * Einmal beim Start laden; ohne Antwort bleibt alles beim Standard. fresh: nach einer
 * Änderung neu holen, am Zwischenspeicher des Browsers vorbei.
 */
export async function loadPlatform(fresh = false) {
  const url = '/api/public/platform/' + (fresh ? `?neu=${Date.now()}` : '')
  try {
    setPlatform(await api.get<PlatformInfo>(url))
  } catch {
    // Standard behalten
  }
}

export function platform(): PlatformInfo {
  return current
}

/** Name der Instanz (Vorgabe „HUBIplan“). */
export function instanceName(): string {
  return current.name
}

/** true, wenn die Instanz einen eigenen Namen trägt. */
export function isWhiteLabel(info: PlatformInfo = current): boolean {
  return info.name !== PRODUCT_NAME
}

export function usePlatform(): PlatformInfo {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l)
      return () => listeners.delete(l)
    },
    () => current,
  )
}
