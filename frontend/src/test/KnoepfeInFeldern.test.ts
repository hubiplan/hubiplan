// Auswahlknöpfe und Kästchen in Formularfeldern (Ralf 14.11.2026, Abschnittsdialog › Hintergrund):
// Die Regel für Textfelder in `.field` (volle Breite, Polster, Rahmen) darf Kästchen und
// Auswahlknöpfe nicht treffen, sonst rutscht der Knopf über die Beschriftung daneben. jsdom
// rechnet kein Layout; der Test liest deshalb index.css und prüft die Selektoren.
import { describe, expect, it } from 'vitest'
import css from '../index.css?raw'

/** Selektoren aller Regeln, die `width: 100%` setzen */
function breiteSelektoren(text: string): string[] {
  const ohneKommentare = text.replace(/\/\*[\s\S]*?\*\//g, '')
  const treffer: string[] = []
  for (const m of ohneKommentare.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    if (!/(^|;)\s*width:\s*100%/.test(m[2])) continue
    for (const teil of m[1].split(/,(?![^(]*\))/)) treffer.push(teil.trim())
  }
  return treffer
}

describe('Auswahlknöpfe in Formularfeldern', () => {
  it('die Textfeld-Breite von .field gilt nicht für Kästchen und Auswahlknöpfe', () => {
    const blank = breiteSelektoren(css).filter((s) => /\.field\s+input$/.test(s))
    expect(blank).toEqual([])
    expect(css).toContain(".field input:not(:where([type='checkbox'], [type='radio']))")
  })
})
