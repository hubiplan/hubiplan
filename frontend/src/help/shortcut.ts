// Einzeltasten-Kürzel „?“ für die Seitenhilfe lässt sich abschalten (WCAG 2.1.4, UX-Audit
// 16.11. VW-03): Spracheingabe löst sonst versehentlich die Hilfe aus. Die Wahl gilt in
// diesem Browser.
const KEY = 'hubiplan.hilfe-kuerzel'

export function helpShortcutEnabled(): boolean {
  try {
    return localStorage.getItem(KEY) !== 'aus'
  } catch {
    return true
  }
}

export function setHelpShortcutEnabled(on: boolean) {
  try {
    if (on) localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, 'aus')
  } catch {
    // ohne Speicher bleibt die Vorgabe (an)
  }
}
