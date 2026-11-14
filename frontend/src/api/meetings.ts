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
  motion_days: number | null
  online_voting: boolean
  remote_allowed: boolean
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
  /** 0 = Punkt, 1 = Unterpunkt des Punkts davor */
  level?: number
  /** Angezeigte Nummer, z. B. „8“ oder „8.1“ */
  number?: string
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
  motions_open?: number
  motions?: Motion[]
  online_voting?: boolean
  remote_allowed?: boolean
  checkin_open?: boolean
  remote?: boolean
}

export type MotionStatus = 'submitted' | 'accepted' | 'rejected' | 'withdrawn'

export interface Motion {
  id: number
  name: string
  title: string
  text: string
  status: MotionStatus
  reply: string
  agenda_item: number | null
  created_at: string
  decided_at: string | null
}

export interface OwnMotion {
  id: number
  title: string
  text: string
  status: MotionStatus
  reply: string
  created_at: string
}

export interface Confirmation {
  name: string
  at: string
}

export type AttendanceStatus = 'present' | 'excused' | 'represented' | 'delegate' | 'left'
/** Wie jemand angemeldet ist: von Hand, per App (Code) oder aus der Ferne */
export type AttendanceMode = '' | 'app' | 'online'

export interface AttendanceRow {
  id: number | null
  membership: number | null
  name: string
  voter: boolean
  status: '' | AttendanceStatus
  mode?: AttendanceMode
  represented_by: number | null
  /** 'organization' bei Organisationsmitgliedern */
  kind?: string
  /** Vertreter eines Organisationsmitglieds, wie eingetragen */
  delegate_name?: string
  /** Ansprechpartner mit „vertritt in Versammlungen“ */
  delegates?: { id: number; name: string; function: string; membership: number | null }[]
  /** Organisationen, die dieses Mitglied zusätzlich vertritt */
  also_represents?: string[]
}

export interface AttendanceList {
  voters: number
  present: number
  represented: number
  guests: number
  online?: number
  quorum: { needed: number; reached: boolean; rule: boolean }
  proxies_allowed: boolean
  editable: boolean
  rows: AttendanceRow[]
}

export type ResolutionStatus = 'open' | 'done' | 'repealed'

export interface BookRow {
  id: number
  number: string
  kind: 'resolution' | 'election'
  text: string
  result: 'accepted' | 'rejected'
  votes_yes: number | null
  votes_no: number | null
  votes_abstain: number | null
  unanimous: boolean
  office: string
  elected_name: string
  /** Mitgliedschaft der gewählten Person (nur bei Auswahl aus der Mitgliederliste) */
  elected: number | null
  status: ResolutionStatus
  meeting: number
  meeting_title: string
  meeting_kind: number
  meeting_kind_name: string
  date: string
  agenda_title: string
  agenda_number?: string
  has_todo: boolean
  todo: { id: number; title: string; status: string } | null
}

export interface Book {
  rows: BookRow[]
  years: number[]
  can_todo: boolean
}

export interface PortalMeetings {
  upcoming: {
    id: number
    title: string
    kind_name: string
    unit: string
    starts_at: string
    location: string
    address: string
    motion_until: string | null
    checkin_open?: boolean
    remote?: boolean
    motions: OwnMotion[]
    agenda: {
      position: number
      level?: number
      number?: string
      title: string
      description: string
    }[]
  }[]
  minutes: { id: number; title: string; kind_name: string; unit: string; starts_at: string }[]
}

export type PollStatus = 'draft' | 'open' | 'closed'

export interface PollOption {
  id: number
  role: 'yes' | 'no' | 'abstain' | 'candidate'
  label: string
}

export interface Poll {
  id: number
  agenda_item: number
  agenda_position: number
  agenda_number?: string
  agenda_title: string
  kind: 'resolution' | 'election'
  question: string
  office: string
  candidate: string
  secret: boolean
  status: PollStatus
  opened_at: string | null
  closed_at: string | null
  cast: number
  entitled: number
  options: PollOption[]
  /** Ergebnis erst nach dem Ende */
  result: (PollOption & { votes: number })[] | null
  resolution: number | null
  /** Offene Abstimmung, beendet: wer wie gestimmt hat (nur Leitung) */
  open_votes?: { name: string; option: string }[]
  /** Mitgliederbereich: eigene Stimmen (eigene, Vollmachten, Organisationen) */
  votes?: { attendance: number; name: string; how: 'own' | 'proxy' | 'delegate'; done: boolean }[]
}

export interface LiveState {
  meeting: number
  organization: number
  status: MeetingStatus
  online_voting: boolean
  remote_allowed: boolean
  checkin_open: boolean
  remote: boolean
  live: boolean
  voters: number
  present_app: number
  present_online: number
  entitled: number
  polls: Poll[]
  code?: string
  refresh_in?: number
}

export interface PortalLive {
  id: number
  title: string
  kind_name: string
  unit: string
  starts_at: string
  location: string
  checkin_open: boolean
  remote: boolean
  voter: boolean
  is_organization: boolean
  status: '' | AttendanceStatus
  mode: AttendanceMode
  votes: number
  polls: Poll[]
}

export interface PollDraft {
  agenda_item: number
  question: string
  secret: boolean
  office: string
  candidates: { name: string; membership?: number | null }[]
}

export const portalMeetingApi = {
  live: (access: number, id: number) =>
    api.get<PortalLive>(`/api/portal/${access}/meetings/${id}/live/`),
  checkin: (access: number, id: number, data: { code?: string; remote?: boolean }) =>
    api.post<PortalLive>(`/api/portal/${access}/meetings/${id}/live/checkin/`, data),
  leave: (access: number, id: number) =>
    api.post<PortalLive>(`/api/portal/${access}/meetings/${id}/live/leave/`),
  vote: (
    access: number,
    id: number,
    poll: number,
    votes: { attendance: number; option: number }[],
  ) => api.post<PortalLive>(`/api/portal/${access}/meetings/${id}/polls/${poll}/vote/`, { votes }),
  list: (access: number) => api.get<PortalMeetings>(`/api/portal/${access}/meetings/`),
  minutes: (access: number, id: number) =>
    requestBlob('GET', `/api/portal/${access}/meetings/${id}/minutes/`),
  submitMotion: (access: number, id: number, data: { title: string; text: string }) =>
    api.post<OwnMotion[]>(`/api/portal/${access}/meetings/${id}/motions/`, data),
  withdrawMotion: (access: number, id: number) =>
    api.post(`/api/portal/${access}/meetings/motions/${id}/withdraw/`),
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
  live: (base: string, id: number) => api.get<LiveState>(`${base}${id}/live/`),
  setLive: (base: string, id: number, data: { open?: boolean; remote?: boolean }) =>
    api.post<LiveState>(`${base}${id}/live/`, data),
  createPoll: (base: string, id: number, data: PollDraft) =>
    api.post<LiveState>(`${base}${id}/polls/`, data),
  pollAction: (base: string, id: number, poll: number, action: 'open' | 'close' | 'apply') =>
    api.post<LiveState>(`${base}${id}/polls/${poll}/`, { action }),
  removePoll: (base: string, id: number, poll: number) =>
    api.del(`${base}${id}/polls/${poll}/`) as Promise<LiveState>,
  kinds: (base: string) => api.get<MeetingKind[]>(`${base}kinds/`),
  createKind: (base: string, data: object) => api.post<MeetingKind>(`${base}kinds/`, data),
  updateKind: (base: string, id: number, data: object) =>
    api.patch<MeetingKind>(`${base}kinds/${id}/`, data),
  removeKind: (base: string, id: number) => api.del(`${base}kinds/${id}/`),
  decideMotion: (base: string, meeting: number, motion: number, data: object) =>
    api.post<Meeting>(`${base}${meeting}/motions/${motion}/`, data),
  book: (base: string, query: string) => api.get<Book>(`${base}resolutions/${query}`),
  bookExport: (base: string, query: string) =>
    requestBlob('GET', `${base}resolutions/export/${query}`),
  setResolutionStatus: (base: string, id: number, status: ResolutionStatus) =>
    api.patch<BookRow>(`${base}resolutions/${id}/`, { status }),
  resolutionTodo: (base: string, id: number, data: object) =>
    api.post<BookRow>(`${base}resolutions/${id}/todo/`, data),
}
