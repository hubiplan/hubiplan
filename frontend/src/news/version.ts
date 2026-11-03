// Dateien der laufenden Fassung, die deploy/server-setup.sh und deploy/web.Dockerfile neben
// der App ablegen (docs/releases.md). In der Entwicklung fehlen sie; dann gilt null.
import { useEffect, useState } from 'react'

/** Commit der laufenden Fassung (AGPL-Quelllink). */
export const COMMIT_FILE = '/lizenzen/fassung.txt'
export const COMMIT_PATTERN = /^[0-9a-f]{40}$/
/** Versionsnummer der laufenden Fassung. */
export const VERSION_FILE = '/lizenzen/version.txt'
/** Release „2026.11.0“ oder Stand danach „2026.11.0+3.0a5d21e“ oder nur der Commit. */
export const VERSION_PATTERN = /^[0-9A-Za-z.+]{1,40}$/
export const RELEASE_PATTERN = /^\d{4}\.\d{1,2}\.\d+$/

/** Liest eine kurze Textdatei der laufenden Fassung; ohne Datei (z. B. Entwicklung) null. */
export function useRunningFile(path: string, pattern: RegExp): string | null {
  const [value, setValue] = useState<string | null>(null)
  useEffect(() => {
    let active = true
    fetch(path)
      .then((resp) => (resp.ok ? resp.text() : ''))
      .then((text) => {
        const line = (text ?? '').trim()
        if (active && pattern.test(line)) setValue(line)
      })
      .catch(() => undefined)
    return () => {
      active = false
    }
  }, [path, pattern])
  return value
}

/** Laufende Version („2026.11.0“, „2026.11.0+3.0a5d21e“) oder null. */
export function useRunningVersion(): string | null {
  return useRunningFile(VERSION_FILE, VERSION_PATTERN)
}
