import { act, render, screen } from '@testing-library/react'
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

  it('zeigt „Wird geprüft“ und fragt nach, bis die Prüfung fertig ist', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      const pending: IncomingInvoice = {
        ...item,
        validation: 'pending',
        report: { status: 'pending', validator: 'KoSIT', messages: [] },
      }
      let calls = 0
      fakeApi({
        [incoming + '1']: () => {
          calls += 1
          return {
            status: 200,
            body: page([
              calls < 2
                ? pending
                : {
                    ...item,
                    validation: 'done',
                    report: { status: 'valid', validator: 'KoSIT', messages: [] },
                  },
            ]),
          }
        },
      })
      show()
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
      expect(await screen.findByText('Wird geprüft')).toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: 'RE-1' }))
      expect(screen.queryByRole('button', { name: 'Erneut prüfen' })).not.toBeInTheDocument()
      await user.type(screen.getByLabelText('Prüfvermerk'), 'Leistung geprüft')
      expect(screen.getByRole('button', { name: 'Fachlich freigeben' })).toBeDisabled()
      await act(async () => {
        vi.advanceTimersByTime(4500)
      })
      expect(
        await screen.findByText(
          'Technische Prüfung erfolgreich. Die fachliche Prüfung bleibt erforderlich.',
        ),
      ).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Fachlich freigeben' })).toBeEnabled()
      expect(screen.queryByText('Wird geprüft')).not.toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
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
    await userEvent.click(screen.getByRole('button', { name: 'Nächste Seite' }))
    expect(await screen.findByRole('button', { name: 'RE-2' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'RE-1' })).not.toBeInTheDocument()
  })

  it('zeigt die Adresse des Rechnungspostfachs, Hinweise und unbekannte Absender', async () => {
    const mail = {
      id: 5,
      sender: 'buchhaltung@lieferant.example.com',
      subject: 'Ihre Rechnung',
      sender_known: false,
      status: 'imported' as const,
      skipped: [],
      received_at: '2026-11-10T12:00:00Z',
      dismissed_at: '2026-11-10T12:00:00Z',
    }
    const hint = {
      ...mail,
      id: 6,
      status: 'no_invoice' as const,
      skipped: [{ name: 'brief.pdf', reason: 'plain_pdf' }],
      dismissed_at: null,
    }
    let hints = [hint]
    const calls = fakeApi({
      [incoming + '1']: () => ({ status: 200, body: page([{ ...item, mail }]) }),
      'GET /api/orgs/7/finance/incoming/mailbox/': () => ({
        status: 200,
        body: { enabled: true, address: 'rechnung+abc234defg@example.org' },
      }),
      'GET /api/orgs/7/finance/incoming/mails/': () => ({ status: 200, body: hints }),
      'POST /api/orgs/7/finance/incoming/mails/6/dismiss/': () => {
        hints = []
        return { status: 200, body: { ...hint, dismissed_at: '2026-11-10T13:00:00Z' } }
      },
    })
    show()
    const user = userEvent.setup()
    expect(await screen.findByText('rechnung+abc234defg@example.org')).toBeInTheDocument()
    expect(await screen.findByText('Keine E-Rechnung im Anhang')).toBeInTheDocument()
    expect(screen.getByText('brief.pdf (PDF ohne E-Rechnung)')).toBeInTheDocument()
    expect(screen.getByText('Absender unbekannt')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Erledigt' }))
    expect(calls.some((call) => call.key.endsWith('/mails/6/dismiss/'))).toBe(true)
    expect(await screen.findByRole('button', { name: 'RE-1' })).toBeInTheDocument()
    expect(screen.queryByText('Keine E-Rechnung im Anhang')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'RE-1' }))
    expect(
      screen.getByText(
        'Der Absender der Mail passt zu keinem Geschäftspartner. Prüfe vor der Freigabe besonders Rechnungssteller und Bankverbindung.',
      ),
    ).toBeInTheDocument()
  })

  it('schlägt einen Geschäftspartner vor und verlangt bei neuer IBAN eine Bestätigung', async () => {
    const valid = {
      ...item,
      report: { status: 'valid' as const, validator: 'KoSIT', messages: [] },
      data: { ...item.data, iban: 'DE89370400440532013000' },
      partner: null,
      partner_name: '',
      suggested_partner: { id: 4, name: 'Lieferant Beispiel GmbH', by: 'vat_id' as const },
      iban_changed: true,
    }
    const linked = {
      ...valid,
      partner: 4,
      partner_name: 'Lieferant Beispiel GmbH',
      suggested_partner: null,
    }
    const calls = fakeApi({
      [incoming + '1']: () => ({ status: 200, body: page([valid]) }),
      'POST /api/orgs/7/finance/incoming/1/partner/': () => ({ status: 200, body: linked }),
      'POST /api/orgs/7/finance/incoming/1/review/': () => ({
        status: 200,
        body: { ...linked, status: 'approved', iban_changed: false },
      }),
    })
    show()
    const user = userEvent.setup()
    expect(await screen.findByText('Neue IBAN')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'RE-1' }))
    expect(
      screen.getByText('Vorschlag: Lieferant Beispiel GmbH (erkannt an der USt-IdNr.)'),
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Vorschlag zuordnen' }))
    const assign = calls.find((call) => call.key.endsWith('/incoming/1/partner/'))
    expect(JSON.parse(String(assign?.init?.body))).toEqual({ partner: 4 })
    await user.type(screen.getByLabelText('Prüfvermerk'), 'Leistung geprüft')
    const approve = screen.getByRole('button', { name: 'Fachlich freigeben' })
    expect(approve).toBeDisabled()
    await user.click(screen.getByLabelText('Neue IBAN telefonisch bestätigt'))
    await user.click(approve)
    const review = calls.find((call) => call.key.endsWith('/incoming/1/review/'))
    expect(JSON.parse(String(review?.init?.body))).toEqual({
      status: 'approved',
      note: 'Leistung geprüft',
      iban_confirmed: true,
    })
  })
})
