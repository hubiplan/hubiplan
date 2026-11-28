// Seiten und Bausteine bleiben überschaubar (docs/architektur.md): Neue Dateien unter pages/
// und components/ haben höchstens MAX_ZEILEN Zeilen. Größere aus dem Bestand stehen in
// grosse-dateien.json und werden nach und nach geteilt; wer eine unter die Grenze bringt,
// streicht sie aus der Liste.
import { describe, expect, it } from 'vitest'
import BESTAND from './grosse-dateien.json'

const MAX_ZEILEN = 800

const QUELLEN = import.meta.glob(['../pages/**/*.tsx', '../components/**/*.tsx'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

const zeilen = Object.fromEntries(
  Object.entries(QUELLEN).map(([pfad, text]) => [pfad.replace('../', ''), text.split('\n').length]),
)

describe('Dateigröße von Seiten und Bausteinen', () => {
  it(`neue Dateien haben höchstens ${MAX_ZEILEN} Zeilen`, () => {
    const zuGross = Object.entries(zeilen)
      .filter(([pfad, n]) => n > MAX_ZEILEN && !BESTAND.includes(pfad))
      .map(([pfad, n]) => `${pfad} (${n} Zeilen)`)
    expect(
      zuGross,
      'Bitte in mehrere Dateien teilen (Komponenten je Thema, Logik in Hooks), nicht in die Bestandsliste eintragen',
    ).toEqual([])
  })

  it('die Bestandsliste nennt nur Dateien, die es gibt und die noch zu groß sind', () => {
    const erledigt = BESTAND.filter((pfad) => !(zeilen[pfad] > MAX_ZEILEN))
    expect(erledigt, 'Aus src/test/grosse-dateien.json streichen').toEqual([])
  })
})
