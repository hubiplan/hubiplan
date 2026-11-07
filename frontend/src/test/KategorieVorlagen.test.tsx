// Vorlagen für Kategorien (Konzept vereinskasse-steuern, S8); erfundene Daten
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedIn = () => ({ status: 200, body: { status: 200, data: { user: testUser } } })
const F = '/api/orgs/7/finance'

const cat = (name: string, exists: boolean) => ({
  name,
  kind: 'income',
  kind_label: 'Einnahmen',
  tax_area: 'ideal',
  tax_area_label: 'ideeller Bereich',
  donations: false,
  artist_fees: false,
  exists,
})

describe('Kategorie-Vorlagen', () => {
  it('legt die fehlenden Kategorien einer Vorlage an', async () => {
    let applied = false
    const calls = fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({
        status: 200,
        body: [
          testOrg({
            modules: ['members', 'finance', 'tax'],
            permissions: ['finance.view', 'finance.edit'],
          }),
        ],
      }),
      [`GET ${F}/categories/`]: () => ({ status: 200, body: [] }),
      [`GET ${F}/settings/`]: () => ({
        status: 200,
        body: { current_year: 2026, years: [], tax_areas: [], tax_areas_enabled: true },
      }),
      [`GET ${F}/categories/templates/`]: () => ({
        status: 200,
        body: [
          {
            key: 'musik',
            label: 'Musikverein',
            categories: [cat('Mitgliedsbeiträge', applied), cat('Konzerte Eintritt', applied)],
          },
        ],
      }),
      [`POST ${F}/categories/templates/`]: () => {
        applied = true
        return { status: 201, body: { created: ['Mitgliedsbeiträge', 'Konzerte Eintritt'] } }
      },
    })
    render(
      <MemoryRouter initialEntries={['/finanzen/einrichtung/kategorien']}>
        <AuthProvider>
          <OrgProvider>
            <App />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>,
    )
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Vorlage übernehmen' }))
    expect(await screen.findByText('Konzerte Eintritt')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '2 Kategorien anlegen' }))
    expect(await screen.findByText('2 Kategorien angelegt.')).toBeInTheDocument()
    expect(calls.some((c) => c.key === `POST ${F}/categories/templates/`)).toBe(true)
  })
})
