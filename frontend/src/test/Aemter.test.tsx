// Mitglieder › Ämter: frühere Amtsinhaber ohne Konto, jahresgenau (Ralf 2026-10-31).
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
const base = '/api/orgs/7/offices/'

const offices = [
  {
    id: 1,
    name: '1. Vorsitzender',
    unit: null,
    unit_name: null,
    in_chronicle: true,
    holders: [
      {
        id: 10,
        role: 1,
        name: 'Wilhelm Vorzeit',
        person: null,
        from_year: 1955,
        until_year: 1972,
        current: false,
        former_entry: true,
        name_public: true,
      },
      {
        id: 11,
        role: 1,
        name: 'Erika Beispiel',
        person: 3,
        from_year: 2020,
        until_year: null,
        current: true,
        former_entry: false,
        name_public: true,
      },
    ],
  },
  { id: 2, name: 'Zugführer', unit: 5, unit_name: 'Zug 1', in_chronicle: false, holders: [] },
]

function renderApp(
  routes: Record<string, () => { status: number; body?: unknown }>,
  path: string,
  permissions = ['members.view', 'members.edit'],
) {
  const org = testOrg({ permissions })
  const calls = fakeApi({
    [SESSION]: loggedIn,
    'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
    ...routes,
  })
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <OrgProvider>
          <App />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
  return calls
}

describe('Ämter', () => {
  it('zeigt Inhaber mit Jahren und trägt einen früheren Inhaber ein', async () => {
    const calls = renderApp(
      {
        [`GET ${base}`]: () => ({
          status: 200,
          body: [
            ...offices,
            {
              id: 4,
              name: 'Kassierer',
              unit: null,
              unit_name: null,
              in_chronicle: false,
              holders: [],
            },
          ].map((o) =>
            // Ein Amt der Untereinheit mit Inhaber: erscheint hier nicht (Ralf 2026-10-31)
            o.id === 2
              ? { ...o, holders: [{ ...offices[0].holders[0], id: 20, role: 2, name: 'Zug Mann' }] }
              : o,
          ),
        }),
        [`POST ${base}`]: () => ({ status: 201, body: offices[0].holders[0] }),
      },
      '/mitglieder/aemter',
    )
    expect(await screen.findByText('Wilhelm Vorzeit')).toBeVisible()
    expect(screen.getByText('1955 bis 1972')).toBeVisible()
    expect(screen.getByText('2020 bis heute')).toBeVisible()
    // Je Amt eine eigene Tabelle (Ralf 2026-10-31)
    expect(screen.getByRole('heading', { name: '1. Vorsitzender' })).toBeVisible()
    expect(screen.getByRole('table', { name: '1. Vorsitzender: Inhaber' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: 'Zugführer (Zug 1)' })).toBeNull()
    expect(screen.queryByText('Zug Mann')).toBeNull()
    // Nur freie Einträge sind hier änderbar
    expect(
      screen.getByRole('button', { name: 'Wilhelm Vorzeit 1955 bis 1972 löschen' }),
    ).toBeVisible()
    expect(screen.queryByRole('button', { name: /Erika Beispiel .* löschen/ })).toBeNull()

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Früheren Inhaber eintragen' }))
    expect(screen.queryByRole('option', { name: 'Zugführer (Zug 1)' })).toBeNull()
    await user.selectOptions(screen.getByLabelText('Amt'), '4')
    await user.type(screen.getByLabelText('Inhaber (Name)'), 'Hans Alt')
    await user.type(screen.getByLabelText('von (Jahr)'), '1960')
    await user.type(screen.getByLabelText('bis (Jahr)'), '1970')
    // Freie Namen erscheinen nur mit Häkchen auf der Webseite (FQ-19)
    const published = screen.getByRole('checkbox', {
      name: /Name darf auf der Webseite erscheinen/,
    })
    expect(published).not.toBeChecked()
    await user.click(published)
    await user.click(screen.getByRole('button', { name: 'Anlegen' }))
    await waitFor(() => expect(calls.some((c) => c.key === `POST ${base}`)).toBe(true))
    const post = calls.find((c) => c.key === `POST ${base}`)
    expect(JSON.parse(String(post?.init?.body))).toEqual({
      role: 4,
      name: 'Hans Alt',
      person: null,
      from_year: 1960,
      until_year: 1970,
      name_public: true,
    })
  })

  it('Statistik: je Amt und je Person nach Jahren, gleichzeitige Ämter nur einmal', async () => {
    const now = new Date().getFullYear()
    const data = [
      {
        ...offices[0],
        is_board: true,
        holders: [
          { ...offices[0].holders[0] }, // Wilhelm Vorzeit 1955 bis 1972: 17 Jahre
          {
            ...offices[0].holders[0],
            id: 12,
            name: 'Karl Kurz',
            from_year: 1973,
            until_year: 1973,
          },
        ],
      },
      {
        ...offices[1],
        name: 'Beisitzer',
        unit: null,
        unit_name: null,
        is_board: false,
        holders: [
          // gleichzeitig Beisitzer 1960 bis 1980: zählt insgesamt bis 1980 (25 Jahre)
          { ...offices[0].holders[0], id: 13, role: 2, from_year: 1960, until_year: 1980 },
          // Frei 2000 bis 2010, heute mit Akte: eine Person (Wilhelm Vorzeit hat keine Akte)
          {
            ...offices[0].holders[0],
            id: 15,
            role: 2,
            name: 'Nora Neu',
            from_year: now - 12,
            until_year: now - 6,
          },
          {
            ...offices[0].holders[0],
            id: 14,
            role: 2,
            name: 'Nora Neu',
            person: 9,
            former_entry: false,
            name_public: true,
            from_year: now - 2,
            until_year: null,
            current: true,
          },
        ],
      },
      // Ämter der Untereinheiten zählen nicht (Ralf 2026-10-31)
      {
        ...offices[1],
        id: 3,
        is_board: false,
        holders: [{ ...offices[0].holders[0], id: 16, role: 3, name: 'Zug Mann' }],
      },
    ]
    renderApp(
      { [`GET ${base}`]: () => ({ status: 200, body: data }) },
      '/mitglieder/aemter/statistik',
    )
    const people = await screen.findByRole('table', { name: 'Personen nach Jahren im Amt' })
    const rows = within(people).getAllByRole('row').slice(1)
    expect(rows[0]).toHaveTextContent('Wilhelm Vorzeit')
    expect(rows[0]).toHaveTextContent('25 Jahre')
    expect(rows.map((r) => r.textContent)).toEqual(
      expect.arrayContaining([expect.stringContaining('Karl Kurz1 Jahr')]),
    )
    const chair = screen.getByRole('table', { name: '1. Vorsitzender: Inhaber nach Jahren' })
    expect(within(chair).getAllByRole('row')[1]).toHaveTextContent('17 Jahre')
    // Blöcke je Amt mit festen Spaltenbreiten, damit sie untereinander gleich stehen
    expect(chair).toHaveClass('table-fixed')
    expect(within(chair).getByRole('columnheader', { name: /Name/ })).toHaveStyle({ width: '40%' })
    // Nora Neu: 6 Jahre frei und 2 Jahre heute im Amt, in der Personenliste zusammen
    expect(within(people).getByText('Nora Neu').closest('tr')).toHaveTextContent('8 Jahre')
    expect(screen.queryByText('Zug Mann')).toBeNull()
    expect(screen.queryByRole('heading', { name: 'Zugführer (Zug 1)' })).toBeNull()
    // Nur Vorstandsrollen: der Beisitzer zählt nicht mit
    const user = userEvent.setup()
    await user.click(screen.getByLabelText('nur Vorstandsrollen zählen'))
    const after = within(screen.getByRole('table', { name: 'Personen nach Jahren im Amt' }))
    expect(after.getAllByRole('row')[1]).toHaveTextContent('17 Jahre')
    expect(after.queryByText('Nora Neu')).toBeNull()
  })

  it('liest eine Liste und übernimmt die geprüften Zeilen', async () => {
    const calls = renderApp(
      {
        [`POST ${base}import/preview/`]: () => ({
          status: 200,
          body: {
            new_roles: ['Ehrenvorsitzender'],
            rows: [
              {
                line: 2,
                role: 'Zugführer',
                role_id: 2,
                unit: 'Zug 1',
                unit_id: 5,
                name: 'Karl Alt',
                person_id: null,
                candidates: [],
                from_year: 1950,
                until_year: 1960,
                duplicate: false,
                errors: [],
              },
              {
                line: 3,
                role: 'Kassierer',
                role_id: null,
                unit: '',
                unit_id: null,
                name: 'Ohne Ende',
                person_id: null,
                candidates: [],
                from_year: 1990,
                until_year: 2999,
                duplicate: false,
                errors: ['Endjahr ist ungültig.'],
              },
            ],
          },
        }),
        [`POST ${base}import/`]: () => ({
          status: 201,
          body: { created: 1, roles_created: [] },
        }),
      },
      '/mitglieder/aemter/import',
    )
    const user = userEvent.setup()
    const file = new File(['x'], 'aemter.xlsx')
    await user.upload(await screen.findByLabelText('Datei auswählen'), file)
    expect(await screen.findByText('Zugführer (Zug 1)')).toBeVisible()
    expect(screen.getByText('Endjahr ist ungültig.')).toBeVisible()
    await user.click(screen.getByRole('button', { name: '1 Einträge übernehmen' }))
    expect(await screen.findByText(/1 Einträge übernommen/)).toBeVisible()
    const post = calls.find((c) => c.key === `POST ${base}import/`)
    expect(JSON.parse(String(post?.init?.body)).rows).toEqual([
      {
        role: 'Zugführer',
        unit_id: 5,
        name: 'Karl Alt',
        person_id: null,
        from_year: 1950,
        until_year: 1960,
      },
    ])
  })
})

describe('Ämter besetzen (Rollen-Vorschlag R2)', () => {
  it('besetzt ein Amt und beendet die Amtszeit des Vorgängers', async () => {
    const role = {
      id: 1,
      name: '1. Vorsitzender',
      description: '',
      permissions: ['members.edit'],
      is_board: true,
      represents: true,
      assignment_count: 1,
    }
    const calls = renderApp(
      {
        [`GET ${base}`]: () => ({ status: 200, body: offices }),
        'GET /api/orgs/7/roles/': () => ({ status: 200, body: [role] }),
        'GET /api/orgs/7/assignments/': () => ({
          status: 200,
          body: [
            {
              id: 30,
              user_email: 'erika@example.org',
              user_name: 'Erika Beispiel',
              person_name: 'Erika Beispiel',
              role: 1,
              role_name: '1. Vorsitzender',
              valid_from: '2020-01-01',
              valid_until: null,
              is_active: true,
            },
          ],
        }),
        'POST /api/orgs/7/assignments/': () => ({
          status: 201,
          body: {
            id: 31,
            user_email: 'max@example.org',
            user_name: '',
            person_name: null,
            role: 1,
            role_name: '1. Vorsitzender',
            valid_from: '2026-11-06',
            valid_until: null,
            is_active: true,
            new_account: true,
            invited: true,
            ended: ['Erika Beispiel'],
          },
        }),
      },
      '/mitglieder/aemter',
      ['members.view', 'members.edit', 'roles.view', 'roles.manage'],
    )
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '1. Vorsitzender besetzen' }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText(/E-Mail-Adresse/), 'max@example.org')
    const end = within(dialog).getByRole('checkbox', { name: /Amtszeit von Erika Beispiel/ })
    expect(end).toBeChecked()
    expect(within(dialog).getByText(/Die Rolle hat Rechte in HUBIplan/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Besetzen' }))
    await waitFor(() =>
      expect(calls.some((c) => c.key === 'POST /api/orgs/7/assignments/')).toBe(true),
    )
    const sent = calls.find((c) => c.key === 'POST /api/orgs/7/assignments/')!
    expect(JSON.parse(sent.init!.body as string)).toMatchObject({
      email: 'max@example.org',
      role: 1,
      end_previous: true,
    })
    expect(await screen.findByText('Amtszeit beendet: Erika Beispiel')).toBeInTheDocument()
    const done = screen.getByRole('dialog')
    expect(within(done).getByRole('link', { name: 'Impressum' })).toHaveAttribute(
      'href',
      '/einstellungen/impressum',
    )
  })
})

describe('Ämter einer Untereinheit (Rollen-Vorschlag R3)', () => {
  const unitOffices = [
    offices[0],
    {
      id: 2,
      name: 'Zugführer',
      unit: 5,
      unit_name: 'Zug 1',
      in_chronicle: false,
      holders: [
        {
          id: 50,
          role: 2,
          name: 'Karl Kette',
          person: 8,
          membership: 80,
          from_year: 2019,
          until_year: null,
          current: true,
          former_entry: false,
          name_public: true,
        },
      ],
    },
  ]

  it('filtert nach Einheit, besetzt mit Vorgänger-Ende und beendet', async () => {
    const calls = renderApp(
      {
        [`GET ${base}`]: () => ({ status: 200, body: unitOffices }),
        'GET /api/orgs/7/roles/': () => ({ status: 200, body: [] }),
        'GET /api/orgs/7/assignments/': () => ({ status: 200, body: [] }),
        'GET /api/orgs/7/members/?suche=An&status=aktiv&page_size=8': () => ({
          status: 200,
          body: {
            count: 1,
            next: null,
            previous: null,
            results: [{ id: 31, first_name: 'Anna', last_name: 'Neu', email: '' }],
          },
        }),
        'POST /api/orgs/7/members/31/department-roles/': () => ({
          status: 201,
          body: { id: 51, role: 2, ended: ['Karl Kette'] },
        }),
        'PATCH /api/orgs/7/members/80/department-roles/50/': () => ({
          status: 200,
          body: { id: 50 },
        }),
      },
      '/mitglieder/aemter?einheit=5',
      ['members.view', 'members.edit', 'roles.view', 'roles.manage'],
    )
    const user = userEvent.setup()
    expect(await screen.findByRole('heading', { name: 'Zugführer (Zug 1)' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '1. Vorsitzender' })).not.toBeInTheDocument()
    expect(screen.getByLabelText('Einheit')).toHaveValue('5')

    await user.click(screen.getByRole('button', { name: 'Zugführer (Zug 1) besetzen' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('checkbox', { name: /Amtszeit von Karl Kette/ })).toBeChecked()
    await user.type(within(dialog).getByLabelText('Person aus der Mitgliederliste'), 'An')
    await user.click(await within(dialog).findByRole('button', { name: /Neu, Anna/ }))
    await user.click(within(dialog).getByRole('button', { name: 'Besetzen' }))
    expect(await screen.findByText('Amtszeit beendet: Karl Kette')).toBeInTheDocument()
    const sent = calls.find((c) => c.key === 'POST /api/orgs/7/members/31/department-roles/')!
    expect(JSON.parse(sent.init!.body as string)).toMatchObject({ role: 2, end_previous: true })
    await user.click(screen.getByRole('button', { name: 'Fertig' }))

    await user.click(screen.getByRole('button', { name: 'Zugführer von Karl Kette beenden' }))
    await user.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Beenden' }),
    )
    await waitFor(() =>
      expect(calls.some((c) => c.key === 'PATCH /api/orgs/7/members/80/department-roles/50/')).toBe(
        true,
      ),
    )
  })
})
