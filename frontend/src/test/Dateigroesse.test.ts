// Seiten und Bausteine bleiben überschaubar (docs/architektur.md): Dateien unter pages/ und
// components/ haben höchstens MAX_ZEILEN Zeilen. Eine Liste mit Ausnahmen gibt es nicht mehr;
// wer an die Grenze stößt, teilt die Datei (Komponenten je Thema, Zustand und Abläufe in Hooks).
import { describe, expect, it } from 'vitest'

const MAX_ZEILEN = 800

const QUELLEN = import.meta.glob(['../pages/**/*.tsx', '../components/**/*.tsx'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

describe('Dateigröße von Seiten und Bausteinen', () => {
  it(`keine Datei hat mehr als ${MAX_ZEILEN} Zeilen`, () => {
    const zuGross = Object.entries(QUELLEN)
      .map(([pfad, text]) => [pfad.replace('../', ''), text.split('\n').length] as const)
      .filter(([, n]) => n > MAX_ZEILEN)
      .map(([pfad, n]) => `${pfad} (${n} Zeilen)`)
    expect(
      zuGross,
      'Bitte in mehrere Dateien teilen (Komponenten je Thema, Zustand und Abläufe in Hooks)',
    ).toEqual([])
  })
})
