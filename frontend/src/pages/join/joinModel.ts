// Beitrittsformular: Werte, Schritte und kleine Regeln, die Seite und Schritte teilen.
import type { Dispatch, SetStateAction } from 'react'
import type { SignatureInput } from '../../api/finance.ts'
import type { FamilyMember, FieldState, Guardian, JoinSchema } from '../../api/admission.ts'
import { t } from '../../i18n/index.ts'

export type Step = 0 | 1 | 2

export interface Values {
  kind: 'person' | 'organization'
  member_type: string
  last_name: string
  first_name: string
  birth_date: string
  adult: '' | 'yes' | 'no'
  gender: string
  email: string
  phone: string
  street: string
  address_extra: string
  postal_code: string
  city: string
  country: string
  unit: string
  entry_wish: string
  note: string
  custom: Record<string, string>
  pay: boolean
  holder: string
  iban: string
  bic: string
  confirmations: string[]
  consents: string[]
  guardians: Guardian[]
  family: FamilyMember[]
  homepage: string
  discount: string
}

export const empty: Values = {
  kind: 'person',
  member_type: '',
  last_name: '',
  first_name: '',
  birth_date: '',
  adult: '',
  gender: '',
  email: '',
  phone: '',
  street: '',
  address_extra: '',
  postal_code: '',
  city: '',
  country: '',
  unit: '',
  entry_wish: '',
  note: '',
  custom: {},
  pay: false,
  holder: '',
  iban: '',
  bic: '',
  confirmations: [],
  consents: [],
  guardians: [{ last_name: '', first_name: '', email: '', phone: '' }],
  family: [],
  homepage: '',
  discount: '',
}

export const FAMILY_LIMIT = 8
export const newRelative = (): FamilyMember => ({
  first_name: '',
  last_name: '',
  birth_date: '',
  member_type: '',
})

/** In welchem Schritt steht das Feld? (für Fehler vom Server) */
export function stepOf(key: string): Step {
  if (key === 'mandate') return 1
  if (key === 'confirmations' || key === 'consents' || key === 'signature') return 2
  return 0
}

/** Fehlerschlüssel einer Bestätigung (Ankreuzfeld) */
export function confirmKey(key: string): string {
  return 'confirm_' + key
}

export function ageOn(birth: string, today = new Date()): number | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(birth)
  if (!m) return null
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])]
  let age = today.getFullYear() - y
  if (today.getMonth() + 1 < mo || (today.getMonth() + 1 === mo && today.getDate() < d)) age--
  return age
}

/** Ohne Geburtsdatum (Feld aus, oder freiwillig und leer) fragt das Formular nach der Volljährigkeit */
export const askAdult = (state: FieldState, person: boolean, birthDate: string) =>
  person && (state === 'off' || (state === 'optional' && !birthDate))

export const label = (base: string, state: FieldState) =>
  state === 'optional' ? t('{x} (freiwillig)', { x: base }) : base

/** Was die drei Schritte des Formulars von der Seite bekommen */
export interface JoinModel {
  s: JoinSchema
  f: JoinSchema['fields']
  kiosk: boolean
  values: Values
  setValues: Dispatch<SetStateAction<Values>>
  set: <K extends keyof Values>(k: K, v: Values[K]) => void
  toggle: (k: 'confirmations' | 'consents', item: string, on: boolean) => void
  setRelative: (i: number, k: keyof FamilyMember, v: string) => void
  setGuardian: (i: number, k: keyof Guardian, v: string) => void
  err: (k: string) => string | undefined
  type: JoinSchema['types'][number] | null
  discounts: NonNullable<JoinSchema['discounts']>
  person: boolean
  minor: boolean
  familyOn: boolean
  confirmations: (JoinSchema['confirmations'][number] | { key: string; label: string })[]
  padKey: number
  setSignature: (signature: SignatureInput | null) => void
}
