// Pflicht-2FA: neue Konten werden einmal zur Einrichtung geführt, und die Buchungsseite nennt
// den Grund, warum das Buchen ruht. Erfundene Daten.
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { MfaBookingNotice, useBookingPaused } from '../components/MfaBookingNotice.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const user = { ...testUser, id: 41, mfa_required_by: '2026-12-31T00:00:00Z' }
const loggedIn = () => ({ status: 200, body: { status: 200, data: { user } } })
const orgs = () => ({
  status: 200,
  body: [testOrg({ modules: ['finance'], permissions: ['finance.view', 'finance.edit'] })],
})

function show(path: string) {
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

describe('Einstieg in die Zwei-Faktor-Anmeldung', () => {
  beforeEach(() => window.localStorage.clear())

  it('führt ein neues Konto einmal von der Startseite zur Einrichtung', async () => {
    fakeApi({ [SESSION]: loggedIn, 'GET /api/me/organizations/': orgs })
    show('/')
    await waitFor(() => expect(window.localStorage.getItem('hubiplan.2fa-gefuehrt:41')).toBe('1'))
    // Nicht mehr auf der Startseite: Die Begrüßung fehlt
    await waitFor(() => expect(screen.queryByText(/Hallo Karla/)).toBeNull())
  })

  it('liest das Konto nach dem Laden der Einheiten neu, weil die Frist erst dann entsteht', async () => {
    window.sessionStorage.clear()
    let calls = 0
    const session = () => {
      calls += 1
      const data = calls === 1 ? { ...user, mfa_required_by: undefined } : user
      return { status: 200, body: { status: 200, data: { user: data } } }
    }
    fakeApi({ [SESSION]: session, 'GET /api/me/organizations/': orgs })
    show('/')
    await waitFor(() => expect(window.localStorage.getItem('hubiplan.2fa-gefuehrt:41')).toBe('1'))
    expect(calls).toBe(2)
  })

  it('nennt den Grund, warum das Buchen ruht, und führt zur Einrichtung', async () => {
    function Probe() {
      return useBookingPaused() ? <MfaBookingNotice /> : <p>frei</p>
    }
    fakeApi({ [SESSION]: loggedIn })
    render(
      <MemoryRouter>
        <AuthProvider>
          <Probe />
        </AuthProvider>
      </MemoryRouter>,
    )
    expect(await screen.findByTestId('buchen-ruht')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Zwei-Faktor-Anmeldung einrichten' })).toHaveAttribute(
      'href',
      '/mein-konto/anmeldung#zwei-faktor',
    )
  })
})
