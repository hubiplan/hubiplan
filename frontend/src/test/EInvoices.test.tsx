import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import type { IncomingInvoice } from '../api/einvoices.ts'
import { IncomingInvoicesPage } from '../pages/billing/IncomingInvoicesPage.tsx'
import { fakeApi } from './fakeApi.ts'

vi.mock('../org/OrgContext.tsx', () => ({ useActiveOrg: () => ({ id: 7 }) }))

const item: IncomingInvoice = {
  id: 1,
  name: 'rechnung.xml',
  sha256: 'example',
  content_type: 'application/xml',
  has_report: false,
  data: { number: 'RE-1', seller: 'Lieferant Beispiel', payable: '119.00', currency: 'EUR' },
  report: {
    status: 'invalid',
    validator: 'KoSIT',
    messages: [{ level: 'error', text: 'Rechnungsdaten unvollständig' }],
  },
  status: 'review',
  review_note: '',
  booking: null,
  created_at: '2026-11-04T12:00:00Z',
}
const page = (results: IncomingInvoice[], next: string | null = null) => ({
  count: next ? 2 : results.length,
  next,
  previous: null,
  results,
})
const incoming = 'GET /api/orgs/7/finance/incoming/?page='

function show(canEdit = true) {
  return render(
    <MemoryRouter>
      <IncomingInvoicesPage canEdit={canEdit} />
    </MemoryRouter>,
  )
}

describe('E-Rechnungseingang', () => {
  it('verhindert die Freigabe einer technisch ungültigen Rechnung trotz Prüfvermerk', async () => {
    const calls = fakeApi({ [incoming + '1']: () => ({ status: 200, body: page([item]) }) })
    show()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'RE-1' }))
    expect(screen.getByText('Rechnungsdaten unvollständig')).toBeInTheDocument()
    await user.type(screen.getByLabelText('Prüfvermerk'), 'Leistung geprüft')
    expect(screen.getByRole('button', { name: 'Fachlich freigeben' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Ablehnen' })).toBeEnabled()
    expect(
      screen.queryByRole('link', { name: 'Prüfbericht herunterladen' }),
    ).not.toBeInTheDocument()
    expect(calls.some((call) => call.key.startsWith('POST'))).toBe(false)
  })

  it('zeigt Leserinnen nur die Originale und keine Schreibaktionen', async () => {
    fakeApi({
      [incoming + '1']: () => ({ status: 200, body: page([{ ...item, has_report: true }]) }),
    })
    show(false)
    await userEvent.click(await screen.findByRole('button', { name: 'RE-1' }))
    expect(screen.getByRole('link', { name: 'Original herunterladen' })).toHaveAttribute(
      'href',
      '/api/orgs/7/finance/incoming/1/download/?part=original',
    )
    expect(screen.getByRole('link', { name: 'Prüfbericht herunterladen' })).toBeInTheDocument()
    expect(screen.queryByLabelText('E-Rechnung importieren')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Fachlich freigeben' })).not.toBeInTheDocument()
  })

  it('blättert durch den vollständigen Rechnungseingang', async () => {
    fakeApi({
      [incoming + '1']: () => ({ status: 200, body: page([item], '?page=2') }),
      [incoming + '2']: () => ({
        status: 200,
        body: page([{ ...item, id: 2, data: { number: 'RE-2' } }]),
      }),
    })
    show(false)
    await screen.findByRole('button', { name: 'RE-1' })
    await userEvent.click(screen.getByRole('button', { name: 'Weiter' }))
    expect(await screen.findByRole('button', { name: 'RE-2' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'RE-1' })).not.toBeInTheDocument()
  })
})
