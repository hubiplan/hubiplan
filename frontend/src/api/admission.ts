// Online-Mitgliedsantrag (konzepte/online-beitrittsformular.md): öffentliches Formular,
// Stand des eigenen Antrags, Antragsliste und Prüfseite im Verein, Einrichtung.
import { api } from './client.ts'
import type { SignatureInput } from './finance.ts'

export type FieldState = 'required' | 'optional' | 'off'
export type FieldKey =
  | 'phone'
  | 'gender'
  | 'birth_date'
  | 'unit'
  | 'entry_wish'
  | 'note'
  /** Familienantrag: weitere Personen mit gleicher Anschrift (an = „optional“) */
  | 'family'

/** Felder des Formulars; „family“ fehlt bei älteren Servern */
export type FieldStates = Record<Exclude<FieldKey, 'family'>, FieldState> & { family?: FieldState }

export interface JoinType {
  id: number
  label: string
  text: string
  fee: string | null
  organizations: boolean
}

export interface JoinConfirmation {
  key: string
  label: string
  url?: string | null
  version?: string
  text?: string
}

export interface JoinSchema {
  organization: string
  language: string
  languages: string[]
  intro: string
  thanks: string
  types: JoinType[]
  fields: FieldStates
  units: { id: number; name: string }[]
  unit: number | null
  unit_label: string
  custom_fields: {
    id: number
    label: string
    type: string
    choices: string[]
    help: string
  }[]
  sepa: 'off' | 'offer' | 'required'
  mandate: { creditor_id?: string; text?: string }
  confirmations: JoinConfirmation[]
  consents: { key: string; label: string }[]
  signature: 'none' | 'required'
  minors: boolean
  min_age: number | null
  /** Link „Mitarbeiter melden“: Name der Firma, die den Beitrag zahlt */
  company?: string | null
  /** Gemeldete Person aus dem Link der Firma (Vorbelegung) */
  invite?: { first_name: string; last_name: string; email: string } | null
  challenge?: { token: string; salt: string; difficulty: number }
  key?: string
  kiosk?: string
  valid_until?: string
}

export interface Guardian {
  last_name: string
  first_name: string
  email: string
  phone?: string
}

export interface FamilyMember {
  first_name: string
  last_name: string
  birth_date: string
  member_type: string
}

export interface JoinSubmission {
  language: string
  kind: 'person' | 'organization'
  member_type: number
  last_name: string
  first_name?: string
  birth_date?: string
  adult?: boolean | null
  gender?: string
  email: string
  phone?: string
  street: string
  address_extra?: string
  postal_code: string
  city: string
  country?: string
  unit?: number | null
  entry_wish?: string
  note?: string
  custom?: Record<string, string>
  mandate?: { holder: string; iban: string; bic?: string } | null
  confirmations: string[]
  consents: string[]
  guardians?: Guardian[]
  family?: { first_name: string; last_name?: string; birth_date?: string; member_type?: number }[]
  signature?: SignatureInput | null
  homepage?: string
  company?: string
  challenge?: string
  nonce?: number
}

export interface JoinStatus {
  number: string
  status: ApplicationStatus
  status_label: string
  organization: string
  name: string
  language: string
  summary: string[]
  signed: boolean
  signature_required: boolean
  can_withdraw: boolean
  can_sign: boolean
}

export type ApplicationStatus =
  'unconfirmed' | 'unsigned' | 'open' | 'query' | 'accepted' | 'rejected' | 'withdrawn'

const lang = (language: string) => `?lang=${encodeURIComponent(language)}`

export const joinApi = {
  form: (key: string, language: string, unit = '', company = '') =>
    api.get<JoinSchema>(
      `/api/public/join/${encodeURIComponent(key)}/${lang(language)}${
        unit ? `&einheit=${encodeURIComponent(unit)}` : ''
      }${company ? `&firma=${encodeURIComponent(company)}` : ''}`,
    ),
  submit: (key: string, data: JoinSubmission) =>
    api.post<{ status: string }>(`/api/public/join/${encodeURIComponent(key)}/`, data),
  kiosk: (token: string, language: string) =>
    api.get<JoinSchema>(`/api/public/join/kiosk/${encodeURIComponent(token)}/${lang(language)}`),
  kioskSubmit: (token: string, data: JoinSubmission) =>
    api.post<{ status: string; number: string }>(
      `/api/public/join/kiosk/${encodeURIComponent(token)}/`,
      data,
    ),
  status: (token: string) =>
    api.get<JoinStatus>(`/api/public/join/application/${encodeURIComponent(token)}/`),
  confirm: (token: string) =>
    api.post<JoinStatus>(`/api/public/join/application/${encodeURIComponent(token)}/confirm/`),
  withdraw: (token: string) =>
    api.post<JoinStatus>(`/api/public/join/application/${encodeURIComponent(token)}/withdraw/`),
  sign: (token: string, signature: SignatureInput) =>
    api.post<JoinStatus>(`/api/public/join/application/${encodeURIComponent(token)}/sign/`, {
      signature,
    }),
  pdfUrl: (token: string) => `/api/public/join/application/${encodeURIComponent(token)}/pdf/`,
}

/** Rechenaufgabe des Spamschutzes im Browser lösen (wie das Kontaktformular der Webseite). */
export async function solveChallenge(salt: string, difficulty: number): Promise<number> {
  const enc = new TextEncoder()
  for (let nonce = 0; nonce < 50_000_000; nonce++) {
    const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', enc.encode(salt + nonce)))
    let bits = 0
    for (const byte of digest) {
      if (byte === 0) {
        bits += 8
        continue
      }
      bits += Math.clz32(byte) - 24
      break
    }
    if (bits >= difficulty) return nonce
  }
  throw new Error('challenge')
}

// --- Verein ---

export interface ApprovalRule {
  mode: 'single' | 'rule' | 'assembly'
  roles: number[]
  min_count: number
  pool: number[]
  unit: boolean
  auto_admit: boolean
  multi_role: boolean
}

export type LangText = Record<string, string>

export interface FormSettings {
  enabled: boolean
  public_key: string
  form_url: string
  types: { id: number; label: LangText; text: LangText; organizations: boolean }[]
  fields: FieldStates
  custom_fields: number[]
  sepa: 'off' | 'offer' | 'required'
  sepa_available: boolean
  confirm_statute: boolean
  confirm_fee_rules: boolean
  statute_docs: Record<string, { url: string | null; version: string }>
  consents: string[]
  signature: 'none' | 'required'
  texts: Record<'intro' | 'thanks' | 'welcome' | 'rejection', LangText>
  notify_roles: number[]
  rule: ApprovalRule
  rule_text: string
  entry_date: 'decision' | 'next_month' | 'wish'
  purge_months: number
  min_age: number | null
  minors: boolean
  choices: {
    member_types: { id: number; name: string }[]
    roles: { id: number; name: string }[]
    custom_fields: { id: number; label: string }[]
    consents: { key: string; label: string }[]
    units: { id: number; name: string }[]
  }
}

export interface ApplicationRow {
  id: number
  number: string
  status: ApplicationStatus
  status_label: string
  source: 'web' | 'kiosk'
  kind: 'person' | 'organization'
  name: string
  last_name: string
  first_name: string
  birth_date: string | null
  member_type: string
  member_type_id: number | null
  unit: string
  unit_id: number | null
  minor: boolean
  created_at: string
  approvals_met: boolean | null
  disputed: boolean
  missing: string[]
  membership_id: number | null
}

export interface ApplicationList {
  results: ApplicationRow[]
  enabled: boolean
  rule: ApprovalRule
  rule_text: string
  may_approve: boolean
  counts: Record<string, number>
}

export interface ApplicationDetail extends ApplicationRow {
  data: Record<string, string | Record<string, string>>
  summary: string[]
  entry_wish: string | null
  mandate: { holder: string; iban: string; bic: string } | null
  consents: { key: string; label: string; version?: string; at: string; given: boolean }[]
  guardians: Guardian[]
  signed: boolean
  signed_at: string | null
  confirmed_at: string | null
  decided_at: string | null
  decided_by: string
  decision_note: string
  approvals: {
    id: number
    user_name: string
    roles: string
    for_unit: boolean
    decision: 'approve' | 'reject'
    note: string
    created_at: string
  }[]
  events: { kind: string; note: string; created_at: string; user: string }[]
  matches: {
    persons: {
      person_id: number
      name: string
      birth_date: string | null
      here: boolean
      member_id: number | null
      former: boolean
      active_elsewhere: string
    }[]
  }
  rule: ApprovalRule
  rule_text: string
  entry_date: string
  may_approve: boolean
  may_decide: boolean
  own_decision: 'approve' | 'reject' | null
  portal_available: boolean
}

export interface KioskLinkRow {
  id: number
  label: string
  valid_until: string
  url?: string
}

const base = (org: number) => `/api/orgs/${org}/admission`

export const admissionApi = {
  settings: (org: number) => api.get<FormSettings>(`${base(org)}/form/`),
  saveSettings: (org: number, data: Partial<FormSettings>) =>
    api.patch<FormSettings>(`${base(org)}/form/`, data),
  list: (org: number, status: string) =>
    api.get<ApplicationList>(`${base(org)}/?status=${encodeURIComponent(status)}`),
  get: (org: number, id: number) => api.get<ApplicationDetail>(`${base(org)}/${id}/`),
  update: (org: number, id: number, data: Record<string, unknown>) =>
    api.patch<ApplicationDetail>(`${base(org)}/${id}/`, data),
  action: (org: number, id: number, action: string, data: Record<string, unknown> = {}) =>
    api.post<ApplicationDetail>(`${base(org)}/${id}/${action}/`, data),
  bulkAccept: (org: number, ids: number[], entryDate: string, invite: boolean) =>
    api.post<{ accepted: number[]; failed: { id: number; number: string; detail: string }[] }>(
      `${base(org)}/bulk-accept/`,
      { ids, entry_date: entryDate || null, invite },
    ),
  pdfUrl: (org: number, id: number) => `${base(org)}/${id}/pdf/`,
  qrUrl: (org: number, unit?: number) => `${base(org)}/qr/${unit ? `?einheit=${unit}` : ''}`,
  kioskLinks: (org: number) => api.get<KioskLinkRow[]>(`${base(org)}/kiosk/`),
  createKiosk: (org: number, label: string, hours: number) =>
    api.post<KioskLinkRow>(`${base(org)}/kiosk/`, { label, hours }),
  endKiosk: (org: number, id: number) => api.del(`${base(org)}/kiosk/${id}/`),
}
