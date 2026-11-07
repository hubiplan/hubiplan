import { describe, expect, it } from 'vitest'
import type { OrgSummary } from '../api/orgs.ts'
import { memberSections, setupTabs } from '../pages/members/access.ts'
import { websiteSections } from '../pages/website/sections.ts'
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
})
