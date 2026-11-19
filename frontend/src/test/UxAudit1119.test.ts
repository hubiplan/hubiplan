// UX-Audit 16.11.2026, Reste der Verwaltung (19.11.): Prüfungen über den Quelltext.
import { describe, expect, it } from 'vitest'
import { DECISIONS, setLearningShooting, tr } from '../learning/content.ts'

const quellen = import.meta.glob(['../**/*.ts', '../**/*.tsx', '!../test/**', '!../**/*.test.*'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

/** Texte in t('…') und tn('…', …), nur der erste (deutsche) Schlüssel. */
function schluessel(quelle: string): string[] {
  return [...quelle.matchAll(/\btn?\(\s*'((?:[^'\\]|\\.)*)'/g)].map((m) => m[1])
}

/** Satzteil: beginnt oder endet mit Leerzeichen, endet mit „(“ oder beginnt mit „)“ oder „:“. */
const SATZTEIL = /^\s|\s$|\($|^[):]/

describe('VW-15: ganze Sätze statt Satzteile', () => {
  it('Rahmen, Tabelle, Rückmeldungen und Speicherstand kommen ohne Satzteile aus', () => {
    for (const datei of [
      '../components/Layout.tsx',
      '../components/DataTable.tsx',
      '../components/calendar/Rsvp.tsx',
      '../components/ui.tsx',
      '../components/RolePreview.tsx',
    ]) {
      const teile = schluessel(quellen[datei] ?? '').filter((k) => SATZTEIL.test(k))
      expect(teile, datei).toEqual([])
    }
  })

  it('die Zahl der Satzteile wächst nicht (Stand 19.11.2026)', () => {
    let zahl = 0
    for (const quelle of Object.values(quellen)) {
      zahl += schluessel(quelle).filter((k) => SATZTEIL.test(k)).length
    }
    expect(zahl).toBeLessThanOrEqual(325)
  })
})

describe('VW-13: Lernhilfen ohne Schützenwörter', () => {
  it('nutzt ohne Modul Schießsport die vereinsneutrale Fassung', () => {
    const text = DECISIONS.comp_own.text
    expect(text.neutral).toBeTruthy()
    setLearningShooting(false)
    try {
      expect(tr(text)).toBe(text.neutral)
      expect(tr(text)).not.toMatch(/Schütz|Schieß/)
    } finally {
      setLearningShooting(true)
    }
    expect(tr(text)).toBe(text.de)
  })
})

describe('VW-23: Löschen ohne Rückfrage, wo Rückgängig greift', () => {
  it('Veranstaltungen, Reihen, Rücklagenbewegungen und Quittungsentwürfe fragen nicht nach', () => {
    for (const datei of [
      '../pages/finance/ProjectsPage.tsx',
      '../pages/finance/ReservesPage.tsx',
      '../pages/finance/CashReceiptsPage.tsx',
    ]) {
      expect(quellen[datei], datei).toBeTruthy()
      expect(quellen[datei], datei).not.toContain('confirmDialog(')
    }
  })
})
