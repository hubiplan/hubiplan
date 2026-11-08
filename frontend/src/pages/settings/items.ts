// Unterpunkte von „Einstellungen“ je Einheit und Rolle. Eine Quelle für die Seitenleiste
// (modules.tsx) und den Rahmen der Seiten (SettingsLayout): Punkte ohne Leserecht erscheinen
// nicht, und ohne einen Punkt verschwindet „Einstellungen“ ganz (UX-Audit 08.11., W-01).
import { PERM } from '../../api/orgs.ts'
import type { OrgSummary } from '../../api/orgs.ts'
import { federationAccess } from '../members/access.ts'
import { t } from '../../i18n/index.ts'

export interface SettingsItem {
  to: string
  label: string
  section: string
}

export function settingsItems(active: OrgSummary): SettingsItem[] {
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
      ? [{ to: '/einstellungen/organisation', label: t('Organisation'), section: general }]
      : []),
    ...(unit || platform || !settings
      ? []
      : [
          { to: '/einstellungen/bezeichnungen', label: t('Bezeichnungen'), section: general },
          // Vereinsdokumente stehen unter Dokumente; hier nur ohne Zugriff auf die Ablage
          ...(can(PERM.docsView)
            ? []
            : [
                {
                  to: '/einstellungen/vereinsdokumente',
                  label: t('Vereinsdokumente'),
                  section: general,
                },
              ]),
        ]),
    // Module ein- und ausschalten (innerhalb der Freigabe der Plattform)
    ...(clubLike && settings
      ? [{ to: '/einstellungen/module', label: t('Module'), section: general }]
      : []),
    ...(!unit && theme
      ? [{ to: '/einstellungen/erscheinungsbild', label: t('Erscheinungsbild'), section: general }]
      : []),
    ...(unit || platform || !settings
      ? []
      : [{ to: '/einstellungen/briefbogen', label: t('Briefbogen'), section: general }]),
    // Dachverband ohne Mitgliederzugriff: kein Menüpunkt Mitglieder, die
    // Einrichtung (Zusatzfelder, Jubiläen) bleibt aber erreichbar.
    ...(active.type === 'federation' && !federationAccess(active) && can(PERM.membersView)
      ? [{ to: '/mitglieder/einrichtung', label: t('Mitglieder-Einrichtung'), section: general }]
      : []),
    ...(unit || platform || !settings
      ? []
      : [
          { to: '/einstellungen/impressum', label: t('Impressum'), section: legal },
          { to: '/einstellungen/datenschutz', label: t('Datenschutz'), section: legal },
        ]),
    // Untereinheit mit eigener Webseite: nur deren Datenschutzhinweise
    ...(unit && active.modules.includes('website') && can(PERM.websiteManage)
      ? [{ to: '/einstellungen/datenschutz', label: t('Datenschutz'), section: legal }]
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
