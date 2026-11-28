// Gemeinsame Helfer, Typen und Konstanten von CompetitionsPage.

export function numOrNull(text: string): number | null {
  const n = parseInt(text, 10)
  return Number.isFinite(n) ? n : null
}
