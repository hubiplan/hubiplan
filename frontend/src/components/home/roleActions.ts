// Schnellaktionen je Rolle (Konzept S-04). Mehrere Rollen teilen sich höchstens vier Aktionen,
// Kasse vor Vorstand vor Schriftführung. Die Aktionen der Kasse sieht nur, wer ein Kassenamt hat
// (home_focus vom Server), nicht schon jeder mit Kassenrechten wie der Vorsitz.
import { PERM } from '../../api/orgs.ts'
import type { OrgSummary } from '../../api/orgs.ts'
import { DEPT_PERM } from '../../api/portal.ts'
import type { DeptSummary } from '../../api/portal.ts'
import { canWriteCirculars } from '../../pages/circulars/access.ts'
import { t } from '../../i18n/index.ts'

export interface QuickAction {
  key: string
  to: string
  label: string
}

/** Höchstens so viele Schnellaktionen (S-04) */
export const MAX_ACTIONS = 4

/** Schnellaktionen der Rollen in der Einheit (höchstens vier), ohne die ausgeblendeten. */
export function roleActions(org: OrgSummary, hidden: string[] = []): QuickAction[] {
  return visibleActions(roleActionCandidates(org), hidden)
}

/** Erste vier nicht ausgeblendete Aktionen; „*“ blendet alle aus. */
export function visibleActions(candidates: QuickAction[], hidden: string[]): QuickAction[] {
  if (hidden.includes('*')) return []
  return candidates.filter((a) => !hidden.includes(a.key)).slice(0, MAX_ACTIONS)
}

/** Alle möglichen Schnellaktionen nach Vorrang: Kasse, Vorstand, Schriftführung. */
export function roleActionCandidates(org: OrgSummary): QuickAction[] {
  if (org.type !== 'club' && org.type !== 'federation') return []
  const can = (perm: string) => org.permissions.includes(perm)
  const on = (module: string) => org.modules.includes(module)
  const treasurer = org.home_focus ? org.home_focus.includes('finance') : true
  const finance = treasurer && on('finance') && can(PERM.financeEdit)
  const billing = treasurer && on('billing') && can(PERM.billingEdit)
  const actions: (QuickAction | false)[] = [
    // Kasse
    finance && {
      key: 'buchung',
      to: '/finanzen/kassenbuch?buchung=neu-ausgabe',
      label: t('Buchung erfassen'),
    },
    finance && {
      key: 'kontoauszug',
      to: '/finanzen/kontoauszuege',
      label: t('Kontoauszug einlesen'),
    },
    finance && { key: 'quittung', to: '/finanzen/quittungen/neu', label: t('Quittung ausstellen') },
    billing &&
      !finance && {
        key: 'rechnung',
        to: '/finanzen/rechnungen?rechnung=neu',
        label: t('Rechnung schreiben'),
      },
    billing && {
      key: 'mahnlauf',
      to: '/finanzen/rechnungen/mahnungen',
      label: t('Mahnlauf vorbereiten'),
    },
    // Vorstand
    on('events') &&
      can(PERM.eventsManage) && { key: 'termin', to: '/termine?neu=1', label: t('Neuer Termin') },
    org.type === 'club' &&
      on('members') &&
      can(PERM.membersEdit) && {
        key: 'aufnahme',
        to: '/mitglieder/neu',
        label: t('Mitglied aufnehmen'),
      },
    canWriteCirculars(org) && {
      key: 'rundschreiben',
      to: '/rundschreiben',
      label: t('Rundschreiben schreiben'),
    },
    // Schriftführung
    on('meetings') &&
      can(PERM.meetingsEdit) && {
        key: 'versammlung',
        to: '/versammlungen?neu=1',
        label: t('Versammlung anlegen'),
      },
    on('meetings') &&
      can(PERM.meetingsEdit) && {
        key: 'protokoll',
        to: '/versammlungen',
        label: t('Protokoll schreiben'),
      },
  ]
  return actions.filter((a): a is QuickAction => !!a)
}

/** Schnellaktionen im Arbeitsbereich einer Untereinheit (Zugführung). */
export function deptActions(dept: DeptSummary): QuickAction[] {
  return [
    ...(dept.events_enabled && dept.permissions.includes(DEPT_PERM.eventsManage)
      ? [{ key: 'einheit-termin', to: '/termine?neu=1', label: t('Termin der Einheit') }]
      : []),
    { key: 'einheit-mitglieder', to: '/abteilung', label: t('Mitglieder ansehen') },
    { key: 'einheit-brief', to: '/briefvorlage', label: t('Briefvorlage') },
  ]
}
