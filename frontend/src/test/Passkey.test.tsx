// Anmeldung mit Passkey, Stufe P1 (konzepte/passkey-anmeldung.md). Erfundene Daten; der
// Browser-Teil (navigator.credentials) ist nachgebildet.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, setStepUpHandler } from '../api/client.ts'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { createPasskey, getPasskey } from '../auth/webauthn.ts'
import { installStepUp } from '../components/stepUp.ts'
import { LoginPage } from '../pages/LoginPage.tsx'
import { PasskeyCard } from '../pages/settings/PasskeyCard.tsx'
import { fakeApi, testUser } from './fakeApi.ts'

const anonymous = () => ({ status: 401, body: { status: 401, data: { flows: [] }, meta: {} } })
const session = () => ({
  status: 200,
  body: { status: 200, data: { user: testUser, methods: [] }, meta: { is_authenticated: true } },
})
const loggedIn = () => ({
  status: 200,
  body: { status: 200, data: { user: testUser }, meta: { is_authenticated: true } },
})

const bytes = (...values: number[]) => new Uint8Array(values).buffer
const requestOptions = {
  publicKey: { challenge: 'AQID', rpId: 'verein.example', allowCredentials: [], timeout: 60000 },
}

function fakeBrowser() {
  const assertion = {
    type: 'public-key',
    id: 'Cg',
    rawId: bytes(10),
    authenticatorAttachment: 'platform',
    getClientExtensionResults: () => ({}),
    response: {
      clientDataJSON: bytes(1, 2),
      authenticatorData: bytes(3),
      signature: bytes(4, 5),
      userHandle: bytes(49),
    },
  }
  const attestation = {
    type: 'public-key',
    id: 'Cg',
    rawId: bytes(10),
    authenticatorAttachment: 'platform',
    getClientExtensionResults: () => ({}),
    response: {
      clientDataJSON: bytes(1, 2),
      attestationObject: bytes(6, 7, 8),
      getTransports: () => ['internal'],
    },
  }
  const get = vi.fn(async (_options: CredentialRequestOptions) => assertion)
  const create = vi.fn(async (_options: CredentialCreationOptions) => attestation)
  vi.stubGlobal('PublicKeyCredential', function PublicKeyCredential() {})
  Object.defineProperty(navigator, 'credentials', {
    configurable: true,
    value: { get, create },
  })
  return { get, create }
}

function renderAt(routes: Parameters<typeof fakeApi>[0], ui: React.ReactNode) {
  const calls = fakeApi(routes)
  render(
    <MemoryRouter initialEntries={['/anmelden']}>
      <AuthProvider>
        <Routes>
          <Route path="*" element={ui} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
  return calls
}

const bodyOf = (calls: ReturnType<typeof fakeApi>, key: string) =>
  JSON.parse(String(calls.find((c) => c.key === key)?.init?.body))

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  Reflect.deleteProperty(navigator, 'credentials')
})

describe('Passkey-Hilfen', () => {
  it('wandelt Base64url für den Browser und zurück', async () => {
    const { get, create } = fakeBrowser()
    const credential = await getPasskey(requestOptions)
    const passed = get.mock.calls[0][0].publicKey!
    expect(new Uint8Array(passed.challenge as ArrayBuffer)).toEqual(new Uint8Array([1, 2, 3]))
    expect(credential).toMatchObject({
      rawId: 'Cg',
      response: {
        clientDataJSON: 'AQI',
        authenticatorData: 'Aw',
        signature: 'BAU',
        userHandle: 'MQ',
      },
    })

    const created = await createPasskey({
      publicKey: {
        challenge: 'AQID',
        rp: { id: 'verein.example', name: 'Musterstadt' },
        user: { id: 'MQ', name: 'karla@example.org', displayName: 'Karla' },
        pubKeyCredParams: [{ type: 'public-key', alg: -7 }],
        excludeCredentials: [{ type: 'public-key', id: 'Cg' }],
      },
    })
    const options = create.mock.calls[0][0].publicKey!
    expect(new Uint8Array(options.user.id as ArrayBuffer)).toEqual(new Uint8Array([49]))
    expect(new Uint8Array(options.excludeCredentials![0].id as ArrayBuffer)).toEqual(
      new Uint8Array([10]),
    )
    expect(created).toMatchObject({
      rawId: 'Cg',
      response: { attestationObject: 'BgcI', transports: ['internal'] },
    })
  })
})

describe('Anmeldeseite', () => {
  it('meldet mit Passkey ohne Passwort an', async () => {
    fakeBrowser()
    const calls = renderAt(
      {
        'GET /_allauth/browser/v1/auth/session': anonymous,
        'GET /_allauth/browser/v1/auth/webauthn/login': () => ({
          status: 200,
          body: { status: 200, data: { request_options: requestOptions } },
        }),
        'POST /_allauth/browser/v1/auth/webauthn/login': loggedIn,
      },
      <LoginPage />,
    )
    await userEvent
      .setup()
      .click(await screen.findByRole('button', { name: 'Mit Passkey anmelden' }))
    await waitFor(() =>
      expect(calls.some((c) => c.key === 'POST /_allauth/browser/v1/auth/webauthn/login')).toBe(
        true,
      ),
    )
    expect(bodyOf(calls, 'POST /_allauth/browser/v1/auth/webauthn/login').credential.rawId).toBe(
      'Cg',
    )
  })

  it('bietet den Passkey als zweiten Faktor an', async () => {
    fakeBrowser()
    const calls = renderAt(
      {
        'GET /_allauth/browser/v1/auth/session': anonymous,
        'POST /_allauth/browser/v1/auth/login': () => ({
          status: 401,
          body: {
            status: 401,
            data: {
              flows: [
                { id: 'mfa_authenticate', is_pending: true, types: ['webauthn', 'recovery_codes'] },
              ],
            },
          },
        }),
        'GET /_allauth/browser/v1/auth/webauthn/authenticate': () => ({
          status: 200,
          body: { status: 200, data: { request_options: requestOptions } },
        }),
        'POST /_allauth/browser/v1/auth/webauthn/authenticate': loggedIn,
      },
      <LoginPage />,
    )
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('E-Mail-Adresse'), 'karla@example.org')
    await user.type(screen.getByLabelText('Passwort'), 'geheim-und-lang')
    await user.click(screen.getByRole('button', { name: 'Anmelden' }))
    await user.click(await screen.findByRole('button', { name: 'Mit Passkey bestätigen' }))
    await waitFor(() =>
      expect(
        calls.some((c) => c.key === 'POST /_allauth/browser/v1/auth/webauthn/authenticate'),
      ).toBe(true),
    )
  })

  it('ohne Passkey-Unterstützung bleibt alles wie bisher', async () => {
    renderAt({ 'GET /_allauth/browser/v1/auth/session': anonymous }, <LoginPage />)
    expect(await screen.findByRole('button', { name: 'Anmelden' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Mit Passkey anmelden' })).toBeNull()
  })
})

describe('Mein Konto › Passkeys', () => {
  it('zeigt, für welche Adresse ein Passkey gilt, und richtet einen neuen ein', async () => {
    fakeBrowser()
    let added = false
    const calls = renderAt(
      {
        'GET /_allauth/browser/v1/auth/session': session,
        'GET /api/me/passkeys/': () => ({
          status: 200,
          body: {
            enabled: true,
            host: 'verein.example',
            passkeys: [
              {
                id: 3,
                name: 'Handy',
                host: 'verband.example',
                here: false,
                passwordless: true,
                created_at: '2026-11-01T10:00:00Z',
                last_used_at: null,
              },
            ],
          },
        }),
        'GET /_allauth/browser/v1/account/authenticators/webauthn?passwordless': () => ({
          status: 200,
          body: {
            status: 200,
            data: {
              creation_options: {
                publicKey: {
                  challenge: 'AQID',
                  rp: { id: 'verein.example', name: 'Musterstadt' },
                  user: { id: 'MQ', name: 'karla@example.org', displayName: 'Karla' },
                  pubKeyCredParams: [{ type: 'public-key', alg: -7 }],
                },
              },
            },
          },
        }),
        'POST /_allauth/browser/v1/account/authenticators/webauthn': () => {
          added = true
          return { status: 200, body: { status: 200, data: {}, meta: {} } }
        },
      },
      <PasskeyCard />,
    )
    expect(await screen.findByText('Handy')).toBeInTheDocument()
    expect(screen.getByText('gilt für verband.example')).toBeInTheDocument()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/Name \(optional/), 'Laptop')
    await user.click(screen.getByRole('button', { name: 'Passkey hinzufügen' }))
    expect(
      await screen.findByText('Der Passkey ist eingerichtet. Du kannst dich jetzt damit anmelden.'),
    ).toBeInTheDocument()
    expect(added).toBe(true)
    expect(
      bodyOf(calls, 'POST /_allauth/browser/v1/account/authenticators/webauthn'),
    ).toMatchObject({
      name: 'Laptop',
      credential: { rawId: 'Cg' },
    })
  })

  it('ist ausgeblendet, wenn Passkeys abgeschaltet sind', async () => {
    renderAt(
      {
        'GET /_allauth/browser/v1/auth/session': session,
        'GET /api/me/passkeys/': () => ({
          status: 200,
          body: { enabled: false, host: 'verein.example', passkeys: [] },
        }),
      },
      <PasskeyCard />,
    )
    await waitFor(() => expect(screen.queryByText('Wird geladen …')).toBeNull())
    expect(screen.queryByRole('heading', { name: 'Passkeys' })).toBeNull()
  })
})

describe('Heikle Aktionen', () => {
  beforeEach(() => installStepUp())
  afterEach(() => setStepUpHandler(null))

  it('bestätigt mit Passkey und sendet die Anfrage erneut', async () => {
    fakeBrowser()
    let confirmed = false
    const calls = fakeApi({
      'GET /_allauth/browser/v1/auth/webauthn/reauthenticate': () => ({
        status: 200,
        body: { status: 200, data: { request_options: requestOptions } },
      }),
      'POST /_allauth/browser/v1/auth/webauthn/reauthenticate': () => {
        confirmed = true
        return loggedIn()
      },
      'POST /api/orgs/1/export/': () =>
        confirmed
          ? { status: 201, body: { id: 7 } }
          : { status: 403, body: { detail: 'Bitte Passkey.', step_up: 'code', passkey: true } },
    })
    const result = api.post<{ id: number }>('/api/orgs/1/export/', { kind: 'full' })
    const dialog = await screen.findByRole('alertdialog')
    await userEvent
      .setup()
      .click(within(dialog).getByRole('button', { name: 'Mit Passkey bestätigen' }))
    expect(await result).toEqual({ id: 7 })
    expect(calls.filter((c) => c.key === 'POST /api/orgs/1/export/')).toHaveLength(2)
  })
})
