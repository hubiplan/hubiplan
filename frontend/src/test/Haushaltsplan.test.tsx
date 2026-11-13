import { render, screen, within } from '@testing-library/react'
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

const categories = [
  { id: 1, name: 'Beiträge', kind: 'income', is_active: true },
  { id: 2, name: 'Schützenfest', kind: 'both', is_active: true },
  { id: 3, name: 'Musik', kind: 'expense', is_active: true },
]

const totals = (plan: string, actual: string | null) => ({
  plan,
  actual,
  forecast: actual,
  previous_plan: '0.00',
  previous_actual: '0.00',
})

function report(withPlan: boolean, status: 'draft' | 'adopted' = 'draft') {
  return {
    year: 2026,
    label: '2026',
    start_date: '2026-01-01',
    end_date: '2026-12-31',
    phase: 'current',
    elapsed_percent: 50,
    years: [
      { year: 2027, label: '2027' },
      { year: 2026, label: '2026' },
    ],
    previous_label: '2025',
    previous_has_budget: false,
    budget: withPlan
      ? {
          id: 5,
          status,
          status_label: status === 'draft' ? 'Entwurf' : 'beschlossen',
          adopted_on: status === 'adopted' ? '2026-03-01' : null,
          adopted_by: status === 'adopted' ? 'Mitgliederversammlung' : '',
          note: '',
          version: 2,
          updated_at: '2026-03-01T10:00:00Z',
        }
      : null,
    lines: withPlan
      ? [
          {
            id: 11,
            kind: 'income',
            category: 1,
            category_name: 'Beiträge',
            category_active: true,
            department: null,
            department_name: null,
            amount: '6000.00',
            note: '',
            actual: '5000.00',
            forecast: '6000.00',
            previous_plan: null,
            previous_actual: '0.00',
          },
        ]
      : [],
    unplanned: withPlan
      ? [
          {
            kind: 'expense',
            category: 3,
            category_name: 'Musik',
            department: null,
            department_name: null,
            actual: '1200.00',
          },
        ]
      : [],
    totals: {
      income: totals(withPlan ? '6000.00' : '0.00', withPlan ? '5000.00' : '0.00'),
      expense: totals('0.00', withPlan ? '1200.00' : '0.00'),
      result: totals(withPlan ? '6000.00' : '0.00', withPlan ? '3800.00' : '0.00'),
    },
  }
}

function renderApp(path: string) {
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

function api(withPlan: boolean, canEdit = true, status: 'draft' | 'adopted' = 'draft') {
  const org = testOrg({
    modules: ['members', 'finance'],
    permissions: canEdit ? ['finance.view', 'finance.edit'] : ['finance.view'],
    parent_name: null,
  })
  return fakeApi({
    [SESSION]: loggedIn,
    'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
    [`GET ${F}/categories/`]: () => ({ status: 200, body: categories }),
    'GET /api/orgs/7/department-choices/': () => ({ status: 200, body: [] }),
    [`GET ${F}/budget/`]: () => ({ status: 200, body: report(withPlan, status) }),
    [`POST ${F}/budget/copy/?jahr=2026`]: () => ({ status: 200, body: report(true) }),
    [`PUT ${F}/budget/?jahr=2026`]: () => ({ status: 200, body: report(true) }),
    [`POST ${F}/budget/status/?jahr=2026`]: () => ({
      status: 200,
      body: report(true, 'adopted'),
    }),
  })
}

describe('Haushaltsplan', () => {
  it('übernimmt das Ist des Vorjahres als Vorlage', async () => {
    const calls = api(false)
    renderApp('/finanzen/haushaltsplan')
    const empty = await screen.findByTestId('budget-empty')
    expect(within(empty).getByText('Noch kein Haushaltsplan für 2026')).toBeInTheDocument()
    await userEvent.click(within(empty).getByRole('button', { name: 'Ist von 2025 übernehmen' }))
    const post = calls.find((c) => c.key === `POST ${F}/budget/copy/?jahr=2026`)
    expect(JSON.parse(String(post?.init?.body))).toEqual({ source: 'actual' })
    expect(await screen.findByText('Ist von 2025 übernommen.')).toBeInTheDocument()
  })

  it('zeigt Plan, Ist, Abweichung und nicht geplante Buchungen', async () => {
    api(true)
    renderApp('/finanzen/haushaltsplan')
    const income = await screen.findByTestId('budget-income')
    expect(within(income).getByText('Beiträge')).toBeInTheDocument()
    expect(within(income).getByText('83 %')).toBeInTheDocument()
    const expense = screen.getByTestId('budget-expense')
    expect(within(expense).getByText('(nicht geplant)')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'PDF' })).toHaveAttribute(
      'href',
      `${F}/budget/?jahr=2026&als=pdf`,
    )
  })

  it('speichert geänderte Beträge und trägt den Beschluss ein', async () => {
    const calls = api(true)
    renderApp('/finanzen/haushaltsplan')
    await userEvent.click(await screen.findByRole('button', { name: 'Bearbeiten' }))
    const amount = screen.getByLabelText('Plan 2026')
    await userEvent.clear(amount)
    await userEvent.type(amount, '6500,50')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    const put = calls.find((c) => c.key === `PUT ${F}/budget/?jahr=2026`)
    expect(JSON.parse(String(put?.init?.body))).toEqual({
      lines: [{ kind: 'income', category: 1, department: null, amount: '6500.50', note: '' }],
      note: '',
      version: 2,
    })
    await userEvent.click(await screen.findByRole('button', { name: 'Als beschlossen eintragen' }))
    await userEvent.type(screen.getByLabelText('beschlossen durch (optional)'), 'JHV')
    await userEvent.click(screen.getByRole('button', { name: 'Eintragen' }))
    const post = calls.find((c) => c.key === `POST ${F}/budget/status/?jahr=2026`)
    expect(JSON.parse(String(post?.init?.body))).toMatchObject({
      status: 'adopted',
      adopted_by: 'JHV',
      version: 2,
    })
    expect(await screen.findByText('Beschlossen durch: Mitgliederversammlung')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Bearbeiten' })).toBeNull()
  })

  it('lässt ohne Schreibrecht nur lesen', async () => {
    api(false, false)
    renderApp('/finanzen/haushaltsplan')
    expect(
      await screen.findByText('Die Kasse hat für dieses Jahr noch nichts geplant.'),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Leer beginnen' })).toBeNull()
  })
})
