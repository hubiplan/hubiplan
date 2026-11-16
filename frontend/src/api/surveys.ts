// Umfragen und Meinungsbilder (konzepte/umfragen-meinungsbilder.md)
import { api, requestBlob } from './client.ts'
import type { PickedMember } from './members.ts'

export type SurveyStatus = 'draft' | 'open' | 'closed'
export type QuestionKind = 'single' | 'multiple' | 'yesno' | 'dates' | 'quantity' | 'text'
export type Audience = 'members' | 'persons' | 'event' | 'event_yes'
export type NamesMode = 'open' | 'managers' | 'anonymous'
export type ResultsMode = 'after_answer' | 'always' | 'after_close' | 'managers'
export type DateValue = 'yes' | 'maybe' | 'no'
export type YesNoValue = 'yes' | 'no' | 'abstain'

export interface SurveyOption {
  id?: number
  label: string
  starts_at: string | null
  ends_at: string | null
  all_day: boolean
  capacity: number | null
}

export interface SurveyQuestion {
  id?: number
  kind: QuestionKind
  text: string
  required: boolean
  max_choices: number | null
  allow_maybe: boolean
  options: SurveyOption[]
  /** Mitgliederbereich: höchstens so viele Stück zusammen (Mengenauswahl) */
  max_total?: number
}

/** Eine Antwort je Frage, wie sie an den Server geht */
export interface AnswerRow {
  question: number
  options?: number[]
  value?: YesNoValue
  dates?: Record<string, DateValue>
  quantities?: Record<string, number>
  text?: string
}

export interface ResultOption {
  id: number
  label: string
  starts_at: string | null
  ends_at: string | null
  all_day: boolean
  capacity: number | null
  count: number
  maybe?: number
  names: string[]
  maybe_names?: string[]
}

export interface ResultQuestion {
  id: number
  kind: QuestionKind
  text: string
  answered: number
  options?: ResultOption[]
  values?: Record<YesNoValue, { count: number; names: string[] }>
  texts?: { text: string; name: string }[]
  best?: number[]
}

export interface SurveyResult {
  participants: number
  hidden: boolean
  // Anonym und noch nicht beendet: Ergebnis erst nach dem Ende (Gesamtaudit 15.11., FF-22)
  until_close?: boolean
  archived?: boolean
  questions: ResultQuestion[]
}

export interface SurveyFilters {
  departments?: number[]
  member_types?: number[]
  board?: boolean
  age_min?: number | null
  age_max?: number | null
}

export interface Survey {
  id: number
  title: string
  description: string
  event: number | null
  event_title: string
  event_starts_at: string | null
  audience: Audience
  filters: SurveyFilters
  persons: number[]
  persons_named?: { id: number; name: string }[]
  names: NamesMode
  results: ResultsMode
  status: SurveyStatus
  closes_at: string | null
  remind_days: number | null
  keep_months: number
  opened_at: string | null
  closed_at: string | null
  purged_at: string | null
  participants: number
  invited: number | null
  follow_event: number | null
  version: number
  can_edit: boolean
  can_create_event: boolean
  questions?: SurveyQuestion[]
  result?: SurveyResult | null
  pending?: string[]
}

export interface SurveyChoices {
  units: { id: number; name: string }[]
  member_types: { id: number; name: string }[]
  events: {
    id: number
    title: string
    starts_at: string
    rsvp_enabled: boolean
    rsvp_deadline: string | null
  }[]
  board: boolean
}

export type SurveyMember = PickedMember & { name: string }

export const surveyApi = {
  list: (base: string) => api.get<Survey[]>(base),
  get: (base: string, id: number) => api.get<Survey>(`${base}${id}/`),
  create: (base: string, data: object) => api.post<Survey>(base, data),
  update: (base: string, survey: Survey, data: object) =>
    api.patch<Survey>(`${base}${survey.id}/`, { ...data, version: survey.version }),
  remove: (base: string, id: number) => api.del(`${base}${id}/`),
  start: (base: string, id: number) => api.post<Survey>(`${base}${id}/start/`),
  close: (base: string, id: number) => api.post<Survey>(`${base}${id}/close/`),
  copy: (base: string, id: number) => api.post<Survey>(`${base}${id}/copy/`),
  answerFor: (base: string, id: number, membership: number, answers: AnswerRow[]) =>
    api.post<Survey>(`${base}${id}/answers/`, { membership, answers }),
  eventFrom: (base: string, id: number, option: number) =>
    api.post<Survey>(`${base}${id}/event/`, { option }),
  choices: (base: string) => api.get<SurveyChoices>(`${base}options/`),
  count: (base: string, data: object) => api.post<{ count: number }>(`${base}count/`, data),
  members: (base: string, term: string) =>
    api.get<SurveyMember[]>(`${base}members/?suche=${encodeURIComponent(term)}`),
  export: (base: string, id: number, format: 'pdf' | 'xlsx') =>
    requestBlob('GET', `${base}${id}/export/?datei=${format}`),
}

export interface FollowEvent {
  id: number
  title: string
  starts_at: string
  ends_at: string
  all_day: boolean
  rsvp_enabled: boolean
  said_yes: boolean
  response: 'yes' | 'no' | 'maybe' | null
}

export interface MemberSurvey {
  id: number
  title: string
  description: string
  unit: string
  event: { id: number; title: string; starts_at: string } | null
  status: SurveyStatus
  closes_at: string | null
  names: NamesMode
  results_mode: ResultsMode
  anonymous: boolean
  answered: boolean
  can_answer: boolean
  can_change: boolean
  mine: AnswerRow[] | null
  questions: SurveyQuestion[]
  results: SurveyResult | null
  follow_event: FollowEvent | null
}

export const portalSurveyApi = {
  list: (access: number) => api.get<{ surveys: MemberSurvey[] }>(`/api/portal/${access}/surveys/`),
  answer: (access: number, id: number, answers: AnswerRow[]) =>
    api.post<MemberSurvey>(`/api/portal/${access}/surveys/${id}/answer/`, { answers }),
  withdraw: (access: number, id: number) =>
    api.del(`/api/portal/${access}/surveys/${id}/answer/`) as Promise<MemberSurvey>,
  follow: (access: number, id: number) =>
    api.post<MemberSurvey>(`/api/portal/${access}/surveys/${id}/follow/`),
}

export interface PublicSurvey {
  club: string
  imprint_key: string
  first_name: string
  survey: MemberSurvey
}

export const publicSurveyApi = {
  get: (token: string) => api.get<PublicSurvey>(`/api/public/survey/${token}/`),
  answer: (token: string, answers: AnswerRow[]) =>
    api.post<PublicSurvey>(`/api/public/survey/${token}/`, { answers }),
}
