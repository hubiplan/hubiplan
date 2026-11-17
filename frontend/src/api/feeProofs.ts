// Beitragsnachweise (docs/beitragsnachweise.md): Ermäßigung mit jährlichem Nachweis, Frist,
// Erinnerungen, Prüfung durch den Vorstand und Wirkung im Beitragslauf.
import { api } from './client.ts'

export type ProofStatus = 'received' | 'question' | 'accepted' | 'rejected'
export type ProofChannel = 'portal' | 'app' | 'link' | 'mail' | 'application' | 'board'
export type YearStateKind = 'accepted' | 'pending' | 'question' | 'open' | 'missing'

export interface ProofDiscount {
  id: number
  name: string
  member_type: number | null
  member_type_name: string | null
  amount: string | null
  discount_percent: string | null
  deadline_month: number
  deadline_day: number
  grace_days: number | null
  late_join_days: number
  remind_month: number | null
  remind_day: number | null
  remind_before_days: number | null
  notify_after: boolean
  kinds: string[]
  is_archived: boolean
  sort_order: number
  in_use: boolean
}

export type DiscountInput = Partial<
  Omit<ProofDiscount, 'id' | 'member_type_name' | 'sort_order' | 'in_use'>
>

export interface Precheck {
  level?: 'green' | 'yellow' | 'red'
  reasons?: string[]
  valid_until?: string
  kind_hint?: string
  signature?: { signer?: string; intact?: boolean }
}

export interface FeeProof {
  id: number
  discount: number
  discount_name: string
  year: number
  year_label: string
  kind: string
  status: ProofStatus
  channel: ProofChannel
  received_on: string
  valid_until: string | null
  has_file: boolean
  file_name: string
  content_type: string
  note: string
  member_note: string
  late: boolean
  outside_deadline: boolean
  reviewed_at: string | null
  // nur für den Vorstand
  precheck?: Precheck
  auto_accepted?: boolean
  membership?: number
  file_deleted?: boolean
  first_name?: string
  last_name?: string
}

export interface YearState {
  discount: number
  discount_name: string
  kinds: string[]
  year: number
  year_label: string
  due: string
  final: string
  state: YearStateKind
  applies: boolean
  proof: FeeProof | null
}

export interface OverviewRow extends YearState {
  membership: number
  first_name: string
  last_name: string
}

export interface Overview {
  year: number
  year_label: string
  counts: Record<YearStateKind, number>
  rows: OverviewRow[]
}

export interface StaleRow {
  assignment: number
  membership: number
  first_name: string
  last_name: string
  discount_name: string
  valid_from: string
}

export interface Assignment {
  id: number
  discount: number
  discount_name: string
  valid_from: string
  valid_until: string | null
}

export interface MemberProofs {
  states: YearState[]
  proofs: FeeProof[]
}

export interface ProofSettings {
  auto_accept: boolean
  mail_replies: boolean
}

export interface DecideInput {
  action: 'accept' | 'reject' | 'question'
  valid_until?: string | null
  kind?: string
  note?: string
}

const org = (id: number) => `/api/orgs/${id}/fee-proofs/`
const member = (orgId: number, memberId: number) => `/api/orgs/${orgId}/members/${memberId}/`

export const feeProofApi = {
  discounts: (orgId: number) => api.get<ProofDiscount[]>(`${org(orgId)}discounts/`),
  createDiscount: (orgId: number, data: DiscountInput) =>
    api.post<ProofDiscount>(`${org(orgId)}discounts/`, data),
  updateDiscount: (orgId: number, id: number, data: DiscountInput) =>
    api.patch<ProofDiscount>(`${org(orgId)}discounts/${id}/`, data),
  removeDiscount: (orgId: number, id: number) => api.del(`${org(orgId)}discounts/${id}/`),
  settings: (orgId: number) => api.get<ProofSettings>(`${org(orgId)}settings/`),
  saveSettings: (orgId: number, data: { auto_accept: boolean }) =>
    api.patch<ProofSettings>(`${org(orgId)}settings/`, data),
  list: (orgId: number, status = 'open', year?: number) =>
    api.get<FeeProof[]>(`${org(orgId)}?status=${status}${year ? `&year=${year}` : ''}`),
  overview: (orgId: number, year?: number) =>
    api.get<Overview>(`${org(orgId)}overview/${year ? `?year=${year}` : ''}`),
  stale: (orgId: number) =>
    api.get<{ stale: StaleRow[] }>(`${org(orgId)}overview/?stand=zwei-jahre`),
  fileUrl: (orgId: number, id: number) => `${org(orgId)}${id}/file/`,
  decide: (orgId: number, id: number, data: DecideInput) =>
    api.post<FeeProof>(`${org(orgId)}${id}/decide/`, data),
  remove: (orgId: number, id: number) => api.del(`${org(orgId)}${id}/`),
  // am Mitglied
  assignments: (orgId: number, memberId: number) =>
    api.get<Assignment[]>(`${member(orgId, memberId)}fee-discounts/`),
  assign: (orgId: number, memberId: number, data: Partial<Assignment>) =>
    api.post<Assignment>(`${member(orgId, memberId)}fee-discounts/`, data),
  updateAssignment: (orgId: number, memberId: number, id: number, data: Partial<Assignment>) =>
    api.patch<Assignment>(`${member(orgId, memberId)}fee-discounts/${id}/`, data),
  removeAssignment: (orgId: number, memberId: number, id: number) =>
    api.del(`${member(orgId, memberId)}fee-discounts/${id}/`),
  memberProofs: (orgId: number, memberId: number) =>
    api.get<MemberProofs>(`${member(orgId, memberId)}fee-proofs/`),
  addMemberProof: (
    orgId: number,
    memberId: number,
    data: {
      discount: number
      year: number
      received_on?: string
      kind?: string
      valid_until?: string
      accept?: boolean
    },
    file?: File | null,
  ) => {
    const form = new FormData()
    for (const [key, value] of Object.entries(data))
      if (value !== undefined && value !== '') form.append(key, String(value))
    if (file) form.append('file', file)
    return api.post<FeeProof>(`${member(orgId, memberId)}fee-proofs/`, form)
  },
}

function uploadForm(
  data: { discount?: number; year?: number; kind?: string; note?: string },
  file: File,
) {
  const form = new FormData()
  for (const [key, value] of Object.entries(data))
    if (value !== undefined && value !== '') form.append(key, String(value))
  form.append('file', file)
  return form
}

const portal = (access: number) => `/api/portal/${access}/fee-proofs/`

export const portalFeeProofApi = {
  get: (access: number) => api.get<MemberProofs>(portal(access)),
  submit: (
    access: number,
    data: { discount: number; year: number; kind?: string; note?: string },
    file: File,
  ) => api.post<MemberProofs>(portal(access), uploadForm(data, file)),
}

export interface PublicFeeProof {
  club: string
  imprint_key: string
  first_name: string
  state: YearState
  proofs: FeeProof[]
}

const pub = (token: string) => `/api/public/fee-proof/${encodeURIComponent(token)}/`

export const publicFeeProofApi = {
  get: (token: string) => api.get<PublicFeeProof>(pub(token)),
  submit: (token: string, data: { kind?: string; note?: string }, file: File) =>
    api.post<PublicFeeProof>(pub(token), uploadForm(data, file)),
}
