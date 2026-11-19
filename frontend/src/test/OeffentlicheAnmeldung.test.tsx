// Öffentliche Anmeldung zu einem Termin (Stufe A4): Formular, Bestätigungslink, eigene
// Anmeldung (Daten erfunden).
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import type { Offer, PublicMine, PublicRegistrationForm } from '../api/registrations.ts'
import { fakeApi } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedOut = () => ({ status: 401, body: { status: 401, data: { flows: [] } } })

function renderAt(path: string) {
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

const offer = {
  id: 1,
  state: 'open',
  state_text: 'Anmeldung möglich bis 1. Juni 2099, 23:59 Uhr.',
  opens_at: null,
  closes_at: '2099-06-01T21:59:00Z',
  capacity: 40,
  free: 38,
  max_persons: 4,
  guests_allowed: true,
  terms: 'Abmeldung nur schriftlich.',
  waitlist: false,
  waiting: 0,
  substitute_allowed: true,
  cancel_rules: [],
  cancel_fee_fixed: null,
  prices: [
    {
      id: 13,
      name: 'Gäste',
      name_en: 'Guests',
      applies: 'guests',
      age_from: null,
      age_to: null,
      capacity: null,
      free: null,
      vat_rate: null,
      is_active: true,
      current: { id: 23, name: '', amount: '40.00', until_date: null, remaining: null },
      next: null,
    },
  ],
  addons: [],
  questions: [],
} as unknown as Offer

const event = {
  title: 'Sommerfest',
  starts_at: '2099-06-13T12:00:00Z',
  ends_at: '2099-06-13T16:00:00Z',
  all_day: false,
  location: 'Festwiese',
  address: 'Musterweg 1, 12345 Musterstadt',
  description: 'Mit Musik und Kuchen.',
  programme: '14:00 Begrüßung',
}

const form: PublicRegistrationForm = {
  organization: 'TV Beispielhausen',
  privacy_text: 'Wir verarbeiten deine Angaben für die Anmeldung.',
  event,
  offer,
  cancel_text: 'Abmelden ist bis zum Anmeldeschluss kostenfrei möglich.',
  challenge: { token: 'ch', salt: 'abc', difficulty: 0 },
}

const mine: PublicMine = {
  organization: 'TV Beispielhausen',
  event,
  offer,
  cancel_text: '',
  token: 'link',
  registration: {
    id: 5,
    number: 'A2099-0007',
    status: 'registered',
    name: 'Erika Beispiel',
    total: '40.00',
    paid_state: 'open',
    created_at: '2099-01-02T10:00:00Z',
    cancelled_at: null,
    participants: [
      {
        id: 9,
        name: 'Erika Beispiel',
        membership_id: null,
        price_id: 13,
        price_name: 'Gäste',
        amount: '40.00',
        status: 'active',
      },
    ],
    invoice: {
      id: 3,
      number: '2099-0042',
      status: 'open',
      total: '40.00',
      paid: '0.00',
      due_date: '2099-01-16',
    },
    waitlist_position: null,
    can_cancel: true,
  } as unknown as PublicMine['registration'],
}

describe('Öffentliche Anmeldung', () => {
  it('Formular: Pflichtangaben, Datenschutz, dann Hinweis auf die Bestätigungsmail', async () => {
    const calls = fakeApi({
      [SESSION]: loggedOut,
      'GET /api/public/registration/key/?lang=de': () => ({ status: 200, body: form }),
      'POST /api/public/registration/key/': () => ({ status: 201, body: { status: 'ok' } }),
    })
    renderAt('/anmeldung/key')
    expect(await screen.findByText('Mit Musik und Kuchen.')).toBeInTheDocument()
    const send = () =>
      screen.getByRole('button', { name: /^(Zahlungspflichtig|Verbindlich) anmelden$/ })
    expect(send()).toBeDisabled()
    const [name] = screen.getAllByLabelText(/^Name/)
    fireEvent.change(name, { target: { value: 'Erika Beispiel' } })
    fireEvent.change(screen.getByLabelText(/^E-Mail/), {
      target: { value: 'erika@example.org' },
    })
    fireEvent.change(screen.getByLabelText(/^Tarif/), { target: { value: '13' } })
    fireEvent.click(
      screen.getByLabelText('Ich habe die Teilnahmebedingungen gelesen und akzeptiere sie.'),
    )
    expect(send()).toBeDisabled()
    fireEvent.click(screen.getByLabelText('Ich habe den Datenschutzhinweis gelesen.'))
    expect(screen.getByText('Summe: 40,00 €')).toBeInTheDocument()
    expect(send()).toHaveTextContent('Zahlungspflichtig anmelden')
    fireEvent.click(send())
    expect(await screen.findByText('Fast geschafft')).toBeInTheDocument()
    const post = calls.find((c) => c.key === 'POST /api/public/registration/key/')
    const body = JSON.parse(String(post?.init?.body))
    expect(body).toMatchObject({
      name: 'Erika Beispiel',
      email: 'erika@example.org',
      persons: [{ name: 'Erika Beispiel', price_id: 13 }],
      terms_accepted: true,
      privacy_accepted: true,
      challenge: 'ch',
      nonce: 0,
      homepage: '',
    })
  })

  it('Bestätigungslink führt zur eigenen Anmeldung, dort abmelden', async () => {
    const calls = fakeApi({
      [SESSION]: loggedOut,
      'POST /api/public/registration/confirm/tok/': () => ({ status: 200, body: mine }),
      'GET /api/public/registration/mine/link/': () => ({ status: 200, body: mine }),
      'GET /api/public/registration/mine/link/cancel/': () => ({
        status: 200,
        body: { fee: '0.00', percent: 0, text: 'Kostenfrei abmelden.', has_fee: false },
      }),
      'POST /api/public/registration/mine/link/cancel/': () => ({
        status: 200,
        body: { ...mine, registration: { ...mine.registration, status: 'cancelled' } },
      }),
    })
    renderAt('/anmeldung/bestaetigen/tok')
    expect(await screen.findByText(/Danke, du bist verbindlich angemeldet/)).toBeInTheDocument()
    expect(screen.getByText(/Rechnung 2099-0042 über 40,00 €/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Abmelden' }))
    await waitFor(() =>
      expect(calls.some((c) => c.key === 'GET /api/public/registration/mine/link/cancel/')).toBe(
        true,
      ),
    )
  })

  it('Unbekannter Link', async () => {
    fakeApi({
      [SESSION]: loggedOut,
      'GET /api/public/registration/nix/?lang=de': () => ({ status: 404, body: {} }),
    })
    renderAt('/anmeldung/nix')
    expect(await screen.findByText(/gibt es nicht oder nicht mehr/)).toBeInTheDocument()
  })
})
