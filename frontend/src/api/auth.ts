import { t } from '../i18n/index.ts'
// Anbindung an die allauth-Headless-API (Anmeldung, 2FA, Abmeldung).
// Doku der Endpunkte: http://localhost:8000/_allauth/openapi.html
import { ApiError, request } from './client.ts'

const BASE = '/_allauth/browser/v1'

export interface User {
  id: number
  email: string
  display: string
  // Noch mit dem ausgegebenen Startpasswort angemeldet: erst eigenes Passwort festlegen
  must_change_password?: boolean
  // Pflicht-2FA: bis dahin einrichten, danach ruhen Rollenverwaltung, Exporte und Kasse
  mfa_required_by?: string
  mfa_overdue?: boolean
  // Plattform-Verwaltung: ohne 2FA ruhen ihre Rechte sofort (Gesamtaudit 10.11.)
  mfa_platform?: boolean
  // Sprache des Kontos (konzepte/englisch.md)
  language?: string
}

interface Flow {
  id: string
  is_pending?: boolean
  // Beim zweiten Faktor: womit bestätigt werden kann (totp, recovery_codes, webauthn)
  types?: string[]
}

interface AuthBody {
  status: number
  data?: {
    user?: User
    flows?: Flow[]
    request_options?: Record<string, unknown>
    creation_options?: Record<string, unknown>
  }
  meta?: { is_authenticated?: boolean }
  errors?: { message: string; param?: string }[]
}

export type LoginResult =
  | { kind: 'ok'; user: User }
  | { kind: 'mfa'; passkey: boolean }
  | { kind: 'error'; message: string }

function errorMessage(body: AuthBody, fallback: string): string {
  return body.errors?.map((e) => e.message).join(' ') || fallback
}

function pendingFlow(body: AuthBody): Flow | undefined {
  return body.data?.flows?.find((f) => f.is_pending)
}

function toLoginResult(status: number, body: AuthBody, fallback: string): LoginResult {
  if (status === 200 && body.data?.user) return { kind: 'ok', user: body.data.user }
  const flow = status === 401 ? pendingFlow(body) : undefined
  if (flow?.id === 'mfa_authenticate')
    return { kind: 'mfa', passkey: (flow.types ?? []).includes('webauthn') }
  if (status === 429)
    return {
      kind: 'error',
      get message() {
        return t('Zu viele Versuche. Bitte später erneut.')
      },
    }
  return { kind: 'error', message: errorMessage(body, fallback) }
}

export async function getSession(): Promise<User | null> {
  const { status, body } = await request<AuthBody>('GET', `${BASE}/auth/session`)
  if (status === 200 && body.data?.user) return body.data.user
  if (status === 401 || status === 403) return null
  // Serverfehler oder ein unbekannter Vertrag beweisen keine Abmeldung. Insbesondere
  // dürfen sie keine noch nicht übertragenen Offline-Eingaben vernichten.
  throw new ApiError(status === 200 ? 502 : status, body)
}

export async function login(email: string, password: string): Promise<LoginResult> {
  const { status, body } = await request<AuthBody>('POST', `${BASE}/auth/login`, {
    email,
    password,
  })
  return toLoginResult(status, body, t('Anmeldung fehlgeschlagen.'))
}

export async function authenticateMfa(code: string): Promise<LoginResult> {
  const { status, body } = await request<AuthBody>('POST', `${BASE}/auth/2fa/authenticate`, {
    code,
  })
  return toLoginResult(status, body, t('Der Code ist ungültig.'))
}

export async function logout(): Promise<void> {
  const { status, body } = await request('DELETE', `${BASE}/auth/session`)
  // allauth antwortet nach erfolgreicher Abmeldung mit 401 (keine Sitzung mehr)
  if (status !== 401 && status !== 200) throw new ApiError(status, body)
}

// --- 2FA verwalten ---

export type TotpState = { active: true } | { active: false; secret: string; totpUrl: string }

export async function getTotp(): Promise<TotpState> {
  const { status, body } = await request<{ meta?: { secret: string; totp_url: string } }>(
    'GET',
    `${BASE}/account/authenticators/totp`,
  )
  if (status === 200) return { active: true }
  // 404 heißt „noch nicht eingerichtet“; alles andere ist ein Fehler, kein „inaktiv“
  if (status !== 404) throw new ApiError(status, body)
  return { active: false, secret: body.meta?.secret ?? '', totpUrl: body.meta?.totp_url ?? '' }
}

export type ChangeResult =
  { kind: 'ok' } | { kind: 'reauthenticate' } | { kind: 'error'; message: string }

async function securityChange(
  method: 'POST' | 'DELETE',
  url: string,
  data?: unknown,
): Promise<ChangeResult> {
  const { status, body } = await request<AuthBody>(method, url, data)
  if (status === 200) return { kind: 'ok' }
  // Für Sicherheitsänderungen verlangt allauth eine frische Passwortbestätigung.
  if (status === 401) return { kind: 'reauthenticate' }
  return { kind: 'error', message: errorMessage(body, t('Das hat nicht geklappt.')) }
}

export function activateTotp(code: string): Promise<ChangeResult> {
  return securityChange('POST', `${BASE}/account/authenticators/totp`, { code })
}

export function deactivateTotp(): Promise<ChangeResult> {
  return securityChange('DELETE', `${BASE}/account/authenticators/totp`)
}

export async function reauthenticate(password: string): Promise<ChangeResult> {
  const { status, body } = await request<AuthBody>('POST', `${BASE}/auth/reauthenticate`, {
    password,
  })
  if (status === 200) return { kind: 'ok' }
  return { kind: 'error', message: errorMessage(body, t('Passwort ist falsch.')) }
}

export async function getRecoveryCodes(): Promise<string[]> {
  const { status, body } = await request<{ data?: { unused_codes?: string[] } }>(
    'GET',
    `${BASE}/account/authenticators/recovery-codes`,
  )
  // Fehler nicht als „keine Codes“ ausgeben (Gesamtaudit 30.10., WEB-F01)
  if (status !== 200) throw new ApiError(status, body)
  return body.data?.unused_codes ?? []
}

// --- Passkeys (konzepte/passkey-anmeldung.md) ---

type Options = Record<string, unknown>

async function options(url: string, key: 'request_options' | 'creation_options'): Promise<Options> {
  const { status, body } = await request<AuthBody>('GET', url)
  const value = body.data?.[key]
  if (status !== 200 || !value) throw new ApiError(status, body)
  return value
}

/** Optionen für „Mit Passkey anmelden“ (auch für den Vorschlag im E-Mail-Feld). */
export function passkeyLoginOptions(): Promise<Options> {
  return options(`${BASE}/auth/webauthn/login`, 'request_options')
}

export async function passkeyLogin(credential: Options): Promise<LoginResult> {
  const { status, body } = await request<AuthBody>('POST', `${BASE}/auth/webauthn/login`, {
    credential,
  })
  return toLoginResult(status, body, t('Die Anmeldung mit Passkey hat nicht geklappt.'))
}

/** Passkey als zweiter Faktor nach dem Passwort. */
export function passkeyMfaOptions(): Promise<Options> {
  return options(`${BASE}/auth/webauthn/authenticate`, 'request_options')
}

export async function passkeyMfa(credential: Options): Promise<LoginResult> {
  const { status, body } = await request<AuthBody>('POST', `${BASE}/auth/webauthn/authenticate`, {
    credential,
  })
  return toLoginResult(status, body, t('Die Bestätigung mit Passkey hat nicht geklappt.'))
}

/** Bestätigen mit Passkey (heikle Aktionen, Verbund, Einrichten weiterer Passkeys). */
export function passkeyReauthOptions(): Promise<Options> {
  return options(`${BASE}/auth/webauthn/reauthenticate`, 'request_options')
}

export async function passkeyReauth(credential: Options): Promise<ChangeResult> {
  const { status, body } = await request<AuthBody>('POST', `${BASE}/auth/webauthn/reauthenticate`, {
    credential,
  })
  if (status === 200) return { kind: 'ok' }
  return {
    kind: 'error',
    message: errorMessage(body, t('Die Bestätigung mit Passkey hat nicht geklappt.')),
  }
}

export interface Passkey {
  id: number
  name: string
  host: string
  here: boolean
  passwordless: boolean
  created_at: string
  last_used_at: string | null
}

export interface PasskeyList {
  enabled: boolean
  host: string
  passkeys: Passkey[]
}

export async function listPasskeys(): Promise<PasskeyList> {
  const { status, body } = await request<PasskeyList>('GET', '/api/me/passkeys/')
  if (status !== 200) throw new ApiError(status, body)
  return body
}

/** Optionen zum Einrichten; ``reauthenticate``, wenn allauth erst eine Bestätigung will. */
export async function passkeyCreationOptions(): Promise<
  { kind: 'ok'; options: Options } | { kind: 'reauthenticate' } | { kind: 'error'; message: string }
> {
  const { status, body } = await request<AuthBody>(
    'GET',
    `${BASE}/account/authenticators/webauthn?passwordless`,
  )
  if (status === 200 && body.data?.creation_options)
    return { kind: 'ok', options: body.data.creation_options }
  if (status === 401) return { kind: 'reauthenticate' }
  return { kind: 'error', message: errorMessage(body, t('Das hat nicht geklappt.')) }
}

export async function addPasskey(
  name: string,
  credential: Options,
): Promise<ChangeResult & { recoveryCodes?: boolean }> {
  const { status, body } = await request<
    AuthBody & { meta?: { recovery_codes_generated?: boolean } }
  >('POST', `${BASE}/account/authenticators/webauthn`, { name, credential })
  if (status === 200)
    return { kind: 'ok', recoveryCodes: Boolean(body.meta?.recovery_codes_generated) }
  if (status === 401) return { kind: 'reauthenticate' }
  return {
    kind: 'error',
    message: errorMessage(body, t('Der Passkey konnte nicht gespeichert werden.')),
  }
}

export function renamePasskey(id: number, name: string): Promise<ChangeResult> {
  return securityChangePut(`${BASE}/account/authenticators/webauthn`, { id, name })
}

export function deletePasskey(id: number): Promise<ChangeResult> {
  return securityChange('DELETE', `${BASE}/account/authenticators/webauthn`, {
    authenticators: [id],
  })
}

async function securityChangePut(url: string, data: unknown): Promise<ChangeResult> {
  const { status, body } = await request<AuthBody>('PUT', url, data)
  if (status === 200) return { kind: 'ok' }
  if (status === 401) return { kind: 'reauthenticate' }
  return { kind: 'error', message: errorMessage(body, t('Das hat nicht geklappt.')) }
}
