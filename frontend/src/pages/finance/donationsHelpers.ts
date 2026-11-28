// Zuwendungsbestätigungen (Spendenbescheinigungen) nach amtlichem Muster.
// Für Einheiten mit Kasse; ausgestellt wird nur mit Schalter „steuerbegünstigt mit
// eigenem Bescheid“ und gültigem Bescheid. Regeln im Backend
// (finance/donations.py).
// Diese Datei: gemeinsame Helfer, Typen und Konstanten des Bereichs.
import { ApiError } from '../../api/client.ts'

export function thisYear() {
  return new Date().getFullYear()
}

/** Jahre für die Auswahl: alle mit Daten, dazu das laufende und das gewählte (UX-Audit 31.10. N01) */
export function yearOptions(withData: number[] | null, selected: number): number[] {
  const all = new Set<number>([thisYear(), selected, ...(withData ?? [])])
  if (!withData) for (let i = 1; i < 6; i++) all.add(thisYear() - i)
  return [...all].sort((a, b) => b - a)
}

export function fieldErrors(err: unknown): Record<string, string> {
  return err instanceof ApiError ? err.fieldErrors : {}
}
