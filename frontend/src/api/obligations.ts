// Fristenkalender: wiederkehrende Pflichten des Vereins mit Erinnerung und Verlauf.
import { api } from './client.ts'

export type ObligationStatus = 'overdue' | 'soon' | 'planned' | 'election' | 'done' | 'inactive'

export interface ObligationDone {
  id: number
  due_date: string | null
  done_on: string
  note: string
  done_by: string
}

export interface Obligation {
  id: number
  key: string
  title: string
  note: string
  trigger: 'date' | 'election'
  due_date: string | null
  interval_months: number | null
  remind_days: number
  days_after: number
  role: number | null
  role_name: string
  active: boolean
  status: ObligationStatus
  version: number
  history: ObligationDone[]
}

export interface ObligationSuggestion {
  key: string
  title: string
  note: string
  trigger: 'date' | 'election'
  interval_months: number | null
  remind_days: number
  due_date: string | null
  registered_only: boolean
}

export interface ObligationList {
  items: Obligation[]
  suggestions: ObligationSuggestion[]
  roles: { id: number; name: string }[]
  registered: boolean
  can_edit: boolean
}

export type ObligationInput = Partial<
  Pick<
    Obligation,
    | 'key'
    | 'title'
    | 'note'
    | 'due_date'
    | 'interval_months'
    | 'remind_days'
    | 'days_after'
    | 'role'
    | 'active'
    | 'version'
  >
>

export const obligationApi = {
  list: (base: string) => api.get<ObligationList>(base),
  create: (base: string, data: ObligationInput) => api.post<Obligation>(base, data),
  update: (base: string, id: number, data: ObligationInput) =>
    api.patch<Obligation>(`${base}${id}/`, data),
  remove: (base: string, id: number) => api.del(`${base}${id}/`),
  done: (base: string, id: number, data: { done_on?: string; note?: string }) =>
    api.post<Obligation>(`${base}${id}/done/`, data),
}
