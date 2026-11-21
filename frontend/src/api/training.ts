// Training und Anwesenheit samt Schießnachweis nach § 14 WaffG (Lückenliste 20.11.2026, B1)
import { api, requestBlob } from './client.ts'

export type WeaponClass = 'short' | 'long'
export type SessionKind = 'practice' | 'training' | 'competition' | 'other'

export interface TrainingSession {
  id: number
  department: number | null
  department_name: string
  event: number | null
  date: string
  starts_at: string | null
  ends_at: string | null
  hours: number | null
  title: string
  kind: SessionKind
  kind_label: string
  location: string
  leader: string
  note: string
  shooting: boolean
  discipline: string
  weapon_class: WeaponClass | ''
  caliber: string
  permit_required: boolean
  checkin_open: boolean
  count: number
  version: number
}

export interface AttendanceRow {
  membership: number
  name: string
  first_name: string
  last_name: string
  present: boolean
  source: 'hand' | 'code' | null
  shooting: boolean
}

export interface SessionDetail extends TrainingSession {
  attendance: AttendanceRow[]
  can_edit: boolean
  checkin_possible: boolean
  shooting_enabled: boolean
}

export interface Discipline {
  name: string
  weapon_class: WeaponClass
  permit_required: boolean
  caliber: string
}

export interface EventSuggestion {
  event: number
  date: string
  starts_at: string | null
  ends_at: string | null
  title: string
  location: string
}

export interface TrainingOptions {
  can_edit: boolean
  kinds: { value: SessionKind; label: string }[]
  shooting_enabled: boolean
  disciplines: Discipline[]
  events: EventSuggestion[]
}

export interface SessionDraft {
  date: string
  starts_at: string
  ends_at: string
  title: string
  kind: SessionKind
  location: string
  leader: string
  note: string
  shooting: boolean
  discipline: string
  weapon_class: WeaponClass | ''
  caliber: string
  permit_required: boolean
  event?: number | null
  version?: number
}

export interface CheckinCode {
  code: string
  refresh_in: number
  session: number
  club: number
  count: number
}

export interface TrainingReport {
  start: string
  end: string
  sessions: TrainingSession[]
  members: { membership: number; name: string; count: number; share: number }[]
  total_sessions: number
  total_attendances: number
  total_hours: number
}

export interface ShootingEntry {
  id: number
  membership: number
  date: string
  discipline: string
  weapon_class: WeaponClass
  weapon_class_label: string
  caliber: string
  permit_required: boolean
  own_weapon: boolean | null
  competition: boolean
  place: string
  external: boolean
  note: string
  status: 'reported' | 'confirmed' | 'rejected'
  status_label: string
  source: 'training' | 'board' | 'member'
  source_label: string
  from_training: boolean
  confirmed_by: string
  confirmed_at: string | null
  /** Nur in der Liste gemeldeter Einträge */
  name?: string
}

export interface Span {
  start: string
  end: string
  count: number
}

export interface Evaluation {
  on: string
  start_12: string
  start_24: string
  member_since: string | null
  acquisition: {
    ok: boolean
    member_12_months: boolean
    by_months: boolean
    by_count: boolean
    count: number
    needed: number
    months: Span[]
    longest_gap_days: number
    gap_ok: boolean
    external: number
    internal: number
    mostly_own_club: boolean
  }
  possession: {
    weapon_class: WeaponClass
    label: string
    count: number
    ok: boolean
    by_quarters: boolean
    by_six: boolean
    quarters: Span[]
    years: Span[]
  }[]
  pending: number
}

export interface EntryDraft {
  date: string
  discipline: string
  weapon_class: WeaponClass
  caliber: string
  permit_required: boolean
  own_weapon: boolean | null
  competition: boolean
  place: string
  external: boolean
  note: string
}

export interface MemberLog {
  membership: number
  name: string
  entries: ShootingEntry[]
  evaluation: Evaluation
  can_edit?: boolean
  disciplines?: Discipline[]
}

export interface ShootingOverview {
  members: {
    membership: number
    name: string
    count_24: number
    pending: number
    last: string | null
  }[]
  reported: ShootingEntry[]
  can_edit: boolean
  disciplines: Discipline[]
}

export interface PortalTraining {
  attendance: {
    session: number
    date: string
    title: string
    kind: SessionKind
    kind_label: string
    department_name: string
    source: 'hand' | 'code'
  }[]
  count_year: number
  count_12: number
  checkin: (TrainingSession & { present: boolean })[]
  shooting_enabled: boolean
  targets: { department: number | null; name: string }[]
  shooting?: {
    entries: ShootingEntry[]
    evaluation: Evaluation
    disciplines: Discipline[]
  }
}

function query(params: Record<string, string | undefined>) {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v) q.set(k, v)
  const s = q.toString()
  return s ? `?${s}` : ''
}

/** Basis der Trainings: Verein oder Untereinheit */
export function trainingBase(orgId: number | null, deptId: number | null) {
  return orgId ? `/api/orgs/${orgId}/training/` : `/api/depts/${deptId}/training/`
}

export const trainingApi = {
  list: (base: string, von?: string, bis?: string) =>
    api.get<{ sessions: TrainingSession[]; can_edit: boolean; start: string; end: string }>(
      `${base}${query({ von, bis })}`,
    ),
  options: (base: string) => api.get<TrainingOptions>(`${base}options/`),
  get: (base: string, id: number) => api.get<SessionDetail>(`${base}${id}/`),
  create: (base: string, draft: SessionDraft) => api.post<SessionDetail>(base, draft),
  update: (base: string, id: number, draft: Partial<SessionDraft>) =>
    api.patch<SessionDetail>(`${base}${id}/`, draft),
  remove: (base: string, id: number) => api.del(`${base}${id}/`),
  setPresent: (base: string, id: number, membership: number, present: boolean) =>
    api.post<SessionDetail>(`${base}${id}/attendance/`, { membership, present }),
  setMany: (base: string, id: number, members: number[], present: boolean) =>
    api.post<SessionDetail>(`${base}${id}/attendance/`, { members, present }),
  checkin: (base: string, id: number, open: boolean) =>
    api.post<SessionDetail>(`${base}${id}/checkin/`, { open }),
  code: (base: string, id: number) => api.get<CheckinCode>(`${base}${id}/checkin/`),
  report: (base: string, von?: string, bis?: string) =>
    api.get<TrainingReport>(`${base}report/${query({ von, bis })}`),
  reportXlsx: (base: string, von?: string, bis?: string) =>
    requestBlob('GET', `${base}report/${query({ von, bis, format: 'xlsx' })}`),
}

export const shootingApi = {
  overview: (orgId: number) => api.get<ShootingOverview>(`/api/orgs/${orgId}/shooting-log/`),
  member: (orgId: number, memberId: number) =>
    api.get<MemberLog>(`/api/orgs/${orgId}/members/${memberId}/shooting-log/`),
  add: (orgId: number, memberId: number, draft: EntryDraft) =>
    api.post<MemberLog>(`/api/orgs/${orgId}/members/${memberId}/shooting-log/`, draft),
  update: (orgId: number, id: number, draft: Partial<EntryDraft>) =>
    api.patch<ShootingEntry>(`/api/orgs/${orgId}/shooting-log/${id}/`, draft),
  remove: (orgId: number, id: number) => api.del(`/api/orgs/${orgId}/shooting-log/${id}/`),
  decide: (orgId: number, id: number, confirm: boolean) =>
    api.post<ShootingEntry>(
      `/api/orgs/${orgId}/shooting-log/${id}/${confirm ? 'confirm' : 'reject'}/`,
    ),
  pdf: (orgId: number, memberId: number, von?: string, bis?: string, waffe?: string) =>
    requestBlob(
      'GET',
      `/api/orgs/${orgId}/members/${memberId}/shooting-log/pdf/${query({ von, bis, waffe })}`,
    ),
}

export const portalTrainingApi = {
  get: (accessId: number) => api.get<PortalTraining>(`/api/portal/${accessId}/training/`),
  checkin: (accessId: number, session: number, code: string) =>
    api.post<PortalTraining>(`/api/portal/${accessId}/training/${session}/checkin/`, { code }),
  report: (accessId: number, draft: EntryDraft, requestKey?: string) =>
    api.post<PortalTraining>(`/api/portal/${accessId}/training/shooting/`, draft, requestKey),
  withdraw: (accessId: number, id: number) =>
    api.delWith<PortalTraining>(`/api/portal/${accessId}/training/shooting/${id}/`, {}),
}
