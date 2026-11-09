/**
 * Kürzel je Kategorie für die Monatsansicht: die ersten drei Buchstaben, bei Gleichstand so
 * viele mehr, bis sie sich unterscheiden. So ist die Kategorie nicht nur an der Farbe
 * erkennbar (UX-Audit 08.11., W-12; WCAG 1.4.1).
 */
export function categoryShorts(names: string[]): Map<string, string> {
  const unique = [...new Set(names)]
  const result = new Map<string, string>()
  for (const name of unique) {
    const letters = name.replace(/[^\p{L}\p{N}]/gu, '') || name
    let len = Math.min(3, letters.length)
    while (
      len < letters.length &&
      unique.some(
        (other) =>
          other !== name &&
          (other.replace(/[^\p{L}\p{N}]/gu, '') || other).slice(0, len).toLowerCase() ===
            letters.slice(0, len).toLowerCase(),
      )
    )
      len++
    result.set(name, letters.slice(0, len))
  }
  return result
}
