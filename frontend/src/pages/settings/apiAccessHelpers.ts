// Gemeinsame Helfer, Typen und Konstanten von ApiAccessPage.
import type { LegalBasis, MemberFieldGroup } from '../../api/apiAccess.ts'
import { t } from '../../i18n/index.ts'

export interface Draft {
  name: string
  purpose: string
  recipient: string
  scopes: string[]
  unit: string
  expires: string
  networks: string
  embeddable: boolean
  partner: string
  basis: LegalBasis
  confirmed: boolean
  thirdCountry: boolean
  memberFields: MemberFieldGroup[]
  onlyActive: boolean
  adultsOnly: boolean
  reportLevel: 'a' | 'b'
  hookUrl: string
  hookEvents: string[]
}

export function basisLabel(basis: LegalBasis): string {
  if (basis === 'processing') return t('Auftragsverarbeitung (Vertrag nach Art. 28 DSGVO)')
  if (basis === 'transfer') return t('Übermittlung an einen eigenen Verantwortlichen')
  return ''
}

export function day(date: Date): string {
  const two = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${two(date.getMonth() + 1)}-${two(date.getDate())}`
}

export function inDays(days: number): string {
  const date = new Date()
  date.setDate(date.getDate() + days)
  return day(date)
}
