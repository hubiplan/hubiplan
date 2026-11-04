import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

it('zeigt bestehende Preisplatz-Auswahl und speichert sie weiter kompatibel', async () => {
  localStorage.clear()
  const base = '/api/orgs/7/competitions/'
  let comp = {
    id: 3,
    title: 'Preisschießen 2027',
    date: '2027-06-14',
    form: 'rangliste',
    own: true,
    status: 'vorbereitung',
    website: 'live',
    website_depth: 'top3',
    can_manage: true,
    occasion: '',
    discipline: '',
    location: '',
    description: '',
    organizer: '',
    details: [],
    scorings: [],
    units: [],
    prizes: [],
    lots: [],
    drop_out: true,
    fixed_order: false,
    share_ranking: false,
    total_shots: null,
    series: null,
    certificate_template: null,
  }
  const org = testOrg({ permissions: ['competitions.manage'], modules: ['competitions'] })
  const calls = fakeApi({
    'GET /_allauth/browser/v1/auth/session': () => ({
      status: 200,
      body: { status: 200, data: { user: testUser } },
    }),
    'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
    [`GET ${base}3/`]: () => ({ status: 200, body: comp }),
    [`PATCH ${base}3/`]: (init) => {
      comp = { ...comp, ...JSON.parse(String(init?.body)) }
      return { status: 200, body: comp }
    },
  })
  render(
    <MemoryRouter initialEntries={['/wettbewerbe/3/einrichten']}>
      <AuthProvider>
        <OrgProvider>
          <App />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
  const user = userEvent.setup()
  const select = await screen.findByLabelText('Umfang auf der Webseite')
  expect(select).toHaveValue('top3')
  expect(within(select).getByRole('option', { name: 'Preisplätze mit Namen' })).toBeVisible()
  expect(within(select).queryByRole('option', { name: 'Plätze 1 bis 3 mit Namen' })).toBeNull()
  await user.selectOptions(select, 'alle')
  await waitFor(() => expect(comp.website_depth).toBe('alle'))
  await user.selectOptions(select, 'top3')
  await waitFor(() => expect(comp.website_depth).toBe('top3'))
  expect(
    calls
      .filter((call) => call.key === `PATCH ${base}3/`)
      .map((call) => JSON.parse(String(call.init?.body)).website_depth),
  ).toEqual(['alle', 'top3'])
})
