// Drei Umbruchbreiten für die ganze Oberfläche (UX-Audit 08.11., W-20 c). CSS kann keine
// Variablen in @media verwenden; die CSS-Dateien nehmen deshalb genau diese Werte, und
// test/Breakpoints.test.ts prüft, dass keine weiteren dazukommen.
/** Telefon: eine Spalte, Kurzformen */
export const BP_NARROW = '40rem'
/** Tablet: Seitenleiste wird zum Menü */
export const BP_MEDIUM = '50rem'
/** Großer Bildschirm: mehrspaltige Übersichten */
export const BP_WIDE = '64rem'

export const BREAKPOINTS = [BP_NARROW, BP_MEDIUM, BP_WIDE] as const

/** Ist das Fenster höchstens so breit wie die Umbruchbreite? */
export function atMost(bp: (typeof BREAKPOINTS)[number]): boolean {
  return typeof window.matchMedia === 'function' && window.matchMedia(`(max-width: ${bp})`).matches
}
