// API-Zugänge für andere Programme (Backend: App partnerapi, docs/api.md).
import { api } from './client.ts'

export interface ApiScope {
  scope: string
  label: string
  description: string
  /** Auch für einen Zugang, der auf eine Untereinheit begrenzt ist */
  unit_ok: boolean
  /** Bereich, der mitgewählt sein muss (sonst leer) */
  needs: string
  /** Gibt Personendaten heraus: nur mit Empfänger und bestätigter Rechtsgrundlage */
  personal: boolean
  /** Schreibt: legt an oder ändert */
  write: boolean
}

export type LegalBasis = '' | 'processing' | 'transfer'
export type MemberFieldGroup = 'contact' | 'membership' | 'units'

export interface ApiRead {
  at: string
  scope: string
  count: number
}

export interface ApiAccess {
  id: number
  name: string
  purpose: string
  recipient: string
  scopes: string[]
  unit: { id: number; name: string } | null
  /** Letzte vier Zeichen des Schlüssels */
  key_hint: string
  key_created_at: string
  /** Bis dahin gilt nach einem Wechsel auch der vorige Schlüssel */
  previous_until: string | null
  expires_at: string
  allowed_networks: string[]
  embeddable: boolean
  state: 'active' | 'idle' | 'expired'
  /** Ohne Nutzung ruht der Zugang ab diesem Zeitpunkt */
  idle_at: string
  created_at: string
  created_by: string
  last_used_at: string | null
  last_used_ip: string
  request_count: number
  /** Darf schreiben (mindestens ein schreibender Bereich) */
  writes: boolean
  write_count: number
  last_write_at: string | null
  /** Empfänger der Personendaten aus den Geschäftspartnern */
  partner: { id: number; name: string } | null
  legal_basis: LegalBasis
  legal_confirmed_at: string | null
  legal_confirmed_by: string
  third_country: boolean
  member_fields: MemberFieldGroup[]
  only_active: boolean
  adults_only: boolean
  /** Verbandsmeldung: a nur Zahlen, b namentlich */
  report_level: 'a' | 'b'
  personal: boolean
  webhook_url: string
  webhook_events: string[]
  webhook_state: 'off' | 'ok' | 'failing' | 'paused'
  webhook_last_ok_at: string | null
  webhook_last_error: string
  /** Gelesene Datensätze mit Personendaten im Zeitraum des Abrufprotokolls */
  records_read: number
  reads: ApiRead[]
  /** Geheimnis der Benachrichtigungen: nur in der Antwort, in der es neu entstanden ist */
  webhook_secret?: string
}

/** Antwort auf Anlegen und „Neuen Schlüssel erzeugen“: der Schlüssel steht nur hier */
export interface ApiAccessWithKey extends ApiAccess {
  key: string
}

export interface ApiAccessList {
  /** Adresse der Schnittstelle dieser Instanz */
  address: string
  /** Beschreibung der Schnittstelle (OpenAPI) */
  docs: string
  requests_per_hour: number
  /** Davon höchstens so viele schreibende Anfragen */
  writes_per_hour: number
  max_days: number
  idle_days: number
  overlap_days: number
  scopes: ApiScope[]
  units: { id: number; name: string }[]
  partners: { id: number; name: string; processor: boolean }[]
  member_fields: MemberFieldGroup[]
  webhook_events: { event: string; label: string; scope: string }[]
  /** So viele Tage bleibt das Abrufprotokoll */
  log_days: number
  accesses: ApiAccess[]
}

export interface ApiAccessInput {
  name: string
  purpose: string
  recipient: string
  scopes: string[]
  unit: number | null
  /** Tag (JJJJ-MM-TT), bis zu dessen Ende der Zugang gilt */
  expires_at: string
  allowed_networks: string[]
  embeddable: boolean
  partner: number | null
  legal_basis: LegalBasis
  legal_confirmed: boolean
  third_country: boolean
  member_fields: MemberFieldGroup[]
  only_active: boolean
  adults_only: boolean
  report_level: 'a' | 'b'
  webhook_url: string
  webhook_events: string[]
  webhook_resume?: boolean
}

export const apiAccessApi = {
  list: (org: number) => api.get<ApiAccessList>(`/api/orgs/${org}/api-accesses/`),
  create: (org: number, input: ApiAccessInput) =>
    api.post<ApiAccessWithKey>(`/api/orgs/${org}/api-accesses/`, input),
  update: (org: number, id: number, input: Partial<ApiAccessInput>) =>
    api.patch<ApiAccess>(`/api/orgs/${org}/api-accesses/${id}/`, input),
  remove: (org: number, id: number) => api.del(`/api/orgs/${org}/api-accesses/${id}/`),
  rotate: (org: number, id: number) =>
    api.post<ApiAccessWithKey>(`/api/orgs/${org}/api-accesses/${id}/rotate/`),
  resume: (org: number, id: number) =>
    api.post<ApiAccess>(`/api/orgs/${org}/api-accesses/${id}/resume/`),
  webhookSecret: (org: number, id: number) =>
    api.post<ApiAccess>(`/api/orgs/${org}/api-accesses/${id}/webhook-secret/`),
  webhookTest: (org: number, id: number) =>
    api.post<{ ok: boolean; error: string }>(`/api/orgs/${org}/api-accesses/${id}/webhook-test/`),
}
