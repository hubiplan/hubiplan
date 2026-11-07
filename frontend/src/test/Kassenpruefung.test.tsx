import { render, screen } from '@testing-library/react'
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

const settings = {
  current_year: 2026,
  years: [
    { year: 2026, label: '2026' },
    { year: 2025, label: '2025' },
  ],
  tax_areas: [],
  tax_areas_enabled: false,
}

const summary = {
  id: 4,
  year: 2025,
  label: '2025',
  status: 'open',
  status_label: 'in Prüfung',
  auditors: 'Erika Musterfrau',
  due_on: '2026-02-28',
  recommendation: '',
  recommendation_label: 'noch offen',
  open_points: 11,
  closed_at: null,
}

function detail(canAudit: boolean) {
  return {
    ...summary,
    sample_size: 1,
    findings: '',
    meeting: null,
    meeting_title: null,
    checks: [{ key: 'receipts', label: 'Belege vollständig und geordnet', result: '', note: '' }],
    samples: [
      {
        id: 9,
        booking: 31,
        number: '2025-0031',
        date: '2025-06-01',
        kind: 'expense',
        kind_label: 'Ausgabe',
        amount: '480.00',
        text: 'Pokale Königsschießen',
        counterparty: 'Pokalhaus Muster',
        category: 'Schießsport',
        account: 'Girokonto',
        receipts: [],
        result: '',
        note: '',
        checked_by: '',
        checked_at: null,
      },
    ],
    accounts: [
      {
        id: 2,
        account: 1,
        name: 'Girokonto',
        kind: 'bank',
        book_balance: '1500.00',
        statement_balance: null,
        difference: null,
        note: '',
        checked_by: '',
        checked_at: null,
      },
    ],
    facts: {
      bookings: 40,
      without_receipt: 3,
      gaps: [],
      gap_count: 0,
      closed: true,
      cash_counts: 1,
    },
    access: canAudit ? [{ name: 'Erika Musterfrau', until: '2026-03-31' }] : [],
    can_audit: canAudit,
    can_manage: !canAudit,
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

function api(canAudit: boolean) {
  const org = testOrg({
    modules: ['members', 'finance'],
    permissions: canAudit ? ['finance.view'] : ['finance.view', 'finance.edit'],
    parent_name: null,
  })
  return fakeApi({
    [SESSION]: loggedIn,
    'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
    [`GET ${F}/settings/`]: () => ({ status: 200, body: settings }),
    [`GET ${F}/audits/`]: () => ({ status: 200, body: [summary] }),
    [`GET ${F}/audits/4/`]: () => ({ status: 200, body: detail(canAudit) }),
    [`GET ${F}/audits/meetings/`]: () => ({ status: 200, body: [] }),
    [`POST ${F}/audits/4/check/`]: () => ({ status: 200, body: detail(canAudit) }),
  })
}

describe('Kassenprüfung', () => {
  it('zeigt die Prüfaufträge und den Hinweis auf fehlende Prüferrechte', async () => {
    api(false)
    renderApp('/finanzen/abschluss/kassenpruefung')
    await userEvent.click(await screen.findByRole('button', { name: '2025' }))
    expect(await screen.findByTestId('audit-detail')).toBeInTheDocument()
    expect(screen.getByText(/Noch hat niemand Prüferrechte/)).toBeInTheDocument()
    expect(screen.getByText(/Abhaken dürfen nur die Kassenprüfer/)).toBeInTheDocument()
    expect(screen.getByText('kein Beleg')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Prüfung abschließen' })).toBeNull()
    expect(screen.getByRole('link', { name: 'Prüfbericht (PDF)' })).toHaveAttribute(
      'href',
      expect.stringContaining('/finance/audits/4/pdf/'),
    )
  })

  it('lässt Kassenprüfer Stichproben abhaken', async () => {
    const calls = api(true)
    renderApp('/finanzen/abschluss/kassenpruefung?pruefung=4')
    const select = await screen.findByLabelText('Ergebnis zu 2025-0031')
    await userEvent.selectOptions(select, 'ok')
    const post = calls.find((c) => c.key === `POST ${F}/audits/4/check/`)
    expect(JSON.parse(String(post?.init?.body))).toEqual({ sample: 9, result: 'ok', note: '' })
    expect(screen.getByText(/Zugang bis/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Prüfung abschließen' })).toBeInTheDocument()
  })
})
