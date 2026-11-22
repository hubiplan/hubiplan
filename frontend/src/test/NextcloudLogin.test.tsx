// Anmeldung an der Nextcloud mit dem HUBIplan-Konto (erfundene Daten).
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App.tsx'
import { leaveTo } from '../api/peering.ts'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { NextcloudLoginPage } from '../pages/NextcloudLoginPage.tsx'
import { NextcloudLogoutPage } from '../pages/NextcloudLogoutPage.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const session = () => ({
  status: 200,
  body: { status: 200, data: { user: testUser, methods: [] }, meta: { is_authenticated: true } },
})
const QUERY =
  'client_id=hp-abc&redirect_uri=https%3A%2F%2Fcloud.example.org%2Fapps%2Fuser_oidc%2Fcode&response_type=code&scope=openid&state=s1'

function renderAt(routes: Parameters<typeof fakeApi>[0]) {
  const calls = fakeApi(routes)
  render(
    <MemoryRouter initialEntries={[`/oidc/anmelden?${QUERY}`]}>
      <AuthProvider>
        <Routes>
          <Route path="*" element={<NextcloudLoginPage />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
  return calls
}

afterEach(() => vi.restoreAllMocks())

describe('Bei der Nextcloud anmelden', () => {
  it('geht ohne Rückfrage mit Code zurück', async () => {
    const go = vi.spyOn(leaveTo, 'go').mockImplementation(() => {})
    const calls = renderAt({
      'GET /_allauth/browser/v1/auth/session': session,
      'POST /api/oidc/authorize/': () => ({
        status: 200,
        body: { redirect: 'https://cloud.example.org/apps/user_oidc/code?code=x&state=s1' },
      }),
    })
    await waitFor(() =>
      expect(go).toHaveBeenCalledWith(
        'https://cloud.example.org/apps/user_oidc/code?code=x&state=s1',
      ),
    )
    const post = calls.find((c) => c.key === 'POST /api/oidc/authorize/')
    expect(JSON.parse(String(post?.init?.body))).toMatchObject({
      client_id: 'hp-abc',
      redirect_uri: 'https://cloud.example.org/apps/user_oidc/code',
      state: 's1',
    })
  })

  it('erklärt, warum es nicht geht', async () => {
    const go = vi.spyOn(leaveTo, 'go').mockImplementation(() => {})
    renderAt({
      'GET /_allauth/browser/v1/auth/session': session,
      'POST /api/oidc/authorize/': () => ({
        status: 400,
        body: {
          detail: 'Dein Konto hat bei Verein A keinen Zugang zu „Nextcloud“.',
          redirect: '',
          back: 'https://cloud.example.org',
        },
      }),
    })
    expect(await screen.findByText(/keinen Zugang/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Zurück zur Nextcloud' })).toHaveAttribute(
      'href',
      'https://cloud.example.org',
    )
    expect(go).not.toHaveBeenCalled()
  })
})

describe('Nach dem Abmelden von der Nextcloud', () => {
  it('meldet erst nach einem Klick wieder an', async () => {
    const go = vi.spyOn(leaveTo, 'go').mockImplementation(() => {})
    let n = 0
    const calls = renderAt({
      'GET /_allauth/browser/v1/auth/session': session,
      'POST /api/oidc/authorize/': () =>
        ++n === 1
          ? { status: 409, body: { confirm: true, name: 'Vereinscloud' } }
          : {
              status: 200,
              body: { redirect: 'https://cloud.example.org/apps/user_oidc/code?code=y&state=s1' },
            },
    })
    expect(await screen.findByText(/von „Vereinscloud“ abgemeldet/)).toBeInTheDocument()
    expect(go).not.toHaveBeenCalled()
    await userEvent
      .setup()
      .click(screen.getByRole('button', { name: 'Bei der Nextcloud anmelden' }))
    await waitFor(() =>
      expect(go).toHaveBeenCalledWith(
        'https://cloud.example.org/apps/user_oidc/code?code=y&state=s1',
      ),
    )
    const posts = calls.filter((c) => c.key === 'POST /api/oidc/authorize/')
    expect(JSON.parse(String(posts[0]?.init?.body))).not.toHaveProperty('confirm')
    expect(JSON.parse(String(posts[1]?.init?.body))).toMatchObject({ confirm: '1', state: 's1' })
  })

  function renderLogout(routes: Parameters<typeof fakeApi>[0]) {
    const calls = fakeApi(routes)
    render(
      <MemoryRouter
        initialEntries={[
          '/oidc/abmelden?client_id=hp-abc&post_logout_redirect_uri=https://cloud.example.org/',
        ]}
      >
        <AuthProvider>
          <Routes>
            <Route path="*" element={<NextcloudLogoutPage />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    )
    return calls
  }

  it('fragt, ob man auch bei HUBIplan abmelden möchte', async () => {
    const calls = renderLogout({
      'GET /_allauth/browser/v1/auth/session': session,
      'POST /api/oidc/end-session/': () => ({
        status: 200,
        body: { name: 'Vereinscloud', back: 'https://cloud.example.org/', logged_in: true },
      }),
      'DELETE /_allauth/browser/v1/auth/session': () => ({
        status: 401,
        body: { status: 401, data: {}, meta: { is_authenticated: false } },
      }),
    })
    expect(await screen.findByText(/von „Vereinscloud“ abgemeldet/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Zurück zur Nextcloud' })).toHaveAttribute(
      'href',
      'https://cloud.example.org/',
    )
    const post = calls.find((c) => c.key === 'POST /api/oidc/end-session/')
    expect(JSON.parse(String(post?.init?.body))).toEqual({
      client_id: 'hp-abc',
      post_logout_redirect_uri: 'https://cloud.example.org/',
    })
    await userEvent
      .setup()
      .click(screen.getByRole('button', { name: 'Auch bei HUBIplan abmelden' }))
    expect(
      await screen.findByText('Du bist jetzt auch bei HUBIplan abgemeldet.'),
    ).toBeInTheDocument()
    expect(calls.some((c) => c.key === 'DELETE /_allauth/browser/v1/auth/session')).toBe(true)
  })

  it('zeigt ohne HUBIplan-Sitzung nur den Weg zurück', async () => {
    renderLogout({
      'GET /_allauth/browser/v1/auth/session': () => ({
        status: 401,
        body: { status: 401, data: {}, meta: { is_authenticated: false } },
      }),
      'POST /api/oidc/end-session/': () => ({
        status: 200,
        body: { name: 'Vereinscloud', back: 'https://cloud.example.org/', logged_in: false },
      }),
    })
    expect(await screen.findByText(/von „Vereinscloud“ abgemeldet/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Auch bei HUBIplan abmelden' })).toBeNull()
    expect(screen.getByRole('link', { name: 'Zurück zur Nextcloud' })).toBeInTheDocument()
  })
})

describe('Einstellungen › Nextcloud', () => {
  it('trägt eine Nextcloud ein und zeigt das Geheimnis einmal', async () => {
    const org = testOrg({ permissions: ['roles.manage'] })
    const created = {
      id: 3,
      name: 'Nextcloud',
      base_url: 'https://cloud.example.org',
      client_id: 'hp-abc',
      audience: 'board',
      require_mfa: false,
      groups_board: true,
      groups_roles: true,
      groups_units: true,
      groups_members: true,
      role_groups: {},
      role_choices: [
        { id: 11, name: '1. Kassierer', unit: '', is_board: true },
        { id: 12, name: 'Zugführer', unit: 'Jäger', is_board: false },
      ],
      is_active: true,
      created_at: '2026-11-01T20:00:00Z',
      last_used_at: null,
      redirect_uri: 'https://cloud.example.org/apps/user_oidc/code',
      discovery_url: 'https://verein.example.org/api/oidc/.well-known/openid-configuration',
      client_secret: 'geheim-123',
    }
    const calls = fakeApi({
      'GET /_allauth/browser/v1/auth/session': session,
      'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
      'GET /api/orgs/7/nextcloud/': () => ({ status: 200, body: [] }),
      'POST /api/orgs/7/nextcloud/': () => ({ status: 201, body: created }),
    })
    render(
      <MemoryRouter initialEntries={['/einstellungen/nextcloud']}>
        <AuthProvider>
          <OrgProvider>
            <App />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>,
    )
    const user = userEvent.setup()
    await user.type(
      await screen.findByLabelText('Adresse der Nextcloud'),
      'https://cloud.example.org',
    )
    await user.click(screen.getByRole('button', { name: 'Eintragen' }))
    expect(await screen.findByText('geheim-123')).toBeInTheDocument()
    expect(screen.getByText('hp-abc')).toBeInTheDocument()
    // Gruppen je Rolle: eine Zeile je Rolle, Ämter mit Untereinheit
    expect(screen.getByText('Gruppen für einzelne Rollen anpassen')).toBeInTheDocument()
    expect(screen.getByLabelText('Gruppen für 1. Kassierer')).toHaveValue('')
    expect(screen.getByLabelText('Gruppen für Zugführer (Jäger)')).toBeInTheDocument()
    const post = calls.find((c) => c.key === 'POST /api/orgs/7/nextcloud/')
    expect(JSON.parse(String(post?.init?.body))).toEqual({
      name: 'Nextcloud',
      base_url: 'https://cloud.example.org',
    })
  })
})
