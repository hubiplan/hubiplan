// Bankanbindung: Umsätze bei der Bank abrufen (PIN, Freigabe mit TAN, Schutz vor Sperre).
import { render, screen, waitFor } from '@testing-library/react'
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

const access = {
  id: 4,
  name: 'Testbank',
  way: 'fints',
  bank_code: '12345678',
  url: 'https://bank.example/fints',
  login_hint: '…t1',
  tan_mechanism: '942',
  tan_mechanism_name: 'mobile TAN',
  tan_medium: '',
  ready: true,
  ibans: ['DE111234567800000001'],
  accounts: [{ id: 1, name: 'Girokonto', iban: 'DE111234567800000001', fetched_until: null }],
  last_success: null,
  paused_until: null,
  retry_needs_confirm: false,
}

function routes(extra: Parameters<typeof fakeApi>[0], enabled = true, item = access) {
  return {
    [SESSION]: loggedIn,
    'GET /api/me/organizations/': () => ({
      status: 200,
      body: [
        testOrg({
          modules: ['members', 'finance'],
          permissions: ['finance.view', 'finance.edit'],
          bank_access_enabled: enabled,
        }),
      ],
    }),
    [`GET ${F}/bank-statements/?page_size=50`]: () => ({
      status: 200,
      body: { count: 0, next: null, previous: null, results: [] },
    }),
    [`GET ${F}/accounts/`]: () => ({ status: 200, body: [] }),
    [`GET ${F}/categories/`]: () => ({ status: 200, body: [] }),
    [`GET ${F}/bank-access/`]: () => ({
      status: 200,
      body: { available: true, enabled: true, accesses: [item] },
    }),
    ...extra,
  }
}

function show() {
  render(
    <MemoryRouter initialEntries={['/finanzen/kontoauszuege']}>
      <AuthProvider>
        <OrgProvider>
          <App />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('Bankanbindung', () => {
  it('ruft Umsätze mit PIN und TAN ab', async () => {
    const sent: { url: string; body: Record<string, unknown> }[] = []
    fakeApi(
      routes({
        [`POST ${F}/bank-access/4/fetch/`]: (init) => {
          sent.push({ url: 'fetch', body: JSON.parse(String(init?.body)) })
          return {
            status: 200,
            body: {
              status: 'tan',
              task: 9,
              challenge: 'Bitte TAN eingeben',
              decoupled: false,
              image: '',
              expires_at: '2026-11-21T10:05:00Z',
            },
          }
        },
        [`POST ${F}/bank-tasks/9/continue/`]: (init) => {
          sent.push({ url: 'continue', body: JSON.parse(String(init?.body)) })
          return {
            status: 200,
            body: { status: 'done', kind: 'fetch', lines: 3, duplicates: 1, statements: [12] },
          }
        },
      }),
    )
    const user = userEvent.setup()
    show()
    await user.click(await screen.findByRole('button', { name: 'Umsätze abrufen' }))
    await user.type(screen.getByLabelText(/PIN für das Online-Banking/), 'geheim77')
    await user.click(
      screen.getAllByRole('button', { name: 'Umsätze abrufen' }).find((b) => b.closest('form'))!,
    )
    expect(await screen.findByText('Bitte TAN eingeben')).toBeInTheDocument()
    await user.type(screen.getByLabelText('TAN'), '123456')
    await user.click(screen.getByRole('button', { name: 'Bestätigen' }))
    expect(await screen.findByText(/3 Umsätze eingelesen\./)).toBeInTheDocument()
    expect(sent).toEqual([
      { url: 'fetch', body: { pin: 'geheim77', confirm_retry: false } },
      { url: 'continue', body: { pin: 'geheim77', tan: '123456' } },
    ])
    // Die PIN steht nach dem Abruf nirgends mehr auf der Seite
    expect(document.body.innerHTML).not.toContain('geheim77')
  })

  it('verlangt nach einer abgelehnten PIN eine Bestätigung', async () => {
    let tries = 0
    fakeApi(
      routes({
        [`POST ${F}/bank-access/4/fetch/`]: () => {
          tries += 1
          return {
            status: 409,
            body: { detail: 'Die Bank hat die Anmeldung abgelehnt.', code: 'pin' },
          }
        },
      }),
    )
    const user = userEvent.setup()
    show()
    await user.click(await screen.findByRole('button', { name: 'Umsätze abrufen' }))
    await user.type(screen.getByLabelText(/PIN für das Online-Banking/), 'falsch')
    const submit = () =>
      screen.getAllByRole('button', { name: 'Umsätze abrufen' }).find((b) => b.closest('form'))!
    await user.click(submit())
    expect(await screen.findByText('Die Bank hat die Anmeldung abgelehnt.')).toBeInTheDocument()
    await waitFor(() => expect(submit()).toBeDisabled())
    expect(tries).toBe(1)
    await user.click(screen.getByLabelText(/Ich habe die PIN geprüft/))
    expect(submit()).toBeEnabled()
  })

  it('zeigt die Karte nur, wenn die Bankanbindung eingeschaltet ist', async () => {
    fakeApi(routes({}, false))
    show()
    expect(await screen.findByText('Noch keine Kontoauszüge eingelesen.')).toBeInTheDocument()
    expect(screen.queryByText('Umsätze bei der Bank abrufen')).not.toBeInTheDocument()
  })

  it('bietet bei einem neuen Zugang das Einrichten an', async () => {
    fakeApi(routes({}, true, { ...access, ready: false, accounts: [], ibans: [] }))
    show()
    expect(await screen.findByRole('button', { name: 'Einrichten' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Umsätze abrufen' })).not.toBeInTheDocument()
    expect(screen.getByText('noch nicht eingerichtet')).toBeInTheDocument()
  })
})
