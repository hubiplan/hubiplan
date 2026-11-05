import { api } from './client.ts'

export interface Material {
  id: number
  inventory_number: string
  title: string
  description: string
  purpose: string
  location_kind: 'member' | 'address' | 'unknown'
  member: number | null
  member_name: string
  address: Record<string, string>
  location_note: string
  condition: 'ready' | 'limited' | 'defective' | 'retired'
  condition_note: string
  version: number
  music_equipment?: { id: number; loaned: boolean; due_date: string | null }
  deleted_at: string | null
  location_review: boolean
  usage_review?: boolean
  photo_url: string | null
  next_use?: { title: string; starts_at: string; all_day?: boolean } | null
  events?: MaterialEvent[]
  todos?: { id: number; title: string; status: string }[]
  documents?: { id: number; title: string }[]
  uses?: {
    event: number
    title: string
    starts_at: string
    original_start: string
    all_day?: boolean
    kind: string
  }[]
}

export interface MaterialEvent {
  id: number
  event: number
  title: string
  kind: 'event' | 'series' | 'occurrence' | 'exclude'
  original_start: string | null
  all_day?: boolean
  valid_from: string | null
  valid_until: string | null
  note: string
  needs_review: boolean
  cancelled: boolean
}

export interface MaterialChoice {
  id: number
  title: string
  series?: boolean
  starts_at?: string
}

export const materialApi = {
  list: (base: string, query = '') =>
    api.get<{ items: Material[]; count: number; page: number; can_edit: boolean }>(
      `${base}?${query}`,
    ),
  get: (base: string, id: number, trash = false) =>
    api.get<Material>(`${base}${id}/${trash ? '?trash=1' : ''}`),
  create: (base: string, data: object) => api.post<Material>(base, data),
  update: (base: string, id: number, data: object) => api.patch<Material>(`${base}${id}/`, data),
  link: (base: string, item: Material, data: object) =>
    api.post<Material>(`${base}${item.id}/links/`, { ...data, version: item.version }),
  remove: (base: string, item: Material) =>
    api.delWith<void>(`${base}${item.id}/`, { version: item.version }),
  restore: (base: string, item: Material) =>
    api.post<Material>(`${base}${item.id}/restore/`, { version: item.version }),
}
