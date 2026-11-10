// Schnellaktionen (Konzept S-04). Ohne eigene Auswahl gilt ein Vorschlag je Rolle: Kasse vor
// Vorstand vor Schriftführung, die Aktionen der Kasse nur mit Kassenamt (home_focus vom Server).
// Unter „Anpassen“ wählt jede Person aus dem Katalog alles, was ihre Rechte erlauben, und legt
// die Reihenfolge fest. Gespeichert wird je Arbeitsbereich (scope) nur die Liste der Schlüssel.
import { PERM } from '../../api/orgs.ts'
import type { OrgSummary } from '../../api/orgs.ts'
import { DEPT_PERM } from '../../api/portal.ts'
import type { DeptSummary } from '../../api/portal.ts'
import { canWriteCirculars } from '../../pages/circulars/access.ts'
import { financeAccess } from '../../pages/finanzen/access.ts'
import { scoresOwnEntry } from '../../pages/music/access.ts'
import { t } from '../../i18n/index.ts'

export interface QuickAction {
  key: string
  to: string
  label: string
}

/** Eintrag im Katalog: Aktion mit dem Bereich, unter dem sie zur Auswahl steht */
export interface CatalogAction extends QuickAction {
  group: string
}

/** Höchstens so viele Schnellaktionen (S-04; bei eigener Auswahl bis zu sechs) */
export const MAX_ACTIONS = 6
/** So viele zeigt der Vorschlag aus den Rollen */
export const SUGGESTED_ACTIONS = 4
/** Höchstens so viele Kennzahlen (S-04) */
export const MAX_FIGURES = 3

/** Schnellaktionen der Rollen in der Einheit (höchstens vier), ohne die ausgeblendeten. */
export function roleActions(org: OrgSummary, hidden: string[] = []): QuickAction[] {
  return visibleActions(roleActionCandidates(org), hidden)
}

/** Erste vier nicht ausgeblendete Aktionen des Vorschlags; „*“ blendet alle aus. */
export function visibleActions(candidates: QuickAction[], hidden: string[]): QuickAction[] {
  if (hidden.includes('*')) return []
  return candidates.filter((a) => !hidden.includes(a.key)).slice(0, SUGGESTED_ACTIONS)
}

/**
 * Gezeigte Aktionen: die eigene Auswahl in ihrer Reihenfolge, soweit die Rechte sie noch
 * erlauben, sonst der Vorschlag. „*“ blendet alles aus.
 */
export function shownActions(
  suggested: QuickAction[],
  catalog: QuickAction[],
  hidden: string[],
  chosen: string[] | undefined,
): QuickAction[] {
  if (hidden.includes('*')) return []
  if (!chosen) return visibleActions(suggested, hidden)
  const byKey = new Map(catalog.map((a) => [a.key, a]))
  return chosen
    .map((k) => byKey.get(k))
    .filter((a): a is QuickAction => !!a)
    .slice(0, MAX_ACTIONS)
}

/** Schlüssel des Arbeitsbereichs, unter dem die Auswahl am Konto steht */
export const actionScope = {
  org: (org: OrgSummary) => `o${org.id}`,
  dept: (dept: DeptSummary) => `d${dept.id}`,
}

/**
 * Alle Schnellaktionen, die die Rechte in der Einheit erlauben, nach Bereichen. Anders als im
 * Vorschlag stehen die Aktionen der Kasse auch ohne Kassenamt zur Wahl, wenn die Rechte reichen.
 */
export function actionCatalog(org: OrgSummary): CatalogAction[] {
  if (org.type !== 'club' && org.type !== 'federation') return []
  const can = (perm: string) => org.permissions.includes(perm)
  const on = (module: string) => org.modules.includes(module)
  const money = financeAccess(org)
  const finance = money.financeEdit
  const billing = money.billingEdit
  const kasse = t('Finanzen')
  const plan = t('Termine und Planung')
  const people = t('Mitglieder')
  const club = t('Verein')
  const talk = t('Schreiben und Ablegen')
  const list: (CatalogAction | false)[] = [
    finance && {
      group: kasse,
      key: 'buchung',
      to: '/finanzen/kassenbuch?buchung=neu-ausgabe',
      label: t('Buchung erfassen'),
    },
    finance && {
      group: kasse,
      key: 'einnahme',
      to: '/finanzen/kassenbuch?buchung=neu-einnahme',
      label: t('Einnahme erfassen'),
    },
    finance && {
      group: kasse,
      key: 'kontoauszug',
      to: '/finanzen/kontoauszuege',
      label: t('Kontoauszug einlesen'),
    },
    finance && {
      group: kasse,
      key: 'quittung',
      to: '/finanzen/quittungen/neu',
      label: t('Quittung ausstellen'),
    },
    money.cashCounts &&
      finance && {
        group: kasse,
        key: 'kassenzaehlung',
        to: '/finanzen/kassenzaehlung',
        label: t('Kasse zählen'),
      },
    billing && {
      group: kasse,
      key: 'rechnung',
      to: '/finanzen/rechnungen?rechnung=neu',
      label: t('Rechnung schreiben'),
    },
    billing && {
      group: kasse,
      key: 'mahnlauf',
      to: '/finanzen/rechnungen/mahnungen',
      label: t('Mahnlauf vorbereiten'),
    },
    billing &&
      money.feeRuns && {
        group: kasse,
        key: 'beitragslauf',
        to: '/finanzen/rechnungen/beitragslaeufe',
        label: t('Beitragslauf vorbereiten'),
      },
    on('events') &&
      can(PERM.eventsManage) && {
        group: plan,
        key: 'termin',
        to: '/termine?neu=1',
        label: t('Neuer Termin'),
      },
    on('meetings') &&
      can(PERM.meetingsEdit) && {
        group: plan,
        key: 'versammlung',
        to: '/versammlungen?neu=1',
        label: t('Versammlung anlegen'),
      },
    on('meetings') &&
      can(PERM.meetingsEdit) && {
        group: plan,
        key: 'protokoll',
        to: '/versammlungen',
        label: t('Protokoll schreiben'),
      },
    on('helpers') &&
      can(PERM.helpersEdit) && {
        group: plan,
        key: 'helferdienst',
        to: '/helferdienste?neu=1',
        label: t('Helferdienst anlegen'),
      },
    can(PERM.todosEdit) && {
      group: plan,
      key: 'aufgabe',
      to: '/aufgaben?neu=1',
      label: t('Aufgabe anlegen'),
    },
    on('bookings') &&
      (on('material') || on('infrastructure')) &&
      can(PERM.bookingsEdit) && {
        group: plan,
        key: 'belegung',
        to: '/belegung',
        label: t('Belegung eintragen'),
      },
    org.type === 'club' &&
      on('members') &&
      can(PERM.membersEdit) && {
        group: people,
        key: 'aufnahme',
        to: '/mitglieder/neu',
        label: t('Mitglied aufnehmen'),
      },
    on('chronicle') &&
      can(PERM.chronicleEdit) && {
        group: club,
        key: 'chronik',
        to: '/chronik',
        label: t('Chronik ergänzen'),
      },
    on('competitions') &&
      can(PERM.competitionsManage) && {
        group: club,
        key: 'wettbewerb',
        to: '/wettbewerbe',
        label: t('Wettbewerb anlegen'),
      },
    on('competitions') &&
      can(PERM.competitionsResults) && {
        group: club,
        key: 'ergebnisse',
        to: '/wettbewerbe',
        label: t('Ergebnisse eintragen'),
      },
    on('scores') &&
      can(PERM.scoresView) &&
      can(PERM.scoresEdit) && {
        group: club,
        key: 'noten',
        // Ohne Menüpunkt Musik steht das Notenarchiv eigenständig
        to: scoresOwnEntry(org) ? '/noten' : '/musik/noten',
        label: t('Noten hochladen'),
      },
    canWriteCirculars(org) && {
      group: talk,
      key: 'rundschreiben',
      to: '/rundschreiben',
      label: t('Rundschreiben schreiben'),
    },
    can(PERM.docsManage) && {
      group: talk,
      key: 'dokument',
      to: '/dokumente',
      label: t('Dokument ablegen'),
    },
    on('website') &&
      can(PERM.websiteContent) && {
        group: talk,
        key: 'webseite',
        to: '/webseite/inhalte',
        label: t('Webseite bearbeiten'),
      },
  ]
  const actions = list.filter((a): a is CatalogAction => !!a)
  // Die Briefvorlage steht allen offen; als Schnellaktion nur neben anderen Aufgaben
  if (actions.length === 0) return []
  return [
    ...actions,
    { group: talk, key: 'briefvorlage', to: '/briefvorlage', label: t('Brief schreiben') },
  ]
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

/** Schnellaktionen im Arbeitsbereich einer Untereinheit (Zugführung): Vorschlag. */
export function deptActions(dept: DeptSummary): QuickAction[] {
  return deptCatalog(dept)
    .filter((a) => a.key !== 'einheit-aufgabe')
    .map(({ key, to, label }) => ({ key, to, label }))
}

/** Alle Schnellaktionen im Arbeitsbereich einer Untereinheit. */
export function deptCatalog(dept: DeptSummary): CatalogAction[] {
  const group = t('Untereinheit')
  return [
    ...(dept.events_enabled && dept.permissions.includes(DEPT_PERM.eventsManage)
      ? [{ group, key: 'einheit-termin', to: '/termine?neu=1', label: t('Termin der Einheit') }]
      : []),
    { group, key: 'einheit-mitglieder', to: '/abteilung', label: t('Mitglieder ansehen') },
    { group, key: 'einheit-brief', to: '/briefvorlage', label: t('Briefvorlage') },
    ...(dept.permissions.includes(PERM.todosEdit)
      ? [
          {
            group,
            key: 'einheit-aufgabe',
            to: `/aufgaben?neu=1&abteilung=${dept.id}`,
            label: t('Aufgabe anlegen'),
          },
        ]
      : []),
  ]
}
