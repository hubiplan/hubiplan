import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { PortalExpenses } from '../pages/portal/PortalExpenses.tsx'
import { amountText } from '../pages/expenses/format.ts'
import { fakeApi } from './fakeApi.ts'

const options = {
  may_submit: true,
  mileage_enabled: true,
  km_rate: '0.30',
  advances_enabled: false,
  waiver_enabled: false,
  payee: { holder: 'Anna Muster', iban: 'DE89370400440532013000' },
  departments: [],
  projects: [],
  categories: [],
  open_advances: [],
}

function claim(over: Record<string, unknown> = {}) {
  return {
    id: 4,
    number: 'A2099-0001',
    kind: 'expense',
    status: 'submitted',
    status_label: 'eingereicht',
    source: 'portal',
    name: 'Anna Muster',
    membership: 1,
    purpose: 'Hemden für die Jugend',
    note: '',
    purchase_date: '2099-01-02',
    department: null,
    department_name: '',
    project: null,
    project_name: '',
    invoice_to: 'club',
    payout: 'bank',
    route: '',
    km: null,
    km_rate: null,
    advance: null,
    advance_number: '',
    total: '45.90',
    approved_amount: null,
    reduce_reason: '',
    amount_due: '45.90',
    reject_reason: '',
    self_approved: false,
    reviewed: false,
    approved_once: false,
    submitted_at: '2099-01-02T10:00:00Z',
    decided_at: null,
    paid_at: null,
    created_at: '2099-01-02T10:00:00Z',
    version: 1,
    file_count: 1,
    lines: [{ id: 1, amount: '45.90', text: 'Hemden', category: null }],
    payee: { holder: 'Anna Muster', iban: 'DE89370400440532013000' },
    ...over,
  }
}

describe('Auslagen im Mitgliederbereich', () => {
  it('meldet eine Auslage mit Beleg und Bankverbindung in einem Schritt', async () => {
    let sent = false
    const api = fakeApi({
      'GET /api/portal/9/expenses/': () => ({
        status: 200,
        body: { claims: sent ? [claim()] : [], options },
      }),
      'POST /api/portal/9/expenses/': () => {
        sent = true
        return { status: 201, body: claim() }
      },
    })
    render(
      <MemoryRouter>
        <PortalExpenses accessId={9} />
      </MemoryRouter>,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Auslage melden' }))
    fireEvent.change(screen.getByLabelText('Wofür, für wen?'), {
      target: { value: 'Hemden für die Jugend' },
    })
    fireEvent.change(screen.getByLabelText('Betrag in €'), { target: { value: '45,90' } })
    const photo = new File(['x'], 'beleg.jpg', { type: 'image/jpeg' })
    fireEvent.change(screen.getByLabelText('Foto aufnehmen', { selector: 'input' }), {
      target: { files: [photo] },
    })
    expect(screen.getByText('beleg.jpg')).toBeInTheDocument()
    // Bankverbindung aus dem Mandat vorbelegt
    expect(screen.getByLabelText('IBAN')).toHaveValue('DE89370400440532013000')
    fireEvent.click(screen.getByRole('button', { name: 'Einreichen' }))
    await waitFor(() =>
      expect(api.some((c) => c.key === 'POST /api/portal/9/expenses/')).toBe(true),
    )
    const call = api.find((c) => c.key === 'POST /api/portal/9/expenses/')!
    const form = call.init?.body as FormData
    expect(form.get('submit')).toBe('true')
    expect(JSON.parse(String(form.get('lines')))).toEqual([{ amount: '45.90', text: '' }])
    expect(form.getAll('file')).toHaveLength(1)
    expect(new Headers(call.init?.headers).get('Idempotency-Key')).toBeTruthy()
    expect(await screen.findByText(/A2099-0001 ist eingereicht/)).toBeInTheDocument()
  })

  it('liest Beträge mit Komma und Tausenderpunkt', () => {
    expect(amountText('1.234,50')).toBe('1234.50')
    expect(amountText('12,5')).toBe('12.5')
    expect(amountText(' 7.20 ')).toBe('7.20')
  })
})
