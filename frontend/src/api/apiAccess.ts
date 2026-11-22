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
  max_days: number
  idle_days: number
  overlap_days: number
  scopes: ApiScope[]
  units: { id: number; name: string }[]
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
}
