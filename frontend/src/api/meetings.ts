import { api, requestBlob } from './client.ts'

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

export interface Resolution {
  id?: number | null
  kind: 'resolution' | 'election'
  text: string
  votes_yes: number | null
  votes_no: number | null
  votes_abstain: number | null
  unanimous: boolean
  result: 'accepted' | 'rejected'
  office: string
  elected_name: string
  elected?: number | null
  number?: string
}

export interface AgendaItem {
  id?: number | null
  position?: number
  title: string
  description: string
  type: AgendaType
  minutes?: string
  resolutions?: Resolution[]
}

export interface MinutesItem {
  id: number
  minutes: string
  resolutions: Resolution[]
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
  can_attendance?: boolean
  invited_at: string | null
  circular: number | null
  circular_status: '' | 'draft' | 'sending' | 'sent'
  chair?: string
  minute_taker?: string
  note?: string
  agenda?: AgendaItem[]
  chair_confirmed?: Confirmation | null
  taker_confirmed?: Confirmation | null
  released_at?: string | null
  minutes_sha256?: string
  minutes_document?: number | null
}

export interface Confirmation {
  name: string
  at: string
}

export type AttendanceStatus = 'present' | 'excused' | 'represented'

export interface AttendanceRow {
  id: number | null
  membership: number | null
  name: string
  voter: boolean
  status: '' | AttendanceStatus
  represented_by: number | null
}

export interface AttendanceList {
  voters: number
  present: number
  represented: number
  guests: number
  quorum: { needed: number; reached: boolean; rule: boolean }
  proxies_allowed: boolean
  editable: boolean
  rows: AttendanceRow[]
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
  saveMinutes: (base: string, meeting: Meeting, items: MinutesItem[]) =>
    api.put<Meeting>(`${base}${meeting.id}/minutes/`, { version: meeting.version, items }),
  confirmMinutes: (base: string, meeting: Meeting, role: 'chair' | 'taker') =>
    api.post<Meeting>(`${base}${meeting.id}/minutes/confirm/`, { version: meeting.version, role }),
  minutesPdf: (base: string, meeting: Meeting) =>
    requestBlob('GET', `${base}${meeting.id}/minutes/pdf/`),
  prepareInvitation: (base: string, meeting: Meeting) =>
    api.post<Meeting>(`${base}${meeting.id}/invitation/`),
  attendance: (base: string, id: number) => api.get<AttendanceList>(`${base}${id}/attendance/`),
  markAttendance: (base: string, id: number, data: object) =>
    api.post<AttendanceList>(`${base}${id}/attendance/`, data),
  removeAttendance: (base: string, id: number, entry: number) =>
    api.del(`${base}${id}/attendance/${entry}/`),
  kinds: (base: string) => api.get<MeetingKind[]>(`${base}kinds/`),
  createKind: (base: string, data: object) => api.post<MeetingKind>(`${base}kinds/`, data),
  updateKind: (base: string, id: number, data: object) =>
    api.patch<MeetingKind>(`${base}kinds/${id}/`, data),
  removeKind: (base: string, id: number) => api.del(`${base}kinds/${id}/`),
}
