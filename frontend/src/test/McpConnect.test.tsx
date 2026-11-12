// KI-Assistent mit dem HUBIplan-Konto verbinden (erfundene Daten).
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { leaveTo } from '../api/peering.ts'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { McpConnectPage } from '../pages/McpConnectPage.tsx'
import { McpConnectionsCard } from '../pages/settings/McpConnectionsCard.tsx'
import { fakeApi, testUser } from './fakeApi.ts'

const session = () => ({
  status: 200,
  body: { status: 200, data: { user: testUser, methods: [] }, meta: { is_authenticated: true } },
})
const QUERY =
  'client_id=hpmc_abc&redirect_uri=https%3A%2F%2Fassistent.example.org%2Fcb&response_type=code&code_challenge=x&code_challenge_method=S256&state=s1'
const DESCRIBE = `GET /api/mcp/oauth/authorize/?${QUERY}`
const REQUEST = {
  client: 'Testassistent',
  redirect_host: 'assistent.example.org',
  redirect_kind: 'bekannt' as const,
  connected_before: false,
  scopes: [{ scope: 'webseite.lesen', label: 'Webseite lesen' }],
  units: [{ id: 7, name: 'Verein A' }],
  problem: '',
}

function renderAt(routes: Parameters<typeof fakeApi>[0]) {
  const calls = fakeApi(routes)
  render(
    <MemoryRouter initialEntries={[`/ki/verbinden?${QUERY}`]}>
      <AuthProvider>
        <Routes>
          <Route path="*" element={<McpConnectPage />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
  return calls
}

afterEach(() => vi.restoreAllMocks())

describe('KI-Assistent verbinden', () => {
  it('zeigt Anfrage und Rechte, erlaubt für die Einheit', async () => {
    const go = vi.spyOn(leaveTo, 'go').mockImplementation(() => {})
    const calls = renderAt({
      'GET /_allauth/browser/v1/auth/session': session,
      [DESCRIBE]: () => ({ status: 200, body: REQUEST }),
      'POST /api/mcp/oauth/authorize/': () => ({
        status: 200,
        body: { redirect: 'https://assistent.example.org/cb?code=c&state=s1' },
      }),
    })
    expect(await screen.findByText('assistent.example.org')).toBeInTheDocument()
    expect(screen.getByText(/nennt sich „Testassistent“/)).toBeInTheDocument()
    expect(screen.queryByText(/keinem bekannten KI-Assistenten/)).not.toBeInTheDocument()
    expect(screen.getByText('Webseite lesen')).toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Erlauben' }))
    await waitFor(() =>
      expect(go).toHaveBeenCalledWith('https://assistent.example.org/cb?code=c&state=s1'),
    )
    const post = calls.find((c) => c.key === 'POST /api/mcp/oauth/authorize/')
    expect(JSON.parse(String(post?.init?.body))).toMatchObject({
      organization: 7,
      params: { client_id: 'hpmc_abc', state: 's1' },
    })
  })

  it('warnt bei unbekannter Adresse, nicht nach früherer Verbindung', async () => {
    renderAt({
      'GET /_allauth/browser/v1/auth/session': session,
      [DESCRIBE]: () => ({ status: 200, body: { ...REQUEST, redirect_kind: 'web' } }),
    })
    expect(await screen.findByText(/keinem bekannten KI-Assistenten/)).toBeInTheDocument()
  })

  it('ohne zweiten Faktor kein Erlauben', async () => {
    renderAt({
      'GET /_allauth/browser/v1/auth/session': session,
      [DESCRIBE]: () => ({
        status: 200,
        body: { ...REQUEST, problem: 'Für KI-Assistenten ist die Zwei-Faktor-Anmeldung nötig.' },
      }),
    })
    expect(await screen.findByText(/Zwei-Faktor-Anmeldung nötig/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Erlauben' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ablehnen' })).toBeInTheDocument()
  })
})

describe('Mein Konto › KI-Assistenten', () => {
  it('listet Verbindungen und trennt sie', async () => {
    let list = [
      {
        id: 4,
        client: 'Testassistent',
        organization: 'Verein A',
        scopes: [],
        created_at: '2026-11-11T08:00:00Z',
        last_used_at: '2026-11-11T09:00:00Z',
        expires_at: '2026-12-11T08:00:00Z',
      },
    ]
    const calls = fakeApi({
      'GET /api/me/mcp/': () => ({
        status: 200,
        body: {
          enabled: true,
          address: 'https://verein.example.org/api/mcp/verein/',
          connections: list,
        },
      }),
      'DELETE /api/me/mcp/4/': () => {
        list = []
        return { status: 204 }
      },
    })
    render(<McpConnectionsCard />)
    expect(
      await screen.findByText('https://verein.example.org/api/mcp/verein/'),
    ).toBeInTheDocument()
    expect(screen.getByText('Testassistent')).toBeInTheDocument()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Trennen' }))
    await user.click(await screen.findByRole('button', { name: /OK|Ja|Bestätigen/ }))
    expect(await screen.findByText('Noch kein Assistent verbunden.')).toBeInTheDocument()
    expect(calls.some((c) => c.key === 'DELETE /api/me/mcp/4/')).toBe(true)
  })
})
