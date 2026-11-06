import { api } from './client.ts'

export type MeetingBase = 'general' | 'board' | 'committee'
export type MeetingStatus = 'draft' | 'invited' | 'held' | 'minutes' | 'done' | 'cancelled'
export type AgendaType = 'report' | 'resolution' | 'election' | 'other'

export interface MeetingKind {
  id: number
  name: string
  base: MeetingBase
  invite_days: number
  invite_form: 'mail' | 'letter'
  voter_types: number[]
  voter_min_age: number | null
  quorum_percent: number | null
  quorum_count: number | null
  proxies_allowed: boolean
  minutes_for: 'board' | 'voters'
  position: number
  active: boolean
  used: boolean
}

export interface AgendaItem {
  id?: number | null
  position?: number
  title: string
  description: string
  type: AgendaType
}

export interface Meeting {
  id: number
  kind: number
  kind_name: string
  base: MeetingBase
  title: string
  starts_at: string
  ends_at: string
  location: string
  address: string
  event: number
  status: MeetingStatus
  invite_by: string
  version: number
  can_edit: boolean
  can_invite: boolean
  invited_at: string | null
  circular: number | null
  circular_status: '' | 'draft' | 'sending' | 'sent'
  chair?: string
  minute_taker?: string
  note?: string
  agenda?: AgendaItem[]
}

export const meetingApi = {
  list: (base: string) => api.get<Meeting[]>(base),
  get: (base: string, id: number) => api.get<Meeting>(`${base}${id}/`),
  create: (base: string, data: object) => api.post<Meeting>(base, data),
  update: (base: string, meeting: Meeting, data: object) =>
    api.patch<Meeting>(`${base}${meeting.id}/`, { ...data, version: meeting.version }),
  remove: (base: string, id: number) => api.del(`${base}${id}/`),
  saveAgenda: (base: string, meeting: Meeting, items: AgendaItem[]) =>
    api.put<Meeting>(`${base}${meeting.id}/agenda/`, { version: meeting.version, items }),
  prepareInvitation: (base: string, meeting: Meeting) =>
    api.post<Meeting>(`${base}${meeting.id}/invitation/`),
  kinds: (base: string) => api.get<MeetingKind[]>(`${base}kinds/`),
  createKind: (base: string, data: object) => api.post<MeetingKind>(`${base}kinds/`, data),
  updateKind: (base: string, id: number, data: object) =>
    api.patch<MeetingKind>(`${base}kinds/${id}/`, data),
  removeKind: (base: string, id: number) => api.del(`${base}kinds/${id}/`),
}
