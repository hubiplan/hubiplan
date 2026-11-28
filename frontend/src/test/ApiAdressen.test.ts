// Jede Adresse, die die API-Schicht (src/api/*.ts) aufruft, gibt es im Server.
//
// Der Server führt die Liste seiner Adressen in backend/config/api_routen.json (dort per Test
// aktuell gehalten). Dieser Test ruft jede Funktion der API-Schicht mit Platzhaltern auf, fängt
// die Anfrage ab und prüft die Adresse gegen die Liste. So fällt ein umbenannter oder
// entfernter Endpunkt im Testlauf auf, nicht erst beim Benutzen (docs/architektur.md).
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'

const ROUTEN = import.meta.glob('../../../backend/config/api_routen.json', {
  import: 'default',
  eager: true,
}) as Record<string, string[]>

const MODULE = import.meta.glob(['../api/*.ts', '!../api/client.ts'], { eager: true }) as Record<
  string,
  Record<string, unknown>
>

/** Platzhalter, der sich wie jede Art von Argument verhält und in Adressen zu `wert` wird. */
function platzhalter(wert: string): unknown {
  const selbst: unknown = new Proxy(function () {}, {
    get(_ziel, name) {
      if (name === Symbol.toPrimitive) return () => wert
      if (name === Symbol.iterator) return function* () {}
      if (name === 'then') return undefined
      if (name === 'toJSON' || name === 'toString' || name === 'valueOf') return () => wert
      if (name === 'length') return 0
      return selbst
    },
    apply: () => wert,
    ownKeys: () => [],
    getOwnPropertyDescriptor: () => undefined,
  })
  return selbst
}

// Verschiedene Platzhalter, weil Adressen Zahlen, Kennungen oder UUIDs erwarten: einmal alle
// Argumente gleich, dann Zahlen mit einem Wort an einer Stelle (z. B. …/signatures/<rolle>/).
const STELLEN = 6
const WERTE = ['1', 'a1', '00000000-0000-4000-8000-000000000000']
const ARGUMENTE: string[][] = [
  ...WERTE.map((wert) => Array<string>(STELLEN).fill(wert)),
  ...[1, 2, 3].map((stelle) =>
    Array.from({ length: STELLEN }, (_, i) => (i === stelle ? 'x' : '1')),
  ),
]

// Funktionen, deren Adresse es nur mit bestimmten Argumenten gibt. Nur mit Begründung ergänzen.
const AUSNAHMEN: Record<string, string> = {
  'entries.ts entriesApi.returnEntry':
    'Zurückgeben gibt es nur im Geltungsbereich einer Untereinheit (unitScope, deptScope)',
}

/** Alle aufrufbaren Funktionen eines Moduls: direkte Exporte und Methoden exportierter Objekte. */
function funktionen(modul: Record<string, unknown>): [string, (...a: unknown[]) => unknown][] {
  const liste: [string, (...a: unknown[]) => unknown][] = []
  for (const [name, wert] of Object.entries(modul)) {
    if (typeof wert === 'function' && !/^[A-Z]/.test(name))
      liste.push([name, wert as (...a: unknown[]) => unknown])
    else if (wert && typeof wert === 'object' && !Array.isArray(wert))
      for (const [methode, f] of Object.entries(wert as Record<string, unknown>))
        if (typeof f === 'function')
          liste.push([`${name}.${methode}`, f as (...a: unknown[]) => unknown])
  }
  return liste
}

describe('Adressen der API-Schicht', () => {
  const muster = Object.values(ROUTEN)
    .flat()
    .map((zeile) => new RegExp(zeile))
  let gesehen: string[] = []

  beforeAll(() => {
    document.cookie = 'csrftoken=test'
    vi.stubGlobal(
      'fetch',
      vi.fn(async (adresse: RequestInfo | URL) => {
        gesehen.push(String(adresse))
        return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })
      }),
    )
  })
  afterAll(() => vi.unstubAllGlobals())

  const gibtEs = (adresse: string) => {
    const pfad = adresse.split(/[?#]/)[0].replace(/^\//, '')
    return muster.some((m) => m.test(pfad))
  }

  it('die Liste des Servers ist da', () => {
    expect(muster.length, 'backend/config/api_routen.json fehlt').toBeGreaterThan(500)
  })

  it('jede aufgerufene Adresse gibt es im Server', async () => {
    const fehlend: string[] = []
    let geprueft = 0
    for (const [datei, modul] of Object.entries(MODULE)) {
      for (const [name, f] of funktionen(modul)) {
        // Je Belegung die Adressen sammeln; es genügt, wenn eine Belegung passt
        const versuche: string[][] = []
        for (const argumente of ARGUMENTE) {
          gesehen = []
          try {
            // Manche Funktionen warten auf mehr (Abfrageschleifen); die Adresse steht dann schon fest
            const lauf = Promise.resolve(f(...argumente.map(platzhalter)))
            lauf.catch(() => {})
            await Promise.race([lauf, new Promise((fertig) => setTimeout(fertig, 100))])
          } catch {
            // Antwort ist leer: Auswerten darf scheitern, die Adresse ist schon notiert
          }
          versuche.push(gesehen.filter((a) => a.startsWith('/api/') || a.startsWith('/_allauth/')))
        }
        const anzahl = Math.max(...versuche.map((v) => v.length))
        for (let i = 0; i < anzahl; i++) {
          const adressen = versuche.map((v) => v[i]).filter(Boolean)
          geprueft += 1
          const stelle = `${datei.replace('../api/', '')} ${name}`
          if (!adressen.some(gibtEs) && !(stelle in AUSNAHMEN))
            fehlend.push(`${stelle}: ${adressen[0]}`)
        }
      }
    }
    expect(fehlend, 'Diese Adressen kennt der Server nicht').toEqual([])
    // Der Test soll nicht still leer laufen
    expect(geprueft).toBeGreaterThan(1500)
  }, 120_000)
})
