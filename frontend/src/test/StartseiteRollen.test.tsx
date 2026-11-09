// Startseite je Rolle (S-04) und Einrichtung bündeln (S-02). Nur erfundene Daten.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import type { OrgSummary } from '../api/orgs.ts'
import { roleActions } from '../components/home/roleActions.ts'
import { addDays, today } from '../components/calendar/time.ts'
import { settingsItems } from '../pages/settings/items.ts'
import { todayIso } from '../api/members.ts'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'
import { occurrence } from './eventFixtures.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedIn = () => ({ status: 200, body: { status: 200, data: { user: testUser } } })

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <OrgProvider>
          <App />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
}

const KASSE = ['finance.view', 'finance.edit', 'billing.view', 'billing.edit']

describe('Schnellaktionen je Rolle', () => {
  it('Kasse vor Vorstand, höchstens vier', () => {
    const both = testOrg({
      permissions: [...KASSE, 'members.view', 'members.edit', 'events.manage'],
      modules: ['members', 'finance', 'billing', 'events'],
      home_focus: ['finance'],
    }) as unknown as OrgSummary
    expect(roleActions(both).map((a) => a.label)).toEqual([
      'Buchung erfassen',
      'Kontoauszug einlesen',
      'Quittung ausstellen',
      'Mahnlauf vorbereiten',
    ])
    const board = testOrg({
      permissions: ['members.view', 'members.edit', 'events.manage', 'meetings.edit'],
      modules: ['members', 'events', 'meetings'],
    }) as unknown as OrgSummary
    expect(roleActions(board).map((a) => a.to)).toEqual([
      '/termine?neu=1',
      '/mitglieder/neu',
      '/versammlungen?neu=1',
      '/versammlungen',
    ])
    // Vorsitz mit Vollrechten, aber ohne Kassenamt: keine Aktionen der Kasse
    const chair = testOrg({
      permissions: [...KASSE, 'members.view', 'members.edit', 'events.manage'],
      modules: ['members', 'finance', 'billing', 'events'],
      home_focus: [],
    }) as unknown as OrgSummary
    expect(roleActions(chair).map((a) => a.key)).toEqual(['termin', 'aufnahme'])
    // Nur lesen: keine Schnellaktion
    const reader = testOrg({ permissions: ['members.view'] }) as unknown as OrgSummary
    expect(roleActions(reader)).toEqual([])
  })

  it('Startseite der Kasse: Schnellaktionen und Kennzahlen', async () => {
    const org = testOrg({
      permissions: KASSE,
      modules: ['finance', 'billing'],
      home_focus: ['finance'],
    })
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
      'GET /api/orgs/7/home-figures/': () => ({
        status: 200,
        body: {
          figures: [
            {
              key: 'cash',
              kind: 'money',
              label: 'Barkasse heute',
              value: '412.30',
              detail: '',
              link: '/finanzen/kassenbuch',
            },
            {
              key: 'open_fees',
              kind: 'money',
              label: 'Offene Beiträge',
              value: '1240.00',
              detail: '',
              link: '/finanzen/rechnungen?status=open',
            },
          ],
        },
      }),
    })
    renderAt('/')
    const actions = await screen.findByRole('heading', { name: 'Schnellaktionen' })
    const card = within(actions.closest('.card') as HTMLElement)
    const first = card.getByRole('link', { name: 'Buchung erfassen' })
    expect(first).toHaveClass('button-primary')
    expect(first).toHaveAttribute('href', '/finanzen/kassenbuch?buchung=neu-ausgabe')
    const figures = await screen.findByRole('group', { name: 'Kennzahlen' })
    expect(within(figures).getByText('Barkasse heute')).toBeInTheDocument()
    expect(within(figures).getByText(/412,30/)).toBeInTheDocument()
  })
})

describe('Schnellaktionen ausblenden', () => {
  it('blendet eine Aktion aus und rückt die nächste nach', async () => {
    let hidden: string[] = []
    const org = testOrg({
      permissions: ['members.view', 'members.edit', 'events.manage'],
      modules: ['members', 'events'],
    })
    const calls = fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
      'GET /api/me/home-actions/': () => ({ status: 200, body: { hidden } }),
      'PUT /api/me/home-actions/': (init) => {
        hidden = JSON.parse(String(init?.body)).hidden
        return { status: 200, body: { hidden } }
      },
    })
    renderAt('/')
    const user = userEvent.setup()
    const heading = await screen.findByRole('heading', { name: 'Schnellaktionen' })
    const card = within(heading.closest('.card') as HTMLElement)
    expect(card.getByRole('link', { name: 'Neuer Termin' })).toHaveClass('button-primary')
    await user.click(card.getByRole('button', { name: 'Anpassen' }))
    await user.click(card.getByRole('checkbox', { name: 'Neuer Termin' }))
    await waitFor(() => expect(hidden).toEqual(['termin']))
    await user.click(card.getByRole('button', { name: 'Fertig' }))
    expect(card.queryByRole('link', { name: 'Neuer Termin' })).not.toBeInTheDocument()
    expect(card.getByRole('link', { name: 'Mitglied aufnehmen' })).toHaveClass('button-primary')

    await user.click(card.getByRole('button', { name: 'Anpassen' }))
    await user.click(card.getByRole('button', { name: 'Schnellaktionen ganz ausblenden' }))
    await waitFor(() =>
      expect(screen.queryByRole('heading', { name: 'Schnellaktionen' })).not.toBeInTheDocument(),
    )
    expect(calls.filter((c) => c.key === 'PUT /api/me/home-actions/')).toHaveLength(2)
    expect(hidden).toEqual(['termin', '*'])
  })
})

describe('Hinweise in einer Karte', () => {
  it('sammelt Impressum und Geburtstage', async () => {
    const org = testOrg({ permissions: ['members.view', 'org.edit'] })
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
      'GET /api/orgs/7/imprint/': () => ({ status: 200, body: { missing: ['Telefon'] } }),
      // Wie die Startseite mit todayIso (Ortszeit): kurz nach Mitternacht weicht today() (Berlin) ab
      [`GET /api/orgs/7/birthdays/?von=${todayIso()}&bis=${addDays(todayIso(), 30)}`]: () => ({
        status: 200,
        body: {
          von: '',
          bis: '',
          results: [
            {
              member_id: 3,
              first_name: 'Erika',
              last_name: 'Muster',
              date: todayIso(),
              age: 50,
            },
          ],
        },
      }),
    })
    renderAt('/')
    const heading = await screen.findByRole('heading', { name: /Hinweise/ })
    const card = within(heading.closest('.card') as HTMLElement)
    expect(await card.findByText(/Im Impressum fehlen noch Angaben: Telefon/)).toBeInTheDocument()
    expect(card.getByRole('link', { name: 'Impressum ergänzen' })).toBeInTheDocument()
    expect(await card.findByRole('link', { name: 'Erika Muster' })).toHaveAttribute(
      'href',
      '/mitglieder/3',
    )
    expect(heading).toHaveTextContent('2')
  })
})

describe('Mitglied: nächster Termin oben', () => {
  it('sagt direkt auf der Startseite zu', async () => {
    const from = today()
    const next = occurrence({ rsvp_enabled: true, my_response: null })
    const calls = fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/contexts/': () => ({
        status: 200,
        body: {
          departments: [],
          portal: [
            {
              id: 5,
              club_id: 7,
              club_name: 'TV Beispielhausen',
              first_name: 'Erika',
              last_name: 'Muster',
              events_enabled: true,
              theme: testOrg().theme,
            },
          ],
        },
      }),
      [`GET /api/portal/5/events/?from=${from}&to=${addDays(from, 90)}&upcoming=1`]: () => ({
        status: 200,
        body: { from, to: from, items: [next], can_manage: false, categories: [] },
      }),
      'PUT /api/portal/5/events/1/response/': () => ({ status: 200, body: {} }),
    })
    renderAt('/')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Zusage' }))
    await waitFor(() =>
      expect(calls.some((c) => c.key === 'PUT /api/portal/5/events/1/response/')).toBe(true),
    )
    const put = calls.find((c) => c.key === 'PUT /api/portal/5/events/1/response/')
    expect(JSON.parse(String(put?.init?.body))).toMatchObject({ status: 'yes' })
  })
})

describe('Einstellungen › Einrichtung', () => {
  it('steht vorn, aber nur mit „Einstellungen ansehen“', () => {
    const board = testOrg({ permissions: ['org.edit', 'members.view'] }) as unknown as OrgSummary
    expect(settingsItems(board)[0].to).toBe('/einstellungen/einrichtung')
    const theme = testOrg({ permissions: ['theme.view'] }) as unknown as OrgSummary
    expect(settingsItems(theme).map((i) => i.to)).not.toContain('/einstellungen/einrichtung')
  })

  it('zeigt Stand, Fortschritt und Suche', async () => {
    const org = testOrg({
      permissions: ['org.edit', 'members.view', ...KASSE],
      modules: ['members', 'finance', 'billing'],
    })
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
      'GET /api/orgs/7/setup-status/': () => ({
        status: 200,
        body: {
          items: {
            '/einstellungen/organisation': { required: true, done: true },
            '/mitglieder/einrichtung/mitgliedsarten': { required: true, done: true, count: 4 },
            '/finanzen/einrichtung/mahnstufen': { required: true, done: false, count: 0 },
            '/mitglieder/einrichtung/zusatzfelder': { required: false, done: false, count: 0 },
          },
        },
      }),
    })
    renderAt('/einstellungen/einrichtung')
    expect(await screen.findByText('2 von 3 Pflichtpunkten erledigt')).toBeInTheDocument()
    const types = screen.getByRole('link', { name: /Mitgliedsarten/ })
    expect(types).toHaveAttribute('href', '/mitglieder/einrichtung/mitgliedsarten')
    expect(types).toHaveTextContent('4 angelegt')
    expect(screen.getByRole('link', { name: /Mahnstufen/ })).toHaveTextContent('0 angelegt')
    expect(screen.getByRole('link', { name: /Zusatzfelder/ })).toHaveTextContent('optional · 0')

    const user = userEvent.setup()
    await user.type(screen.getByRole('searchbox', { name: 'Einrichtung suchen' }), 'mahn')
    expect(screen.getByRole('link', { name: /Mahnstufen/ })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Mitgliedsarten/ })).not.toBeInTheDocument()
  })
})
