// Kontoauszüge (CAMT.053): einlesen, Umsätze zuordnen und buchen.
import { api } from './client.ts'
import type { Page } from './members.ts'

export interface BalanceCheck {
  bank: string
  book: string
  difference: string
  ok: boolean
}

export interface BankStatement {
  id: number
  account: number
  account_name: string
  file_name: string
  reference: string
  date_from: string | null
  date_to: string | null
  opening_balance: string | null
  closing_balance: string | null
  line_count: number
  duplicate_count: number
  open_count: number
  balance: BalanceCheck | null
  created_at: string
  /** leer = hochgeladene Datei, sonst der Bankweg des Abrufs (z. B. „fints“) */
  channel?: string
}

export type BankLineStatus = 'open' | 'done' | 'ignored'
export type Suggestion = '' | 'invoice' | 'debit_run' | 'booked' | 'return'

export interface BankLine {
  id: number
  statement: number
  account: number
  date: string
  amount: string
  credit: boolean
  name: string
  iban: string
  purpose: string
  return_code: string
  batch_count: number
  /** Einzelposten einer Sammelbuchung, wie sie im Auszug stehen */
  details: { amount: string; name: string; iban: string; purpose: string; end_to_end: string }[]
  status: BankLineStatus
  status_label: string
  suggestion: Suggestion
  suggestion_label: string
  /** Vorschlag beruht auf einer Referenz; sonst nur nach Betrag und Datum („bitte prüfen“) */
  suggestion_sure: boolean
  suggested: {
    invoice?: { id: number; number: string; recipient: string; outstanding: string }
    run?: { id: number; date: string; total: string }
    booking?: { id: number; number: string; text: string }
    membership?: { id: number; name: string }
  }
  booking: number | null
  booking_number: string | null
}

export type AssignInput =
  | { action: 'suggestion' | 'ignore' | 'reopen' }
  | { action: 'invoice'; invoice: number }
  | {
      action: 'booking'
      category: number
      membership?: number | null
      project?: number | null
      text?: string
    }

const base = (org: number) => `/api/orgs/${org}/finance`

export const bankApi = {
  statements: (org: number, page = 1) =>
    api.get<Page<BankStatement>>(
      `${base(org)}/bank-statements/?page_size=50${page > 1 ? `&page=${page}` : ''}`,
    ),
  upload: (org: number, file: File, account?: number | null) => {
    const form = new FormData()
    form.append('file', file)
    if (account) form.append('account', String(account))
    return api.post<{ lines: number; duplicates: number; statements: BankStatement[] }>(
      `${base(org)}/bank-statements/`,
      form,
    )
  },
  removeStatement: (org: number, id: number) => api.del(`${base(org)}/bank-statements/${id}/`),
  lines: (
    org: number,
    query: { auszug?: number; status?: BankLineStatus | ''; page?: number; size?: number },
  ) => {
    const p = new URLSearchParams({ page_size: String(query.size ?? 1000) })
    if (query.page && query.page > 1) p.set('page', String(query.page))
    if (query.auszug) p.set('auszug', String(query.auszug))
    if (query.status) p.set('status', query.status)
    return api.get<Page<BankLine>>(`${base(org)}/bank-lines/?${p.toString()}`)
  },
  assign: (org: number, id: number, data: AssignInput) =>
    api.post<BankLine>(`${base(org)}/bank-lines/${id}/assign/`, data),
  applySuggestions: (org: number, statement?: number) =>
    api.post<{ done: number; failed: string[] }>(
      `${base(org)}/bank-lines/apply-suggestions/`,
      statement ? { statement } : {},
    ),
}

// --- Bankanbindung: Umsätze direkt bei der Bank abrufen (finance/bank_fetch.py) ---

export interface BankAccess {
  id: number
  name: string
  way: string
  bank_code: string
  url: string
  /** nur die letzten zwei Zeichen des Anmeldenamens */
  login_hint: string
  tan_mechanism: string
  tan_mechanism_name: string
  tan_medium: string
  ready: boolean
  ibans: string[]
  accounts: { id: number; name: string; iban: string; fetched_until: string | null }[]
  last_success: string | null
  paused_until: string | null
  retry_needs_confirm: boolean
}

export interface BankAccessInput {
  name: string
  bank_code: string
  url: string
  login?: string
  customer_id?: string
}

export interface BankAccessList {
  /** auf diesem Server eingerichtet (Produktregistrierung hinterlegt) */
  available: boolean
  /** für diesen Verein eingeschaltet */
  enabled: boolean
  accesses: BankAccess[]
}

/** Antwort auf einen Schritt bei der Bank */
export type BankStep =
  | {
      status: 'tan'
      task: number
      challenge: string
      decoupled: boolean
      image: string
      expires_at: string
    }
  | {
      status: 'choose'
      need: 'mechanism' | 'medium'
      mechanisms: { id: string; name: string }[]
      media: string[]
      mechanism: string
    }
  | { status: 'done'; kind: 'setup'; linked: string[]; unlinked: string[] }
  | { status: 'done'; kind: 'fetch'; lines: number; duplicates: number; statements: number[] }

/** Die PIN geht nur im Körper dieser einen Anfrage an den Server und wird nie gespeichert. */
export interface BankStepInput {
  pin: string
  tan?: string
  mechanism?: string
  medium?: string
  confirm_retry?: boolean
}

export const bankAccessApi = {
  list: (org: number) => api.get<BankAccessList>(`${base(org)}/bank-access/`),
  create: (org: number, data: BankAccessInput) =>
    api.post<BankAccess>(`${base(org)}/bank-access/`, data),
  update: (org: number, id: number, data: Partial<BankAccessInput>) =>
    api.patch<BankAccess>(`${base(org)}/bank-access/${id}/`, data),
  remove: (org: number, id: number) => api.del(`${base(org)}/bank-access/${id}/`),
  setup: (org: number, id: number, data: BankStepInput) =>
    api.post<BankStep>(`${base(org)}/bank-access/${id}/setup/`, data),
  fetch: (org: number, id: number, data: BankStepInput) =>
    api.post<BankStep>(`${base(org)}/bank-access/${id}/fetch/`, data),
  proceed: (org: number, task: number, data: BankStepInput) =>
    api.post<BankStep>(`${base(org)}/bank-tasks/${task}/continue/`, data),
  cancel: (org: number, task: number) =>
    api.post<unknown>(`${base(org)}/bank-tasks/${task}/cancel/`),
}
