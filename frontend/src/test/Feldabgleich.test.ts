// Feldabgleich mit dem Server (docs/architektur.md): Die Konstanten unter src/test/feldabgleich
// sind echte Antworten des Servers, und die Typprüfung misst sie an den Typen der Oberfläche.
// Dieser Test stellt sicher, dass sie den Antworten in backend/config/feldabgleich entsprechen,
// die der Server mit seinen eigenen Tests aktuell hält. Weicht etwas ab:
// node scripts/feldabgleich.mjs
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { alsTypescript, type Antworten } from './feldabgleichErzeugen.ts'

// vitest läuft im Ordner frontend (im Container /app, Backend unter /backend)
const ANTWORTEN = resolve(process.cwd(), '../backend/config/feldabgleich')

const KONSTANTEN = import.meta.glob('./feldabgleich/*.ts', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

const bereichVon = (pfad: string) => pfad.replace(/^.*\//, '').replace(/\.(json|ts)$/, '')

describe('Feldabgleich mit dem Server', () => {
  it('zu jedem Bereich des Servers gibt es Konstanten und umgekehrt', () => {
    expect(existsSync(ANTWORTEN), 'backend/config/feldabgleich fehlt').toBe(true)
    const server = readdirSync(ANTWORTEN)
      .filter((name) => name.endsWith('.json'))
      .map(bereichVon)
      .sort()
    expect(server.length).toBeGreaterThan(0)
    expect(Object.keys(KONSTANTEN).map(bereichVon).sort()).toEqual(server)
  })

  it.each(Object.keys(KONSTANTEN).map((pfad) => [bereichVon(pfad), pfad]))(
    'die Konstanten für %s sind aus den Antworten des Servers erzeugt',
    (bereich, pfad) => {
      const antworten = JSON.parse(
        readFileSync(resolve(ANTWORTEN, `${bereich}.json`), 'utf-8'),
      ) as Antworten
      expect(
        KONSTANTEN[pfad] === alsTypescript(antworten),
        `src/test/feldabgleich/${bereich}.ts ist veraltet: node scripts/feldabgleich.mjs`,
      ).toBe(true)
    },
  )
})
