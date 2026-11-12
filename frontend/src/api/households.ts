// Haushalte und Firmen (Konzept Familien, Haushalte und Firmen, H1): Mitglieder eines
// Vereins zu einer Familie oder Firma verbinden; Briefe an die Familie gehen gemeinsam.
import { api } from './client.ts'

export type HouseholdKind = 'family' | 'company'
export type HouseholdRole = 'adult' | 'child' | ''

export interface HouseholdMember {
  link: number
  membership: number
  first_name: string
  last_name: string
  title: string
  birth_date: string | null
  role: HouseholdRole
  valid_from: string
  valid_until: string | null
  /** gehört heute (oder ab einem späteren Beginn) dazu */
  current: boolean
}

export interface Household {
  id: number
  kind: HouseholdKind
  name: string
  note: string
  members: HouseholdMember[]
}

export interface HouseholdSuggestion {
  name: string
  street: string
  postal_code: string
  city: string
  members: {
    id: number
    first_name: string
    last_name: string
    birth_date: string | null
    household: number | null
  }[]
}

/** Haushalt in der Mitgliedsakte (aktuelle Zugehörigkeit mit den übrigen Mitgliedern) */
export interface MemberHousehold {
  id: number
  name: string
  kind: HouseholdKind
  role: HouseholdRole
  since: string
  others: { member_id: number; name: string; role: HouseholdRole }[]
}

const base = (org: number) => `/api/orgs/${org}/households/`

export const householdApi = {
  list: (org: number, params: { art?: HouseholdKind; ehemalige?: boolean } = {}) => {
    const q = new URLSearchParams()
    if (params.art) q.set('art', params.art)
    if (params.ehemalige) q.set('ehemalige', '1')
    const qs = q.toString()
    return api.get<Household[]>(`${base(org)}${qs ? `?${qs}` : ''}`)
  },
  get: (org: number, id: number) => api.get<Household>(`${base(org)}${id}/`),
  create: (org: number, data: { kind: HouseholdKind; name: string; note?: string }) =>
    api.post<Household>(base(org), data),
  update: (org: number, id: number, data: Partial<Pick<Household, 'kind' | 'name' | 'note'>>) =>
    api.patch<Household>(`${base(org)}${id}/`, data),
  remove: (org: number, id: number) => api.del(`${base(org)}${id}/`),
  addMember: (
    org: number,
    id: number,
    data: { membership: number; role?: HouseholdRole; valid_from?: string; move?: boolean },
  ) => api.post<Household>(`${base(org)}${id}/members/`, data),
  changeMember: (
    org: number,
    id: number,
    link: number,
    data: { valid_until?: string | null; role?: HouseholdRole },
  ) => api.patch<Household>(`${base(org)}${id}/members/${link}/`, data),
  deleteMember: (org: number, id: number, link: number) =>
    api.del(`${base(org)}${id}/members/${link}/`),
  suggestions: (org: number) => api.get<HouseholdSuggestion[]>(`${base(org)}suggestions/`),
}
