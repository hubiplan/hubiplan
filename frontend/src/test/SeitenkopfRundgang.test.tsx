// Rundgang über alle Menüpunkte (Seitenkopf S-05, UX-Audit 08.11. X-01): Die h1 jeder Seite
// heißt wie der aktive Menüpunkt. Abweichungen stehen in ABWEICHUNGEN und verschwinden mit
// der Umstellung auf PageHeader (P2/P3).
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { PERM } from '../api/orgs.ts'
import type { OrgSummary } from '../api/orgs.ts'
import { modules } from '../modules.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'

const ALL_MODULES = [
  'awards',
  'billing',
  'bookings',
  'calls',
  'chronicle',
  'competitions',
  'donations',
  'entries',
  'events',
  'finance',
  'helpers',
  'honors',
  'infrastructure',
  'material',
  'meetings',
  'members',
  'music',
  'scores',
  'shooting',
  'social',
  'tax',
  'website',
]

const org = testOrg({
  modules: ALL_MODULES,
  permissions: [...new Set(Object.values(PERM))],
  parent_name: null,
}) as unknown as OrgSummary

/** Menüpunkt → heutige h1, solange die Seite noch nicht umgestellt ist */
// Leer: Die Seite zeigt ohne Daten (noch) keine h1. „/einstellungen“ und „/plattform“ leiten
// auf ihren ersten Unterpunkt weiter.
const ABWEICHUNGEN: Record<string, string> = {
  '/mitglieder/einrichtung': 'Mitgliedsarten',
  '/musik': '',
  '/musik/verfuegbarkeit': '',
  '/musik/musiker': '',
  '/musik/proben': '',
  '/musik/noten': '',
  '/musik/vorlagen': '',
  '/wettbewerbe/statistik': 'Wettbewerbsstatistik',
  '/wettbewerbe/einrichtung': '',
  '/chronik': '',
  '/material/musik': '',
  '/einstellungen': 'Organisation',
  '/plattform': 'Einheiten',
}

function pages() {
  const ws = { dept: null, portal: null }
  const list: { to: string; label: string }[] = []
  for (const m of modules.filter((mod) => mod.visible(org, ws))) {
    if (m.path === '/') continue
    const modLabel = m.labelFor?.(org, ws) ?? m.label
    list.push({ to: m.linkFor?.(org, ws) ?? m.path, label: modLabel })
    for (const c of m.children?.(org, ws) ?? []) {
      if (c.to !== m.path) list.push({ to: c.to, label: c.label })
    }
  }
  return list
}

async function headingAt(path: string): Promise<string> {
  // Unbekannte Aufrufe enden als Fehler; die Seite zeigt ihren Kopf trotzdem
  fakeApi({
    [SESSION]: () => ({ status: 200, body: { status: 200, data: { user: testUser } } }),
    'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
  })
  vi.spyOn(console, 'error').mockImplementation(() => undefined)
  const view = render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <OrgProvider>
          <App />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
  let text = ''
  await waitFor(
    () => {
      const h1 = screen.getAllByRole('heading', { level: 1 })[0]
      text = (h1.textContent ?? '').trim()
      expect(text).not.toBe('')
    },
    { timeout: 3000 },
  ).catch(() => undefined)
  view.unmount()
  vi.restoreAllMocks()
  return text
}

describe('Seitenkopf-Rundgang', () => {
  it('h1 = Beschriftung des Menüpunkts auf allen Seiten', async () => {
    const found: Record<string, string> = {}
    for (const p of pages()) {
      const h1 = await headingAt(p.to)
      if (h1 !== p.label) found[p.to] = h1
    }
    expect(found).toEqual(ABWEICHUNGEN)
  }, 300_000)
})
