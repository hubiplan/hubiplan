// Passkeys (WebAuthn) im Browser, ohne fremde Bibliothek (konzepte/passkey-anmeldung.md).
// allauth liefert die Optionen als JSON mit Base64url-Werten; der Browser braucht für
// Schlüssel und Zufallswerte Bytes. Die Antwort geht wieder als JSON zurück.

type Json = Record<string, unknown>

function fromB64url(value: string): ArrayBuffer {
  const base64 = value.replace(/-/g, '+').replace(/_/g, '/')
  const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4)
  const binary = atob(padded)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return bytes.buffer
}

function toB64url(value: ArrayBuffer | null | undefined): string | undefined {
  if (!value) return undefined
  const bytes = new Uint8Array(value)
  let binary = ''
  for (const b of bytes) binary += String.fromCharCode(b)
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function withIds(list: unknown): PublicKeyCredentialDescriptor[] | undefined {
  if (!Array.isArray(list)) return undefined
  return list.map((item: Json) => ({
    ...(item as object),
    id: fromB64url(String(item.id)),
  })) as PublicKeyCredentialDescriptor[]
}

/** Läuft der Browser mit Passkeys? (sicherer Kontext und WebAuthn vorhanden) */
export function passkeysSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.isSecureContext !== false &&
    typeof window.PublicKeyCredential === 'function' &&
    typeof navigator.credentials?.get === 'function'
  )
}

/** Kann das E-Mail-Feld gespeicherte Passkeys direkt vorschlagen? */
export async function autofillSupported(): Promise<boolean> {
  if (!passkeysSupported()) return false
  const check = (
    PublicKeyCredential as unknown as { isConditionalMediationAvailable?: () => Promise<boolean> }
  ).isConditionalMediationAvailable
  try {
    return typeof check === 'function' ? await check.call(PublicKeyCredential) : false
  } catch {
    return false
  }
}

function publicKey(options: Json): Json {
  return ((options?.publicKey as Json | undefined) ?? options) || {}
}

/** Passkey anlegen; ``options`` sind die ``creation_options`` von allauth. */
export async function createPasskey(options: Json): Promise<Json> {
  const pk = publicKey(options)
  const user = (pk.user as Json) ?? {}
  const credential = (await navigator.credentials.create({
    publicKey: {
      ...(pk as object),
      challenge: fromB64url(String(pk.challenge)),
      user: { ...(user as object), id: fromB64url(String(user.id)) },
      excludeCredentials: withIds(pk.excludeCredentials),
    } as PublicKeyCredentialCreationOptions,
  })) as PublicKeyCredential | null
  if (!credential) throw new DOMException('abgebrochen', 'NotAllowedError')
  const response = credential.response as AuthenticatorAttestationResponse
  const transports =
    typeof response.getTransports === 'function' ? response.getTransports() : undefined
  return {
    type: credential.type,
    id: credential.id,
    rawId: toB64url(credential.rawId),
    authenticatorAttachment: credential.authenticatorAttachment ?? undefined,
    clientExtensionResults: credential.getClientExtensionResults?.() ?? {},
    response: {
      clientDataJSON: toB64url(response.clientDataJSON),
      attestationObject: toB64url(response.attestationObject),
      ...(transports ? { transports } : {}),
    },
  }
}

/** Mit Passkey anmelden oder bestätigen; ``options`` sind die ``request_options`` von allauth.
 *  ``conditional``: still im E-Mail-Feld vorschlagen (abbrechen über ``signal``). */
export async function getPasskey(
  options: Json,
  { conditional = false, signal }: { conditional?: boolean; signal?: AbortSignal } = {},
): Promise<Json> {
  const pk = publicKey(options)
  const credential = (await navigator.credentials.get({
    publicKey: {
      ...(pk as object),
      challenge: fromB64url(String(pk.challenge)),
      allowCredentials: withIds(pk.allowCredentials),
    } as PublicKeyCredentialRequestOptions,
    ...(conditional ? { mediation: 'conditional' as CredentialMediationRequirement } : {}),
    ...(signal ? { signal } : {}),
  })) as PublicKeyCredential | null
  if (!credential) throw new DOMException('abgebrochen', 'NotAllowedError')
  const response = credential.response as AuthenticatorAssertionResponse
  return {
    type: credential.type,
    id: credential.id,
    rawId: toB64url(credential.rawId),
    authenticatorAttachment: credential.authenticatorAttachment ?? undefined,
    clientExtensionResults: credential.getClientExtensionResults?.() ?? {},
    response: {
      clientDataJSON: toB64url(response.clientDataJSON),
      authenticatorData: toB64url(response.authenticatorData),
      signature: toB64url(response.signature),
      userHandle: toB64url(response.userHandle),
    },
  }
}

/** Hat die Person die Abfrage abgebrochen (oder ist die Zeit abgelaufen)? */
export function cancelled(error: unknown): boolean {
  return (
    error instanceof DOMException &&
    (error.name === 'NotAllowedError' || error.name === 'AbortError')
  )
}
