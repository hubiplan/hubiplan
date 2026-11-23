// Plattform › Sicherheit: Meldungen des Browsers über Verstöße gegen die Inhaltsregeln (CSP).
import { api } from './client.ts'

export interface CspEntry {
  id: number
  directive: string
  blocked: string
  page: string
  count: number
  first_day: string
  last_day: string
  version: string
  /** Betrifft ein Skript (das meldet HUBIplan auch per Mail) */
  script: boolean
}

export interface CspState {
  total: number
  limit: number
  entries: CspEntry[]
}

export const securityApi = {
  cspReports: () => api.get<CspState>('/api/platform/csp-reports/'),
  dropCspReport: (id: number) => api.delWith<CspState>(`/api/platform/csp-reports/${id}/`, {}),
  clearCspReports: () => api.delWith<CspState>('/api/platform/csp-reports/', {}),
}

/** Köder: erfundenes Mitglied, das kein Verein sieht und dessen Benutzung Alarm auslöst. */
export interface Decoy {
  id: number
  name: string
  email: string
  place: string
  created: string
}

export interface DecoyHit {
  id: number
  kind: 'mail_in' | 'mail_out' | 'login' | 'lookup'
  /** Name des Köders; leer, wenn er inzwischen gelöscht ist */
  decoy: string
  detail: string
  count: number
  last_at: string
}

export interface DecoyState {
  decoys: Decoy[]
  limit: number
  /** Verteiler-Domain, deren Sammelpostfach HUBIplan abholt; leer: keine eingerichtet */
  domain: string
  hits: DecoyHit[]
}

export const decoyApi = {
  state: () => api.get<DecoyState>('/api/platform/decoys/'),
  create: (email: string) => api.post<DecoyState>('/api/platform/decoys/', { email }),
  remove: (id: number) => api.delWith<DecoyState>(`/api/platform/decoys/${id}/`, {}),
  clearHits: () => api.delWith<DecoyState>('/api/platform/decoy-hits/', {}),
}
