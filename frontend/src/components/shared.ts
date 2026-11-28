// Gemeinsamer Zwischenspeicher für Stammdaten (Einstellungen, Auswahllisten), die viele Seiten
// brauchen: Beim Seitenwechsel sind sie sofort da, und mehrere Bausteine einer Seite laden sie
// nur einmal (docs/architektur.md).
//
// Bewusst eng gehalten:
// - nur im Arbeitsspeicher der Seite, nie im Browserspeicher;
// - nach jeder erfolgreichen ändernden Anfrage ist alles vergessen (auch Rollenvorschau,
//   Einstellungen, Stammdaten), ebenso nach Abmelden oder Kontowechsel;
// - nach kurzer Zeit wird neu geladen, damit Änderungen anderer ankommen;
// - nicht für Personen- oder Finanzdaten, nur für Listen und Einstellungen zum Auswählen.
// Der Server prüft weiterhin jede Eingabe; eine veraltete Auswahlliste führt höchstens zu einer
// abgelehnten Eingabe.
import { useCallback, useEffect, useRef, useState } from 'react'
import { currentAuthGeneration, mutationListeners } from '../api/client.ts'
import { errorMessage } from './forms.ts'

/** So lange gilt ein Eintrag als frisch und wird ohne Anfrage verwendet. */
export const SHARED_FRESH_MS = 60_000

interface Entry {
  data: unknown
  at: number
  auth: number
}

const entries = new Map<string, Entry>()
const pending = new Map<string, Promise<unknown>>()
// Zählt bei jedem Leeren hoch: Antworten auf Anfragen von davor werden nicht mehr gespeichert
let epoch = 0

/** Alles vergessen (nach Änderungen, beim Abmelden, zwischen Tests). */
export function clearShared() {
  entries.clear()
  pending.clear()
  epoch += 1
}

mutationListeners.add((_url, status) => {
  if (status < 400) clearShared()
})

function cached<T>(key: string): { data: T; fresh: boolean } | null {
  const entry = entries.get(key)
  // Eintrag eines früheren Kontos: nie zeigen
  if (!entry || entry.auth !== currentAuthGeneration()) return null
  return { data: entry.data as T, fresh: Date.now() - entry.at < SHARED_FRESH_MS }
}

function fetchShared<T>(key: string, loader: () => Promise<T>): Promise<T> {
  const running = pending.get(key)
  if (running) return running as Promise<T>
  const mine = epoch
  const auth = currentAuthGeneration()
  const request = loader().then((data) => {
    if (mine === epoch && auth === currentAuthGeneration())
      entries.set(key, { data, at: Date.now(), auth })
    return data
  })
  const done = () => {
    if (pending.get(key) === request) pending.delete(key)
  }
  request.then(done, done)
  pending.set(key, request)
  return request
}

/**
 * Wie useLoad, aber mit gemeinsamem Zwischenspeicher. `key` benennt die Daten eindeutig,
 * einschließlich der Einheit (z. B. `finance.settings:${org.id}`).
 */
export function useShared<T>(key: string, loader: () => Promise<T>) {
  const [state, setState] = useState<{
    key: string
    data: T | null
    error: string | null
    loading: boolean
  }>(() => {
    const hit = cached<T>(key)
    return { key, data: hit?.data ?? null, error: null, loading: !hit?.fresh }
  })
  const loaderRef = useRef(loader)
  useEffect(() => {
    loaderRef.current = loader
  })
  // Nur die Antwort der neuesten Anfrage dieses Bausteins wird übernommen
  const generation = useRef(0)

  const run = useCallback(
    async (force: boolean) => {
      const mine = ++generation.current
      const hit = cached<T>(key)
      if (hit?.fresh && !force) {
        setState({ key, data: hit.data, error: null, loading: false })
        return
      }
      setState({ key, data: hit?.data ?? null, error: null, loading: true })
      if (force) pending.delete(key)
      try {
        const data = await fetchShared(key, () => loaderRef.current())
        if (mine === generation.current) setState({ key, data, error: null, loading: false })
      } catch (err) {
        if (mine === generation.current)
          setState((s) => ({
            key,
            data: s.key === key ? s.data : null,
            error: errorMessage(err),
            loading: false,
          }))
      }
    },
    [key],
  )

  useEffect(() => {
    void run(false)
    return () => {
      // oxlint-disable-next-line react-hooks/exhaustive-deps
      generation.current++
    }
  }, [run])

  const reload = useCallback(() => run(true), [run])
  const setData = useCallback(
    (data: T) => {
      entries.set(key, { data, at: Date.now(), auth: currentAuthGeneration() })
      setState({ key, data, error: null, loading: false })
    },
    [key],
  )
  // Daten eines anderen Schlüssels (z. B. der vorigen Einheit) nie zeigen
  const current = state.key === key ? state : null
  return {
    data: current?.data ?? null,
    error: current?.error ?? null,
    loading: current?.loading ?? true,
    reload,
    setData,
  }
}
