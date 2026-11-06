// Einstellungen › Konten: Filter und Sammelversand (Rollen-Vorschlag R4).
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const account = (id: number, name: string, extra: object) => ({
  id,
  name,
  email: `${name.split(' ')[0].toLowerCase()}@example.org`,
  membership: null,
  roles: [],
  rights: false,
  member_area: false,
  last_login: '2026-11-01T10:00:00Z',
  awaiting_password: false,
  invitation_expired: false,
  has_mfa: false,
  mfa_missing: false,
  ...extra,
})

describe('Konten', () => {
  it('filtert und sendet Anmeldelinks an die gewählten Konten', async () => {
    const calls = fakeApi({
      'GET /_allauth/browser/v1/auth/session': () => ({
        status: 200,
        body: { data: { user: testUser } },
      }),
      'GET /api/me/organizations/': () => ({
        status: 200,
        body: [testOrg({ permissions: ['logins.view', 'logins.edit'] })],
      }),
      'GET /api/orgs/7/accounts/': () => ({
        status: 200,
        body: [
          account(1, 'Karl Kasse', {
            roles: ['Kassierer'],
            rights: true,
            last_login: null,
            awaiting_password: true,
            invitation_expired: true,
            mfa_missing: true,
          }),
          account(2, 'Erika Muster', { member_area: true }),
        ],
      }),
      'POST /api/orgs/7/accounts/resend/': () => ({
        status: 200,
        body: { sent: ['karl@example.org'], skipped: [] },
      }),
    })
    render(
      <MemoryRouter initialEntries={['/einstellungen/konten']}>
        <AuthProvider>
          <OrgProvider>
            <App />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>,
    )
    const user = userEvent.setup()
    const table = await screen.findByRole('table', { name: 'Konten' })
    expect(within(table).getByText('Erika Muster')).toBeInTheDocument()
    expect(within(table).getByText('nie (Einladung abgelaufen)')).toBeInTheDocument()
    expect(within(table).getByText('fehlt (Pflicht)')).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Zeigen'), 'Einladung abgelaufen')
    expect(within(table).queryByText('Erika Muster')).not.toBeInTheDocument()
    await user.click(screen.getByRole('checkbox', { name: 'Alle auswählen' }))
    await user.click(screen.getByRole('button', { name: 'Anmeldelink erneut senden (1)' }))
    await waitFor(() =>
      expect(calls.some((c) => c.key === 'POST /api/orgs/7/accounts/resend/')).toBe(true),
    )
    const sent = calls.find((c) => c.key === 'POST /api/orgs/7/accounts/resend/')!
    expect(JSON.parse(String(sent.init?.body))).toEqual({ users: [1] })
    expect(await screen.findByText('Gesendet an ein Konto.')).toBeInTheDocument()
  })
})
