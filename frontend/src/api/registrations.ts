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
  /** Termin des Dachverbands: der Verein meldet seine Mitglieder gesammelt an (A8) */
  club_register?: boolean
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
  // Stufe A5 (fehlt bei älteren Ständen)
  catering?: boolean
  minors?: boolean
  health_allowed?: boolean
  addons?: AddOn[]
  questions?: Question[]
  // Stufe A4: öffentliches Formular (nur bei öffentlichen Terminen)
  public?: boolean
  public_url?: string | null
  // Stufe A8: Sammelanmeldung durch die Vereine (Dachverband)
  club_registration?: boolean
}

export type Per = 'person' | 'registration'

/** Zusatzleistung mit Auswahl, z. B. Busfahrt oder Menü */
export interface AddOn {
  id: number
  name: string
  name_en: string
  kind: 'meal' | 'other'
  per: Per
  required: boolean
  is_active: boolean
  choices: AddOnChoice[]
}

export interface AddOnChoice {
  id: number
  name: string
  name_en: string
  amount: string
  vat_rate: string | null
  capacity: number | null
  free: number | null
  is_active: boolean
  taken?: number
}

/** Zusatzfrage; „health“ sind Allergien und Unverträglichkeiten (nur mit Essen) */
export interface Question {
  id: number
  text: string
  text_en: string
  kind: 'text' | 'yesno' | 'choice' | 'health'
  choices: string[]
  required: boolean
  per: Per
  is_active: boolean
}

export type Answer = string | boolean

export interface Booking {
  id: number
  choice_id: number
  addon_id: number
  name: string
  amount: string
}

export interface Guardian {
  name: string
  phone: string
  email: string
  address?: string
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
  bookings?: Booking[]
  answers?: Record<string, Answer>
  guardians?: Guardian[]
  /** nur für die Verwaltung */
  health?: string
  /** Einlass vor Ort (A6), nur für die Verwaltung */
  checked_in_at?: string | null
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
  /** Eintrittskarten mit QR-Code als PDF (A6) */
  has_tickets?: boolean
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
  bookings?: Booking[]
  answers?: Record<string, Answer>
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
  /** Sammelanmeldung eines Vereins (A8) */
  club_id?: number | null
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
  /** Qualifikationen, die nach der Veranstaltung eingetragen werden dürfen (A6) */
  qualification_kinds?: { id: number; name: string }[]
  /** Sammelanmeldung durch die Vereine einstellbar (nur Dachverband, A8) */
  club_registration_possible?: boolean
  registrations: Registration[]
}

/** Sammelanmeldung des Vereins zu einem Termin seines Dachverbands (A8) */
export interface ClubRegistrations {
  event_id: number
  federation: string
  offer: Offer
  max_persons: number
  registered_members: number[]
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
    /** unter 18 am Veranstaltungstag (nur mit „Minderjährige möglich“) */
    minor?: boolean
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
  catering?: boolean
  minors?: boolean
  public?: boolean
  club_registration?: boolean
  addons?: AddOnInput[]
  questions?: QuestionInput[]
}

export interface AddOnInput {
  id?: number | null
  name: string
  name_en: string
  kind: 'meal' | 'other'
  per: Per
  required: boolean
  is_active: boolean
  choices: {
    id?: number | null
    name: string
    name_en: string
    amount: string
    vat_rate: string | null
    capacity: number | null
    is_active: boolean
  }[]
}

export interface QuestionInput {
  id?: number | null
  text: string
  text_en: string
  kind: Question['kind']
  choices: string[]
  required: boolean
  per: Per
  is_active: boolean
}

/** Zusatzleistungen (Zusatzleistung → Auswahl) und Antworten (Frage → Antwort) */
export interface ExtrasInput {
  addons?: Record<string, number | null>
  answers?: Record<string, Answer>
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
  guardians?: Guardian[]
}

export interface PersonInput extends ExtrasInput {
  membership_id?: number | null
  name?: string
  birth_date?: string | null
  price_id: number
  health?: string
  guardians?: Guardian[]
}

const url = (base: CalendarBase, eventId: number) => `${base}events/${eventId}/registration/`

/** Person beim Einlass (A6) */
export interface CheckInRow {
  id: number
  name: string
  price_name: string
  registration_id: number
  number: string
  contact: string
  paid_state: PaidState
  /** Abendkasse: Rechnung der Anmeldung und offener Betrag */
  invoice_id?: number | null
  invoice_number?: string
  outstanding?: string
  checked_in_at: string | null
  /** über welchen Scan-Link eingelassen (leer: in der Verwaltung) */
  checked_in_via?: string
  minor: boolean
  /** gebuchte Zusatzleistungen und wann sie eingelöst wurden */
  bookings?: { name: string; redeemed_at: string | null }[]
}

export interface QualificationResult {
  created: number
  existing: number
  guests: number
  checked_in_only: boolean
}

export interface CheckInList {
  event_id: number
  title: string
  can_edit: boolean
  /** darf an der Abendkasse bar kassieren (Rechnungen bearbeiten) */
  can_cash?: boolean
  participants: CheckInRow[]
  count: number
  checked_in: number
}

/** Scan-Link für Personal ohne Konto: Einlass oder eine Zusatzleistung */
export interface ScanLink {
  id: number
  label: string
  addon_id: number | null
  material_id?: number | null
  material_return?: boolean
  kind?: ScanKind
  station: string
  expires_at: string
  allow_search: boolean
  /** Kassen-Link: nimmt offene Gebühren bar an */
  cash?: boolean
  cashier?: string
  cash_account?: string
  cash_total?: string
  cash_takes?: { at: string; amount: string; invoice_number: string; name: string }[]
  revoked: boolean
  active: boolean
  created_at: string
  last_used_at: string | null
  scans: number
  url?: string
}

export interface Material {
  id: number
  name: string
  returnable: boolean
  is_active: boolean
}

export interface HandoutState {
  handed_out_at: string
  returned_at: string | null
  via: string
}

export interface LabelOptions {
  formats: string[]
  fields: string[]
  questions: { id: number; text: string }[]
  default_fields: string[]
}

export interface MaterialBoard {
  materials: Material[]
  rows: {
    id: number
    name: string
    number: string
    price_name: string
    items: Record<string, HandoutState | null>
  }[]
  counts: Record<string, { out: number; returned: number }>
  can_edit: boolean
  labels: LabelOptions
}

export interface ScanLinks {
  links: ScanLink[]
  addons: { id: number; name: string }[]
  materials: Material[]
  cash_accounts?: { id: number; name: string }[]
  default_expires_at: string
}

/** Scan-Seite für das Personal (ohne Konto) */
export interface ScanPage {
  organization: string
  event: string
  starts_at: string
  label: string
  station: string
  kind: ScanKind
  expires_at: string
  allow_search: boolean
  cash?: boolean
  cashier?: string
}

export type ScanKind = 'entry' | 'addon' | 'material_out' | 'material_return'

export interface ScanHit {
  /** Verweis auf die Person, nur an diesem Link und einige Stunden gültig */
  id: string
  name: string
  birth_date: string | null
  price_name: string
  number: string
  checked_in_at: string | null
}

export type ScanResultKind =
  | 'paid'
  | 'ok'
  | 'already'
  | 'unknown'
  | 'other'
  | 'cancelled'
  | 'waiting'
  | 'not_booked'
  | 'not_out'

export interface ScanResult {
  result: ScanResultKind
  valid: boolean
  message: string
  at: string | null
  card: {
    /** Verweis auf die Person (für die Kasse), keine fortlaufende Nummer */
    id?: string
    /** Kassen-Link: offener Betrag, bar anzunehmen */
    open_amount?: string | null
    name: string
    birth_date: string | null
    minor: boolean
    price_name: string
    number: string
    paid_state: PaidState
    checked_in_at: string | null
    bookings: {
      id: number
      addon_id: number
      name: string
      per_registration: boolean
      redeemed_at: string | null
    }[]
    materials?: {
      id: number
      name: string
      returnable: boolean
      handed_out_at: string | null
      returned_at: string | null
    }[]
  } | null
}

/** Termin des Dachverbands mit Sammelanmeldung (unter Meldungen, A8) */
export interface ClubOffer {
  event_id: number
  title: string
  starts_at: string
  closes_at: string
  state: string
  state_text: string
  persons: number
}

export interface CheckInResult {
  result: 'ok' | 'already' | 'undone' | 'unknown' | 'other' | 'cancelled'
  message: string
  participant: CheckInRow | null
}

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
    } & ExtrasInput & { health_consent?: boolean },
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
  /** Eintrittskarten einer Anmeldung als PDF (Verwaltung und Mitgliederbereich) */
  ticketsUrl: (base: CalendarBase, eventId: number, regId: number) =>
    `${url(base, eventId)}${regId}/tickets/`,
  checkIns: (base: CalendarBase, eventId: number) =>
    api.get<CheckInList>(`${url(base, eventId)}checkin/`),
  checkIn: (
    base: CalendarBase,
    eventId: number,
    data: { code?: string; participant?: number; undo?: boolean },
  ) => api.post<CheckInResult>(`${url(base, eventId)}checkin/`, data),
  club: (base: CalendarBase, eventId: number) =>
    api.get<ClubRegistrations>(`${url(base, eventId)}club/`),
  clubRegister: (
    base: CalendarBase,
    eventId: number,
    data: {
      persons: { membership_id: number; price_id: number }[]
      note: string
      terms_accepted: boolean
    },
  ) => api.post<ClubRegistrations>(`${url(base, eventId)}club/`, data),
  clubCancel: (base: CalendarBase, eventId: number, regId: number, participants: number[]) =>
    api.post<ClubRegistrations>(`${url(base, eventId)}club/${regId}/cancel/`, { participants }),
  scanLinks: (base: CalendarBase, eventId: number) =>
    api.get<ScanLinks>(`${url(base, eventId)}scan-links/`),
  addScanLink: (
    base: CalendarBase,
    eventId: number,
    data: {
      label: string
      addon: number | null
      material?: number | null
      material_return?: boolean
      cash_account?: number | null
      cashier?: string
      expires_at?: string | null
      allow_search?: boolean
    },
  ) => api.post<ScanLink>(`${url(base, eventId)}scan-links/`, data),
  revokeScanLink: (base: CalendarBase, eventId: number, id: number) =>
    api.del(`${url(base, eventId)}scan-links/${id}/`),
  scanPage: (token: string) => api.get<ScanPage>(`/api/public/scan/${token}/`),
  scan: (token: string, data: { code?: string; participant?: string }) =>
    api.post<ScanResult>(`/api/public/scan/${token}/`, data),
  scanCash: (token: string, data: { participant: string; request_key: string }) =>
    api.post<ScanResult>(`/api/public/scan/${token}/cash/`, data),
  scanSearch: (token: string, q: string) =>
    api.get<{ results: ScanHit[] }>(`/api/public/scan/${token}/search/?q=${encodeURIComponent(q)}`),
  clubOffers: (org: number) =>
    api.get<{ federation: string; offers: ClubOffer[] }>(
      `/api/orgs/${org}/registrations/club-offers/`,
    ),
  badgesUrl: (base: CalendarBase, eventId: number, format = '', fields: string[] = []) =>
    `${url(base, eventId)}badges/${
      format ? `?format=${format}&fields=${encodeURIComponent(fields.join(','))}` : ''
    }`,
  materials: (base: CalendarBase, eventId: number) =>
    api.get<MaterialBoard>(`${url(base, eventId)}materials/`),
  addMaterial: (base: CalendarBase, eventId: number, data: { name: string; returnable: boolean }) =>
    api.post<Material>(`${url(base, eventId)}materials/`, data),
  removeMaterial: (base: CalendarBase, eventId: number, id: number) =>
    api.del(`${url(base, eventId)}materials/${id}/`),
  handout: (
    base: CalendarBase,
    eventId: number,
    data: { participant: number; material: number; action: 'out' | 'return' | 'undo' },
  ) => api.post<MaterialBoard>(`${url(base, eventId)}materials/handout/`, data),
  certificatesUrl: (base: CalendarBase, eventId: number) => `${url(base, eventId)}certificates/`,
  addQualification: (
    base: CalendarBase,
    eventId: number,
    data: { kind: number; acquired_on?: string | null },
  ) => api.post<QualificationResult>(`${url(base, eventId)}qualification/`, data),
  exportUrl: (base: CalendarBase, eventId: number, health = false) =>
    `${url(base, eventId)}export/${health ? '?health=1' : ''}`,
  member: (base: CalendarBase, eventId: number) => api.get<MemberRegistrations>(url(base, eventId)),
  register: (
    base: CalendarBase,
    eventId: number,
    data: {
      persons: PersonInput[]
      note: string
      terms_accepted: boolean
      health_consent?: boolean
    } & ExtrasInput,
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

// --- Öffentliche Anmeldung (Stufe A4), ohne Konto ---

export interface PublicEvent {
  id?: number
  title: string
  starts_at: string
  ends_at: string
  all_day: boolean
  location: string
  address: string
  directions?: string
  description?: string
  programme?: string
}

export interface PublicRegistrationForm {
  organization: string
  logo_url?: string | null
  website_url?: string | null
  privacy_text: string
  event: PublicEvent
  offer: Offer
  cancel_text: string
  challenge?: { token: string; salt: string; difficulty: number }
  key?: string
}

export interface PublicSubmission extends ExtrasInput {
  name: string
  email: string
  phone: string
  address: string
  persons: PersonInput[]
  note: string
  terms_accepted: boolean
  privacy_accepted: boolean
  health_consent: boolean
  language: string
  challenge?: string
  nonce?: number
  homepage: string
}

export interface PublicMine {
  organization: string
  event: PublicEvent
  offer: Offer
  registration: Registration
  cancel_text: string
  /** nur nach dem Bestätigen: Schlüssel für den Link „Anmeldung ansehen“ */
  token?: string | null
}

const pub = (path: string) => `/api/public/registration/${path}`

export const publicRegistrationApi = {
  form: (key: string, language: string) =>
    api.get<PublicRegistrationForm>(
      `${pub(encodeURIComponent(key))}/?lang=${encodeURIComponent(language)}`,
    ),
  submit: (key: string, data: PublicSubmission) =>
    api.post<{ status: string }>(`${pub(encodeURIComponent(key))}/`, data),
  confirm: (token: string) =>
    api.post<PublicMine>(`${pub(`confirm/${encodeURIComponent(token)}`)}/`),
  mine: (token: string) => api.get<PublicMine>(`${pub(`mine/${encodeURIComponent(token)}`)}/`),
  ticketsUrl: (token: string) => `${pub(`mine/${encodeURIComponent(token)}`)}/tickets/`,
  quote: (token: string, participants: number[] = []) =>
    api.get<FeeQuote>(
      `${pub(`mine/${encodeURIComponent(token)}`)}/cancel/${
        participants.length ? `?participants=${participants.join(',')}` : ''
      }`,
    ),
  cancel: (token: string, participants: number[] = []) =>
    api.post<PublicMine>(
      `${pub(`mine/${encodeURIComponent(token)}`)}/cancel/`,
      participants.length ? { participants } : {},
    ),
}
