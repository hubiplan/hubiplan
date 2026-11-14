// Terminkalender: gleiche Schnittstelle für Vorstand, Abteilung und Mitgliederbereich.
import { api } from './client.ts'
import { t } from '../i18n/index.ts'

export type Visibility = 'public' | 'members' | 'board'
export type Repeat = 'none' | 'weekly' | 'monthly' | 'yearly'

export interface EventCircular {
  id: number
  subject: string
  status: 'draft' | 'sending' | 'sent'
  status_label: string
  sent_at: string | null
}

export interface EventCategory {
  id: number
  name: string
  color: string
  is_active?: boolean
}

export interface Occurrence {
  key: string
  event_id: number
  title: string
  starts_at: string
  ends_at: string
  original_start: string
  all_day: boolean
  hide_end_time?: boolean
  location: string
  address: string
  category: EventCategory | null
  visibility: Visibility
  is_cancelled: boolean
  note: string
  is_moved: boolean
  is_series: boolean
  changed_at: string | null
  owner: string
  level: 'federation' | 'club' | 'department'
  department_id: number | null
  own: boolean
  can_edit: boolean
  rsvp_enabled: boolean
  /** Fremder Kalender (Vereinsplaner, iCal), aus dem der Termin stammt */
  source?: string | null
  /** Nur im Mitgliederbereich: eigene Rückmeldung (null = noch offen) */
  my_response?: ResponseStatus | null
}

/** Persönliches Kalender-Abo: den Link gibt es nur direkt nach dem Erstellen. */
export interface FeedInfo {
  active: boolean
  ics_url: string | null
}

export type ResponseStatus = 'yes' | 'no' | 'maybe'
export type ResponseSource = 'member' | 'board' | 'link'

export interface MyResponse {
  status: ResponseStatus
  guests: number
  note: string
  source: ResponseSource
  updated_at: string
}

export interface RsvpInfo {
  enabled: boolean
  deadline: string | null
  capacity: number | null
  guests_allowed: boolean
  max_guests: number
  maybe_allowed?: boolean
  note_allowed?: boolean
  note_question?: string
  free?: number
  mine?: MyResponse | null
  can_respond?: boolean
  reason?: string
  can_view_list?: boolean
  can_enter?: boolean
  summary?: { yes: number; no: number; maybe?: number; guests: number; persons: number }
}

export interface ResponseRow {
  membership_id: number
  name: string
  club_number: string
  departments: string
  status: ResponseStatus | null
  guests: number
  note: string
  source: ResponseSource | null
  updated_at: string | null
}

export interface ResponseList {
  event_id: number
  scope: 'all' | 'department'
  summary: {
    yes: number
    no: number
    maybe?: number
    guests: number
    persons: number
    open: number
  }
  capacity: number | null
  items: ResponseRow[]
  open: { membership_id: number; name: string; departments: string }[]
}

export interface EventList {
  from: string
  to: string
  items: Occurrence[]
  can_manage: boolean
  rsvp_allowed?: boolean
  categories: EventCategory[]
  /** Vereinskalender: Untereinheiten ohne eigene Verwaltung, für die der Vorstand Termine anlegt */
  units?: EventUnit[]
}

export interface EventUnit {
  id: number
  name: string
  /** Pfad im Baum, z. B. „Korps › 1. Zug“ */
  path: string
  depth: number
}

export interface Attachment {
  id: number
  /** Datei: hier hochgeladen; Dokument: verknüpft aus der Ablage (neueste Fassung) */
  kind?: 'file' | 'document'
  name: string
  file_name?: string
  size: number
  content_type: string
  /** Verknüpftes Dokument liegt im Papierkorb oder ist gelöscht */
  available?: boolean
  /** Bei öffentlichen Terminen auch auf der Webseite angeboten */
  on_website?: boolean
  url: string
}

export interface LinkableDocument {
  id: number
  title: string
  folder: string
  folder_visibility: string
  /** Ordner enger sichtbar als der Termin: Verknüpfen gibt das Dokument frei */
  narrower: boolean
}

export interface SeriesException {
  original_start: string
  is_cancelled: boolean
  starts_at: string | null
  ends_at: string | null
  note: string
}

export interface EventDetail {
  id: number
  title: string
  description: string
  location: string
  address: string
  directions?: string
  latitude?: number | null
  longitude?: number | null
  map_links?: MapLinks
  category: EventCategory | null
  all_day: boolean
  hide_end_time?: boolean
  starts_at: string
  ends_at: string
  visibility: Visibility
  visibility_label: string
  repeat: Repeat
  repeat_label: string
  repeat_interval: number
  repeat_until: string | null
  is_cancelled: boolean
  cancel_note: string
  changed_at: string | null
  owner: string
  level: string
  department_id: number | null
  can_edit: boolean
  attachments: Attachment[]
  exceptions: SeriesException[]
  rsvp: RsvpInfo
  /** Fremder Kalender, aus dem der Termin stammt (nur lesbare Kopie) */
  source?: { name: string; kind: ExternalKind; kind_label: string } | null
  /** Fremden Termin hier ausblenden (Vorstand der Einheit) */
  can_hide?: boolean
  /** Veranstaltungsfinanzen (nur mit Kassenrecht): zugeordnete Veranstaltung */
  project?: { id: number; name: string } | null
  can_link_project?: boolean
  // Was am Termin hängt (nur mit Modul und Leserecht geliefert)
  meeting?: { id: number; status_label: string } | null
  helper_plans?: { id: number; title: string; status_label: string }[]
  can_create_helper_plan?: boolean
  /** Rundschreiben zu diesem Termin (nur Bearbeitende, mit Modul Rundschreiben) */
  circulars?: EventCircular[]
  can_circular?: boolean
  bookings?: { id: number; item: string; status_label: string }[]
  remind_days?: number | null
  reminded_at?: string | null
  /** Weitergabe nach oben/unten: Angabe am Termin, null = Voreinstellung (nur Bearbeiter) */
  share_up?: boolean | null
  share_down?: boolean | null
  share_defaults?: { up: boolean; down: boolean }
}

/** Routenlinks zum Ort (nur Links, keine eingebettete Karte) */
export interface MapLinks {
  osm?: string
  google?: string
}

export interface EventInput {
  /** Vereinskalender: Untereinheit, für die der Termin gilt (null = die Einheit selbst) */
  department_id?: number | null
  title: string
  description: string
  location: string
  address: string
  directions: string
  latitude: number | null
  longitude: number | null
  category: number | null
  all_day: boolean
  hide_end_time?: boolean
  starts_at: string
  ends_at: string
  visibility: Visibility
  repeat: Repeat
  repeat_interval: number
  repeat_until: string | null
  is_cancelled: boolean
  cancel_note: string
  rsvp_enabled: boolean
  rsvp_deadline: string | null
  rsvp_capacity: number | null
  rsvp_guests: boolean
  rsvp_maybe: boolean
  rsvp_note: boolean
  rsvp_note_question: string
  remind_days: number | null
  /** Weitergabe nach oben/unten; null = wie bei der Einheit voreingestellt */
  share_up?: boolean | null
  share_down?: boolean | null
  /** Eingeladene per E-Mail benachrichtigen */
  notify?: boolean
}

/** Voreinstellung, ob die eigenen Termine nach oben bzw. unten weitergegeben werden */
export interface Sharing {
  share_up: boolean
  share_down: boolean
  up_possible: boolean
  down_possible: boolean
  /** false: entscheidet die Einheit darüber (keine eigene Verwaltung des Kalenders) */
  editable: boolean
  /** Untereinheiten direkt darunter, über die dieser Kalender entscheidet */
  units: {
    id: number
    name: string
    share_up: boolean
    share_down: boolean
    has_children: boolean
    /** entscheidet selbst */
    own_admin: boolean
  }[]
}

export interface Publication {
  is_public: boolean
  ics_url: string | null
  json_url: string | null
}

export type ExternalKind = 'vereinsplaner' | 'ical'

/** Fremder Kalender, dessen Termine HUBIplan stündlich abholt */
export interface ExternalCalendar {
  id: number
  name: string
  kind: ExternalKind
  kind_label: string
  has_token: boolean
  has_secret: boolean
  category: EventCategory | null
  visibility: Visibility
  share_down: boolean
  is_active: boolean
  last_sync_at: string | null
  last_successful_sync_at?: string | null
  last_error: string
  event_count: number
  stale_hidden?: boolean
  hidden: { key: string; title: string; starts_at: string }[]
}

export interface ExternalCalendarInput {
  name: string
  kind: ExternalKind
  /** Vereinsplaner: Token; iCal: Link. Leer lassen = unverändert */
  token: string
  secret: string
  category: number | null
  visibility: Visibility
  share_down: boolean
  is_active: boolean
}

export const VISIBILITY_LABELS: Record<Visibility, string> = {
  get public() {
    return t('nach außen öffentlich')
  },
  get members() {
    return t('Mitglieder')
  },
  get board() {
    return t('nur Vorstand')
  },
}

export const REPEAT_LABELS: Record<Repeat, string> = {
  get none() {
    return t('einmalig')
  },
  get weekly() {
    return t('wöchentlich')
  },
  get monthly() {
    return t('monatlich')
  },
  get yearly() {
    return t('jährlich')
  },
}

/** Basis-URL eines Kalenders, z. B. `/api/orgs/7/` oder `/api/depts/3/`. */
export type CalendarBase = string

export const calendarBase = {
  org: (id: number) => `/api/orgs/${id}/`,
  dept: (id: number) => `/api/depts/${id}/`,
  portal: (id: number) => `/api/portal/${id}/`,
}

export const eventApi = {
  list: (base: CalendarBase, from: string, to: string) =>
    api.get<EventList>(`${base}events/?from=${from}&to=${to}`),
  upcoming: (base: CalendarBase, from: string, to: string) =>
    api.get<EventList>(`${base}events/?from=${from}&to=${to}&upcoming=1`),
  get: (base: CalendarBase, id: number) => api.get<EventDetail>(`${base}events/${id}/`),
  create: (base: CalendarBase, data: EventInput) => api.post<EventDetail>(`${base}events/`, data),
  update: (base: CalendarBase, id: number, data: Partial<EventInput>) =>
    api.patch<EventDetail>(`${base}events/${id}/`, data),
  remove: (base: CalendarBase, id: number) => api.del(`${base}events/${id}/`),
  setProject: (base: CalendarBase, id: number, data: { project?: number | null; create?: true }) =>
    api.post<EventDetail>(`${base}events/${id}/project/`, data),
  notify: (base: CalendarBase, id: number, kind: 'change' | 'cancel') =>
    api.post(`${base}events/${id}/notify/`, { kind }),
  setOccurrence: (
    base: CalendarBase,
    id: number,
    data: {
      original_start: string
      is_cancelled?: boolean
      starts_at?: string | null
      ends_at?: string | null
      note?: string
    },
  ) => api.put<EventDetail>(`${base}events/${id}/occurrence/`, data),
  resetOccurrence: (base: CalendarBase, id: number, originalStart: string) =>
    api.delWith<EventDetail>(`${base}events/${id}/occurrence/`, { original_start: originalStart }),
  upload: (base: CalendarBase, id: number, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<EventDetail>(`${base}events/${id}/attachments/`, form)
  },
  removeAttachment: (url: string) => api.del(url),
  showOnWebsite: (url: string, value: boolean) =>
    api.patch<EventDetail>(url, { on_website: value }),
  linkableDocuments: (base: CalendarBase, id: number) =>
    api.get<{ documents: LinkableDocument[] }>(`${base}events/${id}/attachments/`),
  linkDocument: (base: CalendarBase, id: number, document: number) =>
    api.post<EventDetail>(`${base}events/${id}/attachments/`, { document }),
  categories: (base: CalendarBase) => api.get<EventCategory[]>(`${base}events/categories/`),
  createCategory: (base: CalendarBase, data: { name: string; color: string }) =>
    api.post<EventCategory>(`${base}events/categories/`, data),
  updateCategory: (base: CalendarBase, id: number, data: Partial<EventCategory>) =>
    api.patch<EventCategory>(`${base}events/categories/${id}/`, data),
  removeCategory: (base: CalendarBase, id: number) => api.del(`${base}events/categories/${id}/`),
  externals: (base: CalendarBase) => api.get<ExternalCalendar[]>(`${base}events/external/`),
  createExternal: (base: CalendarBase, data: Partial<ExternalCalendarInput>) =>
    api.post<ExternalCalendar>(`${base}events/external/`, data),
  updateExternal: (base: CalendarBase, id: number, data: Partial<ExternalCalendarInput>) =>
    api.patch<ExternalCalendar>(`${base}events/external/${id}/`, data),
  removeExternal: (base: CalendarBase, id: number) => api.del(`${base}events/external/${id}/`),
  syncExternal: (base: CalendarBase, id: number) =>
    api.post<ExternalCalendar>(`${base}events/external/${id}/sync/`, {}),
  showExternal: (base: CalendarBase, id: number, key: string) =>
    api.post<ExternalCalendar>(`${base}events/external/${id}/show/`, { key }),
  hide: (base: CalendarBase, id: number) => api.post(`${base}events/${id}/hide/`, {}),
  publication: (base: CalendarBase) => api.get<Publication>(`${base}events/publication/`),
  sharing: (base: CalendarBase) => api.get<Sharing>(`${base}events/sharing/`),
  updateSharing: (
    base: CalendarBase,
    data: Partial<Pick<Sharing, 'share_up' | 'share_down'>> & {
      units?: { id: number; share_up?: boolean; share_down?: boolean }[]
    },
  ) => api.patch<Sharing>(`${base}events/sharing/`, data),
  publish: (base: CalendarBase, isPublic: boolean, renew = false) =>
    api.put<Publication>(`${base}events/publication/`, { is_public: isPublic, renew }),
  programUrl: (base: CalendarBase, year: number) => `${base}events/program/?year=${year}`,
  icsUrl: (base: CalendarBase, id: number) => `${base}events/${id}/ics/`,
  respond: (
    base: CalendarBase,
    id: number,
    data: { status: ResponseStatus; guests: number; note: string },
  ) => api.put<EventDetail>(`${base}events/${id}/response/`, data),
  withdraw: (base: CalendarBase, id: number) =>
    api.delWith<EventDetail>(`${base}events/${id}/response/`, {}),
  responses: (base: CalendarBase, id: number) =>
    api.get<ResponseList>(`${base}events/${id}/responses/`),
  enterResponse: (
    base: CalendarBase,
    id: number,
    data: { membership_id: number; status: ResponseStatus; guests: number; note: string },
  ) => api.put<MyResponse>(`${base}events/${id}/responses/`, data),
  removeResponse: (base: CalendarBase, id: number, membershipId: number) =>
    api.del(`${base}events/${id}/responses/${membershipId}/`),
  exportUrl: (base: CalendarBase, id: number, type: 'xlsx' | 'pdf') =>
    `${base}events/${id}/responses/export/?type=${type}`,
  feed: (base: CalendarBase) => api.get<FeedInfo>(`${base}events/feed/`),
  renewFeed: (base: CalendarBase) => api.put<FeedInfo>(`${base}events/feed/`, {}),
  removeFeed: (base: CalendarBase) => api.delWith<FeedInfo>(`${base}events/feed/`, {}),
}
