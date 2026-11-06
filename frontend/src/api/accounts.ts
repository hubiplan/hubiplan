// Einstellungen › Konten: alle Konten der Einheit (Rollen-Vorschlag R4).
import { api } from './client.ts'

export interface Account {
  id: number
  name: string
  email: string
  /** Mitgliedsakte in dieser Einheit */
  membership: number | null
  /** heutige Rollen der Einheit */
  roles: string[]
  /** mindestens eine Rolle mit Rechten */
  rights: boolean
  member_area: boolean
  last_login: string | null
  awaiting_password: boolean
  invitation_expired: boolean
  has_mfa: boolean
  /** Zwei-Faktor wäre Pflicht, ist aber nicht eingerichtet */
  mfa_missing: boolean
}

const base = (org: number) => `/api/orgs/${org}/accounts/`

export const accountsApi = {
  list: (org: number) => api.get<Account[]>(base(org)),
  resend: (org: number, users: number[]) =>
    api.post<{ sent: string[]; skipped: string[] }>(`${base(org)}resend/`, { users }),
}
