// Sicht „Mein Verein“ (Konzept Web-Oberfläche W3): vier Bereiche wie in den Apps.
import { describe, expect, it } from 'vitest'
import type { PortalEntry } from '../api/portal.ts'
import { currentMemberArea, memberAreas } from '../components/memberAreas.tsx'

const entry = (extra: Partial<PortalEntry> = {}) =>
  ({
    id: 5,
    club_id: 7,
    club_name: 'TV Beispielhausen',
    first_name: 'Erika',
    events_enabled: true,
    pinboard_enabled: true,
    ...extra,
  }) as PortalEntry

describe('Bereiche der Sicht „Mein Verein“', () => {
  it('zeigt Start, Termine, Neues und Ich; Pinnwand und Mitteilungen stehen unter Neues', () => {
    const areas = memberAreas(entry(), true)
    expect(areas.map((a) => a.id)).toEqual(['start', 'termine', 'neues', 'ich'])
    expect(areas[2].links.map((l) => l.to)).toEqual([
      '/mein-bereich/pinnwand',
      '/mein-bereich/rundschreiben',
    ])
    const own = areas[3].links.map((l) => l.to)
    expect(own[0]).toBe('/mein-bereich')
    expect(own).toContain('/mein-bereich/rechnungen')
    expect(own).toContain('/dokumente')
    expect(own).not.toContain('/mein-bereich/pinnwand')
  })

  it('lässt leere Bereiche weg', () => {
    const areas = memberAreas(
      entry({ events_enabled: false, pinboard_enabled: false, circulars_enabled: false }),
      false,
    )
    expect(areas.map((a) => a.id)).toEqual(['start', 'ich'])
  })

  it('ordnet die aktuelle Seite dem Bereich mit dem längsten passenden Pfad zu', () => {
    const areas = memberAreas(entry(), true)
    expect(currentMemberArea(areas, '/')?.id).toBe('start')
    expect(currentMemberArea(areas, '/termine/12')?.id).toBe('termine')
    expect(currentMemberArea(areas, '/mein-bereich/pinnwand')?.id).toBe('neues')
    expect(currentMemberArea(areas, '/mein-bereich/ausweis')?.id).toBe('ich')
    expect(currentMemberArea(areas, '/hilfe')).toBeNull()
  })
})
