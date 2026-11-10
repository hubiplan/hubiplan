// KI-Schnittstelle Stufe 0 (docs/mcp.md): Die Kopie der Hilfe im Backend
// (backend/mcpserver/hilfe.json) muss zur Hilfe und zu den Lernhilfen passen.
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { buildMcpExport, mcpExportText } from '../help/mcpExport.ts'
import LEARNING_EN from '../learning/en.json'

const RAW = {
  de: import.meta.glob('../help/de/**/*.md', {
    query: '?raw',
    import: 'default',
    eager: true,
  }) as Record<string, string>,
  en: import.meta.glob('../help/en/**/*.md', {
    query: '?raw',
    import: 'default',
    eager: true,
  }) as Record<string, string>,
}
// scripts/test.sh hängt das Backend ein. Mit node:fs gelesen, weil Vite Dateien außerhalb
// des Frontends nicht als ?raw ausliefert.
const COPY_PATH = fileURLToPath(new URL('../../../backend/mcpserver/hilfe.json', import.meta.url))
const COPY = existsSync(COPY_PATH) ? readFileSync(COPY_PATH, 'utf-8') : undefined

const byName = (files: Record<string, string>) =>
  Object.fromEntries(
    Object.entries(files).map(([path, raw]) => [path.replace(/^\.\.\/help\/(de|en)\//, ''), raw]),
  )

describe('Hilfe für die KI-Schnittstelle', () => {
  it('backend/mcpserver/hilfe.json ist aktuell (sonst: node scripts/mcp-hilfe.mjs)', () => {
    const copy = COPY
    expect(copy, 'backend/mcpserver/hilfe.json fehlt').toBeDefined()
    const files = { de: byName(RAW.de), en: byName(RAW.en) }
    expect(Object.keys(files.de).length).toBeGreaterThan(50)
    expect(Object.keys(files.de)[0]).toMatch(/^(anleitungen|seiten)\//)
    const fresh = mcpExportText(buildMcpExport(files, LEARNING_EN as Record<string, string>))
    // Nur Gleichheit melden, nicht 700 KB Unterschied ausgeben
    expect(fresh === copy, 'Hilfe geändert: node scripts/mcp-hilfe.mjs im Ordner frontend').toBe(
      true,
    )
  })
})
