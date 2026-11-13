// Haushalte und Firmen H2/H3: Beitrag über den Haushalt und Zahler
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedIn = () => ({ status: 200, body: { status: 200, data: { user: testUser } } })
const base = '/api/orgs/7/households/'
const payerUrl = '/api/orgs/7/billing/households/3/payer/'

const muster = {
  id: 3,
  kind: 'family',
  name: 'Familie Muster',
  note: '',
  members: [
    {
      link: 11,
      membership: 21,
      first_name: 'Erika',
      last_name: 'Muster',
      title: '',
      birth_date: '1980-05-17',
      role: 'adult',
      pays_via: false,
      valid_from: '2026-01-01',
      valid_until: null,
      current: true,
    },
  ],
}

function renderApp(routes: Record<string, () => { status: number; body?: unknown }>) {
  const org = testOrg({
    permissions: ['members.view', 'members.edit', 'billing.view', 'billing.edit'],
    modules: ['members', 'billing'],
  })
  const calls = fakeApi({
    [SESSION]: loggedIn,
    'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
    [`GET ${base}?art=family`]: () => ({ status: 200, body: [muster] }),
    ...routes,
  })
  render(
    <MemoryRouter initialEntries={['/mitglieder/haushalte']}>
      <AuthProvider>
        <OrgProvider>
          <App />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
  return calls
}

describe('Beitrag über den Haushalt', () => {
  it('schaltet den Beitrag eines Mitglieds auf den Haushalt', async () => {
    const user = userEvent.setup()
    const calls = renderApp({
      [`PATCH ${base}3/members/11/`]: () => ({
        status: 200,
        body: { ...muster, members: [{ ...muster.members[0], pays_via: true }] },
      }),
    })
    const card = await screen.findByRole('region', { name: 'Familie Muster' })
    await user.click(within(card).getByRole('button', { name: 'Beitrag über den Haushalt' }))
    await waitFor(() =>
      expect(calls.some((c) => c.key === `PATCH ${base}3/members/11/`)).toBe(true),
    )
    const patch = calls.find((c) => c.key === `PATCH ${base}3/members/11/`)!
    expect(JSON.parse(String(patch.init?.body))).toEqual({ pays_via: true })
  })

  it('trägt eine Person ohne Mitgliedschaft als Zahler ein', async () => {
    const user = userEvent.setup()
    const saved = {
      household: 3,
      payer: {
        kind: 'external',
        membership: null,
        membership_name: '',
        partner: null,
        partner_name: '',
        name: 'Gisela Muster',
        attention: '',
        street: '',
        postal_code: '',
        city: '',
        country: '',
        email: '',
        order_reference: '',
        leitweg_id: '',
      },
      mandates: [],
    }
    const calls = renderApp({
      [`GET ${payerUrl}`]: () => ({
        status: 200,
        body: { household: 3, payer: null, mandates: [] },
      }),
      [`PUT ${payerUrl}`]: () => ({ status: 200, body: saved }),
    })
    const card = await screen.findByRole('region', { name: 'Familie Muster' })
    await user.click(within(card).getByRole('button', { name: 'Zahler und Mandat' }))
    await user.click(await within(card).findByRole('button', { name: 'Zahler eintragen' }))
    await user.selectOptions(within(card).getByLabelText('Wer zahlt?'), 'external')
    await user.type(within(card).getByLabelText(/^Name/), 'Gisela Muster')
    await user.click(within(card).getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(calls.some((c) => c.key === `PUT ${payerUrl}`)).toBe(true))
    const put = calls.find((c) => c.key === `PUT ${payerUrl}`)!
    const body = JSON.parse(String(put.init?.body))
    expect(body.kind).toBe('external')
    expect(body.name).toBe('Gisela Muster')
    expect(body.membership).toBeNull()
    expect(await within(card).findByText('Zahler gespeichert.')).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: 'Mandat erfassen' })).toBeInTheDocument()
  })
})
