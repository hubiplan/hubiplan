// Glückwünsche zu Geburtstag und Jubiläum (Rundschreiben › Glückwünsche).
import { api } from './client.ts'

export type GreetingKind = 'birthday' | 'jubilee'
export type GreetingStatus = 'draft' | 'late' | 'sent' | 'skipped'

export interface GreetingSettings {
  birthdays: 'off' | 'round' | 'all'
  round_ages: string
  every_year_from: number
  jubilees: boolean
  approval: boolean
  lead_days: number
  send_hour: number
  via_app: boolean
  also_mail: boolean
  reply_to: string
  birthday_subject: string
  birthday_body: string
  jubilee_subject: string
  jubilee_body: string
  active: boolean
  defaults: Record<
    'birthday_subject' | 'birthday_body' | 'jubilee_subject' | 'jubilee_body',
    string
  >
}

export interface GreetingBatch {
  id: number
  date: string
  kind: GreetingKind
  kind_label: string
  status: GreetingStatus
  note: string
  count: number
  circular: number | null
  letters_url: string | null
  sent_at: string | null
  /** Entwurf: Empfänger mit Weg (app, mail, letter) oder null bei Widerspruch */
  recipients: { name: string; channel: 'app' | 'mail' | 'letter' | 'portal' | null; note: string }[]
  letters: number
}

export interface GreetingOccasion {
  date: string
  kind: GreetingKind
  member_id: number
  name: string
  age: number | null
  years: number | null
  opted_out: boolean
}

export interface GreetingOverview {
  settings: GreetingSettings
  batches: GreetingBatch[]
  upcoming: GreetingOccasion[]
  can_edit: boolean
}

const base = (org: number) => `/api/orgs/${org}/greetings/`

export const greetingApi = {
  overview: (org: number) => api.get<GreetingOverview>(base(org)),
  save: (org: number, data: Partial<GreetingSettings>) =>
    api.put<GreetingSettings>(`${base(org)}settings/`, data),
  send: (org: number, id: number) =>
    api.post<{ sent: Record<string, number> }>(`${base(org)}${id}/send/`),
  skip: (org: number, id: number) => api.post<{ ok: boolean }>(`${base(org)}${id}/skip/`),
  restore: (org: number, id: number) => api.post<{ ok: boolean }>(`${base(org)}${id}/restore/`),
}
