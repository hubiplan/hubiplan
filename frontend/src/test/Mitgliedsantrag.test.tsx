// Online-Mitgliedsantrag: Stand-Modus, eigener Antrag, Prüfseite (Daten erfunden).
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import type { JoinSchema, JoinStatus } from '../api/admission.ts'
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

const schema: JoinSchema = {
  organization: 'TV Beispielhausen',
  language: 'de',
  languages: ['de'],
  intro: 'Willkommen beim Turnverein.',
  thanks: '',
  types: [{ id: 3, label: 'Aktiv', text: '', fee: '36,00', organizations: false }],
  fields: {
    phone: 'optional',
    gender: 'off',
    birth_date: 'required',
    unit: 'off',
    entry_wish: 'off',
    note: 'off',
  },
  units: [],
  unit: null,
  unit_label: 'Abteilung',
  custom_fields: [],
  sepa: 'off',
  mandate: {},
  confirmations: [
    { key: 'privacy', label: 'Ich habe die Datenschutzhinweise gelesen.', text: 'x' },
  ],
  consents: [],
  signature: 'none',
  minors: true,
  min_age: null,
  kiosk: 'Sommerfest',
  valid_until: '2099-06-13T18:00:00Z',
}

const status = (over: Partial<JoinStatus> = {}): JoinStatus => ({
  number: 'A2099-00001',
  status: 'unconfirmed',
  status_label: 'E-Mail noch nicht bestätigt',
  organization: 'TV Beispielhausen',
  name: 'Erika Muster',
  language: 'de',
  summary: ['Mitgliedsart: Aktiv'],
  signed: false,
  signature_required: false,
  can_withdraw: true,
  can_sign: true,
  ...over,
})

describe('Mitgliedsantrag', () => {
  it('Stand-Modus: drei Schritte, Pflichtfelder geprüft, Nummer nach dem Absenden', async () => {
    const calls = fakeApi({
      [SESSION]: loggedOut,
      'GET /api/public/join/kiosk/tok/?lang=de': () => ({ status: 200, body: schema }),
      'POST /api/public/join/kiosk/tok/': () => ({
        status: 201,
        body: { status: 'ok', number: 'A2099-00007' },
      }),
    })
    renderAt('/mitglied-werden/stand/tok')
    expect(await screen.findByText('Willkommen beim Turnverein.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Weiter' }))
    expect(await screen.findByText('Bitte die markierten Angaben prüfen.')).toBeInTheDocument()

    const fill = (label: RegExp, value: string) =>
      fireEvent.change(screen.getByLabelText(label), { target: { value } })
    fill(/^Vorname/, 'Erika')
    fill(/^Nachname/, 'Muster')
    fill(/^Geburtsdatum/, '1990-04-01')
    fill(/^E-Mail-Adresse/, 'erika@example.org')
    fill(/^Straße und Hausnummer/, 'Musterweg 1')
    fill(/^PLZ/, '12345')
    fill(/^Ort/, 'Musterstadt')
    fireEvent.click(screen.getByRole('button', { name: 'Weiter' }))
    expect(await screen.findByText(/Beitrag: 36,00 € im Jahr/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Weiter' }))
    fireEvent.click(screen.getByRole('button', { name: 'Antrag absenden' }))
    expect(await screen.findByText('Bitte bestätigen.')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Ich habe die Datenschutzhinweise gelesen.'))
    fireEvent.click(screen.getByRole('button', { name: 'Antrag absenden' }))
    expect(await screen.findByText(/A2099-00007/)).toBeInTheDocument()
    const post = calls.find((c) => c.key === 'POST /api/public/join/kiosk/tok/')
    const body = JSON.parse(String(post?.init?.body))
    expect(body).toMatchObject({
      member_type: 3,
      first_name: 'Erika',
      birth_date: '1990-04-01',
      confirmations: ['privacy'],
      guardians: [],
      mandate: null,
    })
    fireEvent.click(screen.getByRole('button', { name: 'Nächster Antrag' }))
    expect(await screen.findByLabelText(/^Vorname/)).toHaveValue('')
  })

  it('Minderjährige brauchen Erziehungsberechtigte und deren Bestätigung', async () => {
    fakeApi({
      [SESSION]: loggedOut,
      'GET /api/public/join/kiosk/tok/?lang=de': () => ({ status: 200, body: schema }),
    })
    renderAt('/mitglied-werden/stand/tok')
    await screen.findByText('Willkommen beim Turnverein.')
    fireEvent.change(screen.getByLabelText(/^Geburtsdatum/), {
      target: { value: `${new Date().getFullYear() - 10}-01-01` },
    })
    expect(await screen.findByText('Erziehungsberechtigte')).toBeInTheDocument()
  })

  it('eigener Antrag: Link aus der Mail bestätigt, Zurückziehen fragt nach', async () => {
    const calls = fakeApi({
      [SESSION]: loggedOut,
      'GET /api/public/join/application/abc/': () => ({ status: 200, body: status() }),
      'POST /api/public/join/application/abc/confirm/': () => ({
        status: 200,
        body: status({ status: 'open', status_label: 'eingegangen', can_sign: false }),
      }),
      'POST /api/public/join/application/abc/withdraw/': () => ({
        status: 200,
        body: status({ status: 'withdrawn', status_label: 'zurückgezogen', can_withdraw: false }),
      }),
    })
    renderAt('/antrag/abc?bestaetigen=1')
    expect(await screen.findByText('Danke, der Antrag ist bestätigt.')).toBeInTheDocument()
    expect(calls.some((c) => c.key === 'POST /api/public/join/application/abc/confirm/')).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Mitgliedsantrag zurückziehen' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Ja, zurückziehen' }))
    await waitFor(() =>
      expect(screen.getByText('Du hast den Antrag zurückgezogen.')).toBeInTheDocument(),
    )
  })
})
