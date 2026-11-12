// Haushalte und Firmen H5: Firmen melden Mitarbeiter (Daten erfunden)
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import type { JoinSchema } from '../api/admission.ts'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const base = '/api/portal/5/company/'

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <OrgProvider>
          <App />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
}

const company = {
  can_report: true,
  companies: [
    {
      id: 3,
      name: 'Musterbau GmbH',
      members: [
        { link: 11, name: 'Ina Beispiel', since: '2025-01-01', until: null, pays_via: true },
      ],
    },
  ],
}

function portalRoutes(routes: Record<string, () => { status: number; body?: unknown }>) {
  return fakeApi({
    [SESSION]: () => ({ status: 200, body: { status: 200, data: { user: testUser } } }),
    'GET /api/me/organizations/': () => ({ status: 200, body: [] }),
    'GET /api/me/contexts/': () => ({
      status: 200,
      body: {
        departments: [],
        portal: [
          {
            id: 5,
            club_id: 7,
            club_name: 'Musterverein',
            first_name: 'Petra',
            last_name: 'Beispiel',
            member_kind: 'organization',
            member_name: 'Musterbau GmbH',
            company: true,
            theme: testOrg().theme,
          },
        ],
      },
    }),
    [`GET ${base}`]: () => ({ status: 200, body: company }),
    ...routes,
  })
}

describe('Firmen melden Mitarbeiter', () => {
  it('zeigt die Mitarbeiter und meldet einen neuen', async () => {
    const user = userEvent.setup()
    const calls = portalRoutes({
      [`POST ${base}3/report/`]: () => ({ status: 201, body: { status: 'sent' } }),
    })
    renderAt('/mein-bereich/firma')
    const card = await screen.findByRole('region', { name: 'Musterbau GmbH' })
    expect(within(card).getByText('Ina Beispiel')).toBeInTheDocument()
    expect(within(card).getByText('über die Firma')).toBeInTheDocument()
    await user.type(within(card).getByLabelText(/^Vorname/), 'Tom')
    await user.type(within(card).getByLabelText(/^Nachname/), 'Muster')
    await user.type(within(card).getByLabelText(/^E-Mail/), 'tom@example.org')
    await user.click(within(card).getByRole('button', { name: 'Melden' }))
    expect(await within(card).findByText('Mail an tom@example.org gesendet.')).toBeInTheDocument()
    const post = calls.find((c) => c.key === `POST ${base}3/report/`)!
    expect(JSON.parse(String(post.init?.body))).toEqual({
      first_name: 'Tom',
      last_name: 'Muster',
      email: 'tom@example.org',
    })
  })

  it('meldet einen Mitarbeiter ab einem Datum ab', async () => {
    const user = userEvent.setup()
    const calls = portalRoutes({
      [`POST ${base}3/members/11/end/`]: () => ({
        status: 200,
        body: { members: [{ ...company.companies[0].members[0], until: '2099-12-31' }] },
      }),
    })
    renderAt('/mein-bereich/firma')
    const card = await screen.findByRole('region', { name: 'Musterbau GmbH' })
    await user.click(within(card).getByRole('button', { name: 'Beitrag beenden' }))
    const form = within(card).getByRole('form', { name: 'Beitrag für Ina Beispiel beenden' })
    const date = within(form).getByLabelText(/^Firma zahlt bis/)
    await user.clear(date)
    await user.type(date, '2099-12-31')
    await user.click(within(form).getByRole('button', { name: 'Beitrag beenden' }))
    await waitFor(() =>
      expect(calls.some((c) => c.key === `POST ${base}3/members/11/end/`)).toBe(true),
    )
    const post = calls.find((c) => c.key === `POST ${base}3/members/11/end/`)!
    expect(JSON.parse(String(post.init?.body))).toEqual({ valid_until: '2099-12-31' })
    expect(await within(card).findByText(/bis 31\.12\.2099/)).toBeInTheDocument()
  })
})

const joinSchema: Partial<JoinSchema> = {
  organization: 'Musterverein',
  language: 'de',
  languages: ['de'],
  intro: '',
  thanks: '',
  types: [{ id: 3, label: 'Aktiv', text: '', fee: '36,00', organizations: false }],
  fields: {
    phone: 'optional',
    gender: 'off',
    birth_date: 'off',
    unit: 'off',
    entry_wish: 'off',
    note: 'off',
  },
  units: [],
  unit: null,
  unit_label: 'Abteilung',
  custom_fields: [],
  sepa: 'off',
  mandate: {},
  confirmations: [],
  consents: [],
  signature: 'none',
  minors: false,
  min_age: null,
  company: 'Musterbau GmbH',
}

describe('Online-Antrag mit Link der Firma', () => {
  it('füllt Name und Mail vor und zeigt, wer den Beitrag zahlt', async () => {
    const schema = joinSchema
    fakeApi({
      [SESSION]: () => ({ status: 401, body: { status: 401, data: { flows: [] } } }),
      'GET /api/public/join/abc/?lang=de&firma=tok': () => ({ status: 200, body: schema }),
    })
    renderAt('/mitglied-werden/abc?firma=tok&vorname=Tom&name=Muster&mail=tom%40example.org')
    expect(
      await screen.findByText('Den Mitgliedsbeitrag zahlt Musterbau GmbH.'),
    ).toBeInTheDocument()
    expect(screen.getByLabelText(/^Vorname/)).toHaveValue('Tom')
    expect(screen.getByLabelText(/^E-Mail/)).toHaveValue('tom@example.org')
  })

  it('Familienantrag: weitere Personen hinzufügen und entfernen', async () => {
    const user = userEvent.setup()
    const schema = {
      ...joinSchema,
      company: null,
      fields: {
        ...joinSchema.fields!,
        birth_date: 'optional' as const,
        family: 'optional' as const,
      },
    }
    fakeApi({
      [SESSION]: () => ({ status: 401, body: { status: 401, data: { flows: [] } } }),
      'GET /api/public/join/abc/?lang=de': () => ({ status: 200, body: schema }),
    })
    renderAt('/mitglied-werden/abc')
    const section = await screen.findByRole('group', { name: 'Weitere Familienmitglieder' })
    await user.click(within(section).getByRole('button', { name: 'Familienmitglied hinzufügen' }))
    const first = within(section).getByRole('group', { name: 'Familienmitglied 1' })
    await user.type(within(first).getByLabelText(/^Vorname/), 'Lisa')
    expect(within(first).getByLabelText(/^Geburtsdatum/)).toBeInTheDocument()
    await user.click(within(first).getByRole('button', { name: 'Entfernen' }))
    expect(within(section).queryByRole('group', { name: 'Familienmitglied 1' })).toBeNull()
  })

  it('ohne Einstellung kein Familienantrag', async () => {
    fakeApi({
      [SESSION]: () => ({ status: 401, body: { status: 401, data: { flows: [] } } }),
      'GET /api/public/join/abc/?lang=de': () => ({
        status: 200,
        body: { ...joinSchema, company: null },
      }),
    })
    renderAt('/mitglied-werden/abc')
    expect(await screen.findByLabelText(/^Vorname/)).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Weitere Familienmitglieder' })).toBeNull()
  })
})
