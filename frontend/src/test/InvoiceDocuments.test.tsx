import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { CommercialInvoice } from '../api/einvoices.ts'
import { InvoiceDocumentsPanel } from '../pages/billing/InvoiceDocumentsPanel.tsx'
import { fakeApi } from './fakeApi.ts'

const invoice = { id: 4, status: 'open', has_hybrid: false } as CommercialInvoice
const path = '/api/orgs/7/billing/electronic/4/'

describe('Rechnungsoriginale und Gateway', () => {
  it('fordert eine geprüfte Hybriddatei an und zeigt anschließend den Download', async () => {
    const calls = fakeApi({
      [`GET ${path}delivery/`]: () => ({
        status: 200,
        body: { configuration: { enabled: false }, deliveries: [] },
      }),
      [`POST ${path}hybrid/`]: () => ({ status: 200, body: { ...invoice, has_hybrid: true } }),
    })
    const reload = vi.fn(async () => {})
    const view = render(<InvoiceDocumentsPanel org={7} invoice={invoice} canEdit reload={reload} />)
    await userEvent.click(screen.getByRole('button', { name: 'ZUGFeRD erstellen und prüfen' }))
    expect(reload).toHaveBeenCalledOnce()
    expect(calls.filter((c) => c.key === `POST ${path}hybrid/`)).toHaveLength(1)
    view.rerender(
      <InvoiceDocumentsPanel
        org={7}
        invoice={{ ...invoice, has_hybrid: true }}
        canEdit
        reload={reload}
      />,
    )
    expect(screen.getByRole('link', { name: 'ZUGFeRD herunterladen' })).toHaveAttribute(
      'href',
      `${path}hybrid/`,
    )
    expect(
      screen.queryByRole('button', { name: 'Elektronisch übermitteln' }),
    ).not.toBeInTheDocument()
  })

  it('gleicht einen unbestätigten Versand ausdrücklich ab', async () => {
    let refreshed = false
    const calls = fakeApi({
      [`GET ${path}delivery/`]: () => ({
        status: 200,
        body: {
          configuration: { enabled: true, label: 'Musteranbieter', participant: '0204:BEISPIEL' },
          deliveries: [
            {
              id: 1,
              document: 'invoice',
              status: refreshed ? 'delivered' : 'unknown',
              provider: 'Musteranbieter',
              receipt: {},
            },
          ],
        },
      }),
      [`POST ${path}delivery/`]: () => {
        refreshed = true
        return { status: 200, body: { status: 'delivered' } }
      },
    })
    render(<InvoiceDocumentsPanel org={7} invoice={invoice} canEdit reload={async () => {}} />)
    await screen.findByRole('button', { name: 'Übermittlung erneut abgleichen' })
    expect(calls.some((c) => c.key.startsWith('POST'))).toBe(false)
    await userEvent.click(screen.getByRole('button', { name: 'Versandstatus abrufen' }))
    expect(await screen.findByText(/Zugestellt · Musteranbieter/)).toBeInTheDocument()
    expect(
      JSON.parse(String(calls.find((c) => c.key === `POST ${path}delivery/`)?.init?.body)),
    ).toEqual({ document: 'invoice', operation: 'refresh' })
  })

  it('bietet Leserechten ausschließlich vorhandene Downloads an', async () => {
    fakeApi({
      [`GET ${path}delivery/`]: () => ({
        status: 200,
        body: { configuration: { enabled: true }, deliveries: [] },
      }),
    })
    render(
      <InvoiceDocumentsPanel
        org={7}
        invoice={{
          ...invoice,
          status: 'cancelled',
          has_hybrid: true,
          has_cancellation_hybrid: true,
        }}
        canEdit={false}
        reload={async () => {}}
      />,
    )
    expect(screen.getAllByRole('link', { name: 'ZUGFeRD herunterladen' })).toHaveLength(2)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
