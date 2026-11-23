// Plattform › Sicherheit: Meldungen des Browsers über CSP-Verstöße (Härtung B3).
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const LISTE = '/api/platform/csp-reports/'
const KOEDER = '/api/platform/decoys/'
const OHNE_KOEDER = { decoys: [], limit: 5, domain: 'verteiler.example', hits: [] }

const STATE = {
  total: 2,
  limit: 500,
  entries: [
    {
      id: 3,
      directive: 'script-src-elem',
      blocked: 'https://fremd.example',
      page: '/orgs/…/members/…',
      count: 4,
      first_day: '2026-11-20',
      last_day: '2026-11-22',
      version: '2026.11.1',
      script: true,
    },
    {
      id: 4,
      directive: 'style-src-attr',
      blocked: 'inline',
      page: '/finanzen',
      count: 1,
      first_day: '2026-11-21',
      last_day: '2026-11-21',
      version: '2026.11.1',
      script: false,
    },
  ],
}

function renderPage(routes: Parameters<typeof fakeApi>[0]) {
  const api = fakeApi({
    [SESSION]: () => ({ status: 200, body: { status: 200, data: { user: testUser } } }),
    'GET /api/me/organizations/': () => ({
      status: 200,
      body: [testOrg({ type: 'platform', permissions: ['platform.manage'] })],
    }),
    [`GET ${KOEDER}`]: () => ({ status: 200, body: OHNE_KOEDER }),
    ...routes,
  })
  render(
    <MemoryRouter initialEntries={['/plattform/sicherheit']}>
      <AuthProvider>
        <OrgProvider>
          <App />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
  return api
}

describe('Plattform › Sicherheit', () => {
  it('zeigt die Meldungen, entfernt eine und leert die Liste nach Rückfrage', async () => {
    const user = userEvent.setup()
    const rest = { ...STATE, total: 1, entries: [STATE.entries[1]] }
    const api = renderPage({
      [`GET ${LISTE}`]: () => ({ status: 200, body: STATE }),
      [`DELETE ${LISTE}3/`]: () => ({ status: 200, body: rest }),
      [`DELETE ${LISTE}`]: () => ({ status: 200, body: { ...STATE, total: 0, entries: [] } }),
    })
    const fremd = (
      await screen.findByRole('rowheader', { name: /https:\/\/fremd\.example/ })
    ).closest('tr')!
    expect(within(fremd).getByText('(Skript)')).toBeInTheDocument()
    expect(within(fremd).getByText('script-src-elem')).toBeInTheDocument()
    // „inline“ steht in Worten da
    expect(
      screen.getByRole('rowheader', { name: 'eingebetteter Code auf der Seite' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Sicherheit' })).toBeInTheDocument()

    await user.click(within(fremd).getByRole('button', { name: /^Meldung „https:\/\/fremd/ }))
    await waitFor(() =>
      expect(screen.queryByRole('rowheader', { name: /fremd\.example/ })).not.toBeInTheDocument(),
    )
    expect(api.some((c) => c.key === `DELETE ${LISTE}3/`)).toBe(true)

    await user.click(screen.getByRole('button', { name: 'Alle entfernen' }))
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: 'Alle entfernen' }))
    expect(
      await screen.findByText('Bisher hat kein Browser einen Verstoß gemeldet.'),
    ).toBeInTheDocument()
    expect(api.some((c) => c.key === `DELETE ${LISTE}`)).toBe(true)
  })

  it('weist auf eine volle Liste hin', async () => {
    renderPage({
      [`GET ${LISTE}`]: () => ({ status: 200, body: { ...STATE, total: 500 } }),
    })
    expect(await screen.findByText(/Die Liste ist voll \(500 Einträge\)/)).toBeInTheDocument()
  })

  it('legt einen Köder an, zeigt Auslösungen und löscht den Köder nach Rückfrage', async () => {
    const user = userEvent.setup()
    const koeder = {
      id: 9,
      name: 'Karin Brandt',
      email: 'karin.brandt@verteiler.example',
      place: '12345 Musterstadt',
      created: '2026-11-23',
    }
    const mitTreffer = {
      ...OHNE_KOEDER,
      decoys: [koeder],
      hits: [
        {
          id: 1,
          kind: 'mail_in',
          decoy: 'Karin Brandt',
          detail: 'von fremd@example.net, Betreff: Ihr Gewinn',
          count: 2,
          last_at: '2026-11-23T08:15:00+01:00',
        },
      ],
    }
    const api = renderPage({
      [`GET ${LISTE}`]: () => ({ status: 200, body: { ...STATE, total: 0, entries: [] } }),
      [`POST ${KOEDER}`]: () => ({ status: 201, body: mitTreffer }),
      [`DELETE ${KOEDER}9/`]: () => ({ status: 200, body: OHNE_KOEDER }),
    })
    expect(await screen.findByText('Noch kein Köder angelegt.')).toBeInTheDocument()
    expect(screen.getByText('Bisher hat niemand einen Köder benutzt.')).toBeInTheDocument()
    expect(screen.getByText(/nimmt eine Adresse an verteiler\.example/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Köder anlegen' }))
    const zeile = (await screen.findByText('Karin Brandt', { selector: 'strong' })).closest('li')!
    expect(zeile).toHaveTextContent('karin.brandt@verteiler.example')
    const gesendet = api.find((c) => c.key === `POST ${KOEDER}`)?.init?.body
    expect(JSON.parse(String(gesendet))).toEqual({ email: '' })
    // Auslösung in Worten und mit Warnung
    expect(screen.getByRole('rowheader', { name: 'Mail an die Köderadresse' })).toBeInTheDocument()
    expect(screen.getByText(/Jemand hat Köderdaten benutzt/)).toBeInTheDocument()

    await user.click(within(zeile).getByRole('button', { name: 'Köder „Karin Brandt“ löschen' }))
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: 'Köder löschen' }))
    expect(await screen.findByText('Noch kein Köder angelegt.')).toBeInTheDocument()
    expect(api.some((c) => c.key === `DELETE ${KOEDER}9/`)).toBe(true)
  })
})
