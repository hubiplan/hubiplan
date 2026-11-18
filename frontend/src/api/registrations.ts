// Verbindliche Anmeldung mit Teilnahmegebühr am Termin (konzepte/veranstaltungen-anmeldung-gebuehr.md).
// Verwaltung: /api/orgs/<id>/events/<pk>/registration/…, Mitglied: /api/portal/<id>/events/<pk>/registration/…
import { api } from './client.ts'
import type { CalendarBase } from './events.ts'

export type RegistrationState = 'not_yet' | 'open' | 'closed' | 'full' | 'cancelled'
export type PaidState = 'free' | 'open' | 'partly' | 'paid' | 'cancelled' | 'waiting'
export type Applies = 'all' | 'members' | 'guests'

/** Kurzer Stand am Termin (EventDetail.registration) */
export interface RegistrationBrief {
  enabled: boolean
  state?: RegistrationState
  state_text?: string
  closes_at?: string
  free?: number | null
  can_setup?: boolean
  can_view_list?: boolean
  can_register?: boolean
}

export interface PriceStep {
  id?: number
  name: string
  amount: string
  until_date: string | null
  until_count: number | null
  taken?: number
}

export interface Price {
  id: number
  name: string
  name_en: string
  applies: Applies
  age_from: number | null
  age_to: number | null
  capacity: number | null
  free: number | null
  vat_rate: string | null
  is_active: boolean
  current: {
    id: number
    name: string
    amount: string
    until_date: string | null
    remaining: number | null
  } | null
  next: { name: string; amount: string; until_date: string | null } | null
  steps?: PriceStep[]
  taken?: number
}

export interface Offer {
  id: number
  state: RegistrationState
  state_text: string
  opens_at: string | null
  closes_at: string
  is_open: boolean
  capacity: number | null
  free: number | null
  taken: number
  max_persons: number
  guests_allowed: boolean
  due_days: number
  category: number | null
  terms: string
  prices: Price[]
  waitlist: boolean
  waiting: number
  substitute_allowed: boolean
  cancel_rules: CancelRule[]
  cancel_fee_fixed: string | null
  expire_unpaid_days: number | null
}

/** Stornostaffel: „weniger als {days} Tage vorher: {percent} %“ */
export interface CancelRule {
  days: number
  percent: number
}

/** Vorschau der Stornogebühr */
export interface FeeQuote {
  base: string
  percent: number
  fee: string
  free_reason: '' | 'waitlist' | 'moved_up' | 'event_cancelled' | 'waived' | 'replaced'
}

export interface Participant {
  id: number
  name: string
  membership_id: number | null
  price_id: number
  price_name: string
  amount: string
  status: 'active' | 'cancelled'
}

export interface InvoiceBrief {
  id: number
  number: string
  status: string
  total: string
  paid: string
  due_date: string
}

export interface Registration {
  id: number
  number: string
  status: 'registered' | 'waiting' | 'cancelled'
  name: string
  total: string
  paid_state: PaidState
  created_at: string
  cancelled_at: string | null
  participants: Participant[]
  invoice: InvoiceBrief | null
  waitlist_position: number | null
  moved_up_at: string | null
  free_cancel_until: string | null
  cancel_fee: string
  fee_invoice: InvoiceBrief | null
  // nur im Mitgliederbereich
  can_cancel?: boolean
  can_substitute?: boolean
  // nur für die Verwaltung
  membership_id?: number | null
  email?: string
  phone?: string
  address?: string
  note?: string
  source?: string
  source_label?: string
  cancel_reason?: string
}

export interface BoardRegistrations {
  event_id: number
  offer: Offer | null
  summary?: {
    registrations: number
    persons: number
    waiting: number
    total: string
    paid: string
    open: string
    fees: string
    refund: string
  }
  can_edit: boolean
  can_set_prices: boolean
  registrations: Registration[]
}

export interface MemberRegistrations {
  event_id: number
  offer: Offer
  can_cancel: boolean
  persons: {
    membership_id: number
    name: string
    self: boolean
    registered: boolean
    has_birth_date: boolean
  }[]
  mine: Registration[]
}

export interface PriceInput {
  id?: number | null
  name: string
  name_en?: string
  applies: Applies
  age_from: number | null
  age_to: number | null
  capacity: number | null
  vat_rate: string | null
  is_active: boolean
  steps: { name: string; amount: string; until_date: string | null; until_count: number | null }[]
}

export interface SetupInput {
  opens_at: string | null
  closes_at: string
  is_open: boolean
  capacity: number | null
  max_persons: number
  guests_allowed: boolean
  due_days: number
  category: number | null
  terms: string
  waitlist: boolean
  substitute_allowed: boolean
  cancel_rules: CancelRule[]
  cancel_fee_fixed: string | null
  expire_unpaid_days: number | null
  prices: PriceInput[]
}

export interface CancelInput {
  reason?: string
  participants?: number[] | null
  waive?: boolean
}

export interface SubstituteInput {
  membership_id?: number | null
  name?: string
  birth_date?: string | null
}

export interface PersonInput {
  membership_id?: number | null
  name?: string
  birth_date?: string | null
  price_id: number
}

const url = (base: CalendarBase, eventId: number) => `${base}events/${eventId}/registration/`

export const registrationApi = {
  board: (base: CalendarBase, eventId: number) => api.get<BoardRegistrations>(url(base, eventId)),
  save: (base: CalendarBase, eventId: number, data: SetupInput) =>
    api.put<BoardRegistrations>(url(base, eventId), data),
  remove: (base: CalendarBase, eventId: number) => api.del(url(base, eventId)),
  add: (
    base: CalendarBase,
    eventId: number,
    data: {
      membership_id?: number | null
      name?: string
      email?: string
      phone?: string
      address?: string
      note?: string
      persons: PersonInput[]
    },
  ) => api.post<BoardRegistrations>(`${url(base, eventId)}list/`, data),
  cancel: (base: CalendarBase, eventId: number, regId: number, data: CancelInput = {}) =>
    api.post<BoardRegistrations>(`${url(base, eventId)}${regId}/cancel/`, data),
  quote: (base: CalendarBase, eventId: number, regId: number, participants: number[] = []) =>
    api.get<FeeQuote>(
      `${url(base, eventId)}${regId}/cancel/${participants.length ? `?participants=${participants.join(',')}` : ''}`,
    ),
  substitute: (
    base: CalendarBase,
    eventId: number,
    regId: number,
    participantId: number,
    data: SubstituteInput,
  ) =>
    api.post<BoardRegistrations>(
      `${url(base, eventId)}${regId}/participants/${participantId}/`,
      data,
    ),
  exportUrl: (base: CalendarBase, eventId: number) => `${url(base, eventId)}export/`,
  member: (base: CalendarBase, eventId: number) => api.get<MemberRegistrations>(url(base, eventId)),
  register: (
    base: CalendarBase,
    eventId: number,
    data: { persons: PersonInput[]; note: string; terms_accepted: boolean },
  ) => api.post<MemberRegistrations>(url(base, eventId), data),
  cancelMine: (base: CalendarBase, eventId: number, regId: number, participants: number[] = []) =>
    api.post<MemberRegistrations>(
      `${url(base, eventId)}${regId}/cancel/`,
      participants.length ? { participants } : {},
    ),
  substituteMine: (
    base: CalendarBase,
    eventId: number,
    regId: number,
    participantId: number,
    data: SubstituteInput,
  ) =>
    api.post<MemberRegistrations>(
      `${url(base, eventId)}${regId}/participants/${participantId}/`,
      data,
    ),
}
