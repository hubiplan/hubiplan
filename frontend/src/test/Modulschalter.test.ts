import { describe, expect, it } from 'vitest'
import type { OrgSummary } from '../api/orgs.ts'
import { memberSections, setupTabs } from '../pages/members/access.ts'
import { modules } from '../modules.tsx'
import { websiteSections } from '../pages/website/sections.ts'
import { musicSections } from '../pages/music/access.ts'
import { testOrg } from './fakeApi.ts'

const club = (modules: string[], permissions = ['members.view', 'members.edit']) =>
  testOrg({ modules, permissions }) as unknown as OrgSummary

describe('Module Ehrungen & Jubiläen, Würden und Social Media', () => {
  it('ohne die Module fehlen Jubiläen, Würdenträger und die Einrichtung der Ehrungen', () => {
    const org = club(['members'])
    const items = memberSections(org).map((s) => s.label)
    expect(items).not.toContain('Jubiläen')
    expect(items).not.toContain('Würdenträger')
    const tabs = setupTabs(org).map((s) => s.label)
    expect(tabs).not.toContain('Ehrungen')
    expect(tabs).not.toContain('Jubiläen & Dauer')
  })

  it('mit den Modulen erscheinen sie', () => {
    const org = club(['members', 'awards', 'honors'])
    const items = memberSections(org).map((s) => s.label)
    expect(items).toContain('Jubiläen')
    expect(items).toContain('Würdenträger')
    expect(setupTabs(org).map((s) => s.label)).toContain('Ehrungen')
  })

  it('Social Media nur mit Modul', () => {
    const perms = ['website.manage', 'website.view']
    const without = websiteSections(club(['website'], perms)).map((s) => s.to)
    expect(without).not.toContain('/webseite/beitraege')
    const withSocial = websiteSections(club(['website', 'social'], perms)).map((s) => s.to)
    expect(withSocial).toContain('/webseite/beitraege')
  })

  it('Chronik ist ein eigener Menüpunkt, nur mit Modul und Leserecht', () => {
    const chronik = modules.find((m) => m.id === 'chronik')!
    const ws = { dept: null, portal: null }
    expect(chronik.visible(club(['chronicle'], ['chronicle.view']), ws)).toBe(true)
    expect(chronik.visible(club([], ['chronicle.view']), ws)).toBe(false)
    expect(chronik.visible(club(['chronicle'], ['members.view']), ws)).toBe(false)
  })

  it('Notenarchiv: unter Musik, ohne Musik als eigener Menüpunkt „Noten“', () => {
    const noten = modules.find((m) => m.id === 'noten')!
    const ws = { dept: null, portal: null }
    const choir = club(['scores'], ['scores.view'])
    expect(noten.visible(choir, ws)).toBe(true)
    const band = club(['music', 'events', 'scores'], ['music.view', 'scores.view'])
    expect(noten.visible(band, ws)).toBe(false)
    expect(musicSections(band).map((s) => s.to)).toContain('/musik/noten')
    const musicOnly = club(['music', 'events', 'scores'], ['music.view'])
    expect(musicSections(musicOnly).map((s) => s.to)).not.toContain('/musik/noten')
    expect(noten.visible(club([], ['scores.view']), ws)).toBe(false)
  })
})
