// Stehender Tabellenkopf (W5): In Tabellen, die in einem eigenen Rollbehälter liegen, bezöge
// sich der Abstand nach oben auf den Behälter, und der Kopf läge über der ersten Zeile
// (Kassenbuch, Ralf 22.11.2026). jsdom rechnet kein Layout; der Test sichert die Regel in
// index.css.
import { describe, expect, it } from 'vitest'
import css from '../index.css?raw'

describe('Stehender Tabellenkopf', () => {
  const at = css.indexOf('@media not all and (max-width: 50rem) {\n  .content\n    .table:not(')
  const rule = css.slice(at, css.indexOf('{', css.indexOf('> th', at)))

  it('gilt für Tabellen im Inhalt', () => {
    expect(at).toBeGreaterThan(-1)
    expect(rule).toContain('> thead')
  })

  it('nimmt Tabellen in eigenen Rollbehältern aus', () => {
    for (const box of ['.table-scroll *', '.table-wrap *', '.side-sheet-body *', '.modal *']) {
      expect(rule).toContain(box)
    }
  })
})
