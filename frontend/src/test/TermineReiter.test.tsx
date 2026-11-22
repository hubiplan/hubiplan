// Termine: nur eine Reiterzeile (Ralf 22.11.). Kalender und Einrichtung stehen im Menü,
// die Reiter der Einrichtung erscheinen nur in der Einrichtung.
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

function renderApp(path: string, permissions: string[]) {
  fakeApi({
    'GET /_allauth/browser/v1/auth/session': () => ({
      status: 200,
      body: { status: 200, data: { user: testUser } },
    }),
    'GET /api/me/organizations/': () => ({
      status: 200,
      body: [{ ...testOrg({ permissions }), modules: ['members', 'events'] }],
    }),
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
}

const rows = () => [...document.querySelectorAll('main nav.tabs')]

describe('Termine: eine Reiterzeile', () => {
  it('Kalender ohne Reiter, Kalender und Einrichtung im Menü', async () => {
    renderApp('/termine', ['events.view', 'events.manage'])
    const menu = within(await screen.findByRole('navigation', { name: 'Hauptmenü' }))
    expect(await menu.findByRole('link', { name: 'Kalender' })).toBeInTheDocument()
    expect(menu.getByRole('link', { name: 'Einrichtung' })).toBeInTheDocument()
    expect(rows()).toHaveLength(0)
  })

  it('in der Einrichtung genau eine Reiterzeile mit deren Unterpunkten', async () => {
    renderApp('/termine/einrichtung/kategorien', ['events.view', 'events.manage'])
    const main = within(await screen.findByRole('main'))
    expect(await main.findByRole('link', { name: 'Fremde Kalender' })).toBeInTheDocument()
    expect(rows()).toHaveLength(1)
    expect(main.queryByRole('link', { name: 'Kalender' })).toBeNull()
    expect(main.getByRole('heading', { level: 1 })).toHaveTextContent('Kategorien')
  })

  it('ohne Verwalten weder Reiter noch Unterpunkte', async () => {
    renderApp('/termine', ['events.view'])
    const menu = within(await screen.findByRole('navigation', { name: 'Hauptmenü' }))
    expect(await menu.findByRole('link', { name: 'Termine' })).toBeInTheDocument()
    expect(menu.queryByRole('link', { name: 'Einrichtung' })).toBeNull()
    expect(rows()).toHaveLength(0)
  })
})
