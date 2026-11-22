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
