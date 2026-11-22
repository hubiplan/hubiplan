// Dichte der Oberfläche (Konzept Web-Oberfläche W5): „Bequem“ mit großen Bedienelementen als
// Vorgabe, „Kompakt“ für große Bildschirme und lange Listen. Die Wahl gilt in diesem Browser;
// index.css setzt die kleineren Maße unter :root[data-density='compact'].
export type Density = 'comfortable' | 'compact'

const KEY = 'hubiplan.dichte'

export function density(): Density {
  try {
    return localStorage.getItem(KEY) === 'kompakt' ? 'compact' : 'comfortable'
  } catch {
    return 'comfortable'
  }
}

function apply(value: Density) {
  if (typeof document === 'undefined') return
  if (value === 'compact') document.documentElement.dataset.density = 'compact'
  else delete document.documentElement.dataset.density
}

export function setDensity(value: Density) {
  try {
    if (value === 'compact') localStorage.setItem(KEY, 'kompakt')
    else localStorage.removeItem(KEY)
  } catch {
    // ohne Speicher gilt die Wahl bis zum Neuladen
  }
  apply(value)
}

/** Einmal beim Start: gespeicherte Wahl anwenden. */
export function initDensity() {
  apply(density())
}
