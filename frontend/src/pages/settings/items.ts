// Unterpunkte von „Einstellungen“ je Einheit und Rolle. Eine Quelle für die Seitenleiste
// (modules.tsx) und den Rahmen der Seiten (SettingsLayout): Punkte ohne Leserecht erscheinen
// nicht, und ohne einen Punkt verschwindet „Einstellungen“ ganz (UX-Audit 08.11., W-01).
import { PERM } from '../../api/orgs.ts'
import type { OrgSummary } from '../../api/orgs.ts'
import { federationAccess } from '../members/access.ts'
import { t } from '../../i18n/index.ts'
import { setupGroups } from './setup.ts'

/** Wer Orte speichern darf (wie places/access.py, EDITORS) */
const PLACE_EDITORS = [
  PERM.eventsManage,
  PERM.eventsEdit,
  PERM.competitionsManage,
  PERM.competitionsEdit,
  PERM.helpersEdit,
  PERM.meetingsEdit,
  PERM.settingsEdit,
  PERM.orgEdit,
]

export interface SettingsItem {
  to: string
  label: string
  section: string
  /** Einrichtungspunkt: erscheint auch in der Übersicht Einstellungen › Einrichtung (S-02) */
  setup?: boolean
}

/**
 * Einstellungen mit der Übersicht „Einrichtung“ als erstem Punkt (S-02). Sie gehört zu den
 * Einstellungen des ganzen Vereins und erscheint deshalb nur mit „Einstellungen ansehen“;
 * wer nur einen Bereich einrichtet (z. B. die Kasse), findet seine Seiten dort (W-01).
 */
export function settingsItems(active: OrgSummary): SettingsItem[] {
  const items = baseSettingsItems(active)
  return active.permissions.includes(PERM.settingsView) && setupGroups(active, items).length > 0
    ? [
        {
          to: '/einstellungen/einrichtung',
          label: t('Einrichtung (Übersicht)'),
          section: t('Allgemein'),
        },
        ...items,
      ]
    : items
}

/** Einstellungen ohne die Übersicht (Quelle der Einrichtungspunkte unter „Verein“). */
export function baseSettingsItems(active: OrgSummary): SettingsItem[] {
  const can = (perm: string) => active.permissions.includes(perm)
  // Arbeitsbereich einer Untereinheit: Stammdaten pflegt die Einheit darüber
  const unit = active.type === 'unit'
  const platform = active.type === 'platform'
  const clubLike = active.type === 'federation' || active.type === 'club'
  // Stammdaten, Bezeichnungen, Vereinsdokumente, Briefbogen, Impressum und Datenschutz
  // liest der Server nur mit „Einstellungen ansehen“, das Erscheinungsbild mit „Farben ansehen“
  const settings = can(PERM.settingsView)
  const theme = can(PERM.themeView)
  // Zwischenüberschriften in der Seitenleiste (Menüprüfung M-11)
  const general = t('Allgemein')
  const legal = t('Recht')
  const access = t('Rollen und Anbindungen')
  const records = t('Daten')
  return [
    ...(!unit && settings
      ? [
          {
            to: '/einstellungen/organisation',
            label: t('Organisation'),
            section: general,
            setup: true,
          },
        ]
      : []),
    ...(unit || platform || !settings
      ? []
      : [
          {
            to: '/einstellungen/bezeichnungen',
            label: t('Bezeichnungen'),
            section: general,
            setup: true,
          },
          // Vereinsdokumente stehen unter Dokumente; hier nur ohne Zugriff auf die Ablage
          ...(can(PERM.docsView)
            ? []
            : [
                {
                  to: '/einstellungen/vereinsdokumente',
                  label: t('Vereinsdokumente'),
                  section: general,
                  setup: true,
                },
              ]),
        ]),
    // Module ein- und ausschalten (innerhalb der Freigabe der Plattform)
    ...(clubLike && settings
      ? [{ to: '/einstellungen/module', label: t('Module'), section: general, setup: true }]
      : []),
    ...(!unit && theme
      ? [
          {
            to: '/einstellungen/erscheinungsbild',
            label: t('Erscheinungsbild'),
            section: general,
            setup: true,
          },
        ]
      : []),
    ...(unit || platform || !settings
      ? []
      : [
          {
            to: '/einstellungen/briefbogen',
            label: t('Briefbogen'),
            section: general,
            setup: true,
          },
        ]),
    // Gespeicherte Orte für Termine, Wettbewerbe, Helferdienste und Versammlungen
    ...(clubLike && (settings || PLACE_EDITORS.some(can))
      ? [{ to: '/einstellungen/orte', label: t('Orte'), section: general, setup: true }]
      : []),
    // Dachverband ohne Mitgliederzugriff: kein Menüpunkt Mitglieder, die
    // Einrichtung (Zusatzfelder, Jubiläen) bleibt aber erreichbar.
    ...(active.type === 'federation' && !federationAccess(active) && can(PERM.membersView)
      ? [{ to: '/mitglieder/einrichtung', label: t('Mitglieder-Einrichtung'), section: general }]
      : []),
    ...(unit || platform || !settings
      ? []
      : [
          { to: '/einstellungen/impressum', label: t('Impressum'), section: legal, setup: true },
          {
            to: '/einstellungen/datenschutz',
            label: t('Datenschutz'),
            section: legal,
            setup: true,
          },
        ]),
    // Untereinheit mit eigener Webseite: nur deren Datenschutzhinweise
    ...(unit && active.modules.includes('website') && can(PERM.websiteManage)
      ? [{ to: '/einstellungen/datenschutz', label: t('Datenschutz'), section: legal, setup: true }]
      : []),
    // Untereinheiten stehen als eigener Punkt im Hauptmenü (modules.tsx)
    ...(can(PERM.rolesView) || can(PERM.rolesManage)
      ? [{ to: '/einstellungen/rollen', label: t('Rollen und Rechte'), section: access }]
      : []),
    // Konten (Rollen-Vorschlag R4): alle Anmeldungen der Einheit
    ...(!platform && !unit && (can(PERM.rolesView) || can(PERM.loginsView))
      ? [{ to: '/einstellungen/konten', label: t('Konten'), section: access }]
      : []),
    ...(clubLike && can(PERM.peeringManage)
      ? [{ to: '/einstellungen/verbund', label: t('Verbund'), section: access }]
      : []),
    ...(clubLike && can(PERM.rolesManage)
      ? [{ to: '/einstellungen/nextcloud', label: t('Nextcloud'), section: access }]
      : []),
    ...(!platform && (can(PERM.dataExport) || (active.type === 'club' && can(PERM.orgEdit)))
      ? [{ to: '/einstellungen/datenuebernahme', label: t('Datenübernahme'), section: records }]
      : []),
    ...(can(PERM.auditView)
      ? [
          { to: '/einstellungen/protokoll', label: t('Protokoll'), section: records },
          { to: '/einstellungen/postausgang', label: t('Postausgang'), section: records },
        ]
      : []),
  ]
}
