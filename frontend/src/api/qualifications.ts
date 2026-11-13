// Qualifikationen mit Ablaufdatum: Arten des Vereins, Nachweise am Mitglied, Übersicht.
import { api } from './client.ts'

export type QualificationStatus = 'valid' | 'expiring' | 'expired'

export interface QualificationType {
  id: number
  name: string
  description: string
  /** übliche Gültigkeit in Monaten (leer: unbefristet) */
  validity_months: number | null
  /** Erinnerung so viele Tage vor dem Ablauf (leer: keine) */
  remind_days: number | null
  /** nur Vermerk über die Einsicht (z. B. Führungszeugnis), ohne Bemerkung */
  inspection_only: boolean
  is_archived: boolean
  sort_order: number
  in_use: boolean
}

export interface Qualification {
  id: number
  kind: number
  kind_name: string
  inspection_only: boolean
  acquired_on: string
  valid_until: string | null
  note: string
  status: QualificationStatus
  /** maßgeblicher Nachweis dieser Art (sonst früherer, im Verlauf) */
  current: boolean
}

export interface QualificationRow {
  id: number
  member: number
  first_name: string
  last_name: string
  kind: number
  kind_name: string
  inspection_only: boolean
  acquired_on: string
  valid_until: string | null
  status: QualificationStatus
}

const base = (org: number) => `/api/orgs/${org}`
const records = (org: number, member: number) => `${base(org)}/members/${member}/qualifications/`

export const qualificationApi = {
  types: (org: number) => api.get<QualificationType[]>(`${base(org)}/qualification-types/`),
  createType: (org: number, data: Partial<QualificationType>) =>
    api.post<QualificationType>(`${base(org)}/qualification-types/`, data),
  updateType: (org: number, id: number, data: Partial<QualificationType>) =>
    api.patch<QualificationType>(`${base(org)}/qualification-types/${id}/`, data),
  deleteType: (org: number, id: number) => api.del(`${base(org)}/qualification-types/${id}/`),
  archiveType: (org: number, id: number) =>
    api.post<QualificationType>(`${base(org)}/qualification-types/${id}/archive/`),
  restoreType: (org: number, id: number) =>
    api.post<QualificationType>(`${base(org)}/qualification-types/${id}/restore/`),
  reorderTypes: (org: number, ids: number[]) =>
    api.post(`${base(org)}/qualification-types/reorder/`, { ids }),
  records: (org: number, member: number) => api.get<Qualification[]>(records(org, member)),
  addRecord: (org: number, member: number, data: Partial<Qualification>) =>
    api.post<Qualification>(records(org, member), data),
  updateRecord: (org: number, member: number, id: number, data: Partial<Qualification>) =>
    api.patch<Qualification>(`${records(org, member)}${id}/`, data),
  deleteRecord: (org: number, member: number, id: number) =>
    api.del(`${records(org, member)}${id}/`),
  overview: (org: number, params: { stand?: string; art?: string } = {}) => {
    const q = new URLSearchParams()
    if (params.stand) q.set('stand', params.stand)
    if (params.art) q.set('art', params.art)
    const s = q.toString()
    return api.get<QualificationRow[]>(`${base(org)}/qualifications/${s ? `?${s}` : ''}`)
  },
}

/** Tag plus Monate wie im Backend (31.1. + 1 Monat → 28./29.2.). */
export function addMonths(iso: string, months: number): string {
  const [y, m, d] = iso.split('-').map(Number)
  const total = m - 1 + months
  const year = y + Math.floor(total / 12)
  const month = (total % 12) + 1
  const last = new Date(Date.UTC(year, month, 0)).getUTCDate()
  const day = Math.min(d, last)
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}
