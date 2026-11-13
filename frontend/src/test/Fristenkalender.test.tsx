import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const audit = {
  id: 3,
  key: 'cash_audit',
  title: 'Kassenprüfung vor der Jahreshauptversammlung',
  note: 'Wer prüft und wann, regelt die Satzung.',
  trigger: 'date',
  due_date: '2099-02-15',
  interval_months: 12,
  remind_days: 45,
  days_after: 14,
  role: 4,
  role_name: 'Kassierer',
  active: true,
  status: 'soon',
  version: 2,
  history: [
    {
      id: 1,
      due_date: '2098-02-15',
      done_on: '2098-02-10',
      note: 'Bericht liegt vor',
      done_by: 'Erika Muster',
    },
  ],
}
const suggestion = {
  key: 'insurance',
  title: 'Versicherungen prüfen',
  note: 'Passen Deckung und Beiträge noch?',
  trigger: 'date',
  interval_months: 12,
  remind_days: 30,
  due_date: '2099-03-01',
  registered_only: false,
}

function show(permissions: string[], path = '/fristenkalender') {
  const list = {
    items: [audit],
    suggestions: [suggestion],
    roles: [{ id: 4, name: 'Kassierer' }],
    registered: true,
    can_edit: permissions.includes('obligations.edit'),
  }
  const api = fakeApi({
    'GET /_allauth/browser/v1/auth/session': () => ({
      status: 200,
      body: { status: 200, data: { user: testUser } },
    }),
    'GET /api/me/organizations/': () => ({
      status: 200,
      body: [testOrg({ modules: ['obligations'], permissions })],
    }),
    'GET /api/orgs/7/obligations/': () => ({ status: 200, body: list }),
    'POST /api/orgs/7/obligations/': (init?: RequestInit) => {
      const data = JSON.parse(String(init?.body ?? '{}'))
      return { status: 201, body: { ...audit, id: 9, history: [], ...data } }
    },
    'POST /api/orgs/7/obligations/3/done/': () => ({
      status: 200,
      body: { ...audit, due_date: '2100-02-15', status: 'planned', version: 3 },
    }),
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
  return api
}

describe('Fristenkalender', () => {
  it('zeigt Fristen mit Verlauf und vermerkt die Erledigung', async () => {
    const api = show(['obligations.view', 'obligations.edit'])
    const title = await screen.findByText('Kassenprüfung vor der Jahreshauptversammlung')
    const row = title.closest('li')!
    expect(within(row).getByText('bald fällig')).toBeInTheDocument()
    expect(
      within(row).getByText(/jedes Jahr · Erinnerung 45 Tage vorher · zuständig: Kassierer/),
    ).toBeInTheDocument()
    expect(within(row).getByText('Bericht liegt vor')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Nach einer Vorstandswahl' })).toBeInTheDocument()
    fireEvent.click(within(row).getByRole('button', { name: 'Erledigt' }))
    fireEvent.change(within(row).getByLabelText('Vermerk'), { target: { value: 'geprüft' } })
    fireEvent.click(within(row).getByRole('button', { name: 'Als erledigt vermerken' }))
    await waitFor(() =>
      expect(api.some((c) => c.key === 'POST /api/orgs/7/obligations/3/done/')).toBe(true),
    )
    const call = api.find((c) => c.key === 'POST /api/orgs/7/obligations/3/done/')!
    expect(JSON.parse(String(call.init?.body)).note).toBe('geprüft')
    expect(await screen.findByText(/Frist 15\.2\.2100/)).toBeInTheDocument()
  })

  it('übernimmt einen Vorschlag mit zuständiger Rolle', async () => {
    const api = show(['obligations.view', 'obligations.edit'])
    const heading = await screen.findByRole('heading', { name: 'Vorschläge' })
    const section = heading.closest('section')!
    fireEvent.click(within(section).getByRole('button', { name: 'Übernehmen' }))
    const form = (await screen.findByRole('heading', { name: 'Vorschlag übernehmen' })).closest(
      'section',
    )!
    expect(within(form).getByLabelText(/Bezeichnung/)).toHaveValue('Versicherungen prüfen')
    fireEvent.change(within(form).getByLabelText('Zuständig'), { target: { value: '4' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Übernehmen' }))
    await waitFor(() =>
      expect(api.some((c) => c.key === 'POST /api/orgs/7/obligations/')).toBe(true),
    )
    const body = JSON.parse(
      String(api.find((c) => c.key === 'POST /api/orgs/7/obligations/')!.init?.body),
    )
    expect(body).toMatchObject({ key: 'insurance', role: 4, due_date: '2099-03-01' })
  })

  it('zeigt Lesenden keine Bearbeitung', async () => {
    show(['obligations.view'])
    await screen.findByText('Kassenprüfung vor der Jahreshauptversammlung')
    expect(screen.queryByRole('button', { name: 'Neue Pflicht' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Vorschläge' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Löschen' })).not.toBeInTheDocument()
  })
})
