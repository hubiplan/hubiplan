// Scan-Seite für Personal ohne Konto: Karte prüfen, ohne Karte per Namenssuche einbuchen
// (Anmeldung A6). Erfundene Daten.
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PublicScanPage } from '../pages/PublicScanPage.tsx'
import { fakeApi } from './fakeApi.ts'

const API = '/api/public/scan/abc123/'
const PAGE = {
  organization: 'Schützenverein Musterstadt',
  event: 'Sommerfest',
  starts_at: '2027-07-03T14:00:00+02:00',
  label: 'Eingang Nord',
  station: 'Einlass',
  kind: 'entry',
  expires_at: '2027-07-04T23:59:00+02:00',
  allow_search: true,
}
const CARD = {
  name: 'Anna Muster',
  birth_date: '1990-05-01',
  minor: false,
  price_name: 'Erwachsene',
  number: 'A2027-0001',
  paid_state: 'paid',
  checked_in_at: '2027-07-03T14:05:00+02:00',
  bookings: [
    {
      id: 1,
      addon_id: 2,
      name: 'Mittagessen: Schnitzel',
      per_registration: false,
      redeemed_at: null,
    },
  ],
}

function renderPage(routes: Parameters<typeof fakeApi>[0]) {
  const calls = fakeApi(routes)
  render(
    <MemoryRouter initialEntries={['/kartenscan/abc123']}>
      <Routes>
        <Route path="/kartenscan/:token" element={<PublicScanPage />} />
      </Routes>
    </MemoryRouter>,
  )
  return calls
}

afterEach(() => vi.restoreAllMocks())

describe('Kartenscan für Personal', () => {
  it('prüft eine Karte und zeigt Inhaber, Tarif und Leistungen', async () => {
    renderPage({
      [`GET ${API}`]: () => ({ status: 200, body: PAGE }),
      [`POST ${API}`]: () => ({
        status: 200,
        body: { result: 'ok', valid: true, message: 'Eingelassen.', at: null, card: CARD },
      }),
    })
    expect(await screen.findByRole('heading', { name: 'Sommerfest' })).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Code der Eintrittskarte'), 'T1:abc')
    await userEvent.click(screen.getByRole('button', { name: 'Prüfen' }))
    expect(await screen.findByText('Gültig: einlassen')).toBeInTheDocument()
    expect(screen.getByText('Anna Muster')).toBeInTheDocument()
    expect(screen.getByText(/Mittagessen: Schnitzel/)).toBeInTheDocument()
    expect(screen.getByText('noch nicht eingelöst')).toBeInTheDocument()
  })

  it('bucht ohne Karte über die Namenssuche ein', async () => {
    const calls = renderPage({
      [`GET ${API}`]: () => ({ status: 200, body: PAGE }),
      [`GET ${API}search/?q=Mus`]: () => ({
        status: 200,
        body: {
          results: [
            {
              id: 7,
              name: 'Anna Muster',
              birth_date: '1990-05-01',
              price_name: 'Erwachsene',
              number: 'A2027-0001',
              checked_in_at: null,
            },
          ],
        },
      }),
      [`POST ${API}`]: () => ({
        status: 200,
        body: { result: 'ok', valid: true, message: 'Eingelassen.', at: null, card: CARD },
      }),
    })
    await screen.findByRole('heading', { name: 'Sommerfest' })
    await userEvent.type(screen.getByLabelText('Name suchen'), 'Mus')
    await userEvent.click(screen.getByRole('button', { name: 'Suchen' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Einbuchen' }))
    expect(await screen.findByText('Gültig: einlassen')).toBeInTheDocument()
    const post = calls.find((c) => c.key === `POST ${API}`)
    expect(JSON.parse(String(post?.init?.body))).toEqual({ participant: 7 })
  })

  it('nimmt am Kassen-Link Bargeld an', async () => {
    const calls = renderPage({
      [`GET ${API}`]: () => ({ status: 200, body: { ...PAGE, cash: true, cashier: 'Erika' } }),
      [`POST ${API}`]: () => ({
        status: 200,
        body: {
          result: 'waiting',
          valid: false,
          message: 'Noch nicht bezahlt.',
          at: null,
          card: { ...CARD, id: 7, paid_state: 'open', open_amount: '25.00' },
        },
      }),
      [`POST ${API}cash/`]: () => ({
        status: 200,
        body: {
          result: 'paid',
          valid: true,
          message: 'Barzahlung gebucht.',
          at: null,
          card: { ...CARD, id: 7, open_amount: null },
        },
      }),
    })
    await screen.findByRole('heading', { name: 'Sommerfest' })
    await userEvent.type(screen.getByLabelText('Code der Eintrittskarte'), 'T1:abc')
    await userEvent.click(screen.getByRole('button', { name: 'Prüfen' }))
    await userEvent.click(await screen.findByRole('button', { name: /bar erhalten$/ }))
    await userEvent.click(await screen.findByRole('button', { name: 'Barzahlung buchen' }))
    expect(await screen.findByText('Barzahlung gebucht.')).toBeInTheDocument()
    const post = calls.find((c) => c.key === `POST ${API}cash/`)
    expect(JSON.parse(String(post?.init?.body))).toMatchObject({ participant: 7 })
  })

  it('meldet einen gesperrten Link', async () => {
    renderPage({ [`GET ${API}`]: () => ({ status: 404, body: { detail: 'Nicht gefunden.' } }) })
    expect(await screen.findByText('Dieser Link ist ungültig oder abgelaufen.')).toBeInTheDocument()
  })
})
