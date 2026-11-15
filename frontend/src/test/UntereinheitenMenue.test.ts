// Vereine ohne Untereinheiten blenden den Menüpunkt aus (Einstellungen › Bezeichnungen).
import { describe, expect, it } from 'vitest'
import { modules } from '../modules.tsx'
import type { OrgSummary } from '../api/orgs.ts'
import { testOrg } from './fakeApi.ts'

const org = (extra: Record<string, unknown> = {}) =>
  testOrg({ permissions: ['settings.view'], ...extra }) as unknown as OrgSummary
const NO_WS = { dept: null, portal: null }
const units = modules.find((m) => m.id === 'untereinheiten')!

describe('Menüpunkt Untereinheiten', () => {
  it('erscheint standardmäßig mit Leserecht', () => {
    expect(units.visible(org(), NO_WS)).toBe(true)
  })

  it('verschwindet, wenn der Verein ihn ausschaltet', () => {
    expect(units.visible(org({ units_in_menu: false }), NO_WS)).toBe(false)
  })
})
