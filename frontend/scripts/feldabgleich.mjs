// Schreibt die Konstanten für den Feldabgleich mit dem Server neu (docs/architektur.md):
// aus backend/config/feldabgleich/<bereich>.json wird src/test/feldabgleich/<bereich>.ts.
// Nach geänderten Antworten des Servers ausführen und die Dateien mit einchecken:
//
//   node scripts/feldabgleich.mjs        (im Ordner frontend, Node ab 22.18)
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { alsTypescript } from '../src/test/feldabgleichErzeugen.ts'

const root = fileURLToPath(new URL('..', import.meta.url))
const quelle = join(root, '..', 'backend', 'config', 'feldabgleich')
const ziel = join(root, 'src', 'test', 'feldabgleich')

mkdirSync(ziel, { recursive: true })
for (const name of readdirSync(quelle).filter((n) => n.endsWith('.json'))) {
  const daten = JSON.parse(readFileSync(join(quelle, name), 'utf-8'))
  const datei = join(ziel, name.replace(/\.json$/, '.ts'))
  writeFileSync(datei, alsTypescript(daten))
  console.log(`geschrieben: ${datei}`)
}
