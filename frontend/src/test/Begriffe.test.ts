// UX-Audit 16.11. X-01, VW-11, VW-12, VW-14: ein Wort je Sache. Die Wörter stehen in
// docs/begriffe.md (Deutsch) und docs/glossar-en.md (Englisch). Dieser Test meldet Wörter aus der
// Spalte „Nicht verwenden“, sobald sie in neuen Texten des Katalogs auftauchen. Die Zahl hinter
// einem Wort ist der Bestand am 17.11.2026; sie darf nur sinken.
import { describe, expect, it } from 'vitest'
import EN from '../i18n/en.json'

const CATALOG: Record<string, string> = Object.fromEntries(
  Object.entries(EN as Record<string, unknown>).map(([k, v]) => [
    k,
    typeof v === 'string' ? v : JSON.stringify(v),
  ]),
)
const KEYS = Object.keys(CATALOG)

/** Deutsch: Wort oder Muster, höchstens so viele Katalogtexte, stattdessen */
const GERMAN: [RegExp, number, string][] = [
  // Die oben gewählte Einheit heißt „Einheit“. „Arbeitsbereich“ gibt es nur noch für die
  // Untereinheit mit eigener Kasse und eigenen Rollen („Eigener Arbeitsbereich“).
  [/Arbeitsbereich/, 7, '„Einheit“; nur „Eigener Arbeitsbereich“ einer Untereinheit bleibt'],
  [
    /Organisation wechseln|aktive Organisation|Organisation zugeordnet|ganze Organisation/,
    0,
    '„Einheit“',
  ],
  [/Benutzerkonto/, 1, '„Konto“'],
  [/Mitgliedskarte/, 0, '„Ausweis“'],
  [/To-do/, 0, '„Aufgabe“'],
  [/Offene Punkte/, 0, '„Zu erledigen“'],
  [/Verwalter(?!in)/, 2, '„Leitung“'],
]

/** Englisch: deutsches Wort im Schlüssel, verbotenes englisches Wort im Wert, stattdessen */
const ENGLISH: [RegExp, RegExp, string][] = [
  [/Verbund(?!en)/, /federation/i, '“network”'],
  [/Dachverband/, /federation/i, '“umbrella association”'],
  [/Wechselanfrage/, /change request/i, '“transfer request”'],
  [/Arbeitsbereich/, /\bunit\b/i, '“workspace” (the sub-unit feature)'],
  [/^Entwicklung$/, /development/i, '“Trends”'],
]

describe('Begriffe (docs/begriffe.md)', () => {
  it('verbotene Nebenwörter kommen nicht in neue Texte', () => {
    for (const [pattern, max, instead] of GERMAN) {
      const hits = KEYS.filter((k) => pattern.test(k))
      expect(
        hits.length,
        `${pattern}: ${hits.length} Texte, erlaubt ${max}. Stattdessen ${instead} (docs/begriffe.md). Neu z. B.: ${hits.at(-1)}`,
      ).toBeLessThanOrEqual(max)
    }
  })

  it('englische Fassung folgt dem Glossar (docs/glossar-en.md)', () => {
    for (const [key, banned, instead] of ENGLISH) {
      const hits = KEYS.filter((k) => key.test(k) && banned.test(CATALOG[k]))
      expect(hits, `${key} → ${banned}: stattdessen ${instead}`).toEqual([])
    }
  })

  it('Menünamen der Finanzen und der Einstellungen sind nicht doppelt belegt', () => {
    // VW-12: „Konten“ sind die Anmeldekonten (Einstellungen), „Anlagen“ gehören zu „Räume und
    // Anlagen“; die Kasse sagt „Bankkonten und Kassen“ und „Anlagegüter“.
    expect(CATALOG['Bankkonten und Kassen']).toBe('Bank accounts and cash')
    expect(CATALOG['Anlagegüter']).toBe('Fixed assets')
    expect(CATALOG['Konten']).toBe('Accounts')
  })
})
