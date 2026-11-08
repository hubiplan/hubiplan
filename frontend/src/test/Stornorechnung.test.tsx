import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import type { BillingSettings, Invoice } from '../api/billing.ts'
import { InvoicesPage } from '../pages/billing/InvoicesPage.tsx'
import { fakeApi } from './fakeApi.ts'

vi.mock('../org/OrgContext.tsx', () => ({
  useActiveOrg: () => ({ id: 7, type: 'club', modules: ['billing'], permissions: [] }),
}))

const settings = {
  rhythm: 'yearly',
  due_days: 14,
  accounts: [{ id: 1, name: 'Girokonto', kind: 'bank', has_iban: true }],
  categories: [],
  rhythms: [],
  years: [],
  periods: {},
  clubs: [],
  org_type: 'club',
  department_label: 'Abteilung',
  department_label_plural: 'Abteilungen',
  current_year: 2026,
  account: 1,
  can_edit: true,
} as unknown as BillingSettings

const invoice = {
  id: 5,
  number: 'R2026-0012',
  status: 'paid',
  status_label: 'bezahlt',
  has_cancellation_pdf: false,
  recipient_kind: 'member',
  partner: null,
  payment_category: null,
  recipient_name: 'Erika Muster',
  recipient_email: 'erika@example.org',
  membership: 3,
  department: null,
  department_name: null,
  club: null,
  club_name: null,
  issuer_name: '',
  run: null,
  run_label: null,
  project: null,
  project_name: null,
  date: '2026-11-01',
  due_date: '2026-11-15',
  subject: 'Uniform',
  total: '80.00',
  document_kind: 'invoice',
  prepaid: '0.00',
  paid: '80.00',
  outstanding: '0.00',
  sent_at: null,
  overdue: false,
  dunning_level: 0,
  dunned_at: null,
  recipient_address: '',
  note: '',
  cancelled_at: null,
  cancel_reason: '',
  cancellation_date: null,
  cancellation_number: '',
  cancellation_sent_at: null,
  credit: '0.00',
  copyable: true,
  lines: [{ id: 1, text: 'Uniform', detail: '', amount: '80.00', vat_rate: null }],
  payments: [],
  dunnings: [],
  vat: [],
} as unknown as Invoice

const cancelled = {
  ...invoice,
  status: 'cancelled',
  status_label: 'storniert',
  has_cancellation_pdf: true,
  cancel_reason: 'Größe falsch',
  cancellation_date: '2026-11-08',
  cancellation_number: 'R2026-0012-S',
  credit: '80.00',
} as Invoice

function show() {
  return render(
    <MemoryRouter initialEntries={['/finanzen/rechnungen?rechnung=5']}>
      <InvoicesPage />
    </MemoryRouter>,
  )
}

const base = '/api/orgs/7/billing'
const routes = (detail: Invoice) => ({
  [`GET ${base}/settings/`]: () => ({ status: 200, body: settings }),
  [`GET ${base}/runs/`]: () => ({ status: 200, body: [] }),
  [`GET ${base}/invoices/?page=1`]: () => ({
    status: 200,
    body: { count: 0, next: null, previous: null, results: [] },
  }),
  [`GET ${base}/invoices/5/`]: () => ({ status: 200, body: detail }),
})

describe('Stornorechnung', () => {
  it('fragt nach dem Grund und schickt ihn mit', async () => {
    const calls = fakeApi({
      ...routes(invoice),
      [`POST ${base}/invoices/5/cancel/`]: () => ({ status: 200, body: cancelled }),
    })
    show()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Stornieren' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/Bereits gezahlt/)).toBeInTheDocument()
    await user.type(within(dialog).getByRole('textbox'), 'Größe falsch')
    await user.click(within(dialog).getByRole('button', { name: 'Stornieren' }))
    expect(await screen.findByText('Stornorechnung R2026-0012-S')).toBeInTheDocument()
    const post = calls.find((c) => c.key === `POST ${base}/invoices/5/cancel/`)
    expect(JSON.parse(String(post?.init?.body))).toEqual({ reason: 'Größe falsch' })
  })

  it('zeigt Stornobeleg und Guthaben mit Erstatten und Verrechnen', async () => {
    fakeApi(routes(cancelled))
    show()
    expect(await screen.findByText('Stornorechnung R2026-0012-S')).toBeInTheDocument()
    expect(screen.getByText('Grund: Größe falsch')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Stornorechnung ansehen' })).toHaveAttribute(
      'href',
      `${base}/invoices/5/cancellation-pdf/`,
    )
    expect(screen.getByRole('button', { name: 'Erstatten' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Verrechnen' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Als neuen Entwurf anlegen' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Stornieren' })).not.toBeInTheDocument()
  })
})
