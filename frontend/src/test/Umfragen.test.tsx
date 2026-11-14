import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { PortalSurveys } from '../pages/portal/PortalSurveys.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const questions = [
  {
    id: 1,
    kind: 'single',
    text: 'Wie fährst du mit?',
    required: true,
    max_choices: null,
    allow_maybe: false,
    options: [
      { id: 11, label: 'Bus', starts_at: null, ends_at: null, all_day: false, capacity: 50 },
      {
        id: 12,
        label: 'eigenes Auto',
        starts_at: null,
        ends_at: null,
        all_day: false,
        capacity: null,
      },
    ],
  },
  {
    id: 2,
    kind: 'text',
    text: 'Anmerkungen',
    required: false,
    max_choices: null,
    allow_maybe: false,
    options: [],
  },
]

function memberSurvey(over: Record<string, unknown> = {}) {
  return {
    id: 5,
    title: 'Ausflug 2099',
    description: 'Wir fahren nach Musterstadt.',
    unit: '',
    event: null,
    status: 'open',
    closes_at: '2099-05-01T18:00:00Z',
    names: 'open',
    results_mode: 'after_answer',
    anonymous: false,
    answered: false,
    can_answer: true,
    can_change: false,
    mine: null,
    questions,
    results: null,
    follow_event: null,
    ...over,
  }
}

const result = {
  participants: 3,
  hidden: false,
  questions: [
    {
      id: 1,
      kind: 'single',
      text: 'Wie fährst du mit?',
      answered: 3,
      options: [
        {
          id: 11,
          label: 'Bus',
          starts_at: null,
          ends_at: null,
          all_day: false,
          capacity: 50,
          count: 2,
          names: ['Erika Beispiel', 'Max Muster'],
        },
        {
          id: 12,
          label: 'eigenes Auto',
          starts_at: null,
          ends_at: null,
          all_day: false,
          capacity: null,
          count: 1,
          names: ['Anna Probe'],
        },
      ],
    },
  ],
}

describe('Umfragen im Mitgliederbereich', () => {
  it('beantwortet eine Umfrage und zeigt danach das Ergebnis', async () => {
    let answered = false
    const api = fakeApi({
      'GET /api/portal/9/surveys/': () => ({
        status: 200,
        body: {
          surveys: [
            answered
              ? memberSurvey({
                  answered: true,
                  can_answer: true,
                  can_change: true,
                  mine: [{ question: 1, options: [11] }],
                  results: result,
                })
              : memberSurvey(),
          ],
        },
      }),
      'POST /api/portal/9/surveys/5/answer/': () => {
        answered = true
        return { status: 200, body: memberSurvey({ answered: true }) }
      },
    })
    render(
      <MemoryRouter>
        <PortalSurveys accessId={9} />
      </MemoryRouter>,
    )
    expect(await screen.findByRole('heading', { name: 'Ausflug 2099' })).toBeInTheDocument()
    const submit = screen.getByRole('button', { name: 'Absenden' })
    expect(submit).toBeDisabled()
    fireEvent.click(screen.getByLabelText(/Bus/))
    expect(submit).toBeEnabled()
    fireEvent.click(submit)
    await waitFor(() =>
      expect(api.some((c) => c.key === 'POST /api/portal/9/surveys/5/answer/')).toBe(true),
    )
    const body = JSON.parse(
      String(api.find((c) => c.key === 'POST /api/portal/9/surveys/5/answer/')!.init?.body),
    )
    // freiwillige leere Frage geht nicht mit
    expect(body).toEqual({ answers: [{ question: 1, options: [11] }] })
    expect(await screen.findByText('Danke, deine Antwort ist gespeichert.')).toBeInTheDocument()
    const results = screen.getByRole('region', { name: 'Ergebnis' })
    expect(within(results).getByText('Erika Beispiel, Max Muster')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Antwort ändern' })).toBeInTheDocument()
  })

  it('zeigt bei anonymen Umfragen den Hinweis und verdeckt kleine Ergebnisse', async () => {
    fakeApi({
      'GET /api/portal/9/surveys/': () => ({
        status: 200,
        body: {
          surveys: [
            memberSurvey({
              id: 6,
              title: 'Stimmung im Verein',
              anonymous: true,
              names: 'anonymous',
            }),
            memberSurvey({
              id: 7,
              title: 'Vereinsfarbe',
              anonymous: true,
              names: 'anonymous',
              answered: true,
              can_answer: false,
              results: { participants: 2, hidden: true, questions: [] },
            }),
          ],
        },
      }),
    })
    render(
      <MemoryRouter>
        <PortalSurveys accessId={9} />
      </MemoryRouter>,
    )
    expect(
      await screen.findByText('Anonym. Deine Antwort lässt sich danach nicht mehr ändern.'),
    ).toBeInTheDocument()
    expect(screen.getByText(/ab drei Antworten/)).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Absenden' })).toHaveLength(1)
    expect(screen.queryByRole('button', { name: 'Antwort ändern' })).not.toBeInTheDocument()
  })

  it('übernimmt die Zusage zum Termin aus der Terminfindung', async () => {
    const api = fakeApi({
      'GET /api/portal/9/surveys/': () => ({
        status: 200,
        body: {
          surveys: [
            memberSurvey({
              status: 'closed',
              can_answer: false,
              answered: true,
              follow_event: {
                id: 40,
                title: 'Grillabend',
                starts_at: '2099-06-13T16:00:00Z',
                ends_at: '2099-06-13T20:00:00Z',
                all_day: false,
                rsvp_enabled: true,
                said_yes: true,
                response: null,
              },
            }),
          ],
        },
      }),
      'POST /api/portal/9/surveys/5/follow/': () => ({ status: 200, body: memberSurvey() }),
    })
    render(
      <MemoryRouter>
        <PortalSurveys accessId={9} />
      </MemoryRouter>,
    )
    expect(await screen.findByText(/Termin steht fest: Grillabend/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Zusage übernehmen' }))
    await waitFor(() =>
      expect(api.some((c) => c.key === 'POST /api/portal/9/surveys/5/follow/')).toBe(true),
    )
  })
})

describe('Umfrage über den Link aus der Mail', () => {
  it('antwortet ohne Anmeldung', async () => {
    const api = fakeApi({
      'GET /_allauth/browser/v1/auth/session': () => ({
        status: 401,
        body: { status: 401, data: { flows: [] } },
      }),
      'GET /api/public/survey/abc/': () => ({
        status: 200,
        body: {
          club: 'TV Beispielhausen',
          imprint_key: 'k1',
          first_name: 'Anna',
          survey: memberSurvey(),
        },
      }),
      'POST /api/public/survey/abc/': () => ({
        status: 200,
        body: {
          club: 'TV Beispielhausen',
          imprint_key: 'k1',
          first_name: 'Anna',
          survey: memberSurvey({ answered: true, can_answer: true, can_change: true }),
        },
      }),
    })
    render(
      <MemoryRouter initialEntries={['/umfrage/abc']}>
        <AuthProvider>
          <OrgProvider>
            <App />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>,
    )
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Ausflug 2099' }),
    ).toBeInTheDocument()
    expect(screen.getByText(/Hallo Anna/)).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText(/eigenes Auto/))
    fireEvent.click(screen.getByRole('button', { name: 'Absenden' }))
    expect(await screen.findByText('Danke, deine Antwort ist gespeichert.')).toBeInTheDocument()
    const body = JSON.parse(
      String(api.find((c) => c.key === 'POST /api/public/survey/abc/')!.init?.body),
    )
    expect(body.answers).toEqual([{ question: 1, options: [12] }])
  })
})

describe('Umfragen in der Verwaltung', () => {
  it('legt aus der Vorlage eine Essenswahl an', async () => {
    const created = {
      id: 5,
      title: 'Essenswahl',
      description: '',
      event: null,
      event_title: '',
      event_starts_at: null,
      audience: 'members',
      filters: {},
      persons: [],
      names: 'open',
      results: 'after_answer',
      status: 'draft',
      closes_at: '2099-05-01T18:00:00Z',
      remind_days: 1,
      keep_months: 12,
      opened_at: null,
      closed_at: null,
      purged_at: null,
      participants: 0,
      invited: null,
      follow_event: null,
      version: 1,
      can_edit: true,
      can_create_event: false,
      questions: [],
      result: null,
      pending: [],
    }
    const api = fakeApi({
      'GET /_allauth/browser/v1/auth/session': () => ({
        status: 200,
        body: { status: 200, data: { user: testUser } },
      }),
      'GET /api/me/organizations/': () => ({
        status: 200,
        body: [testOrg({ modules: ['surveys'], permissions: ['surveys.view', 'surveys.edit'] })],
      }),
      'GET /api/orgs/7/surveys/': () => ({ status: 200, body: [] }),
      'GET /api/orgs/7/surveys/options/': () => ({
        status: 200,
        body: { units: [], member_types: [], events: [], board: true },
      }),
      'POST /api/orgs/7/surveys/': () => ({ status: 201, body: created }),
      'GET /api/orgs/7/surveys/5/': () => ({ status: 200, body: created }),
    })
    render(
      <MemoryRouter initialEntries={['/umfragen']}>
        <AuthProvider>
          <OrgProvider>
            <App />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>,
    )
    expect(await screen.findByText('Noch keine Umfrage.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Neue Umfrage' }))
    const form = (await screen.findByRole('heading', { name: 'Neue Umfrage' })).closest('form')!
    fireEvent.click(within(form).getByRole('button', { name: 'Essenswahl' }))
    expect(within(form).getByLabelText('Titel')).toHaveValue('Essenswahl')
    expect(within(form).getByLabelText('Frage')).toHaveValue('Was möchtest du essen?')
    for (const [i, label] of ['Schnitzel', 'Fisch', 'vegetarisch'].entries()) {
      fireEvent.change(within(form).getByLabelText(`Antwort ${i + 1}`), {
        target: { value: label },
      })
    }
    fireEvent.click(within(form).getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(api.some((c) => c.key === 'POST /api/orgs/7/surveys/')).toBe(true))
    const body = JSON.parse(
      String(api.find((c) => c.key === 'POST /api/orgs/7/surveys/')!.init?.body),
    )
    expect(body).toMatchObject({ title: 'Essenswahl', names: 'open', audience: 'members' })
    expect(body.questions[0].kind).toBe('quantity')
    expect(body.questions[0].options.map((o: { label: string }) => o.label)).toEqual([
      'Schnitzel',
      'Fisch',
      'vegetarisch',
    ])
  })
})
