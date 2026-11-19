// Vorschläge für SuggestInput: Datentyp und Filter (eigene Datei wegen Fast Refresh).

export interface Suggestion {
  /** Wert, der ins Feld übernommen wird */
  value: string
  /** Zweite, kleinere Zeile (z. B. Anschrift) */
  detail?: string
}

/** Vorschläge passend zur Eingabe: leer oder genau getroffen → alle, sonst enthält den Text. */
export function matchSuggestions(items: Suggestion[], query: string): Suggestion[] {
  const q = query.trim().toLocaleLowerCase('de')
  if (!q || items.some((s) => s.value.toLocaleLowerCase('de') === q)) return items
  return items.filter(
    (s) =>
      s.value.toLocaleLowerCase('de').includes(q) ||
      (s.detail ?? '').toLocaleLowerCase('de').includes(q),
  )
}
