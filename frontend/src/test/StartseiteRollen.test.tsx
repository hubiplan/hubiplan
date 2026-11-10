// Startseite je Rolle (S-04) und Einrichtung bündeln (S-02). Nur erfundene Daten.
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import type { OrgSummary } from '../api/orgs.ts'
import { actionCatalog, roleActions, shownActions } from '../components/home/roleActions.ts'
import { layoutOf, placeBlocks } from '../components/home/homeLayout.ts'
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

  it('Startseite der Kasse: Schnellaktionen ohne Kennzahlen', async () => {
    const org = testOrg({
      permissions: KASSE,
      modules: ['finance', 'billing'],
      home_focus: ['finance'],
    })
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
    })
    renderAt('/')
    const actions = await screen.findByRole('heading', { name: 'Schnellaktionen' })
    const card = within(actions.closest('.card') as HTMLElement)
    const first = card.getByRole('link', { name: 'Buchung erfassen' })
    expect(first).toHaveClass('button-primary')
    expect(first).toHaveAttribute('href', '/finanzen/kassenbuch?buchung=neu-ausgabe')
    expect(screen.queryByRole('group', { name: 'Kennzahlen' })).not.toBeInTheDocument()
  })
})

describe('Schnellaktionen wählen', () => {
  it('Katalog nach Rechten, auch Kasse ohne Kassenamt; nur Lesen ergibt keinen', () => {
    const chair = testOrg({
      permissions: [...KASSE, 'members.view', 'members.edit', 'events.manage', 'todos.edit'],
      modules: ['members', 'finance', 'billing', 'events'],
      home_focus: [],
    }) as unknown as OrgSummary
    const keys = actionCatalog(chair).map((a) => a.key)
    expect(keys).toEqual(expect.arrayContaining(['buchung', 'rechnung', 'termin', 'aufgabe']))
    expect(keys).not.toContain('versammlung')
    expect(keys.at(-1)).toBe('briefvorlage')
    const reader = testOrg({ permissions: ['members.view'] }) as unknown as OrgSummary
    expect(actionCatalog(reader)).toEqual([])
  })

  it('wählt aus dem Katalog, ordnet um und blendet alles aus', async () => {
    let state: { hidden: string[]; chosen: Record<string, string[]> } = { hidden: [], chosen: {} }
    const org = testOrg({
      permissions: [...KASSE, 'members.view', 'members.edit', 'events.manage'],
      modules: ['members', 'events', 'finance', 'billing'],
      home_focus: [],
    })
    const calls = fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
      'GET /api/me/home-actions/': () => ({ status: 200, body: state }),
      'PUT /api/me/home-actions/': (init) => {
        const body = JSON.parse(String(init?.body))
        const chosen = { ...state.chosen }
        for (const [scope, keys] of Object.entries(body.chosen ?? {})) {
          if (keys === null) delete chosen[scope]
          else chosen[scope] = keys as string[]
        }
        state = { hidden: body.hidden ?? state.hidden, chosen }
        return { status: 200, body: state }
      },
    })
    renderAt('/')
    const user = userEvent.setup()
    const heading = await screen.findByRole('heading', { name: 'Schnellaktionen' })
    const card = within(heading.closest('.card') as HTMLElement)
    // Vorschlag ohne Kassenamt: Vorstand
    expect(card.getByRole('link', { name: 'Neuer Termin' })).toHaveClass('button-primary')
    expect(card.queryByRole('link', { name: 'Buchung erfassen' })).not.toBeInTheDocument()

    await user.click(card.getByRole('button', { name: 'Anpassen' }))
    await user.click(card.getByRole('checkbox', { name: 'Buchung erfassen' }))
    await waitFor(() => expect(state.chosen).toEqual({ o7: ['termin', 'aufnahme', 'buchung'] }))
    // Ganze Zeile ziehbar; mit der Tastatur über den Griff
    const grip = await card.findByRole('button', { name: 'Buchung erfassen verschieben' })
    expect(grip.closest('li')).toHaveClass('sortable-row-drag')
    grip.focus()
    await user.keyboard('{ArrowUp}')
    await waitFor(() => expect(state.chosen.o7).toEqual(['termin', 'buchung', 'aufnahme']))
    await user.click(card.getByRole('checkbox', { name: 'Neuer Termin' }))
    await waitFor(() => expect(state.chosen.o7).toEqual(['buchung', 'aufnahme']))
    await user.click(card.getByRole('button', { name: 'Fertig' }))
    expect(card.getByRole('link', { name: 'Buchung erfassen' })).toHaveClass('button-primary')
    expect(card.queryByRole('link', { name: 'Neuer Termin' })).not.toBeInTheDocument()

    await user.click(card.getByRole('button', { name: 'Anpassen' }))
    await user.click(card.getByRole('button', { name: 'Vorschlag wiederherstellen' }))
    await waitFor(() => expect(state.chosen).toEqual({}))
    await user.click(card.getByRole('button', { name: 'Schnellaktionen ganz ausblenden' }))
    await waitFor(() =>
      expect(screen.queryByRole('heading', { name: 'Schnellaktionen' })).not.toBeInTheDocument(),
    )
    expect(calls.filter((c) => c.key === 'PUT /api/me/home-actions/')).toHaveLength(5)
    expect(state.hidden).toEqual(['*'])
  })

  it('höchstens sechs', () => {
    const many = ['a', 'b', 'c', 'd', 'e', 'f', 'g'].map((key) => ({ key, to: '/', label: key }))
    expect(
      shownActions(
        [],
        many,
        [],
        many.map((a) => a.key),
      ).map((a) => a.key),
    ).toHaveLength(6)
    // Schlüssel, die die Rechte nicht mehr erlauben, fallen weg
    expect(shownActions([], many, [], ['x', 'b']).map((a) => a.key)).toEqual(['b'])
    expect(shownActions(many, many, ['*'], ['a'])).toEqual([])
  })
})

describe('Hinweise in einer Karte', () => {
  it('zählt nur Hinweise; Geburtstage stehen in einer eigenen Karte', async () => {
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
    expect(heading).toHaveTextContent('1')
    const birthdays = await screen.findByRole('heading', { name: 'Geburtstage', level: 2 })
    const bCard = within(birthdays.closest('.card') as HTMLElement)
    expect(bCard.getByRole('link', { name: 'Erika Muster' })).toHaveAttribute(
      'href',
      '/mitglieder/3',
    )
    expect(birthdays.querySelector('.badge')).toBeNull()
  })
})

describe('Übersicht ohne Module', () => {
  it('steht unter dem Raster, nicht als halbe Zeile darin', async () => {
    // Im feinen Raster bekäme die Karte nur eine Zeile und läge über der Fußzeile
    const org = testOrg({ permissions: [], modules: [], home_focus: [] })
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
    })
    renderAt('/')
    const heading = await screen.findByRole('heading', { name: 'Übersicht', level: 2 })
    const card = heading.closest('.card') as HTMLElement
    expect(card.closest('.home-grid')).toBeNull()
    expect(card.parentElement).toHaveClass('home-board-extra')
  })
})

describe('Jubiläen je Kalenderjahr', () => {
  afterEach(() => vi.useRealTimers())

  const zug = {
    id: 4,
    kind: 'unit',
    name: 'Die Härtesten',
    short_name: '',
    path: 'Die Härtesten',
    label: 'Zug',
    label_plural: 'Züge',
    label_gender: 'm',
    label_genitive: '',
    founding_year: 1977,
    years: 50,
    year: 2027,
  }
  const erika = {
    member_id: 3,
    first_name: 'Erika',
    last_name: 'Muster',
    birth_date: null,
    member_number: null,
    kind: 'club',
    organization: 'TV Beispielhausen',
    organization_short: 'TVB',
    years: 40,
    date: '2026-01-01',
    precision: 'year',
  }

  function routes(von: string, bis: string) {
    return {
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({
        status: 200,
        body: [testOrg({ modules: ['members', 'awards'], permissions: ['members.view'] })],
      }),
      [`GET /api/orgs/7/jubilees/?von=${von}&bis=${bis}`]: () => ({
        status: 200,
        body: { von, bis, results: [erika] },
      }),
      [`GET /api/orgs/7/unit-jubilees/?von=${von}&bis=${bis}`]: () => ({
        status: 200,
        body: { von, bis, results: [zug] },
      }),
    }
  }

  it('zeigt im Herbst das laufende und das nächste Jahr getrennt, ohne Stichtag', async () => {
    vi.setSystemTime(new Date('2026-11-10T10:00:00'))
    fakeApi(routes('2026-01-01', '2027-12-31'))
    renderAt('/')
    const heading = await screen.findByRole('heading', { name: 'Jubiläen', level: 2 })
    expect(heading.querySelector('.badge')).toBeNull()
    const y2026 = await screen.findByRole('heading', { name: 'Jubiläen 2026' })
    const y2027 = screen.getByRole('heading', { name: 'Jubiläen 2027' })
    const in2026 = within(y2026.closest('section') as HTMLElement)
    expect(in2026.getByRole('link', { name: 'Erika Muster' }).closest('li')).toHaveTextContent(
      /^Erika Muster40 J\.·TVB$/,
    )
    expect(in2026.queryByText(/Die Härtesten/)).not.toBeInTheDocument()
    const in2027 = within(y2027.closest('section') as HTMLElement)
    expect(in2027.getByText('50 Jahre Die Härtesten').closest('li')).toHaveTextContent(
      /^50 Jahre Die HärtestenZug$/,
    )
    expect(screen.queryByText(/nächsten 90 Tagen/)).not.toBeInTheDocument()
  })

  it('zeigt bis September nur das laufende Jahr', async () => {
    vi.setSystemTime(new Date('2026-03-10T10:00:00'))
    fakeApi(routes('2026-01-01', '2026-12-31'))
    renderAt('/')
    expect(await screen.findByRole('heading', { name: 'Jubiläen 2026' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Jubiläen 2027' })).not.toBeInTheDocument()
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

describe('Startseite selbst zusammenstellen', () => {
  const blocks = ['a', 'b', 'c', 'd'].map((key) => ({
    key,
    label: key.toUpperCase(),
    wide: key === 'a',
    render: () => null,
  }))

  it('ordnet nach eigener Anordnung, neue Blöcke an ihrer Standardstelle', () => {
    expect(placeBlocks(blocks).map((b) => [b.key, b.shown, b.wide])).toEqual([
      ['a', true, true],
      ['b', true, false],
      ['c', true, false],
      ['d', true, false],
    ])
    // „b“ kam erst nach dem Speichern dazu, „x“ gibt es nicht mehr
    const placed = placeBlocks(blocks, { order: ['c', 'x', 'a', 'd'], hidden: ['d'], wide: ['c'] })
    expect(placed.map((b) => b.key)).toEqual(['c', 'a', 'b', 'd'])
    expect(placed.map((b) => b.cols)).toEqual([12, 6, 6, 6])
    expect(layoutOf(placed)).toEqual({
      order: ['c', 'a', 'b', 'd'],
      hidden: ['d'],
      wide: ['c'],
      sizes: {
        c: { w: 12, h: null },
        a: { w: 6, h: null },
        b: { w: 6, h: null },
        d: { w: 6, h: null },
      },
    })
    // Größen gehen vor „wide“ und bleiben im Raster
    const sized = placeBlocks(blocks, {
      order: ['a', 'b'],
      hidden: [],
      wide: ['a'],
      sizes: { a: { w: 4, h: 30 }, b: { w: 20, h: 1 } },
    })
    expect(sized.map((b) => [b.key, b.cols, b.rows])).toEqual([
      ['a', 4, 30],
      ['b', 12, 6],
      ['c', 6, null],
      ['d', 6, null],
    ])
  })

  it('blendet Blöcke aus, stellt die Breite um, verschiebt und stellt den Standard her', async () => {
    type Layout = {
      order: string[]
      hidden: string[]
      wide: string[]
      sizes: Record<string, { w: number; h: number | null }>
    }
    let state: {
      hidden: string[]
      chosen: Record<string, string[]>
      layout: Record<string, Layout>
    } = { hidden: ['*'], chosen: {}, layout: {} }
    const org = testOrg({
      permissions: ['members.view', 'members.edit', 'events.view', 'events.manage'],
      modules: ['members', 'events'],
      home_focus: [],
    })
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
      'GET /api/me/home-actions/': () => ({ status: 200, body: state }),
      'PUT /api/me/home-actions/': (init) => {
        const body = JSON.parse(String(init?.body))
        const layout = { ...state.layout }
        for (const [scope, value] of Object.entries(body.layout ?? {})) {
          if (value === null) delete layout[scope]
          else layout[scope] = value as Layout
        }
        state = { ...state, hidden: body.hidden ?? state.hidden, layout }
        return { status: 200, body: state }
      },
    })
    renderAt('/')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Startseite anpassen' }))
    const grid = document.querySelector('.home-grid') as HTMLElement
    const names = () =>
      [...grid.querySelectorAll('.home-block-name')].map((el) => el.textContent ?? '')
    expect(names()).toEqual([
      'Zu erledigen',
      'Schnellaktionen',
      'Nächste Termine',
      'Geburtstage',
      'Hinweise',
    ])
    // Schnellaktionen waren überall ausgeblendet: Zeigen hebt das auf
    const actions = screen.getByRole('checkbox', { name: 'Schnellaktionen zeigen' })
    expect(actions).not.toBeChecked()
    await user.click(actions)
    await waitFor(() => expect(state.hidden).toEqual([]))
    await user.click(screen.getByRole('checkbox', { name: 'Hinweise zeigen' }))
    await waitFor(() => expect(state.layout.o7?.hidden).toEqual(['hinweise']))
    await user.selectOptions(
      screen.getByRole('combobox', { name: 'Nächste Termine: Breite' }),
      '12',
    )
    await waitFor(() => expect(state.layout.o7?.wide).toContain('termine'))
    expect(state.layout.o7?.sizes.termine).toEqual({ w: 12, h: null })
    // Feste Höhe, dann an der Ecke mit den Pfeiltasten kleiner und schmaler
    await user.click(screen.getByRole('checkbox', { name: 'Hinweise: Höhe nach Inhalt' }))
    await waitFor(() => expect(state.layout.o7?.sizes.hinweise?.h).toBe(20))
    const corner = screen.getByRole('button', { name: 'Hinweise: Größe ändern' })
    corner.focus()
    await user.keyboard('{ArrowUp}')
    await waitFor(() => expect(state.layout.o7?.sizes.hinweise).toEqual({ w: 6, h: 16 }))
    expect(corner).toHaveFocus()
    await user.keyboard('{ArrowLeft}')
    await waitFor(() => expect(state.layout.o7?.sizes.hinweise).toEqual({ w: 5, h: 16 }))
    await user.click(screen.getByRole('checkbox', { name: 'Hinweise: Höhe nach Inhalt' }))
    await waitFor(() => expect(state.layout.o7?.sizes.hinweise).toEqual({ w: 5, h: null }))
    // Überall am Block ziehbar; mit der Tastatur über den Griff
    const grip = screen.getByRole('button', { name: 'Nächste Termine verschieben' })
    grip.focus()
    await user.keyboard('{ArrowUp}')
    await waitFor(() =>
      expect(state.layout.o7?.order.slice(0, 3)).toEqual([
        'zu-erledigen',
        'termine',
        'schnellaktionen',
      ]),
    )
    expect(names().slice(0, 3)).toEqual(['Zu erledigen', 'Nächste Termine', 'Schnellaktionen'])
    await user.click(screen.getByRole('button', { name: 'Fertig' }))
    expect(screen.queryByRole('heading', { name: /Hinweise/ })).not.toBeInTheDocument()
    const termine = await screen.findByRole('heading', { name: 'Nächste Termine' })
    expect(termine.closest('.home-block')).toHaveAttribute('data-cols', '12')

    await user.click(screen.getByRole('button', { name: 'Startseite anpassen' }))
    await user.click(screen.getByRole('button', { name: 'Standard wiederherstellen' }))
    await waitFor(() => expect(state.layout).toEqual({}))
    expect(names().slice(0, 3)).toEqual(['Zu erledigen', 'Schnellaktionen', 'Nächste Termine'])
  })

  it('zieht einen Block mit der Maus an eine andere Stelle', async () => {
    let state: { hidden: string[]; layout: Record<string, { order: string[] }> } = {
      hidden: [],
      layout: {},
    }
    const org = testOrg({
      permissions: ['members.view', 'events.view'],
      modules: ['members', 'events'],
      home_focus: [],
    })
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
      'GET /api/me/home-actions/': () => ({ status: 200, body: state }),
      'PUT /api/me/home-actions/': (init) => {
        state = { ...state, layout: JSON.parse(String(init?.body)).layout }
        return { status: 200, body: state }
      },
    })
    renderAt('/')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Startseite anpassen' }))
    const blocks = [...document.querySelectorAll<HTMLElement>('.home-block')]
    const names = blocks.map((b) => b.querySelector('.home-block-name')?.textContent)
    expect(names).toEqual(['Nächste Termine', 'Geburtstage', 'Hinweise'])
    // jsdom kennt kein Layout: Kästen untereinander vorgeben
    blocks.forEach((b, i) => {
      b.getBoundingClientRect = () =>
        ({ left: 0, right: 100, top: i * 100, bottom: i * 100 + 90 }) as DOMRect
    })
    const last = blocks[2]
    // Anfassen mitten im Block, nicht am Griff
    const content = last.querySelector('.home-block-content') as HTMLElement
    fireEvent.pointerDown(content, { button: 0, pointerId: 1, clientX: 50, clientY: 250 })
    fireEvent.pointerMove(last, { pointerId: 1, clientX: 50, clientY: 40 })
    fireEvent.pointerUp(last, { pointerId: 1 })
    await waitFor(() =>
      expect(state.layout.o7.order).toEqual(['hinweise', 'termine', 'geburtstage']),
    )
  })
})

describe('Jubiläen und Geburtstage getrennt', () => {
  it('zeigt zwei eigene Karten', async () => {
    vi.setSystemTime(new Date('2026-03-10T10:00:00'))
    const day = todayIso()
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({
        status: 200,
        body: [testOrg({ modules: ['members', 'awards'], permissions: ['members.view'] })],
      }),
      'GET /api/orgs/7/jubilees/?von=2026-01-01&bis=2026-12-31': () => ({
        status: 200,
        body: {
          von: '',
          bis: '',
          results: [
            {
              member_id: 3,
              first_name: 'Erika',
              last_name: 'Muster',
              birth_date: null,
              member_number: null,
              kind: 'club',
              organization: 'TV Beispielhausen',
              organization_short: 'TVB',
              years: 40,
              date: '2026-01-01',
              precision: 'year',
            },
          ],
        },
      }),
      'GET /api/orgs/7/unit-jubilees/?von=2026-01-01&bis=2026-12-31': () => ({
        status: 200,
        body: { von: '', bis: '', results: [] },
      }),
      [`GET /api/orgs/7/birthdays/?von=${day}&bis=${addDays(day, 30)}`]: () => ({
        status: 200,
        body: {
          von: '',
          bis: '',
          results: [{ member_id: 5, first_name: 'Max', last_name: 'Beispiel', date: day, age: 30 }],
        },
      }),
    })
    renderAt('/')
    const jub = await screen.findByRole('heading', { name: 'Jubiläen', level: 2 })
    const bday = await screen.findByRole('heading', { name: 'Geburtstage', level: 2 })
    expect(jub.closest('.card')).not.toBe(bday.closest('.card'))
    expect(within(jub.closest('.card') as HTMLElement).queryByText('Max Beispiel')).toBeNull()
    expect(
      within(bday.closest('.card') as HTMLElement).getByText('Max Beispiel'),
    ).toBeInTheDocument()
    vi.useRealTimers()
  })
})
