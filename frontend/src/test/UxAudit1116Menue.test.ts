// UX-Audit 16.11.2026, VW-33 (kleine Fassung): Meldungen stehen als Unterpunkt unter
// Wettbewerbe, solange es diesen Menüpunkt gibt; ohne Wettbewerbe bleiben sie ein Hauptpunkt.
import { describe, expect, it } from 'vitest'
import { modules } from '../modules.tsx'
import type { OrgSummary } from '../api/orgs.ts'
import { testOrg } from './fakeApi.ts'

const org = (mods: string[], permissions: string[]) =>
  testOrg({ modules: mods, permissions }) as unknown as OrgSummary
const NO_WS = { dept: null, portal: null }
const competitions = modules.find((m) => m.id === 'wettbewerbe')!
const entries = modules.find((m) => m.id === 'meldungen')!

describe('VW-33 Meldungen unter Wettbewerbe', () => {
  it('zeigt Meldungen als Unterpunkt, wenn beide Bereiche da sind', () => {
    const both = org(['competitions', 'entries'], ['competitions.view', 'entries.view'])
    expect(competitions.visible(both, NO_WS)).toBe(true)
    expect(entries.visible(both, NO_WS)).toBe(false)
    const children = competitions.children!(both, NO_WS)
    expect(children.map((c) => c.to)).toContain('/meldungen')
    // „Einrichtung“ bleibt der letzte Unterpunkt (docs/begriffe.md)
    expect(children[children.length - 1].to).toBe('/wettbewerbe/einrichtung')
    expect(competitions.also).toContain('/meldungen')
  })

  it('lässt Meldungen als Hauptpunkt, wenn es Wettbewerbe nicht gibt', () => {
    const only = org(['entries'], ['entries.view'])
    expect(competitions.visible(only, NO_WS)).toBe(false)
    expect(entries.visible(only, NO_WS)).toBe(true)
  })

  it('zeigt unter Wettbewerbe keine Meldungen ohne das Recht dazu', () => {
    const none = org(['competitions', 'entries'], ['competitions.view'])
    expect(competitions.children!(none, NO_WS).map((c) => c.to)).not.toContain('/meldungen')
  })
})
