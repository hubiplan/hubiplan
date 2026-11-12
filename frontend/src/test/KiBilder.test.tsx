// KI-Schnittstelle W2/W3: Hochladelink und Entwürfe für Beiträge (erfundene Daten)
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedOut = () => ({ status: 401, body: { status: 401, data: { flows: [] } } })
const link = '/api/public/website-images/k7m2q9/'

function show(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <OrgProvider>
          <App />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
}

const info = {
  organization: 'TV Beispielhausen',
  logo_url: null,
  theme: { primary: '#123e7a', on_primary: '#ffffff', accent: '#e0a526', on_accent: '#1d2421' },
  expires_at: '2026-11-13T12:00:00Z',
  remaining: 2,
}

describe('Hochladelink für Bilder', () => {
  it('lädt die gewählten Bilder einzeln hoch und meldet den Rest', async () => {
    let left = 2
    const calls = fakeApi({
      [SESSION]: loggedOut,
      [`GET ${link}`]: () => ({ status: 200, body: info }),
      [`POST ${link}`]: () => {
        left -= 1
        return { status: 201, body: { id: 10 + left, remaining: left } }
      },
    })
    show('/bilder-hochladen/k7m2q9')
    expect(await screen.findByRole('heading', { name: 'Bilder für die Webseite' })).toBeVisible()
    expect(screen.getByText(/noch 2 Bilder/)).toBeInTheDocument()
    const input = document.querySelector('input[type=file]') as HTMLInputElement
    const files = ['a.jpg', 'b.jpg', 'c.jpg'].map(
      (name) => new File(['x'], name, { type: 'image/jpeg' }),
    )
    await userEvent.setup({ applyAccept: false }).upload(input, files)
    expect(await screen.findByText(/Fertig\. Sag im Chat Bescheid/)).toBeInTheDocument()
    // Nur so viele, wie der Link noch erlaubt
    expect(calls.filter((c) => c.key === `POST ${link}`)).toHaveLength(2)
    expect(screen.getByText('a.jpg: gespeichert')).toBeInTheDocument()
    expect(screen.queryByText(/c\.jpg/)).not.toBeInTheDocument()
    expect(screen.queryByText('Bilder auswählen')).not.toBeInTheDocument()
    // Ohne Anmeldung: keine Sitzungscookies
    expect(calls.find((c) => c.key === `POST ${link}`)?.init?.credentials).toBe('omit')
  })

  it('meldet ungültige Links', async () => {
    fakeApi({
      [SESSION]: loggedOut,
      [`GET ${link}`]: () => ({ status: 404, body: { detail: 'Nicht gefunden.' } }),
    })
    show('/bilder-hochladen/k7m2q9')
    expect(await screen.findByText(/nicht \(mehr\) gültig/)).toBeInTheDocument()
  })
})
