// Jeder Stilregler der Webseite (backend/website/style.py, OPTIONS) steht auch in der
// Feinabstimmung (pages/website/StyleTuning.tsx). Ersetzt die feste Anzahl im Backend-Test:
// Zwei Zweige mit je einem neuen Regler sind so einzeln und zusammen grün.
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import TUNING from '../pages/website/StyleTuning.tsx?raw'

// vitest läuft im Ordner frontend (im Container /app, Backend unter /backend)
const STYLE_PATH = resolve(process.cwd(), '../backend/website/style.py')

function optionKeys(src: string): string[] {
  const start = src.indexOf('OPTIONS: dict')
  const end = src.indexOf('LOCKS: dict')
  return [...src.slice(start, end).matchAll(/^ {4}"([a-z_]+)":/gm)].map((m) => m[1])
}

describe('Stilregler der Webseite', () => {
  it('die Feinabstimmung zeigt jeden Regler aus backend/website/style.py', () => {
    expect(existsSync(STYLE_PATH), 'backend/website/style.py fehlt').toBe(true)
    const keys = optionKeys(readFileSync(STYLE_PATH, 'utf-8'))
    expect(keys.length).toBeGreaterThan(50)
    const fehlt = keys.filter((k) => !TUNING.includes(`'${k}'`) && !TUNING.includes(`${k}:`))
    expect(fehlt).toEqual([])
  })
})
