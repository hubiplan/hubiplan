import { api, requestBlob } from './client.ts'
import type { PickedMember } from './members.ts'

export type PlanStatus = 'draft' | 'published' | 'closed'

export interface Assignment {
  id: number
  membership: number | null
  name: string
  external: boolean
  origin: 'self' | 'assigned'
  status: 'active' | 'cancelled'
  done: boolean | null
  phone?: string
}

export interface Shift {
  id: number
  starts_at: string
  ends_at: string
  needed: number
  note: string
  taken: number
  assignments: Assignment[]
}

export interface Duty {
  id: number
  name: string
  description: string
  location: string
  min_age: number | null
  position: number
  shifts: Shift[]
}

export interface HelperPlan {
  id: number
  title: string
  event: number | null
  event_title: string
  event_starts_at: string | null
  status: PlanStatus
  signup: 'self' | 'assign'
  cancel_days: number
  max_shifts: number | null
  show_names: boolean
  remind_days: number | null
  version: number
  can_edit: boolean
  needed: number
  open: number
  note?: string
  duties?: Duty[]
}

export interface PlanEvent {
  id: number
  title: string
  starts_at: string
}

export const helperApi = {
  list: (base: string) => api.get<HelperPlan[]>(base),
  get: (base: string, id: number) => api.get<HelperPlan>(`${base}${id}/`),
  create: (base: string, data: object) => api.post<HelperPlan>(base, data),
  update: (base: string, plan: HelperPlan, data: object) =>
    api.patch<HelperPlan>(`${base}${plan.id}/`, { ...data, version: plan.version }),
  remove: (base: string, id: number) => api.del(`${base}${id}/`),
  events: (base: string) => api.get<PlanEvent[]>(`${base}events/`),
  members: (base: string, term: string) =>
    api.get<PickedMember[]>(`${base}members/?suche=${encodeURIComponent(term)}`),
  addDuty: (base: string, plan: number, data: object) =>
    api.post<Duty>(`${base}${plan}/duties/`, data),
  updateDuty: (base: string, id: number, data: object) =>
    api.patch<Duty>(`${base}duties/${id}/`, data),
  removeDuty: (base: string, id: number) => api.del(`${base}duties/${id}/`),
  addShifts: (base: string, duty: number, data: object) =>
    api.post<Shift[]>(`${base}duties/${duty}/shifts/`, data),
  updateShift: (base: string, id: number, data: object) =>
    api.patch<Shift>(`${base}shifts/${id}/`, data),
  removeShift: (base: string, id: number) => api.del(`${base}shifts/${id}/`),
  assign: (base: string, shift: number, data: object) =>
    api.post<Assignment>(`${base}shifts/${shift}/assignments/`, data),
  updateAssignment: (base: string, id: number, data: object) =>
    api.patch<Assignment>(`${base}assignments/${id}/`, data),
  removeAssignment: (base: string, id: number) => api.del(`${base}assignments/${id}/`),
  export: (base: string, id: number, format: 'pdf' | 'xlsx') =>
    requestBlob('GET', `${base}${id}/export/?datei=${format}`),
}

export interface PortalShift {
  id: number
  starts_at: string
  ends_at: string
  needed: number
  taken: number
  note: string
  names: string[]
  mine: number | null
  can_cancel: boolean
  past: boolean
}

export interface PortalPlan {
  id: number
  title: string
  unit: string
  event_title: string
  signup: 'self' | 'assign'
  cancel_days: number
  max_shifts: number | null
  note: string
  duties: {
    id: number
    name: string
    description: string
    location: string
    min_age: number | null
    shifts: PortalShift[]
  }[]
}

export interface MyDuty {
  id: number
  plan: string
  duty: string
  location: string
  starts_at: string
  ends_at: string
}

export const portalHelperApi = {
  list: (access: number) =>
    api.get<{ plans: PortalPlan[]; mine: MyDuty[] }>(`/api/portal/${access}/helpers/`),
  signup: (access: number, shift: number) =>
    api.post<PortalPlan>(`/api/portal/${access}/helpers/shifts/${shift}/signup/`),
  cancel: (access: number, assignment: number) =>
    api.post(`/api/portal/${access}/helpers/assignments/${assignment}/cancel/`),
  calendar: (access: number) => requestBlob('GET', `/api/portal/${access}/helpers/calendar/`),
}
