// Reihenfolge einer Liste für das Blättern in der Akte (siehe RecordPager.tsx).

const key = (list: string) => `hubiplan.blaettern.${list}`

export function rememberOrder(list: string, ids: number[]): void {
  try {
    sessionStorage.setItem(key(list), JSON.stringify(ids))
  } catch {
    // ohne Speicher eben ohne Blättern
  }
}

export function order(list: string): number[] {
  try {
    const parsed: unknown = JSON.parse(sessionStorage.getItem(key(list)) ?? '[]')
    return Array.isArray(parsed) ? parsed.filter((x): x is number => typeof x === 'number') : []
  } catch {
    return []
  }
}
