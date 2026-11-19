// Zusatzleistungen, Zusatzfragen, Gesundheitsangaben und Erziehungsberechtigte: Hilfsfunktionen
// (konzepte/veranstaltungen-anmeldung-gebuehr.md, Stufe A5, F11, F13).
import type {
  AddOn,
  AddOnInput,
  Answer,
  Booking,
  Guardian,
  Offer,
  Per,
  Question,
  QuestionInput,
} from '../../api/registrations.ts'
import { euro, parseAmount } from '../../api/finance.ts'
import { lang, t } from '../../i18n/index.ts'

/** Was eine Person (oder die Anmeldung) wählt und antwortet */
export interface ExtrasState {
  addons: Record<string, number | null>
  answers: Record<string, Answer>
  health: string
  guardians: Guardian[]
}

export function emptyExtras(): ExtrasState {
  return { addons: {}, answers: {}, health: '', guardians: [] }
}

export const name = (x: { name: string; name_en: string }) =>
  lang() === 'en' && x.name_en ? x.name_en : x.name
export const question = (q: Question) => (lang() === 'en' && q.text_en ? q.text_en : q.text)

export function activeAddons(offer: Offer, per: Per): AddOn[] {
  return (offer.addons ?? []).filter((a) => a.is_active && a.per === per)
}

export function activeQuestions(offer: Offer, per: Per): Question[] {
  return (offer.questions ?? []).filter(
    (q) => q.is_active && q.per === per && (q.kind !== 'health' || offer.health_allowed),
  )
}

/** Hat die Anmeldung eine Frage nach Allergien? */
export function asksHealth(offer: Offer): boolean {
  return activeQuestions(offer, 'person').some((q) => q.kind === 'health')
}

/** Aufpreis der gewählten Zusatzleistungen */
export function extrasSum(offer: Offer, state: ExtrasState): number {
  let sum = 0
  for (const addon of offer.addons ?? []) {
    const choice = addon.choices.find((c) => c.id === state.addons[String(addon.id)])
    if (choice) sum += Number(choice.amount)
  }
  return sum
}

/** Fehlt eine Pflichtangabe? (Der Server prüft genauso.) */
export function extrasReady(offer: Offer, state: ExtrasState, per: Per, minor = false): boolean {
  const addons = activeAddons(offer, per).every(
    (a) => !a.required || state.addons[String(a.id)] != null,
  )
  const answers = activeQuestions(offer, per).every((q) => {
    if (!q.required || q.kind === 'health') return true
    const v = state.answers[String(q.id)]
    return v !== undefined && v !== ''
  })
  const g = state.guardians[0]
  const guardian = !minor || !!(g && g.name.trim() && g.phone.trim() && g.email.trim())
  return addons && answers && guardian
}

/** Für die Schnittstelle: leere Antworten weglassen */
export function extrasPayload(offer: Offer, state: ExtrasState, minor = false) {
  const answers: Record<string, Answer> = {}
  for (const [k, v] of Object.entries(state.answers)) if (v !== '') answers[k] = v
  return {
    addons: state.addons,
    answers,
    ...(asksHealth(offer) && state.health.trim() ? { health: state.health.trim() } : {}),
    ...(minor ? { guardians: state.guardians.filter((g) => g.name.trim() || g.phone.trim()) } : {}),
  }
}

/** Alter am Veranstaltungstag aus dem Geburtsdatum */
export function isMinor(birth: string, startsAt: string): boolean {
  if (!birth) return false
  const b = new Date(`${birth}T12:00:00`)
  const s = new Date(startsAt)
  let age = s.getFullYear() - b.getFullYear()
  const before =
    s.getMonth() < b.getMonth() || (s.getMonth() === b.getMonth() && s.getDate() < b.getDate())
  if (before) age -= 1
  return age < 18
}

/** Auswahl der Zusatzleistungen und Antworten auf die Zusatzfragen, je Person oder Anmeldung */
/** Einwilligung für die Gesundheitsangaben (Art. 9 DSGVO) */
/** Gebuchte Zusatzleistungen als Text */
export function bookingText(bookings: Booking[] | undefined): string {
  return (bookings ?? [])
    .map((b) => (Number(b.amount) > 0 ? `${b.name} (${euro(b.amount)})` : b.name))
    .join(', ')
}

/** Antworten als Text, in der Reihenfolge der Fragen */
export function answerText(offer: Offer, answers: Record<string, Answer> | undefined): string {
  const rows: string[] = []
  for (const q of offer.questions ?? []) {
    const v = answers?.[String(q.id)]
    if (v === undefined || v === '') continue
    rows.push(`${question(q)}: ${v === true ? t('ja') : v === false ? t('nein') : v}`)
  }
  return rows.join(' · ')
}

export function addonInputs(offer: Offer | null): AddOnInput[] {
  return (offer?.addons ?? []).map((a) => ({
    id: a.id,
    name: a.name,
    name_en: a.name_en,
    kind: a.kind,
    per: a.per,
    required: a.required,
    is_active: a.is_active,
    choices: a.choices.map((c) => ({
      id: c.id,
      name: c.name,
      name_en: c.name_en,
      amount: c.amount,
      vat_rate: c.vat_rate,
      capacity: c.capacity,
      is_active: c.is_active,
    })),
  }))
}

export function questionInputs(offer: Offer | null): QuestionInput[] {
  return (offer?.questions ?? [])
    .filter((q) => q.is_active)
    .map((q) => ({
      id: q.id,
      text: q.text,
      text_en: q.text_en,
      kind: q.kind,
      choices: q.choices,
      required: q.required,
      per: q.per,
      is_active: q.is_active,
    }))
}

/** Beträge für die Schnittstelle („12,50“ → „12.50“) */
export function cleanAddons(addons: AddOnInput[]): AddOnInput[] {
  return addons.map((a) => ({
    ...a,
    name: a.name.trim(),
    choices: a.choices.map((c) => ({
      ...c,
      name: c.name.trim() || a.name.trim(),
      amount: parseAmount(c.amount) || '0',
    })),
  }))
}
