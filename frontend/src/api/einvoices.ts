import { api } from './client.ts'
import type { Invoice } from './billing.ts'
import type { Page } from './members.ts'

export interface Party {
  name: string
  street: string
  postcode: string
  city: string
  country: string
  email: string
  vat_id: string
  tax_number: string
  contact: string
  phone: string
  identifier: string
  endpoint_id?: string
  endpoint_scheme?: string
}
export interface Partner {
  id: number
  name: string
  details: Party
  is_customer: boolean
  is_supplier: boolean
  is_active: boolean
}
export interface CommercialLine {
  text: string
  quantity: string
  unit: string
  unit_price: string
  allowance: string
  charge: string
  adjustment_reason: string
  tax_category: string
  tax_rate: string
  tax_reason: string
}
export interface Header {
  seller: Party
  buyer: Party
  buyer_reference: string
  order_reference: string
  service_start: string
  service_end: string
  iban: string
  currency: 'EUR'
}
export interface CommercialInput extends Header {
  document_kind?: 'invoice' | 'advance' | 'final'
  advance_invoices?: number[]
  partner: number
  payment_category: number
  date: string
  due_date: string
  subject: string
  note: string
  project: number | null
  lines: CommercialLine[]
}
export type CommercialInvoice = Omit<Invoice, 'electronic_data' | 'lines'> & {
  advance_invoices?: number[]
  has_hybrid?: boolean
  has_cancellation_hybrid?: boolean
  partner: number
  payment_category: number
  electronic_data: Header
  lines: { electronic_data: CommercialLine }[]
}
export interface ValidationReport {
  status: 'valid' | 'invalid' | 'unavailable' | 'pending'
  validator: string
  messages: { level: string; code?: string; text: string }[]
}
/** Mail aus dem Rechnungspostfach (#374). */
export interface IncomingMail {
  id: number
  sender: string
  subject: string
  /** Absender passt zur E-Mail-Adresse eines Geschäftspartners. */
  sender_known: boolean
  status: 'imported' | 'no_invoice' | 'spam' | 'virus' | 'error'
  skipped: { name: string; reason: string }[]
  received_at: string
  dismissed_at: string | null
}
export interface IncomingMailbox {
  enabled: boolean
  address: string
}
export interface IncomingInvoice {
  id: number
  name: string
  sha256: string
  content_type: string
  has_report: boolean
  data: {
    number?: string
    seller?: string
    buyer?: string
    date?: string
    currency?: string
    payable?: string
    iban?: string
    credit_note?: boolean
    lines?: { text: string; quantity: string; amount: string; unit: string }[]
  }
  report: ValidationReport
  status: 'review' | 'approved' | 'rejected'
  /** Technische Prüfung läuft im Hintergrund ('pending') oder ist fertig. */
  validation?: 'pending' | 'done'
  review_note: string
  booking: number | null
  created_at: string
  /** Aus dem Rechnungspostfach; null beim Hochladen. */
  mail?: IncomingMail | null
  /** Zugeordneter Geschäftspartner (Konzept Geschäftspartner, P3). */
  partner?: number | null
  partner_name?: string
  /** Vorschlag, solange kein Partner zugeordnet ist. */
  suggested_partner?: {
    id: number
    name: string
    by: 'vat_id' | 'iban' | 'sender' | 'domain' | 'name'
  } | null
  /** Die IBAN der Rechnung weicht von der beim Partner gespeicherten ab. */
  iban_changed?: boolean
}
const base = (org: number) => `/api/orgs/${org}`
export interface DeliveryState {
  id: number
  document: 'invoice' | 'cancellation'
  request_id: string
  provider: string
  status: string
  receipt: { reference?: string }
  error_code: string
  updated_at: string
}
export interface DeliveryOverview {
  configuration: { enabled: boolean; label?: string; channel?: string; participant?: string }
  deliveries: DeliveryState[]
}
export const einvoiceApi = {
  advances: (org: number, partner: number, project: number | null) =>
    api.get<CommercialInvoice[]>(
      `${base(org)}/billing/electronic/advances/?partner=${partner}${project ? `&project=${project}` : ''}`,
    ),
  createHybrid: (org: number, id: number, cancel: boolean) =>
    api.post<CommercialInvoice>(
      `${base(org)}/billing/electronic/${id}/hybrid/${cancel ? '?cancellation=1' : ''}`,
      {},
    ),
  hybrid: (org: number, id: number, cancel: boolean) =>
    `${base(org)}/billing/electronic/${id}/hybrid/${cancel ? '?cancellation=1' : ''}`,
  delivery: (org: number, id: number) =>
    api.get<DeliveryOverview>(`${base(org)}/billing/electronic/${id}/delivery/`),
  dispatch: (org: number, id: number, document: string, operation: string) =>
    api.post<DeliveryState>(`${base(org)}/billing/electronic/${id}/delivery/`, {
      document,
      operation,
    }),
  partners: (org: number) => api.get<Partner[]>(`${base(org)}/billing/partners/`),
  savePartner: (org: number, value: Omit<Partner, 'id'>, id?: number) =>
    id
      ? api.patch<Partner>(`${base(org)}/billing/partners/${id}/`, value)
      : api.post<Partner>(`${base(org)}/billing/partners/`, value),
  invoices: (org: number, page: number) =>
    api.get<Page<CommercialInvoice>>(`${base(org)}/billing/electronic/?page=${page}`),
  invoice: (org: number, id: number) =>
    api.get<CommercialInvoice>(`${base(org)}/billing/electronic/${id}/`),
  save: (org: number, value: CommercialInput, key: string, id?: number) =>
    id
      ? api.patch<CommercialInvoice>(`${base(org)}/billing/electronic/${id}/`, value)
      : api.post<CommercialInvoice>(`${base(org)}/billing/electronic/`, value, key),
  validate: (org: number, id: number) =>
    api.post<ValidationReport>(`${base(org)}/billing/electronic/${id}/validate/`, {}),
  xml: (org: number, id: number, cancel = false) =>
    `${base(org)}/billing/electronic/${id}/xml/${cancel ? '?cancellation=1' : ''}`,
  report: (org: number, id: number) => `${base(org)}/billing/electronic/${id}/report/`,
  incoming: (org: number, page = 1) =>
    api.get<Page<IncomingInvoice>>(`${base(org)}/finance/incoming/?page=${page}`),
  upload: (org: number, file: File) => {
    const data = new FormData()
    data.append('file', file)
    return api.post<IncomingInvoice>(`${base(org)}/finance/incoming/`, data)
  },
  review: (org: number, id: number, status: string, note: string, ibanConfirmed = false) =>
    api.post<IncomingInvoice>(`${base(org)}/finance/incoming/${id}/review/`, {
      status,
      note,
      ...(ibanConfirmed ? { iban_confirmed: true } : {}),
    }),
  assignPartner: (org: number, id: number, partner: number | null) =>
    api.post<IncomingInvoice>(`${base(org)}/finance/incoming/${id}/partner/`, { partner }),
  createPartner: (org: number, id: number) =>
    api.post<IncomingInvoice>(`${base(org)}/finance/incoming/${id}/create-partner/`, {}),
  link: (org: number, id: number, booking: number) =>
    api.post<IncomingInvoice>(`${base(org)}/finance/incoming/${id}/link/`, { booking }),
  revalidate: (org: number, id: number) =>
    api.post<IncomingInvoice>(`${base(org)}/finance/incoming/${id}/revalidate/`, {}),
  mailbox: (org: number) => api.get<IncomingMailbox>(`${base(org)}/finance/incoming/mailbox/`),
  renewMailbox: (org: number) =>
    api.post<IncomingMailbox>(`${base(org)}/finance/incoming/mailbox/`, {}),
  mails: (org: number) => api.get<IncomingMail[]>(`${base(org)}/finance/incoming/mails/`),
  dismissMail: (org: number, id: number) =>
    api.post<IncomingMail>(`${base(org)}/finance/incoming/mails/${id}/dismiss/`, {}),
  download: (org: number, id: number, part = 'original') =>
    `${base(org)}/finance/incoming/${id}/download/?part=${part}`,
}
