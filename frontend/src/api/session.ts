// Laufzeit der Anmeldung (UX-Audit 16.11. VW-04): Rest in Sekunden und „Angemeldet bleiben“.
import { api } from './client.ts'

export interface SessionInfo {
  /** Sekunden, bis die Anmeldung abläuft */
  expires_in: number
}

export const sessionApi = {
  get: () => api.get<SessionInfo>('/api/me/session/'),
  /** Anmeldung um die volle Laufzeit verlängern */
  extend: () => api.post<SessionInfo>('/api/me/session/'),
}
