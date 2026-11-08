import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedIn = () => ({ status: 200, body: { status: 200, data: { user: testUser } } })
const F = '/api/orgs/7/finance'

const report = {
  year: 2026,
  rate: '4.90',
  threshold: '450.00',
  total: '1000.00',
  levy: '49.00',
  over_threshold: true,
  due: '2027-03-31',
  recipients: [{ name: 'Blaskapelle Musterdorf', total: '1000.00', count: 2 }],
  bookings: [],
}

function renderApp(path: string) {
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

describe('Künstlersozialabgabe', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-11-07T12:00:00'))
  })
  afterEach(() => vi.useRealTimers())

  it('zeigt Summe, Abgabe und Empfänger des Jahres', async () => {
    const org = testOrg({
      modules: ['members', 'finance', 'tax'],
      permissions: ['finance.view', 'finance.edit'],
      parent_name: null,
    })
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
      [`GET ${F}/artist-fees/?jahr=2026`]: () => ({ status: 200, body: report }),
    })
    renderApp('/finanzen/steuern/kuenstlersozialabgabe')
    expect(await screen.findByText('Blaskapelle Musterdorf')).toBeInTheDocument()
    expect(screen.getByText('Abgabe (4,9 %)')).toBeInTheDocument()
    expect(screen.getByText(/49,00/)).toBeInTheDocument()
    expect(
      screen.getByText(/Meldung an die Künstlersozialkasse bis 31\.0?3\.2027/),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Excel' })).toHaveAttribute(
      'href',
      expect.stringContaining('/finance/artist-fees/?jahr=2026&als=xlsx'),
    )
  })
})
