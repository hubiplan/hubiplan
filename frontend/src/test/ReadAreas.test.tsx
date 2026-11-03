import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

function setup(permissions: string[], endpoint: string) {
  const calls = fakeApi({
    'GET /_allauth/browser/v1/auth/session': () => ({
      status: 200,
      body: { data: { user: testUser } },
    }),
    'GET /api/me/organizations/': () => ({ status: 200, body: [testOrg({ permissions })] }),
    [`GET /api/orgs/7/${endpoint}/`]: () => ({
      status: 200,
      body: [
        {
          id: 5,
          name: 'Musterzug',
          is_active: true,
          roles: [],
          founding_year: 1920,
          sort_order: 0,
          fiscal_start_month: 1,
          fiscal_start_day: 1,
          logo_url: null,
        },
      ],
    }),
    'GET /api/permissions/?org_type=department&org=7': () => ({ status: 200, body: [] }),
  })
  render(
    <MemoryRouter initialEntries={['/untereinheiten']}>
      <AuthProvider>
        <OrgProvider>
          <App />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
  return calls
}

describe('Getrennte Lese- und Rollenbereiche', () => {
  it('lädt für Rollenleser nur die begrenzte Auswahl ohne Einheitsverwaltung', async () => {
    const calls = setup(['roles.view'], 'department-choices')
    expect(await screen.findByRole('heading', { name: 'Rollen in Musterzug' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Neue Rolle' })).not.toBeInTheDocument()
    expect(calls.some((c) => c.key === 'GET /api/orgs/7/departments/')).toBe(false)
  })

  it('gibt reinen Einstellungsbearbeitern keine Rollenpflege', async () => {
    setup(['org.edit'], 'departments')
    await userEvent.click(await screen.findByRole('button', { name: 'Musterzug bearbeiten' }))
    expect(screen.queryByRole('button', { name: 'Neue Rolle' })).not.toBeInTheDocument()
    expect(screen.queryByText('Rollen in')).not.toBeInTheDocument()
    expect(screen.queryByTestId('unit-manager')).not.toBeInTheDocument()
  })
})
