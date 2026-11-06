import { api } from './client.ts'
import type { StockKind } from './materials.ts'

export interface BookingRules {
  enabled: boolean
  approval: boolean
  buffer_before: number
  buffer_after: number
  horizon_days: number
  website: 'off' | 'busy' | 'titles'
}

export interface BookableItem {
  id: number
  kind: StockKind
  inventory_number: string
  title: string
  facility: number | null
  facility_type: string
  condition: string
  rules: BookingRules
  can_book: boolean
  can_manage: boolean
}

export type BookingStatus = 'requested' | 'confirmed' | 'rejected' | 'cancelled'

export interface Booking {
  id: number
  item: number
  item_title: string
  title: string
  details: boolean
  note: string
  starts_at: string
  ends_at: string
  all_day: boolean
  repeat: 'none' | 'weekly' | 'monthly' | 'yearly'
  repeat_interval: number
  repeat_until: string | null
  status: BookingStatus
  visibility: 'public' | 'members' | 'board'
  contact: { name?: string; email?: string; phone?: string }
  event: number | null
  event_title: string
  competition: number | null
  competition_title: string
  needs_review: boolean
  own: boolean
  booked_by: string
  can_manage: boolean
  can_cancel: boolean
  version: number
  loan: boolean
  handed_out_at: string | null
  handed_out_by: string
  returned_at: string | null
  returned_by: string
  exceptions: string[]
}

export interface Occurrence {
  booking: number
  item: number
  item_title: string
  title: string
  starts_at: string
  ends_at: string
  original_start: string
  all_day: boolean
  status: BookingStatus
  series: boolean
  own: boolean
  needs_review: boolean
}

export interface BookingConflict {
  booking: number
  starts_at: string
  ends_at: string
}

export const bookingApi = {
  items: (base: string) =>
    api.get<{ items: BookableItem[]; can_manage_all: boolean }>(`${base}items/`),
  list: (base: string, query: string) =>
    api.get<{ occurrences: Occurrence[]; requests: Booking[] }>(`${base}?${query}`),
  get: (base: string, id: number) => api.get<Booking>(`${base}${id}/`),
  create: (base: string, data: object) => api.post<Booking>(base, data),
  update: (base: string, booking: Booking, data: object) =>
    api.patch<Booking>(`${base}${booking.id}/`, { ...data, version: booking.version }),
  decide: (base: string, booking: Booking, action: 'confirm' | 'reject' | 'cancel') =>
    api.post<Booking>(`${base}${booking.id}/decision/`, { action, version: booking.version }),
  handover: (
    base: string,
    booking: Booking,
    action: 'out' | 'return' | 'undo',
    extra: { update_item?: boolean; condition?: string; condition_note?: string } = {},
  ) =>
    api.post<Booking>(`${base}${booking.id}/handover/`, {
      action,
      version: booking.version,
      ...extra,
    }),
  skip: (base: string, booking: Booking, originalStart: string, restore = false) =>
    api.post<Booking>(`${base}${booking.id}/skip/`, {
      original_start: originalStart,
      restore,
      version: booking.version,
    }),
}
