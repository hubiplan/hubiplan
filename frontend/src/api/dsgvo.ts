// Datenschutz-Werkzeuge: Verzeichnis der Verarbeitungstätigkeiten (Art. 30 DSGVO),
// Auftragsverarbeiter und Protokoll von Datenpannen (Art. 33 DSGVO).
import { api } from './client.ts'

export interface Activity {
  id: number | null
  key: string
  module: string
  title: string
  purpose: string
  legal_basis: string
  subjects: string
  categories: string
  recipients: string
  third_country: string
  retention: string
  hidden: boolean
  version?: number
}

export type ActivityInput = Partial<
  Pick<
    Activity,
    | 'title'
    | 'purpose'
    | 'legal_basis'
    | 'subjects'
    | 'categories'
    | 'recipients'
    | 'third_country'
    | 'retention'
    | 'version'
  >
>

export interface PrivacySettings {
  dpo_name: string
  dpo_contact: string
  hoster: string
  toms: string
  version: number
}

export interface Processor {
  id: number
  name: string
  agreement: { id: number; title: string; start: string; end: string | null } | null
}

export type BreachRisk = 'unlikely' | 'risk' | 'high'
export type BreachStatus = 'report_due' | 'overdue' | 'open' | 'closed'

export interface Breach {
  id: number
  title: string
  discovered_at: string
  occurred: string
  description: string
  categories: string
  affected: string
  consequences: string
  measures: string
  risk: BreachRisk
  report_deadline: string
  reported_at: string | null
  report_reference: string
  no_report_reason: string
  notified_at: string | null
  closed_at: string | null
  status: BreachStatus
  created_by: string
  version: number
}

export type BreachInput = Partial<
  Omit<Breach, 'id' | 'report_deadline' | 'status' | 'created_by' | 'closed_at'>
> & { closed?: boolean }

export interface PrivacyOverview {
  controller: { name: string; address: string; representatives: string; contact: string }
  settings: PrivacySettings
  activities: Activity[]
  processors: Processor[]
  open_breaches: Breach[]
  can_edit: boolean
  can_partners: boolean
}

export const dsgvoBase = (org: number) => `/api/orgs/${org}/privacy/`

export const dsgvoApi = {
  overview: (base: string) => api.get<PrivacyOverview>(base),
  registerPdfUrl: (base: string) => `${base}?als=pdf`,
  saveSettings: (base: string, data: Partial<PrivacySettings>) =>
    api.put<PrivacySettings>(`${base}settings/`, data),
  hide: (base: string, key: string, hidden: boolean) =>
    api.post<{ hidden_keys: string[] }>(`${base}hide/`, { key, hidden }),
  createActivity: (base: string, data: ActivityInput) =>
    api.post<Activity>(`${base}activities/`, data),
  updateActivity: (base: string, id: number, data: ActivityInput) =>
    api.patch<Activity>(`${base}activities/${id}/`, data),
  removeActivity: (base: string, id: number) => api.del(`${base}activities/${id}/`),
  breaches: (base: string) => api.get<{ items: Breach[]; can_edit: boolean }>(`${base}breaches/`),
  createBreach: (base: string, data: BreachInput) => api.post<Breach>(`${base}breaches/`, data),
  updateBreach: (base: string, id: number, data: BreachInput) =>
    api.patch<Breach>(`${base}breaches/${id}/`, data),
  removeBreach: (base: string, id: number) => api.del(`${base}breaches/${id}/`),
  breachPdfUrl: (base: string, id: number) => `${base}breaches/${id}/?als=pdf`,
}
