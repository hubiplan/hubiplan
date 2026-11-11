// Geschäftspartner (Konzept geschaeftspartner.md): Firmen, Behörden, Vereine und Personen
// außerhalb der Mitgliederliste, mit Ansprechpartnern.
import { api, requestBlob } from './client.ts'
import type { FieldDefinition, FieldUsage, FieldValue, MemberField } from './fields.ts'

export const PARTNER_KINDS = ['company', 'authority', 'association', 'person', 'other'] as const
export type PartnerKind = (typeof PARTNER_KINDS)[number]

export const PARTNER_ROLES = [
  'supplier',
  'service',
  'customer',
  'sponsor',
  'donor',
  'venue',
  'artist',
  'authority',
  'press',
  'insurance',
  'bank',
] as const
export type PartnerRole = (typeof PARTNER_ROLES)[number]

export interface PartnerDetails {
  name: string
  street: string
  postcode: string
  city: string
  country: string
  email: string
  phone: string
  website?: string
  vat_id: string
  tax_number: string
  contact: string
  identifier: string
  leitweg_id?: string
  endpoint_id?: string
  endpoint_scheme?: string
}

export interface PartnerBank {
  iban: string
  bic: string
  holder: string
  changed_at?: string
  changed_by?: string
}

export interface PartnerContact {
  id: number
  last_name: string
  first_name: string
  function: string
  email: string
  phone: string
  is_primary: boolean
  receives_invoices: boolean
  receives_mail: boolean
  notes: string
}

export interface BusinessPartner {
  id: number
  name: string
  kind: PartnerKind
  roles: PartnerRole[]
  number: string
  unit: number | null
  unit_name: string
  membership: number | null
  membership_name: string
  /** Mitgliedschaft, die den Kontakt betreut */
  liaison: number | null
  liaison_name: string
  first_contact_on: string | null
  first_contact_note: string
  details: PartnerDetails
  /** nur mit Kassen- oder Beitragsrecht */
  bank?: PartnerBank
  our_customer_number: string
  default_category?: number | null
  payment_terms_days?: number | null
  artist?: boolean
  notes: string
  website_consent: boolean
  website_url: string
  is_customer: boolean
  is_supplier: boolean
  is_active: boolean
  contacts: PartnerContact[]
  updated_at: string
}

export type PartnerInput = Partial<
  Omit<
    BusinessPartner,
    'id' | 'name' | 'contacts' | 'unit_name' | 'membership_name' | 'liaison_name' | 'updated_at'
  >
>
export type ContactInput = Partial<Omit<PartnerContact, 'id'>>

export const AGREEMENT_KINDS = ['sponsoring', 'framework', 'contract', 'other'] as const
export type AgreementKind = (typeof AGREEMENT_KINDS)[number]
export const AGREEMENT_TAX_KINDS = ['mention', 'advertising', 'none'] as const
export type AgreementTaxKind = (typeof AGREEMENT_TAX_KINDS)[number]
export const AGREEMENT_BENEFITS = [
  'website',
  'banner',
  'publication',
  'clothing',
  'event',
  'other',
] as const
export type AgreementBenefit = (typeof AGREEMENT_BENEFITS)[number]

export interface PartnerAgreement {
  id: number
  kind: AgreementKind
  title: string
  start: string
  end: string | null
  amount: string | null
  in_kind: string
  benefits: AgreementBenefit[]
  benefits_text: string
  tax_kind: AgreementTaxKind
  category: number | null
  notice_days: number | null
  auto_renew: boolean
  notice_by: string | null
  remind_days: number
  reminder: number | null
  reminder_due: string | null
  thanked_at: string | null
  notes: string
  updated_at: string
}
export type AgreementInput = Partial<
  Omit<
    PartnerAgreement,
    'id' | 'reminder' | 'reminder_due' | 'notice_by' | 'thanked_at' | 'updated_at'
  >
>

export interface PartnerLogo {
  id: number
  name: string
  url: string
}

export interface PartnerDocument {
  id: number
  title: string
  name: string
  size: number
  content_type: string
  agreement: number | null
  uploaded_at: string
  uploaded_by: string
  url: string
}

export interface MailingRow {
  id: number
  name: string
  emails: string[]
  has_address: boolean
}

export interface Turnover {
  years: { year: number; income: string; expense: string; count: number }[]
  recent: { id: number; number: string; date: string; kind: string; amount: string; text: string }[]
}

export interface Suggestion {
  name: string
  count: number
}

export interface ImportResult {
  created: number
  updated: number
  skipped: number
  contacts_created: number
  contacts_updated: number
  errors: string[]
}

const base = (org: number) => `/api/orgs/${org}/billing/partners/`
const fieldBase = (org: number) => `/api/orgs/${org}/billing/partner-fields/`

/** Zusatzfelder für Geschäftspartner (gleiche Form wie bei den Mitgliedern). */
export const partnerFieldApi = {
  list: (org: number) => api.get<FieldDefinition[]>(fieldBase(org)),
  create: (org: number, data: Partial<FieldDefinition>) =>
    api.post<FieldDefinition>(fieldBase(org), data),
  update: (org: number, id: number, data: Partial<FieldDefinition>, withValues = false) =>
    api.patch<FieldDefinition>(`${fieldBase(org)}${id}/${withValues ? '?mit_werten=1' : ''}`, data),
  remove: (org: number, id: number, withValues = false) =>
    api.del(`${fieldBase(org)}${id}/${withValues ? '?mit_werten=1' : ''}`),
  usage: (org: number, id: number) => api.get<FieldUsage>(`${fieldBase(org)}${id}/usage/`),
  archive: (org: number, id: number) =>
    api.post<FieldDefinition>(`${fieldBase(org)}${id}/archive/`),
  restore: (org: number, id: number) =>
    api.post<FieldDefinition>(`${fieldBase(org)}${id}/restore/`),
  values: (org: number, partner: number) =>
    api.get<MemberField[]>(`${base(org)}${partner}/fields/`),
  saveValues: (org: number, partner: number, values: Record<string, FieldValue>) =>
    api.put<MemberField[]>(`${base(org)}${partner}/fields/`, { values }),
}

export const partnerApi = {
  list: (org: number) => api.get<BusinessPartner[]>(base(org)),
  get: (org: number, id: number) => api.get<BusinessPartner>(`${base(org)}${id}/`),
  save: (org: number, value: PartnerInput, id?: number) =>
    id
      ? api.patch<BusinessPartner>(`${base(org)}${id}/`, value)
      : api.post<BusinessPartner>(base(org), value),
  remove: (org: number, id: number) => api.del(`${base(org)}${id}/`),
  setMenu: (org: number, on: boolean) =>
    api.post<{ partners_in_menu: boolean }>(`${base(org)}menu/`, { partners_in_menu: on }),
  merge: (org: number, keep: number, other: number) =>
    api.post<BusinessPartner & { moved: number }>(`${base(org)}${keep}/merge/`, { other }),
  saveContact: (org: number, partner: number, value: ContactInput, id?: number) =>
    id
      ? api.patch<PartnerContact>(`${base(org)}${partner}/contacts/${id}/`, value)
      : api.post<PartnerContact>(`${base(org)}${partner}/contacts/`, value),
  removeContact: (org: number, partner: number, id: number) =>
    api.del(`${base(org)}${partner}/contacts/${id}/`),
  agreements: (org: number, partner: number) =>
    api.get<PartnerAgreement[]>(`${base(org)}${partner}/agreements/`),
  saveAgreement: (org: number, partner: number, value: AgreementInput, id?: number) =>
    id
      ? api.patch<PartnerAgreement>(`${base(org)}${partner}/agreements/${id}/`, value)
      : api.post<PartnerAgreement>(`${base(org)}${partner}/agreements/`, value),
  removeAgreement: (org: number, partner: number, id: number) =>
    api.del(`${base(org)}${partner}/agreements/${id}/`),
  thanks: (org: number, partner: number, id: number, text: string) =>
    requestBlob('POST', `${base(org)}${partner}/agreements/${id}/thanks/`, { text }),
  websiteLogos: (org: number) => api.get<PartnerLogo[]>(`/api/orgs/${org}/billing/partner-logos/`),
  documents: (org: number, partner: number) =>
    api.get<PartnerDocument[]>(`${base(org)}${partner}/documents/`),
  uploadDocument: (org: number, partner: number, file: File, title: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('title', title)
    return api.post<PartnerDocument>(`${base(org)}${partner}/documents/`, form)
  },
  removeDocument: (org: number, partner: number, id: number) =>
    api.del(`${base(org)}${partner}/documents/${id}/`),
  downloadDocument: (url: string) => requestBlob('GET', url),
  mailing: (org: number, role: string, kind: string) =>
    api.get<MailingRow[]>(`${base(org)}mailing/?${new URLSearchParams({ role, kind }).toString()}`),
  letters: (org: number, value: { role: string; kind: string; subject: string; text: string }) =>
    requestBlob('POST', `${base(org)}mailing/`, value),
  turnover: (org: number, id: number) => api.get<Turnover>(`${base(org)}${id}/turnover/`),
  suggestions: (org: number) => api.get<Suggestion[]>(`${base(org)}suggestions/`),
  adopt: (org: number, name: string, roles: PartnerRole[] = []) =>
    api.post<BusinessPartner & { linked: number }>(`${base(org)}suggestions/`, { name, roles }),
  exportFile: (org: number) => requestBlob('GET', `${base(org)}export/`),
  importFile: (org: number, file: File, probe: boolean) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<ImportResult>(`${base(org)}import/${probe ? '?probe=1' : ''}`, form)
  },
}
