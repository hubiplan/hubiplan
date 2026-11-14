// HUBIplan-App auf dem iPhone über den eingebetteten Browser verbinden (erfundene Daten).
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { leaveTo } from '../api/peering.ts'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { AppLoginPage } from '../pages/AppLoginPage.tsx'
import { fakeApi, testUser } from './fakeApi.ts'

const session = () => ({
  status: 200,
  body: { status: 200, data: { user: testUser, methods: [] }, meta: { is_authenticated: true } },
})

function renderPage(routes: Parameters<typeof fakeApi>[0]) {
  const calls = fakeApi(routes)
  render(
    <MemoryRouter initialEntries={['/app/anmelden']}>
      <AuthProvider>
        <Routes>
          <Route path="*" element={<AppLoginPage />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
  return calls
}

afterEach(() => vi.restoreAllMocks())

describe('App im Browser verbinden', () => {
  it('erzeugt den Code erst nach dem Tippen und gibt ihn an die App', async () => {
    const go = vi.spyOn(leaveTo, 'go').mockImplementation(() => {})
    const calls = renderPage({
      'GET /_allauth/browser/v1/auth/session': session,
      'POST /api/app/v1/pairing/': () => ({
        status: 201,
        body: {
          id: 3,
          url: 'https://verein.example.de/app/verbinden#code=Ab-_9',
          expires_at: '2026-11-15T10:00:00Z',
        },
      }),
    })
    const button = await screen.findByRole('button', { name: 'Verbinden' })
    expect(calls.some((c) => c.key === 'POST /api/app/v1/pairing/')).toBe(false)
    await userEvent.setup().click(button)
    await waitFor(() =>
      expect(go).toHaveBeenCalledWith(
        'hubiplan://verbinden?server=https%3A%2F%2Fverein.example.de&code=Ab-_9',
      ),
    )
  })

  it('zeigt einen Fehler ohne Mitgliederbereich', async () => {
    const go = vi.spyOn(leaveTo, 'go').mockImplementation(() => {})
    renderPage({
      'GET /_allauth/browser/v1/auth/session': session,
      'POST /api/app/v1/pairing/': () => ({
        status: 400,
        body: { detail: 'Für dieses Konto ist kein Mitgliederbereich freigeschaltet.' },
      }),
    })
    await userEvent.setup().click(await screen.findByRole('button', { name: 'Verbinden' }))
    expect(await screen.findByText(/kein Mitgliederbereich/)).toBeInTheDocument()
    expect(go).not.toHaveBeenCalled()
  })
})
