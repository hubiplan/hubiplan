// Hilfe: Hilfsfunktionen zu HelpExtras.tsx (erste Schritte, ausgegraute Anleitungen,
// „Zeig es mir“).
import { t } from '../i18n/index.ts'
import type { HelpEntry } from './content.ts'
import { useHelp } from './HelpContext.tsx'

/** Erste Schritte als Pakete je Aufgabenbereich (konzepte/hilfe-neustruktur.md 3.4). Ein Paket
 *  erscheint, sobald die Person eine seiner Anleitungen sehen darf (Modul und Recht). */
export const FIRST_STEP_PACKAGES: readonly { id: string; label: () => string; keys: string[] }[] = [
  {
    id: 'alle',
    label: () => t('Für alle'),
    keys: [
      'guide.password',
      'guide.two_factor',
      'guide.passkey',
      'guide.language',
      'guide.app_pair',
      'guide.home_arrange',
    ],
  },
  {
    id: 'mitglieder',
    label: () => t('Mitglieder verwalten'),
    keys: [
      'guide.member_admit',
      'guide.member_import',
      'guide.member_change_review',
      'guide.member_export',
      'guide.household_add',
      'guide.custom_field',
      'guide.office_fill',
    ],
  },
  {
    id: 'beitraege',
    label: () => t('Beiträge und Rechnungen'),
    keys: [
      'guide.fee_rates',
      'guide.debit_mandate',
      'guide.fee_run',
      'guide.debit_run',
      'guide.dunning',
    ],
  },
  {
    id: 'kasse',
    label: () => t('Kasse und Abschluss'),
    keys: [
      'guide.bank_statement',
      'guide.booking',
      'guide.cash_count',
      'guide.cash_receipt',
      'guide.einvoice_receive',
      'guide.year_closing',
      'guide.cash_audit',
      'guide.budget_plan',
      'guide.event_finance',
    ],
  },
  {
    id: 'termine',
    label: () => t('Termine und Versammlungen'),
    keys: [
      'guide.event_create',
      'guide.meeting_invite',
      'guide.meeting_minutes',
      'guide.helpers_plan',
      'guide.todo_create',
    ],
  },
  {
    id: 'kommunikation',
    label: () => t('Rundschreiben und Dokumente'),
    keys: [
      'guide.circular_send',
      'guide.letter_write',
      'guide.document_upload',
      'guide.folder_share',
    ],
  },
  {
    id: 'webseite',
    label: () => t('Webseite pflegen'),
    keys: [
      'guide.website_text',
      'guide.website_images',
      'guide.website_design',
      'guide.website_home',
      'guide.website_page',
      'guide.website_album',
      'guide.website_publish',
    ],
  },
  {
    id: 'vereinsleben',
    label: () => t('Wettbewerbe, Musik und Umfragen'),
    keys: [
      'guide.competition_create',
      'guide.certificates',
      'guide.entry_submit',
      'guide.musician_add',
      'guide.rehearsal_plan',
      'guide.survey_meal',
    ],
  },
  {
    id: 'einstellungen',
    label: () => t('Vereinseinstellungen'),
    keys: [
      'guide.club_setup',
      'guide.role_create',
      'guide.role_preview',
      'guide.unit_create',
      'guide.appearance',
      'guide.letterhead',
      'guide.obligation_add',
    ],
  },
  {
    id: 'anlass',
    label: () => t('Was tun, wenn …'),
    keys: [
      'guide.debit_return',
      'guide.fee_change',
      'guide.board_change',
      'guide.year_change',
      'guide.member_moved',
      'guide.member_deceased',
      'guide.privacy_request',
      'guide.account_create',
      'guide.mail_trouble',
      'guide.backup',
    ],
  },
]

/** Alle ersten Schritte (ohne Doppelte), in Paketreihenfolge */
export const FIRST_STEPS = [...new Set(FIRST_STEP_PACKAGES.flatMap((p) => p.keys))]

/** Fragen auf der Hilfe-Startseite für Mitglieder ohne Verwaltungsrechte (3.3) */
export const MEMBER_TOPICS = [
  'guide.portal_change',
  'guide.portal_card',
  'guide.portal_invoices',
  'guide.portal_helpers',
  'guide.portal_meetings',
  'guide.portal_meeting_live',
  'guide.portal_survey',
  'guide.portal_cancel',
  'guide.app_pair',
  'guide.password',
  'guide.two_factor',
  'guide.passkey',
  'guide.language',
]

/** Einträge, die die Person sehen könnte, wenn sie das Recht hätte (nur bei passender Suche). */
export function useBlocked(filter: (e: HelpEntry) => boolean): HelpEntry[] {
  const help = useHelp()
  if (!help?.entries) return []
  return help.entries.filter((e) => e.kind === 'guide' && help.missing(e).length > 0 && filter(e))
}

/** Beschriftungen, die eine Anleitung fett nennt (Knöpfe, Reiter, Felder). */
export function labelsIn(body: string): string[] {
  return [...new Set([...body.matchAll(/\*\*([^*]+)\*\*/g)].map((m) => m[1].trim()))]
}

const TARGETS = 'button, a, [role="tab"], label, legend, summary, h1, h2, h3, th'

/** „Zeig es mir“: erstes Bedienelement mit einer der Beschriftungen auf der Seite hervorheben. */
export function highlight(labels: string[], root: ParentNode = document): boolean {
  const main = root.querySelector('#inhalt') ?? root
  const norm = (s: string | null) => (s ?? '').replace(/\s+/g, ' ').trim().toLocaleLowerCase()
  const wanted = labels.map(norm)
  for (const want of wanted) {
    for (const el of main.querySelectorAll<HTMLElement>(TARGETS)) {
      if (norm(el.textContent) !== want && norm(el.getAttribute('aria-label')) !== want) continue
      if (el.closest('.help-panel')) continue
      el.scrollIntoView?.({ block: 'center', behavior: 'smooth' })
      el.classList.add('help-highlight')
      window.setTimeout(() => el.classList.remove('help-highlight'), 4000)
      return true
    }
  }
  return false
}
