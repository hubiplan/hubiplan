import { api } from './client.ts'
import type { ResponseStatus } from './events.ts'

/** Rückmeldeseite hinter dem Link aus der Mail (ohne Anmeldung). */
export interface PublicRsvp {
  club: string
  owner: string
  imprint_key: string
  first_name: string
  event: {
    title: string
    starts_at: string
    ends_at: string
    all_day: boolean
    when: string
    location: string
    address: string
    description: string
    is_cancelled: boolean
    cancel_note: string
  }
  attachments: { id: number; name: string; size: number; url: string }[]
  rsvp: {
    deadline: string | null
    capacity: number | null
    free: number | null
    guests_allowed: boolean
    max_guests: number
    maybe_allowed: boolean
    note_allowed: boolean
    note_question: string
    can_respond: boolean
    reason: string
    mine: { status: ResponseStatus; guests: number; note: string } | null
  }
}

export const publicRsvpApi = {
  get: (token: string) => api.get<PublicRsvp>(`/api/public/rsvp/${token}/`),
  save: (token: string, data: { status: ResponseStatus; guests: number; note: string }) =>
    api.post<PublicRsvp>(`/api/public/rsvp/${token}/`, data),
}
