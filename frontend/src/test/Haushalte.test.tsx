// Haushalte und Firmen (Konzept Familien, Haushalte und Firmen, H1)
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
      valid_from: '2026-01-01',
      valid_until: null,
      current: true,
    },
  ],
}

function renderApp(
  routes: Record<string, () => { status: number; body?: unknown }>,
  permissions = ['members.view', 'members.edit'],
) {
  const org = testOrg({ permissions })
  const calls = fakeApi({
    [SESSION]: loggedIn,
    'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
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

describe('Haushalte und Firmen', () => {
  it('zeigt Haushalte und legt einen neuen an', async () => {
    const user = userEvent.setup()
    const calls = renderApp({
      [`GET ${base}?art=family`]: () => ({ status: 200, body: [muster] }),
      [`POST ${base}`]: () => ({
        status: 201,
        body: { ...muster, id: 4, name: 'Familie Beispiel', members: [] },
      }),
    })
    const card = await screen.findByRole('region', { name: 'Familie Muster' })
    expect(within(card).getByRole('link', { name: 'Erika Muster' })).toHaveAttribute(
      'href',
      '/mitglieder/21',
    )
    expect(within(card).getByText('Erwachsener')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Haushalt anlegen' }))
    await user.type(screen.getByLabelText('Name'), 'Familie Beispiel')
    await user.click(screen.getByRole('button', { name: 'Anlegen' }))
    await waitFor(() => expect(calls.some((c) => c.key === `POST ${base}`)).toBe(true))
    const post = calls.find((c) => c.key === `POST ${base}`)!
    expect(JSON.parse(String(post.init?.body))).toEqual({
      kind: 'family',
      name: 'Familie Beispiel',
    })
    expect(await screen.findByText('„Familie Beispiel“ angelegt.')).toBeInTheDocument()
  })

  it('nimmt ein Mitglied nach Rückfrage heraus', async () => {
    const user = userEvent.setup()
    const calls = renderApp({
      [`GET ${base}?art=family`]: () => ({ status: 200, body: [muster] }),
      [`PATCH ${base}3/members/11/`]: () => ({ status: 200, body: muster }),
    })
    const card = await screen.findByRole('region', { name: 'Familie Muster' })
    await user.click(within(card).getByRole('button', { name: 'Herausnehmen' }))
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: 'Herausnehmen' }))
    await waitFor(() =>
      expect(calls.some((c) => c.key === `PATCH ${base}3/members/11/`)).toBe(true),
    )
    const patch = calls.find((c) => c.key === `PATCH ${base}3/members/11/`)!
    expect(Object.keys(JSON.parse(String(patch.init?.body)))).toEqual(['valid_until'])
  })

  it('ohne Bearbeitungsrecht nur lesen', async () => {
    renderApp({ [`GET ${base}?art=family`]: () => ({ status: 200, body: [muster] }) }, [
      'members.view',
    ])
    await screen.findByRole('region', { name: 'Familie Muster' })
    expect(screen.queryByRole('button', { name: 'Haushalt anlegen' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Herausnehmen' })).not.toBeInTheDocument()
  })
})
