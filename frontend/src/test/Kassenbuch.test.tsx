import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import type { OrgSummary } from '../api/orgs.ts'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { inReach } from '../help/content.ts'
import { financeAccess, financeGroups, financeSections } from '../pages/finanzen/access.ts'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedIn = () => ({ status: 200, body: { status: 200, data: { user: testUser } } })

// Einheit nur mit dem Modul Kasse (Vorlage „Kassenbuch“)
const NUR_KASSE = testOrg({
  id: 7,
  name: 'Kassenbuch Musterstadt',
  parent_name: '',
  modules: ['finance'],
  permissions: ['finance.view', 'finance.edit', 'partners.view'],
})

function renderAt(path: string, org: unknown) {
  const api = fakeApi({
    [SESSION]: loggedIn,
    'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
  })
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <OrgProvider>
          <App />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
  return api
}

describe('Nur Kassenbuch', () => {
  it('beschreibt die Finanzgruppen ohne Beiträge, Mahnungen, Steuern und Zuwendungen', () => {
    const a = financeAccess(NUR_KASSE as unknown as OrgSummary)
    const texts = Object.values(financeGroups(a)).map((g) => g.text ?? '')
    for (const text of texts) {
      expect(text).not.toMatch(/Beitr|Mahn|Lastschrift|Steuern|Zuwendung|Rücklagen/)
    }
    // Ohne Zugang (Hilfe) bleibt der volle Text
    expect(financeGroups().setup.text).toMatch(/Beitragssätze/)
    const labels = financeSections(a).map((s) => s.label)
    expect(labels).toContain('Kassenbuch')
    expect(labels).not.toContain('Beitragsläufe')
  })

  it('zeigt unter /termine ohne Modul „Kein Zugriff“ statt eines Ladefehlers', async () => {
    const api = renderAt('/termine', NUR_KASSE)
    expect(await screen.findByTestId('kein-zugriff')).toBeInTheDocument()
    expect(api.some((c) => c.key.startsWith('GET /api/orgs/7/events/'))).toBe(false)
  })

  it('zeigt dem Nur-lesen-Konto keinen Hinweis auf fehlende Bereiche', async () => {
    renderAt('/', testOrg({ id: 7, modules: ['finance'], permissions: ['finance.view'] }))
    expect(await screen.findByRole('link', { name: 'Finanzen' })).toBeInTheDocument()
    expect(
      screen.queryByText(/noch keine Bereiche für dich freigeschaltet/),
    ).not.toBeInTheDocument()
  })
})

describe('Hilfe im reinen Kassenbuch', () => {
  const none = { portal: false, dept: false, units: false, cashCounts: false }
  const all = { portal: true, dept: true, units: true, cashCounts: true }

  it('lässt Hilfen zu Bereichen weg, die es nicht gibt', () => {
    for (const routes of [
      ['/mein-bereich/ausweis'],
      ['/mein-bereich/daten', '/mein-bereich'],
      ['/abteilung'],
      ['/untereinheiten'],
      ['/finanzen/kassenzaehlung'],
    ]) {
      expect(inReach({ routes }, none)).toBe(false)
      expect(inReach({ routes }, all)).toBe(true)
    }
  })

  it('zeigt alles andere unverändert', () => {
    expect(inReach({ routes: ['/finanzen/kassenbuch'] }, none)).toBe(true)
    expect(inReach({ routes: ['/mein-konto/app'] }, none)).toBe(true)
    expect(inReach({ routes: [] }, none)).toBe(true)
    // Gemischte Routen gehören nicht nur zu dem Bereich
    expect(inReach({ routes: ['/mein-bereich', '/termine'] }, none)).toBe(true)
  })
})
