// Haushalte und Firmen (Konzept Familien, Haushalte und Firmen, H1): Mitglieder eines
// Vereins zu einer Familie oder Firma verbinden; Briefe an die Familie gehen gemeinsam.
import type { Mandate } from './billing.ts'
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
  /** Beitrag läuft über die Rechnung an den Zahler des Haushalts (H2) */
  pays_via: boolean
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
    data: {
      membership: number
      role?: HouseholdRole
      valid_from?: string
      move?: boolean
      pays_via?: boolean
    },
  ) => api.post<Household>(`${base(org)}${id}/members/`, data),
  changeMember: (
    org: number,
    id: number,
    link: number,
    data: { valid_until?: string | null; role?: HouseholdRole; pays_via?: boolean },
  ) => api.patch<Household>(`${base(org)}${id}/members/${link}/`, data),
  deleteMember: (org: number, id: number, link: number) =>
    api.del(`${base(org)}${id}/members/${link}/`),
  suggestions: (org: number) => api.get<HouseholdSuggestion[]>(`${base(org)}suggestions/`),
}

// --- Zahler und Familien-/Firmenbeitrag (H2/H3), Rechte wie bei Beiträgen ---

export type PayerKind = 'member' | 'external' | 'organization' | 'partner'

export interface HouseholdPayer {
  kind: PayerKind
  membership: number | null
  membership_name: string
  partner: number | null
  partner_name: string
  name: string
  attention: string
  street: string
  postal_code: string
  city: string
  country: string
  email: string
  order_reference: string
  leitweg_id: string
}

export interface HouseholdPayerData {
  household: number
  payer: HouseholdPayer | null
  mandates: Mandate[]
}

export type FeeRuleMode = 'none' | 'cap' | 'flat' | 'stagger'

export interface HouseholdFeeRule {
  kind: HouseholdKind
  mode: FeeRuleMode
  amount: string | null
  min_persons: number
  adult_required: boolean
  second_percent: string
  third_percent: string
}

const billing = (org: number) => `/api/orgs/${org}/billing/`

export const householdBillingApi = {
  payer: (org: number, id: number) =>
    api.get<HouseholdPayerData>(`${billing(org)}households/${id}/payer/`),
  savePayer: (org: number, id: number, data: Partial<HouseholdPayer>) =>
    api.put<HouseholdPayerData>(`${billing(org)}households/${id}/payer/`, data),
  removePayer: (org: number, id: number) => api.del(`${billing(org)}households/${id}/payer/`),
  feeRules: (org: number) => api.get<HouseholdFeeRule[]>(`${billing(org)}household-fee-rules/`),
  saveFeeRule: (org: number, data: HouseholdFeeRule) =>
    api.put<HouseholdFeeRule[]>(`${billing(org)}household-fee-rules/`, data),
}
