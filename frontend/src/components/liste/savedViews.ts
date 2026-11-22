// Gespeicherte Ansichten einer Liste (Web-Oberfläche W11): Filter, Sortierung und Spalten unter
// einem Namen, je Gerät im Browser. Nichts davon geht an den Server.

export interface SavedView<T> {
  name: string
  params: T
}

const key = (list: string) => `hubiplan.ansichten.${list}`

export function loadViews<T>(list: string): SavedView<T>[] {
  try {
    const raw = localStorage.getItem(key(list))
    const parsed: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed)
      ? (parsed as SavedView<T>[]).filter((v) => v && typeof v.name === 'string')
      : []
  } catch {
    return []
  }
}

export function storeViews<T>(list: string, views: SavedView<T>[]): void {
  try {
    if (views.length) localStorage.setItem(key(list), JSON.stringify(views))
    else localStorage.removeItem(key(list))
  } catch {
    // ohne Speicher gibt es eben keine gemerkten Ansichten
  }
}

/** Gleiche Angaben, egal in welcher Reihenfolge und ohne leere Werte. */
export function sameParams(a: object, b: object): boolean {
  const norm = (o: object) =>
    JSON.stringify(
      Object.entries(o)
        .filter(([, v]) => v !== '' && v !== undefined && v !== null)
        .sort(([x], [y]) => x.localeCompare(y)),
    )
  return norm(a) === norm(b)
}
