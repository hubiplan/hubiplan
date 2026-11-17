// UX-Audit 16.11.2026, Handy in der Verwaltung: „Hilfe zu dieser Seite“ auch schmal erreichbar
// (VW-02), Empfängerliste eines Rundschreibens beginnt kurz und lässt sich durchsuchen (VW-58).
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App.tsx'
import { circularBase } from '../api/circulars.ts'
import type { CircularOptions } from '../api/circulars.ts'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { RecipientPanel } from '../components/circulars/RecipientPanel.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const ORG = testOrg({ permissions: ['members.view'] })

afterEach(() => vi.unstubAllGlobals())

describe('Hilfe zu dieser Seite am Handy', () => {
  it('steht auch im schmalen Fenster im Kopf', async () => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: query.includes('max-width'),
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
    }))
    fakeApi({
      [SESSION]: () => ({ status: 200, body: { status: 200, data: { user: testUser } } }),
      'GET /api/me/organizations/': () => ({ status: 200, body: [ORG] }),
    })
    render(
      <MemoryRouter initialEntries={['/']}>
        <AuthProvider>
          <OrgProvider>
            <App />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>,
    )
    const button = await screen.findByRole('button', { name: 'Hilfe zu dieser Seite' })
    expect(button.closest('header')).not.toBeNull()
    expect(button).toHaveClass('help-button-compact')
  })
})

describe('Empfängerliste eines Rundschreibens', () => {
  const items = Array.from({ length: 214 }, (_, i) => ({
    key: `m${i}`,
    last_name: `Muster${String(i).padStart(3, '0')}`,
    first_name: 'Kim',
    email: `kim${i}@example.org`,
    channel: 'mail',
  }))

  function renderPanel() {
    fakeApi({
      'GET /api/orgs/7/circulars/3/recipients/': () => ({
        status: 200,
        body: { counts: { mail: 214, letter: 0 }, items },
      }),
    })
    return render(
      <RecipientPanel
        base={circularBase.org(7)}
        circularId={3}
        options={{ org_type: 'club' } as CircularOptions}
        audience="members"
        filters={{}}
        onFilters={() => {}}
        version={0}
        fixed
      />,
    )
  }

  it('zeigt zuerst höchstens 20 und auf Wunsch alle', async () => {
    renderPanel()
    const table = await screen.findByRole('table')
    expect(within(table).getAllByRole('row')).toHaveLength(21)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Alle 214 anzeigen' }))
    expect(within(table).getAllByRole('row')).toHaveLength(215)
    await user.click(screen.getByRole('button', { name: 'Weniger anzeigen' }))
    expect(within(table).getAllByRole('row')).toHaveLength(21)
  })

  it('findet eine Person über die Suche in der Liste', async () => {
    renderPanel()
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('In der Empfängerliste suchen'), 'muster213')
    const rows = within(screen.getByRole('table')).getAllByRole('row')
    expect(rows).toHaveLength(2)
    expect(rows[1]).toHaveTextContent('Muster213, Kim')
  })
})
