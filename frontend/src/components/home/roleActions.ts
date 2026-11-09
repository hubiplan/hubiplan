// Schnellaktionen je Rolle (Konzept S-04). Die Rolle ergibt sich aus den Rechten; mehrere
// Rollen teilen sich höchstens vier Aktionen, Kasse vor Vorstand vor Schriftführung.
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
/** Höchstens so viele Kennzahlen (S-04) */
export const MAX_FIGURES = 3

/** Schnellaktionen der Rollen in der Einheit, nach Vorrang: Kasse, Vorstand, Schriftführung. */
export function roleActions(org: OrgSummary): QuickAction[] {
  if (org.type !== 'club' && org.type !== 'federation') return []
  const can = (perm: string) => org.permissions.includes(perm)
  const on = (module: string) => org.modules.includes(module)
  const finance = on('finance') && can(PERM.financeEdit)
  const billing = on('billing') && can(PERM.billingEdit)
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
  return actions.filter((a): a is QuickAction => !!a).slice(0, MAX_ACTIONS)
}

/** Schnellaktionen im Arbeitsbereich einer Untereinheit (Zugführung). */
export function deptActions(dept: DeptSummary): QuickAction[] {
  return [
    ...(dept.events_enabled && dept.permissions.includes(DEPT_PERM.eventsManage)
      ? [{ key: 'termin', to: '/termine?neu=1', label: t('Termin der Einheit') }]
      : []),
    { key: 'mitglieder', to: '/abteilung', label: t('Mitglieder ansehen') },
    { key: 'brief', to: '/briefvorlage', label: t('Briefvorlage') },
  ]
}
