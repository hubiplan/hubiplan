// Tabellen in Karten (Ralf 10.11.2026, Versammlungen › Arten und Fristen): Die Knöpfe der
// Aktionsspalte stehen nebeneinander, und die Karte wird so breit, wie die Tabelle mindestens
// braucht, statt dass die Tabelle über den Kartenrand ragt. jsdom rechnet kein Layout; der
// Test sichert deshalb die Regeln in index.css.
import { describe, expect, it } from 'vitest'
import css from '../index.css?raw'

function block(start: string): string {
  const at = css.indexOf(start)
  expect(at).toBeGreaterThan(-1)
  let depth = 0
  for (let i = css.indexOf('{', at); i < css.length; i++) {
    if (css[i] === '{') depth++
    if (css[i] === '}' && --depth === 0) return css.slice(at, i + 1)
  }
  throw new Error(start)
}

describe('Tabellen in Karten', () => {
  const desktop = block('@media not all and (max-width: 40rem) {\n  .table td.actions')

  it('hält die Knöpfe der Aktionsspalte in einer Zeile', () => {
    expect(desktop).toMatch(/\.table td\.actions > \.button-row \{[^}]*flex-wrap: nowrap/)
  })

  it('macht Karten mit Tabelle so breit wie nötig, höchstens so breit wie der Platz', () => {
    expect(desktop).toMatch(/\.card:has\(\.table/)
    expect(desktop).toContain('min-width: min-content')
    expect(desktop).toContain('min-width: calc-size(min-content, min(size, 100%))')
  })

  it('lässt Tabellen mit eigenem Rollbereich außen vor', () => {
    expect(desktop).toMatch(/:not\(\s*:has\(\.table-scroll, \.table-wrap, \.booking-scroll\)/)
  })
})
