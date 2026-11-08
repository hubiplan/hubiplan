import { describe, expect, it } from 'vitest'
import type { PortalEntry } from '../api/portal.ts'
import { portalNav, portalSections } from '../pages/portal/sections.ts'

const entry = (extra: Partial<PortalEntry> = {}) =>
  ({ id: 3, club_name: 'Schützenverein Beispieldorf', ...extra }) as PortalEntry

describe('Mein Bereich aus einer Liste (Menüprüfung M-07)', () => {
  it('nimmt freigeschaltete Punkte in die Seitenleiste auf', () => {
    const labels = portalNav(
      entry({
        bookings_enabled: true,
        entries_enabled: true,
        competitions_enabled: true,
        musician: true,
      }),
    ).map((s) => s.label)
    expect(labels).toEqual([
      'Übersicht',
      'Aufgaben',
      'Ausweis',
      'Belegung',
      'Wettbewerbe',
      'Musik',
      'Rechnungen',
      'Mitteilungen',
      'Meine Daten',
    ])
  })

  it('Kontomenü und Kacheln nutzen dasselbe Wort', () => {
    const sections = portalSections(entry({ events_enabled: true }))
    expect(sections.flatMap((s) => (s.account ? [s.account] : []))).toEqual([
      'Übersicht',
      'Mein Ausweis',
      'Meine Termine',
      'Meine Rechnungen',
    ])
    const termine = sections.find((s) => s.to === '/termine')
    expect(termine?.label).toBeUndefined()
    expect(termine?.tile?.title).toBe('Meine Termine')
  })
})
