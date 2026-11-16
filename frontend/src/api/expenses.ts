// Auslagen erstatten (docs/auslagen.md): Mitglieder melden selbst bezahlte Ausgaben mit
// Beleg, die Kasse prüft, gibt frei und zahlt aus.
import { api, newRequestKey, requestBlob } from './client.ts'

export type ExpenseKind = 'expense' | 'mileage' | 'advance'
export type ExpenseStatus =
  | 'draft'
  | 'submitted'
  | 'question'
  | 'confirmed'
  | 'approved'
  | 'paid'
  | 'rejected'
  | 'withdrawn'
  | 'waived'
export type Payout = 'bank' | 'cash' | 'waiver'
export type InvoiceTo = 'club' | 'member' | 'none'

export interface ExpenseLine {
  id?: number
  amount: string
  text: string
  category: number | null
  category_name?: string
}

export interface Payee {
  holder: string
  iban: string
  bic?: string
}

export interface ExpenseFile {
  id: number
  name: string
  content_type: string
  size: number
  created_at: string
  einvoice: { payable?: string; seller?: string; number?: string } | null
}

export interface ExpenseEvent {
  kind: string
  label: string
  who: string
  text: string
  at: string
}

export interface ExpenseClaim {
  id: number
  number: string
  kind: ExpenseKind
  status: ExpenseStatus
  status_label: string
  source: 'portal' | 'app' | 'treasury' | 'link'
  name: string
  membership: number | null
  purpose: string
  note: string
  purchase_date: string | null
  department: number | null
  department_name: string
  project: number | null
  project_name: string
  invoice_to: InvoiceTo
  payout: Payout
  route: string
  km: string | null
  km_rate: string | null
  advance: number | null
  advance_number: string
  total: string
  approved_amount: string | null
  reduce_reason: string
  amount_due: string
  reject_reason: string
  self_approved: boolean
  reviewed: boolean
  approved_once: boolean
  submitted_at: string | null
  decided_at: string | null
  paid_at: string | null
  created_at: string
  version: number
  file_count: number
  lines: ExpenseLine[]
  payee: Payee | null
  booking?: number
  booking_number?: string
  // Mit Einzelheiten
  files?: ExpenseFile[]
  events?: ExpenseEvent[]
  problems?: Record<string, string>
  // Sicht des Mitglieds
  can_edit?: boolean
  can_withdraw?: boolean
  can_waive?: boolean
  // Sicht der Kasse
  own?: boolean
  needs_confirm?: boolean
  /** Untereinheit: darf jetzt sachlich bestätigen */
  can_confirm?: boolean
  confirm_unit?: string
  needs_second?: boolean
  hints?: string[]
  budget?: string
  epc?: string
  self_limit?: string
}

/** Angaben eines Antrags, wie sie an den Server gehen */
export interface ClaimInput {
  kind?: ExpenseKind
  purpose?: string
  note?: string
  purchase_date?: string | null
  invoice_to?: InvoiceTo
  payout?: Payout
  payee?: Payee | null
  department?: number | null
  project?: number | null
  advance?: number | null
  route?: string
  km?: string | null
  lines?: { amount: string; text: string; category?: number | null }[]
}

export interface Choice {
  id: number
  name: string
}

export interface MemberOptions {
  may_submit: boolean
  mileage_enabled: boolean
  km_rate: string
  advances_enabled: boolean
  waiver_enabled: boolean
  payee: Payee | null
  departments: Choice[]
  projects: Choice[]
  categories: Choice[]
  open_advances: { id: number; number: string; amount: string; purpose: string }[]
}

export interface ExpenseSettings {
  submitters: 'members' | 'officers'
  self_limit: string
  second_from: string | null
  hint_months: number
  confirm_departments: number[]
  mileage_enabled: boolean
  km_rate: string
  waiver_basis: string
  waiver_basis_date: string | null
  advances_enabled: boolean
  links_enabled: boolean
  can_edit: boolean
  donations_enabled: boolean
  departments: Choice[]
}

export type ExpenseTab = 'review' | 'approved' | 'done' | 'unreviewed' | 'drafts'

export interface ExpenseList {
  claims: ExpenseClaim[]
  counts: { review: number; approved: number; unreviewed: number }
  can_edit: boolean
  can_pay: boolean
  summary: { approved_count: number; approved_sum: string; in_review: number; unreviewed: number }
}

export interface TransferRunItem {
  claim: number
  number: string
  name: string
  amount: string
  holder: string
  iban: string
  paid: boolean
}

export interface TransferRun {
  id: number
  reference: string
  bank_account: number
  execution_date: string
  cancelled: boolean
  exported: boolean
  created_at: string
  total: string
  items: TransferRunItem[]
}

export interface TransferOverview {
  runs: TransferRun[]
  ready: {
    id: number
    number: string
    name: string
    purpose: string
    amount: string
    holder: string
    iban: string
    categories_ok: boolean
  }[]
  banks: Choice[]
  can_pay: boolean
}

export interface ExpenseLink {
  id: number
  name: string
  email: string
  membership: number | null
  valid_until: string
  revoked: boolean
  used_at: string | null
  created_at: string
  /** nur direkt nach dem Ausstellen */
  url?: string
}

/** Mehrteiliges Formular: Angaben als Felder, Positionen und Bankverbindung als JSON-Text */
export function claimForm(
  data: ClaimInput,
  files: File[] = [],
  extra: Record<string, string> = {},
) {
  const form = new FormData()
  for (const [key, value] of Object.entries(data)) {
    if (value === undefined) continue
    if (key === 'lines' || key === 'payee') form.append(key, value ? JSON.stringify(value) : '')
    else form.append(key, value === null ? '' : String(value))
  }
  for (const [key, value] of Object.entries(extra)) form.append(key, value)
  for (const file of files) form.append('file', file)
  return form
}

const org = (id: number) => `/api/orgs/${id}/expenses/`

export const expenseApi = {
  list: (orgId: number, tab: ExpenseTab, year?: number) =>
    api.get<ExpenseList>(`${org(orgId)}?ansicht=${tab}${year ? `&jahr=${year}` : ''}`),
  get: (orgId: number, id: number) => api.get<ExpenseClaim>(`${org(orgId)}${id}/`),
  create: (orgId: number, data: ClaimInput & { membership?: number | null; name?: string }) =>
    api.post<ExpenseClaim>(org(orgId), data, newRequestKey()),
  update: (orgId: number, id: number, data: object) =>
    api.patch<ExpenseClaim>(`${org(orgId)}${id}/`, data),
  action: (orgId: number, id: number, action: string, data: object = {}) =>
    api.post<ExpenseClaim>(
      `${org(orgId)}${id}/${action}/`,
      data,
      action === 'pay' ? newRequestKey() : undefined,
    ),
  addFile: (orgId: number, id: number, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<ExpenseClaim>(`${org(orgId)}${id}/files/`, form)
  },
  fileUrl: (orgId: number, id: number, fileId: number) => `${org(orgId)}${id}/files/${fileId}/`,
  review: (orgId: number, ids: number[]) =>
    api.post<{ reviewed: number }>(`${org(orgId)}review/`, { ids }),
  options: (orgId: number) =>
    api.get<{ categories: Choice[]; accounts: (Choice & { kind: string })[] }>(
      `${org(orgId)}options/`,
    ),
  settings: (orgId: number) => api.get<ExpenseSettings>(`${org(orgId)}settings/`),
  saveSettings: (orgId: number, data: Partial<ExpenseSettings>) =>
    api.patch<ExpenseSettings>(`${org(orgId)}settings/`, data),
  transfers: (orgId: number) => api.get<TransferOverview>(`${org(orgId)}transfers/`),
  createTransfer: (
    orgId: number,
    data: { bank_account: number; execution_date: string; claims: number[] },
  ) => api.post<TransferRun>(`${org(orgId)}transfers/`, data, newRequestKey()),
  cancelTransfer: (orgId: number, id: number) =>
    api.post<TransferRun>(`${org(orgId)}transfers/${id}/`, { action: 'cancel' }),
  exportTransfer: (orgId: number, id: number) =>
    requestBlob('POST', `${org(orgId)}transfers/${id}/`, { action: 'export' }),
  links: (orgId: number) => api.get<{ links: ExpenseLink[] }>(`${org(orgId)}links/`),
  createLink: (orgId: number, data: { name: string; email: string; days: number }) =>
    api.post<ExpenseLink>(`${org(orgId)}links/`, data),
  revokeLink: (orgId: number, id: number) =>
    api.del(`${org(orgId)}links/${id}/`) as Promise<ExpenseLink>,
}

const dept = (id: number) => `/api/depts/${id}/expenses/`

export const deptExpenseApi = {
  list: (deptId: number) =>
    api.get<{ claims: ExpenseClaim[]; waiting: number; can_confirm: boolean }>(dept(deptId)),
  get: (deptId: number, id: number) => api.get<ExpenseClaim>(`${dept(deptId)}${id}/`),
  action: (deptId: number, id: number, action: 'confirm' | 'ask', data: object = {}) =>
    api.post<ExpenseClaim>(`${dept(deptId)}${id}/${action}/`, data),
  fileUrl: (deptId: number, id: number, fileId: number) => `${dept(deptId)}${id}/files/${fileId}/`,
}

const portal = (access: number) => `/api/portal/${access}/expenses/`

export const portalExpenseApi = {
  list: (access: number) =>
    api.get<{ claims: ExpenseClaim[]; options: MemberOptions }>(portal(access)),
  get: (access: number, id: number) => api.get<ExpenseClaim>(`${portal(access)}${id}/`),
  create: (access: number, data: ClaimInput, files: File[], submit: boolean) =>
    api.post<ExpenseClaim>(
      portal(access),
      claimForm(data, files, submit ? { submit: 'true' } : {}),
      newRequestKey(),
    ),
  update: (access: number, id: number, data: ClaimInput & { version?: number }) =>
    api.patch<ExpenseClaim>(`${portal(access)}${id}/`, data),
  remove: (access: number, id: number) => api.del(`${portal(access)}${id}/`),
  action: (
    access: number,
    id: number,
    action: 'submit' | 'withdraw' | 'answer' | 'waive',
    data: object = {},
  ) => api.post<ExpenseClaim | null>(`${portal(access)}${id}/${action}/`, data),
  addFile: (access: number, id: number, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<ExpenseClaim>(`${portal(access)}${id}/files/`, form)
  },
  removeFile: (access: number, id: number, fileId: number) =>
    api.del(`${portal(access)}${id}/files/${fileId}/`) as Promise<ExpenseClaim>,
  fileUrl: (access: number, id: number, fileId: number) =>
    `${portal(access)}${id}/files/${fileId}/`,
}

export interface PublicExpense {
  club: string
  imprint_key: string
  name: string
  valid_until: string
  mileage_enabled: boolean
  km_rate: string
  claims: ExpenseClaim[]
}

export const publicExpenseApi = {
  get: (token: string) => api.get<PublicExpense>(`/api/public/expense/${token}/`),
  submit: (token: string, data: ClaimInput, files: File[]) =>
    api.post<PublicExpense>(`/api/public/expense/${token}/`, claimForm(data, files)),
}
