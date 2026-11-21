// Sammelbestellungen: Vereinskleidung, Festschrift, Uniformteile oder reine Größenabfragen
// (Lückenliste 20.11.2026, B4). Preis und Rechnung sind freiwillig.
import { api, requestBlob } from './client.ts'

export type CampaignState = 'draft' | 'open' | 'closed'

export interface OrderArticle {
  id?: number
  name: string
  text: string
  /** Preis als Text („25.00“); leer: ohne Preis */
  price: string | null
  /** Größen oder Varianten zur Auswahl; leer: keine Auswahl */
  variants: string[]
  /** Überschrift der Auswahl, z. B. „Größe“ */
  variant_label: string
  max_per_member: number | null
  max_total: number | null
  /** noch verfügbar (nur mit Gesamtmenge) */
  left?: number
}

export interface OrderLine {
  article: number
  name: string
  variant: string
  quantity: number
  price: string | null
  amount: string | null
}

export interface OrderInvoice {
  id: number
  number: string
  status: string
  total: string
  outstanding: string
}

export interface MemberOrder {
  id: number
  lines: OrderLine[]
  note: string
  /** Summe; leer, wenn kein Artikel einen Preis hat oder der Verein zahlt */
  total: string | null
  handed_out: boolean
  handed_out_at: string | null
  updated_at: string
  invoice: OrderInvoice | null
  /** nur in der Verwaltung */
  membership?: number
  name?: string
  number?: string
  entered_by_board?: boolean
}

export interface OrderSum {
  article: number
  name: string
  variant_label: string
  variants: { variant: string; quantity: number }[]
  quantity: number
  amount: string | null
}

export interface Campaign {
  id: number
  title: string
  text: string
  deadline: string
  state: CampaignState
  department: number | null
  unit: string
  from: string
  club_pays: boolean
  payment_category: number | null
  push: boolean
  pushed: boolean
  published_at: string | null
  closed_at: string | null
  version: number
  articles: OrderArticle[]
}

export interface CampaignDetail extends Campaign {
  orders: MemberOrder[]
  sums: OrderSum[]
  /** Zahl der Mitglieder, die bestellen dürfen */
  audience: number
  can_edit: boolean
  can_invoice: boolean
  /** nach „Rechnungen anlegen“: wie viele neu entstanden */
  created?: number
}

export interface CampaignRow {
  id: number
  title: string
  deadline: string
  state: CampaignState
  unit: string
  club_pays: boolean
  orders: number
}

export interface CampaignList {
  campaigns: CampaignRow[]
  can_edit: boolean
  can_invoice: boolean
  departments: { id: number; name: string }[]
  categories: { id: number; name: string }[]
}

export interface CampaignDraft {
  title: string
  text: string
  deadline: string
  department: number | null
  club_pays: boolean
  payment_category: number | null
  push: boolean
  articles: OrderArticle[]
}

export interface LineInput {
  article: number
  variant: string
  quantity: number
}

export interface PickMember {
  id: number
  first_name: string
  last_name: string
  name: string
  number: string
}

export const ordersApi = {
  list: (base: string) => api.get<CampaignList>(base),
  get: (base: string, id: number) => api.get<CampaignDetail>(`${base}${id}/`),
  create: (base: string, draft: CampaignDraft) => api.post<CampaignDetail>(base, draft),
  update: (base: string, id: number, data: Partial<CampaignDraft> & { version?: number }) =>
    api.patch<CampaignDetail>(`${base}${id}/`, data),
  remove: (base: string, id: number) => api.del(`${base}${id}/`),
  publish: (base: string, id: number, action: 'publish' | 'close' | 'reopen') =>
    api.post<CampaignDetail>(`${base}${id}/publish/`, { action }),
  members: (base: string, id: number, term: string) =>
    api.get<{ members: PickMember[] }>(`${base}${id}/members/?q=${encodeURIComponent(term)}`),
  setOrder: (base: string, id: number, membership: number, lines: LineInput[], note: string) =>
    api.put<CampaignDetail>(`${base}${id}/orders/`, { membership, lines, note }),
  handOut: (base: string, id: number, order: number, handed_out: boolean) =>
    api.patch<CampaignDetail>(`${base}${id}/orders/${order}/`, { handed_out }),
  removeOrder: (base: string, id: number, order: number) =>
    api.delWith<CampaignDetail>(`${base}${id}/orders/${order}/`, {}),
  invoices: (base: string, id: number, orders: number[] | null) =>
    api.post<CampaignDetail>(`${base}${id}/invoices/`, { orders }),
  export: (base: string, id: number) => requestBlob('GET', `${base}${id}/export/`),
}

// --- Mitgliederbereich und App ---

export interface MemberCampaign {
  id: number
  title: string
  deadline: string
  state: CampaignState
  from: string
  club_pays: boolean
  ordered: boolean
  can_order: boolean
  order: MemberOrder | null
  /** nur in der Einzelansicht */
  text?: string
  articles?: OrderArticle[]
}

export const portalOrdersBase = (access: number) => `/api/portal/${access}/orders/`

export const portalOrdersApi = {
  list: (base: string) => api.get<{ campaigns: MemberCampaign[] }>(base),
  get: (base: string, id: number) => api.get<MemberCampaign>(`${base}${id}/`),
  order: (base: string, id: number, lines: LineInput[], note: string) =>
    api.put<MemberCampaign>(`${base}${id}/order/`, { lines, note }),
  withdraw: (base: string, id: number) => api.delWith<MemberCampaign>(`${base}${id}/order/`, {}),
}

/** Betrag aus der Schnittstelle („25.00“) als Zahl */
export function amount(value: string | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}
