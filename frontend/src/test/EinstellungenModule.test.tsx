// Einstellungen › Module: freigegebene Module ein- und ausschalten (M3).
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedIn = () => ({ status: 200, body: { status: 200, data: { user: testUser } } })
const M = '/api/orgs/7/modules/'

function mod(id: string, label: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    label,
    description: '',
    requires: [],
    requires_any: [],
    released: true,
    enabled: false,
    needed_by: [],
    ...extra,
  }
}

const groups = (musicOn: boolean) => [
  {
    id: 'life',
    label: 'Vereinsleben',
    modules: [
      mod('events', 'Termine', { enabled: true }),
      mod('website', 'Webseite', { released: false }),
    ],
  },
  {
    id: 'music',
    label: 'Musik',
    modules: [
      mod('music', 'Musik', { requires: ['events', 'scores'], enabled: musicOn }),
      mod('scores', 'Notenarchiv', { enabled: musicOn }),
    ],
  },
]

it('schaltet ein Modul mit seinen Voraussetzungen ein, nicht freigegebene sind gesperrt', async () => {
  const calls = fakeApi({
    [SESSION]: loggedIn,
    'GET /api/me/organizations/': () => ({
      status: 200,
      body: [testOrg({ permissions: ['settings.view', 'settings.edit'] })],
    }),
    [`GET ${M}`]: () => ({ status: 200, body: { groups: groups(false) } }),
    [`PATCH ${M}`]: (init) => {
      const body = JSON.parse(String(init?.body))
      return {
        status: 200,
        body: body.dry_run
          ? { changes: { on: ['music', 'scores'], off: [] } }
          : { changes: { on: ['music', 'scores'], off: [] }, groups: groups(true) },
      }
    },
  })
  render(
    <MemoryRouter initialEntries={['/einstellungen/module']}>
      <AuthProvider>
        <OrgProvider>
          <App />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
  const user = userEvent.setup()
  expect(await screen.findByRole('checkbox', { name: /Webseite/ })).toBeDisabled()
  await user.click(screen.getByRole('checkbox', { name: /^Musik/ }))
  expect(await screen.findByText(/Mit eingeschaltet: Notenarchiv/)).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: /OK|Ja|Bestätigen/ }))
  await waitFor(() => expect(screen.getByRole('checkbox', { name: /^Musik/ })).toBeChecked())
  const saves = calls.filter((c) => c.key === `PATCH ${M}`)
  expect(saves.map((c) => JSON.parse(String(c.init?.body)).dry_run)).toEqual([true, false])
})
